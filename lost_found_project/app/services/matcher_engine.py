import os
import asyncpg
import asyncio
from functools import partial
from openai import OpenAI

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
# Standard OpenAI client initializer
if OPENROUTER_API_KEY:
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=OPENROUTER_API_KEY,
    )
else:
    client = None

OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free")

async def calculate_llm_match_case(report_id: int, db_pool: asyncpg.Pool) -> dict:
    """
    Compares a lost report's unique_features with registered found items using LLM and overlap algorithms.
    Returns the matching case and candidate items sorted in descending order of match rate.
    
    Cases:
    - Case 1: No matches found (highest match rate < 40%).
    - Case 2: AI Recommended cards grid display (highest match rate between 40% and 89%).
    - Case 3: Auto-approval fixed bar activation (highest match rate is 90% or higher).
    - Case 4: Already matched/resolved.
    """
    async with db_pool.acquire() as conn:
        # 1. Fetch the lost report
        report = await conn.fetchrow("""
            SELECT category, item_name, unique_features, matching_status, matched_lost_item_id
            FROM lost_reports
            WHERE id = $1;
        """, report_id)

        if not report:
            return {
                "case": 1,
                "matched_items": [],
                "extracted_keywords": []
            }

        # 1.5. If the report is already completed (Case 4)
        if report["matching_status"] == '매칭완료' and report["matched_lost_item_id"] is not None:
            matched_item = await conn.fetchrow("""
                SELECT id, management_number, category, sub_category, item_name, 
                       found_date, found_location_building, found_location_detail, 
                       detail_memo, thumbnail_path, vlm_keywords, status,
                       recipient_name, recipient_phone, recipient_student_id, released_at
                FROM lost_items
                WHERE id = $1;
            """, report["matched_lost_item_id"])
            
            if matched_item:
                return {
                    "case": 4,
                    "matched_items": [dict(matched_item)],
                    "extracted_keywords": []
                }

        # 2. Fetch all '보관중' items within the same category, excluding manually excluded items
        items = await conn.fetch("""
            SELECT id, management_number, item_name, vlm_keywords, thumbnail_path, found_location_building, found_location_detail
            FROM lost_items
            WHERE category = $1
              AND status = '보관중'
              AND id NOT IN (SELECT lost_item_id FROM excluded_matches WHERE report_id = $2);
        """, report["category"], report_id)

        if not items:
            return {
                "case": 1,
                "matched_items": [],
                "extracted_keywords": []
            }

        # 3. Extract physical features using OpenRouter or fallback to token split
        extracted_keywords = []
        if client and OPENROUTER_API_KEY:
            system_instruction = (
                "You are an assistant for a lost and found system. "
                "Extract 3 to 5 core physical characteristic keywords (such as color, brand, item type, or material) "
                "from the user's Korean sentence. "
                "Output ONLY the keywords separated by spaces, without any punctuation, bullets, or numbers. "
                "Example input: '검은색 가죽으로 된 지갑인데 나이키 로고가 있어요' "
                "Example output: '검은색 가죽 지갑 나이키'"
            )
            try:
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(
                    None,
                    partial(
                        client.chat.completions.create,
                        model=OPENROUTER_MODEL,
                        messages=[
                            {"role": "system", "content": system_instruction},
                            {"role": "user", "content": report["unique_features"]}
                        ],
                        temperature=0.1,
                        max_tokens=50,
                        timeout=10.0
                    )
                )
                llm_output = response.choices[0].message.content.strip()
                extracted_keywords = [w.strip() for w in llm_output.split() if w.strip()]
            except Exception as e:
                print(f"[Matcher Engine] OpenRouter error: {e}. Falling back to simple parsing.")
                # Fallback: split by space, clean punctuation
                extracted_keywords = [w.replace(",", "").replace(".", "").strip() for w in report["unique_features"].split() if len(w.strip()) > 1]
        else:
            print("[Matcher Engine] OPENROUTER_API_KEY is not defined. Using fallback parser.")
            extracted_keywords = [w.replace(",", "").replace(".", "").strip() for w in report["unique_features"].split() if len(w.strip()) > 1]

        # 4. Measure match rates across items
        matched_candidates = []
        for item in items:
            hit_count = 0
            # Target corpus combines the item name and the VLM-extracted keywords
            target_corpus = f"{item['item_name']} {item['vlm_keywords']}".lower()

            for kw in extracted_keywords:
                if kw.lower() in target_corpus:
                    hit_count += 1

            if len(extracted_keywords) > 0:
                match_rate = int((hit_count / len(extracted_keywords)) * 100)
            else:
                match_rate = 0

            # Minimum 40% matching criteria to show in recommendations list
            if match_rate >= 40:
                matched_candidates.append({
                    "id": item["id"],
                    "management_number": item["management_number"],
                    "name": item["item_name"],
                    "match_rate": min(match_rate, 95),  # Cap similarity score display at 95%
                    "tags": [t.strip() for t in item["vlm_keywords"].replace(",", " ").split() if t.strip()][:4],
                    "image": f"/static/thumbnails/{item['thumbnail_path']}",
                    "found_location_building": item["found_location_building"],
                    "found_location_detail": item["found_location_detail"]
                })

        # 5. Sort matches in descending order of match rate
        matched_candidates = sorted(matched_candidates, key=lambda x: x["match_rate"], reverse=True)

        # 6. Evaluate final case structure
        if not matched_candidates:
            final_case = 1
        else:
            if matched_candidates[0]["match_rate"] >= 90:
                final_case = 3
            else:
                final_case = 2

        return {
            "case": final_case,
            "matched_items": matched_candidates,
            "extracted_keywords": extracted_keywords
        }

async def search_found_items_by_android_request(req: dict, db_pool: asyncpg.Pool) -> list:
    """
    Searches active found items based on a structured search query from Android.
    """
    category = req.get("category", "")
    lost_location = req.get("lostLocation", "")
    detail = req.get("detail", "")
    
    # 1. Extract physical keywords from 'detail' description using OpenRouter LLM
    extracted_keywords = []
    if client and OPENROUTER_API_KEY:
        system_instruction = (
            "You are an assistant for a lost and found system. "
            "Extract 3 to 5 core physical characteristic keywords (such as color, brand, item type, or material) "
            "from the user's Korean description. "
            "Output ONLY the keywords separated by spaces, without any punctuation, bullets, or numbers. "
            "Example input: '검은색 숄더백인데 개구리 키링이 같이 달려있어요' "
            "Example output: '검은색 숄더백 개구리 키링'"
        )
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                partial(
                    client.chat.completions.create,
                    model=OPENROUTER_MODEL,
                    messages=[
                        {"role": "system", "content": system_instruction},
                        {"role": "user", "content": detail}
                    ],
                    temperature=0.1,
                    max_tokens=50,
                    timeout=10.0
                )
            )
            llm_output = response.choices[0].message.content.strip()
            extracted_keywords = [w.strip() for w in llm_output.split() if w.strip()]
        except Exception as e:
            print(f"[Android Search Engine] OpenRouter error: {e}. Falling back to simple parsing.")
            extracted_keywords = [w.replace(",", "").replace(".", "").strip() for w in detail.split() if len(w.strip()) > 1]
    else:
        print("[Android Search Engine] OPENROUTER_API_KEY is not defined. Using fallback parser.")
        extracted_keywords = [w.replace(",", "").replace(".", "").strip() for w in detail.split() if len(w.strip()) > 1]

    # 2. Fetch all '보관중' items matching the category from DB
    async with db_pool.acquire() as conn:
        items = await conn.fetch("""
            SELECT id, management_number, category, sub_category, item_name, 
                   found_date, found_location_building, found_location_detail, 
                   detail_memo, thumbnail_path, vlm_keywords
            FROM lost_items
            WHERE category = $1
              AND status = '보관중';
        """, category)

    # 3. Calculate match rates across items
    matched_candidates = []
    for item in items:
        hit_count = 0
        target_corpus = f"{item['item_name']} {item['sub_category']} {item['vlm_keywords']}".lower()

        # Count match hits on detail keywords
        for kw in extracted_keywords:
            if kw.lower() in target_corpus:
                hit_count += 1

        if len(extracted_keywords) > 0:
            match_rate = int((hit_count / len(extracted_keywords)) * 100)
        else:
            match_rate = 0

        # Location similarity boost (e.g. +15% if location names overlap)
        location_boost = 0
        if lost_location:
            lost_loc_words = [w.strip() for w in lost_location.replace("-", " ").split() if len(w.strip()) > 1]
            found_loc_corpus = f"{item['found_location_building']} {item['found_location_detail']}".lower()
            loc_hits = sum(1 for lw in lost_loc_words if lw.lower() in found_loc_corpus)
            if loc_hits > 0:
                location_boost = 15

        final_match_rate = min(match_rate + location_boost, 95)

        # Include candidates with at least 20% match rate
        if final_match_rate >= 20:
            matched_candidates.append({
                "id": item["id"],
                "management_number": item["management_number"],
                "item_name": item["item_name"],
                "category": item["category"],
                "sub_category": item["sub_category"],
                "found_date": str(item["found_date"]),
                "found_location_building": item["found_location_building"],
                "found_location_detail": item["found_location_detail"],
                "thumbnail_path": f"/static/thumbnails/{item['thumbnail_path']}",
                "match_rate": final_match_rate
            })

    # 4. Sort matches in descending order of match rate
    matched_candidates = sorted(matched_candidates, key=lambda x: x["match_rate"], reverse=True)
    return {
        "keywords": extracted_keywords,
        "results": matched_candidates
    }
