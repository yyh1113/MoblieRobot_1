import os
import uuid
import datetime
from fastapi import APIRouter, Request, Form, File, UploadFile, Depends, status, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
import asyncpg
import requests

from config.database import get_db_pool
from app.models.schemas import ReleaseRequest, MatchConfirmRequest, AndroidSearchRequest
from app.services.matcher_engine import calculate_llm_match_case, search_found_items_by_android_request

router = APIRouter()
templates = Jinja2Templates(directory="templates")

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "1234")
SESSION_TOKEN = os.getenv("SESSION_TOKEN", "secret_lost_found_admin_token_2026")

# Directory for storing thumbnails
THUMBNAIL_DIR = "static/thumbnails"
os.makedirs(THUMBNAIL_DIR, exist_ok=True)

# Helper function to check admin authentication
def check_admin_auth(request: Request) -> bool:
    session_cookie = request.cookies.get("admin_session")
    return session_cookie == SESSION_TOKEN

# Helper function to require admin authentication
def require_admin(request: Request):
    if not check_admin_auth(request):
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={"Location": "/admin/login"}
        )

# -------------------------------------------------------------------
# [Authentication Routes]
# -------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def root_redirect():
    return RedirectResponse(url="/admin/login")

@router.get("/admin", response_class=HTMLResponse)
async def admin_root():
    return RedirectResponse(url="/admin/lost-items")

@router.get("/admin/login", response_class=HTMLResponse)
async def login_page(request: Request, error: str = None):
    if check_admin_auth(request):
        return RedirectResponse(url="/admin/lost-items")
    return templates.TemplateResponse(request, "login.html", {"error": error})

@router.post("/admin/login")
async def handle_login(username: str = Form(...), password: str = Form(...)):
    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        response = RedirectResponse(url="/admin/lost-items", status_code=status.HTTP_303_SEE_OTHER)
        response.set_cookie(key="admin_session", value=SESSION_TOKEN, httponly=True, max_age=3600)
        return response
    else:
        return RedirectResponse(url="/admin/login?error=아이디 또는 비밀번호가 일치하지 않습니다.", status_code=status.HTTP_303_SEE_OTHER)

@router.get("/admin/logout")
async def handle_logout():
    response = RedirectResponse(url="/admin/login", status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(key="admin_session")
    return response

# -------------------------------------------------------------------
# [Admin Dashboard: Found Items Console]
# -------------------------------------------------------------------

@router.get("/admin/lost-items", response_class=HTMLResponse)
async def list_lost_items(
    request: Request, 
    category: str = None, 
    status_filter: str = None,
    db_pool: asyncpg.Pool = Depends(get_db_pool)
):
    if not check_admin_auth(request):
        return RedirectResponse(url="/admin/login", status_code=status.HTTP_303_SEE_OTHER)

    query = """
        SELECT id, management_number, category, sub_category, item_name, 
               found_date, found_location_building, found_location_detail, 
               thumbnail_path, vlm_keywords, status 
        FROM lost_items
        WHERE 1=1
    """
    params = []
    param_idx = 1
    
    if category:
        query += f" AND category = ${param_idx}"
        params.append(category)
        param_idx += 1
        
    if status_filter:
        query += f" AND status = ${param_idx}"
        params.append(status_filter)
        param_idx += 1
        
    query += " ORDER BY found_date DESC, id DESC;"

    async with db_pool.acquire() as conn:
        items = await conn.fetch(query, *params)
        
        # Get category list for filter dropdown
        categories = await conn.fetch("SELECT DISTINCT category FROM lost_items;")
        category_list = [c["category"] for c in categories]

    return templates.TemplateResponse(request, "lost-items.html", {
        "items": [dict(i) for i in items],
        "categories": category_list,
        "selected_category": category,
        "selected_status": status_filter
    })

# -------------------------------------------------------------------
# [Admin Dashboard: Found Item Details & Release Form]
# -------------------------------------------------------------------

@router.get("/admin/lost-items/{item_id}", response_class=HTMLResponse)
async def view_lost_item(
    request: Request, 
    item_id: int, 
    db_pool: asyncpg.Pool = Depends(get_db_pool)
):
    if not check_admin_auth(request):
        return RedirectResponse(url="/admin/login", status_code=status.HTTP_303_SEE_OTHER)

    async with db_pool.acquire() as conn:
        item = await conn.fetchrow("""
            SELECT id, management_number, category, sub_category, item_name, 
                   found_date, found_location_building, found_location_detail, 
                   detail_memo, thumbnail_path, vlm_keywords, status,
                   recipient_name, recipient_phone, recipient_student_id, released_at
            FROM lost_items
            WHERE id = $1;
        """, item_id)

    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    return templates.TemplateResponse(request, "detail.html", {
        "item": dict(item)
    })

@router.post("/admin/lost-items/{item_id}/release")
async def release_lost_item(
    item_id: int,
    recipient_name: str = Form(...),
    recipient_phone: str = Form(...),
    recipient_student_id: str = Form(...),
    db_pool: asyncpg.Pool = Depends(get_db_pool)
):
    # Update found item details
    async with db_pool.acquire() as conn:
        async with conn.transaction():
            # Verify if item is already released
            item = await conn.fetchrow("SELECT status FROM lost_items WHERE id = $1;", item_id)
            if not item:
                raise HTTPException(status_code=404, detail="Item not found")
            if item["status"] == "수령완료":
                return RedirectResponse(url=f"/admin/lost-items/{item_id}?error=이미 수령 완료된 물품입니다.", status_code=status.HTTP_303_SEE_OTHER)

            await conn.execute("""
                UPDATE lost_items
                SET status = '수령완료',
                    recipient_name = $1,
                    recipient_phone = $2,
                    recipient_student_id = $3,
                    released_at = CURRENT_TIMESTAMP
                WHERE id = $4;
            """, recipient_name, recipient_phone, recipient_student_id, item_id)

    return RedirectResponse(url=f"/admin/lost-items/{item_id}", status_code=status.HTTP_303_SEE_OTHER)

# -------------------------------------------------------------------
# [Admin Dashboard: Lost Reports Console]
# -------------------------------------------------------------------

@router.get("/admin/lost-reports", response_class=HTMLResponse)
async def list_lost_reports(
    request: Request,
    category: str = None,
    matching_status: str = None,
    db_pool: asyncpg.Pool = Depends(get_db_pool)
):
    if not check_admin_auth(request):
        return RedirectResponse(url="/admin/login", status_code=status.HTTP_303_SEE_OTHER)

    query = """
        SELECT id, report_number, category, item_name, start_date, end_date, 
               lost_building, lost_detail, unique_features, reporter_name, 
               reporter_phone, reporter_student_id, report_time_clock, 
               matching_status, matched_lost_item_id, image_path
        FROM lost_reports
        WHERE 1=1
    """
    params = []
    param_idx = 1
    
    if category:
        query += f" AND category = ${param_idx}"
        params.append(category)
        param_idx += 1
        
    if matching_status:
        query += f" AND matching_status = ${param_idx}"
        params.append(matching_status)
        param_idx += 1
        
    query += " ORDER BY report_time_clock DESC, id DESC;"

    async with db_pool.acquire() as conn:
        reports = await conn.fetch(query, *params)
        
        # Get category list
        categories = await conn.fetch("SELECT DISTINCT category FROM lost_reports;")
        category_list = [c["category"] for c in categories]

    return templates.TemplateResponse(request, "lost-reports.html", {
        "reports": [dict(r) for r in reports],
        "categories": category_list,
        "selected_category": category,
        "selected_matching_status": matching_status
    })

# -------------------------------------------------------------------
# [Admin Dashboard: AI Control Center (Report Match Detail)]
# -------------------------------------------------------------------

@router.get("/admin/lost-reports/{report_id}", response_class=HTMLResponse)
async def view_lost_report(
    request: Request,
    report_id: int,
    db_pool: asyncpg.Pool = Depends(get_db_pool)
):
    if not check_admin_auth(request):
        return RedirectResponse(url="/admin/login", status_code=status.HTTP_303_SEE_OTHER)

    async with db_pool.acquire() as conn:
        report = await conn.fetchrow("""
            SELECT id, report_number, category, item_name, start_date, end_date, 
                   lost_building, lost_detail, unique_features, reporter_name, 
                   reporter_phone, reporter_student_id, report_time_clock, 
                   matching_status, matched_lost_item_id, image_path
            FROM lost_reports
            WHERE id = $1;
        """, report_id)

    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    # Run the AI Matching Engine logic
    matching_result = await calculate_llm_match_case(report_id, db_pool)
    
    return templates.TemplateResponse(request, "report-detail.html", {
        "report": dict(report),
        "case": matching_result["case"],
        "matched_items": matching_result["matched_items"],
        "extracted_keywords": matching_result["extracted_keywords"]
    })

@router.post("/admin/lost-reports/{report_id}/match-confirm")
async def confirm_report_match(
    report_id: int,
    lost_item_id: int = Form(...),
    db_pool: asyncpg.Pool = Depends(get_db_pool)
):
    async with db_pool.acquire() as conn:
        async with conn.transaction():
            # 1. Fetch report and found item details
            report = await conn.fetchrow("""
                SELECT reporter_name, reporter_phone, reporter_student_id 
                FROM lost_reports WHERE id = $1;
            """, report_id)
            
            item = await conn.fetchrow("SELECT status FROM lost_items WHERE id = $1;", lost_item_id)

            if not report or not item:
                raise HTTPException(status_code=404, detail="Report or Found Item not found")

            if item["status"] == "수령완료":
                return RedirectResponse(url=f"/admin/lost-reports/{report_id}?error=해당 습득물은 이미 수령 완료 상태입니다.", status_code=status.HTTP_303_SEE_OTHER)

            # 2. Update found item: Set status '수령완료', copy reporter info to recipient, and timestamp
            await conn.execute("""
                UPDATE lost_items
                SET status = '수령완료',
                    recipient_name = $1,
                    recipient_phone = $2,
                    recipient_student_id = $3,
                    released_at = CURRENT_TIMESTAMP
                WHERE id = $4;
            """, report["reporter_name"], report["reporter_phone"], report["reporter_student_id"], lost_item_id)

            # 3. Update report: Set status '매칭완료', link the matched_lost_item_id
            await conn.execute("""
                UPDATE lost_reports
                SET matching_status = '매칭완료',
                    matched_lost_item_id = $1
                WHERE id = $2;
            """, lost_item_id, report_id)

    return RedirectResponse(url=f"/admin/lost-reports/{report_id}", status_code=status.HTTP_303_SEE_OTHER)

@router.get("/admin/lost-reports/{report_id}/compare/{item_id}", response_class=HTMLResponse)
async def compare_report_item(
    request: Request,
    report_id: int,
    item_id: int,
    db_pool: asyncpg.Pool = Depends(get_db_pool)
):
    if not check_admin_auth(request):
        return RedirectResponse(url="/admin/login", status_code=status.HTTP_303_SEE_OTHER)

    async with db_pool.acquire() as conn:
        report = await conn.fetchrow("""
            SELECT id, report_number, category, item_name, start_date, end_date, 
                   lost_building, lost_detail, unique_features, reporter_name, 
                   reporter_phone, reporter_student_id, report_time_clock, 
                   matching_status, matched_lost_item_id, image_path
            FROM lost_reports
            WHERE id = $1;
        """, report_id)

        item = await conn.fetchrow("""
            SELECT id, management_number, category, sub_category, item_name, 
                   found_date, found_location_building, found_location_detail, 
                   detail_memo, thumbnail_path, vlm_keywords, status
            FROM lost_items
            WHERE id = $1;
        """, item_id)

    if not report or not item:
        raise HTTPException(status_code=404, detail="Report or Item not found")

    matching_result = await calculate_llm_match_case(report_id, db_pool)
    
    match_rate = 0
    item_tags = []
    for candidate in matching_result["matched_items"]:
        if candidate["id"] == item_id:
            match_rate = candidate["match_rate"]
            item_tags = candidate["tags"]
            break
            
    if not item_tags:
        item_tags = [t.strip() for t in item["vlm_keywords"].replace(",", " ").split() if t.strip()][:5]
        extracted = matching_result["extracted_keywords"]
        hit_count = sum(1 for kw in extracted if kw.lower() in f"{item['item_name']} {item['vlm_keywords']}".lower())
        if extracted:
            match_rate = int((hit_count / len(extracted)) * 100)
            match_rate = min(match_rate, 95)
        else:
            match_rate = 0

    highlights = []
    if report["category"] == item["category"]:
        highlights.append("물품 분류 일치")
        
    colors = ["검은색", "블랙", "흰색", "화이트", "빨간색", "레드", "파란색", "블루", "노란색", "옐로우", "초록색", "그린", "회색", "그레이", "실버", "골드", "핑크", "보라색"]
    matched_colors = [c for c in colors if c in report["item_name"] + " " + report["unique_features"] and c in item["item_name"] + " " + item["vlm_keywords"]]
    if matched_colors:
        highlights.append("색상 일치")
        
    if report["lost_building"] == item["found_location_building"]:
        highlights.append("장소 일치")
    elif (report["lost_building"] in item["found_location_building"]) or (item["found_location_building"] in report["lost_building"]):
        highlights.append("장소 유사")
        
    overlap = sum(1 for tag in item_tags if tag.lower() in report["unique_features"].lower())
    if overlap >= 1:
        highlights.append("특이사항 유사")
        
    if not highlights:
        highlights.append("카테고리 연관")

    return templates.TemplateResponse(request, "ai-matching-detail.html", {
        "report": dict(report),
        "item": dict(item),
        "match_rate": match_rate,
        "highlights": highlights,
        "item_tags": item_tags,
        "extracted_keywords": matching_result["extracted_keywords"]
    })

@router.post("/admin/lost-reports/{report_id}/exclude")
async def exclude_report_match(
    report_id: int,
    lost_item_id: int = Form(...),
    db_pool: asyncpg.Pool = Depends(get_db_pool)
):
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO excluded_matches (report_id, lost_item_id)
            VALUES ($1, $2)
            ON CONFLICT DO NOTHING;
        """, report_id, lost_item_id)

    return RedirectResponse(url=f"/admin/lost-reports/{report_id}", status_code=status.HTTP_303_SEE_OTHER)

# -------------------------------------------------------------------
# [VLM MacBook / Temi Client API Endpoint]
# -------------------------------------------------------------------

@router.post("/api/save-found-item")
async def save_found_item(
    category: str = Form(...),
    sub_category: str = Form(...),
    item_name: str = Form(...),
    found_date: str = Form(...), # Format: YYYYMMDD or YYYY-MM-DD
    found_location_building: str = Form(...),
    found_location_detail: str = Form(...),
    detail_memo: str = Form(None),
    vlm_keywords: str = Form(...),
    thumbnail: UploadFile = File(...),
    db_pool: asyncpg.Pool = Depends(get_db_pool)
):
    """
    Receives analyzed items and thumbnails from MacBook VLM client.
    Downsizes/Saves the image inside static/thumbnails/ and registers it.
    """
    try:
        # Parse or default found_date
        try:
            if "-" in found_date:
                parsed_date = datetime.datetime.strptime(found_date, "%Y-%m-%d").date()
            else:
                parsed_date = datetime.datetime.strptime(found_date, "%Y%m%d").date()
        except Exception:
            parsed_date = datetime.date.today()

        date_str = parsed_date.strftime("%Y%m%d")

        async with db_pool.acquire() as conn:
            async with conn.transaction():
                # Generate management number L-YYYYMMDD-XXXX
                count_row = await conn.fetchrow("""
                    SELECT COUNT(*) as count 
                    FROM lost_items 
                    WHERE found_date = $1;
                """, parsed_date)
                
                seq = count_row["count"] + 1
                management_num = f"L-{date_str}-{seq:04d}"
                
                # Save thumbnail file securely
                # Use management number as file name to keep it distinct
                file_extension = os.path.splitext(thumbnail.filename)[1] or ".jpg"
                save_filename = f"thumb_{management_num}{file_extension}"
                file_path = os.path.join(THUMBNAIL_DIR, save_filename)
                
                # Read binary file content and write the thumbnail to disk
                content = await thumbnail.read()
                with open(file_path, "wb") as f:
                    f.write(content)

                # Insert to PostgreSQL DB
                insert_query = """
                    INSERT INTO lost_items (
                        management_number, category, sub_category, item_name, found_date,
                        found_location_building, found_location_detail, detail_memo,
                        thumbnail_path, vlm_keywords, status
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, '보관중')
                    RETURNING id;
                """
                inserted_id = await conn.fetchval(
                    insert_query,
                    management_num,
                    category,
                    sub_category,
                    item_name,
                    parsed_date,
                    found_location_building,
                    found_location_detail,
                    detail_memo,
                    save_filename,
                    vlm_keywords
                )

        print(f"[API] Registered Found Item ID: {inserted_id}, Management No: {management_num}")
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "status": "success",
                "item_id": inserted_id,
                "management_number": management_num,
                "thumbnail_path": f"/static/thumbnails/{save_filename}"
            }
        )
    except Exception as e:
        print(f"[API Error] Failed to register found item: {e}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"status": "error", "message": str(e)}
        )

@router.post("/api/search-items")
async def search_items_api(
    payload: AndroidSearchRequest,
    db_pool: asyncpg.Pool = Depends(get_db_pool)
):
    """
    Receives JSON search payload from Android (Kiosk/App client),
    performs AI matching, and returns ranked found items in JSON format.
    """
    try:
        req_dict = payload.dict()
        print(f"[API Search] Received explore request for category: {req_dict.get('category')}")
        
        search_result = await search_found_items_by_android_request(req_dict, db_pool)
        
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "status": "success",
                "phase": req_dict.get("phase"),
                "query": req_dict.get("detail"),
                "keywords": search_result["keywords"],
                "results": search_result["results"]
            }
        )
    except Exception as e:
        print(f"[API Search Error] Failed to process search request: {e}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"status": "error", "message": str(e)}
        )

@router.post("/api/lost-reports")
async def create_lost_report(
    category: str = Form(None),
    item_name: str = Form(None),
    start_date: str = Form(None),
    end_date: str = Form(None),
    lost_building: str = Form(None),
    lost_detail: str = Form(None),
    unique_features: str = Form(None),
    reporter_name: str = Form(None),
    reporter_phone: str = Form(None),
    reporter_student_id: str = Form(None),
    report_time_clock: str = Form(None),
    matching_status: str = Form(None),
    image: UploadFile = File(None),
    db_pool: asyncpg.Pool = Depends(get_db_pool)
):
    """
    Receives lost report form data from Android client, generates report number (R-YYYYMMDD-XXXX),
    and saves the report inside PostgreSQL database.
    """
    try:
        # Fallback values for optional fields
        safe_category = category or "기타"
        safe_item_name = item_name or "분실물"
        safe_lost_building = lost_building or "미지정"
        safe_lost_detail = lost_detail or "미지정"
        safe_unique_features = unique_features or ""
        safe_reporter_name = reporter_name or "익명"
        safe_reporter_phone = reporter_phone or "010-0000-0000"
        safe_reporter_student_id = reporter_student_id or "0000000000"

        # Parse dates safely
        def parse_date(date_str: str) -> datetime.date:
            try:
                if not date_str:
                    return datetime.date.today()
                if "-" in date_str:
                    return datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
                else:
                    return datetime.datetime.strptime(date_str, "%Y%m%d").date()
            except Exception:
                return datetime.date.today()

        parsed_start_date = parse_date(start_date)
        parsed_end_date = parse_date(end_date)

        # Parse report_time_clock (ISO 8601 format like "yyyy-MM-dd'T'HH:mm:ssXXX")
        try:
            if report_time_clock:
                parsed_report_time = datetime.datetime.fromisoformat(report_time_clock)
                if parsed_report_time.tzinfo is not None:
                    parsed_report_time = parsed_report_time.replace(tzinfo=None)
            else:
                parsed_report_time = datetime.datetime.now()
        except Exception:
            parsed_report_time = datetime.datetime.now()

        # Generate report_number in format R-YYYYMMDD-XXXX
        today_str = datetime.date.today().strftime("%Y%m%d")

        async with db_pool.acquire() as conn:
            async with conn.transaction():
                # Count today's reports to generate sequence number
                count_row = await conn.fetchrow("""
                    SELECT COUNT(*) as count 
                    FROM lost_reports 
                    WHERE report_number LIKE $1;
                """, f"R-{today_str}-%")
                seq = count_row["count"] + 1
                report_num = f"R-{today_str}-{seq:04d}"

                # Save report image securely if uploaded
                save_filename = None
                if image and image.filename:
                    try:
                        file_extension = os.path.splitext(image.filename)[1] or ".jpg"
                        save_filename = f"report_{report_num}{file_extension}"
                        file_path = os.path.join(THUMBNAIL_DIR, save_filename)
                        
                        content = await image.read()
                        with open(file_path, "wb") as f:
                            f.write(content)
                    except Exception as img_err:
                        print(f"[API Warning] Failed to save uploaded image: {img_err}")
                        save_filename = None

                # Insert to PostgreSQL DB
                insert_query = """
                    INSERT INTO lost_reports (
                        report_number, category, item_name, start_date, end_date,
                        lost_building, lost_detail, unique_features,
                        reporter_name, reporter_phone, reporter_student_id,
                        report_time_clock, matching_status, image_path
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, '매칭대기', $13)
                    RETURNING id;
                """
                inserted_id = await conn.fetchval(
                    insert_query,
                    report_num,
                    safe_category,
                    safe_item_name,
                    parsed_start_date,
                    parsed_end_date,
                    safe_lost_building,
                    safe_lost_detail,
                    safe_unique_features,
                    safe_reporter_name,
                    safe_reporter_phone,
                    safe_reporter_student_id,
                    parsed_report_time,
                    save_filename
                )


        print(f"[API] Registered Lost Report ID: {inserted_id}, Report No: {report_num}")
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "status": "success",
                "report_id": inserted_id,
                "reportNumber": report_num,
                "report_number": report_num,
                "requestNumber": report_num,
                "request_number": report_num
            }
        )
    except Exception as e:
        print(f"[API Error] Failed to register lost report: {e}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"status": "error", "message": str(e)}
        )

# -------------------------------------------------------------------

# [Android Confirmation API Endpoint]
# -------------------------------------------------------------------

@router.post("/api/locker/open")
@router.get("/api/locker/open")
@router.post("/api/confirm")
@router.post("/api/comfirm")
@router.get("/api/confirm")
@router.get("/api/comfirm")
async def api_confirm_relay(
    request: Request,
    db_pool: asyncpg.Pool = Depends(get_db_pool)
):
    """
    안드로이드 앱으로부터 수령 확정(Confirm) 신호를 수신하여,
    데이터베이스 상태를 업데이트하고 다른 기기(Tailscale IP 등)로 신호를 릴레이 전송합니다.
    """
    try:
        # 1. 요청 정보 파싱 (JSON, Form, Query Parameter 모두 대응 가능한 유연한 설계)
        payload_data = {}
        
        # Query parameters 우선 추출
        for key, value in request.query_params.items():
            payload_data[key] = value
            
        # JSON 바디 추출 시도
        try:
            body_json = await request.json()
            if isinstance(body_json, dict):
                payload_data.update(body_json)
        except Exception:
            pass
            
        # Form 데이터 추출 시도
        try:
            body_form = await request.form()
            for key, value in body_form.items():
                payload_data[key] = value
        except Exception:
            pass

        print(f"\n================ [안드로이드 Confirm 신호 수신] ================")
        print(f" - Method: {request.method}")
        print(f" - Payload: {payload_data}")
        print("=========================================================\n")

        # 2. 데이터베이스 상태 업데이트 (물품 ID 혹은 관리 번호가 있는 경우 수령 완료로 업데이트)
        target_item_id = (
            payload_data.get("lost_item_id") or 
            payload_data.get("item_id") or 
            payload_data.get("itemId") or 
            payload_data.get("id")
        )
        management_number = payload_data.get("management_number") or payload_data.get("managementNumber")
        
        recipient_name = (
            payload_data.get("recipient_name") or 
            payload_data.get("claimantName")
        )
        recipient_phone = (
            payload_data.get("recipient_phone") or 
            payload_data.get("claimantPhone")
        )
        recipient_student_id = (
            payload_data.get("recipient_student_id") or 
            payload_data.get("claimantStudentNumber") or
            payload_data.get("claimantStudentId")
        )
        
        updated_db = False
        print(f"[Confirm DB Log] target_item_id: {target_item_id} (type: {type(target_item_id)}), management_number: {management_number}")
        if target_item_id or management_number:
            async with db_pool.acquire() as conn:
                async with conn.transaction():
                    if target_item_id:
                        try:
                            item_id_int = int(target_item_id)
                            # 물품 존재 여부 및 현재 상태 확인
                            item = await conn.fetchrow("SELECT id, status FROM lost_items WHERE id = $1;", item_id_int)
                            print(f"[Confirm DB Log] ID {item_id_int} 조회 결과: {item}")
                            if item:
                                await conn.execute("""
                                    UPDATE lost_items
                                    SET status = '수령완료',
                                        released_at = CURRENT_TIMESTAMP,
                                        recipient_name = COALESCE($1, recipient_name, '안드로이드 키오스크'),
                                        recipient_phone = COALESCE($2, recipient_phone, ''),
                                        recipient_student_id = COALESCE($3, recipient_student_id, '')
                                    WHERE id = $4;
                                """, recipient_name, recipient_phone, recipient_student_id, item_id_int)
                                updated_db = True
                                print(f"[Confirm DB] Item ID {item_id_int} 상태를 '수령완료'로 업데이트 완료.")
                        except ValueError as ve:
                            print(f"[Confirm DB Log] ValueError 발생: {ve}")
                        except Exception as inner_err:
                            print(f"[Confirm DB Log] Inner Exception 발생: {inner_err}")
                    
                    if not updated_db and management_number:
                        item = await conn.fetchrow("SELECT id FROM lost_items WHERE management_number = $1;", management_number)
                        print(f"[Confirm DB Log] management_number {management_number} 조회 결과: {item}")
                        if item:
                            await conn.execute("""
                                UPDATE lost_items
                                SET status = '수령완료',
                                    released_at = CURRENT_TIMESTAMP,
                                    recipient_name = COALESCE($1, recipient_name, '안드로이드 키오스크'),
                                    recipient_phone = COALESCE($2, recipient_phone, ''),
                                    recipient_student_id = COALESCE($3, recipient_student_id, '')
                                WHERE management_number = $4;
                            """, recipient_name, recipient_phone, recipient_student_id, management_number)
                            updated_db = True
                            print(f"[Confirm DB] 관리번호 {management_number} 상태를 '수령완료'로 업데이트 완료.")

        # 3. Tailscale IP 기기(RDK X5)로 단일 신호 전송
        # 127.0.0.1이 기본값이며, 환경변수나 페이로드로 타겟 주소를 커스텀 가능하게 구현
        target_ip = payload_data.get("target_ip") or os.getenv("TAILSCALE_IP", "127.0.0.1")
        
        # arducam_yolo_web (Flask)의 문 열림 제어 엔드포인트 단일 매핑 (GET /api/door/open)
        relay_url = f"http://{target_ip}:8000/api/door/open"
        if payload_data.get("relay_url"):
            relay_url = payload_data.get("relay_url")

        relay_success = False
        relay_response_info = {}
        
        try:
            print(f"[Confirm Relay] {relay_url}로 GET 신호 전송 시도 중...")
            resp = requests.get(relay_url, params=payload_data, timeout=5.0)
            
            if resp.status_code < 300:
                relay_success = True
                relay_response_info = {
                    "url": str(relay_url),
                    "status_code": int(resp.status_code),
                    "content_type": str(resp.headers.get("content-type", ""))
                }
                print(f"[Confirm Relay] {relay_url}로 신호 전송 성공! 응답코드: {resp.status_code}")
            else:
                print(f"[Confirm Relay] {relay_url} 응답 실패: {resp.status_code}")
        except Exception as relay_err:
            print(f"[Confirm Relay Fail] {relay_url} 접속 에러: {relay_err}")

        # 4. 결과 응답 반환
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={
                "status": "success" if (relay_success or updated_db) else "warning",
                "message": "안드로이드 수령 확정 신호를 정상 수신했습니다.",
                "db_updated": updated_db,
                "relay_success": relay_success,
                "relay_info": relay_response_info
            }
        )

    except Exception as e:
        print(f"[Confirm Error] 처리 실패: {e}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "status": "error",
                "message": f"신호 처리 중 에러 발생: {str(e)}"
            }
        )
