import io
import logging
from PIL import Image
from mlx_vlm import load, generate

# Configure logger
logger = logging.getLogger("vlm_coordination")

LOCAL_MODEL_PATH = "./Qwen3.5-9B"
model, processor = None, None


def initialize_vlm_model():
    """Loads the local Qwen multimodal VLM weights into memory using mlx_vlm."""
    global model, processor
    logger.info(f"Loading local VLM model from directory: {LOCAL_MODEL_PATH}...")
    try:
        model, processor = load(LOCAL_MODEL_PATH)
        logger.info("Successfully initialized Qwen 3.5 VLM engine.")
    except Exception as e:
        logger.error(f"Failed to initialize VLM weights: {e}", exc_info=True)
        model, processor = None, None


def run_mlx_vlm_inference(data_packet: dict) -> str:
    """
    Constructs a visual prompt combined with contextual text inputs, 
    and triggers the MLX-accelerated VLM model to extract characteristic tags.
    """
    global model, processor

    fields = data_packet["text_fields"]
    img_data = data_packet["images"]

    user_prompt = (
        "제공된 이미지와 텍스트 정보를 바탕으로, 분실물의 물리적 특징을 나타내는 핵심 태그(키워드)들을 추출해 주세요.\n\n"
        "[제공된 정보]\n"
        f"- 대분류: {fields['category']}\n"
        f"- 소분류: {fields['sub_category']}\n"
        f"- 제보된 물품명: {fields['item_name']}\n"
        f"- 습득 장소: {fields['found_location']}\n"
        f"- 사용자 상세 설명: {fields['detail']}\n\n"
        "[태그 추출 및 생성 지침]\n"
        "1. 이미지에서 시각적으로 확인 가능한 구체적인 특징을 최우선으로 추출하세요:\n"
        "   - 색상 (예: 검은색, 네이비, 체크패턴 등)\n"
        "   - 브랜드 또는 로고 (예: Apple, 스타벅스, 구찌 등 - 식별 가능한 경우만)\n"
        "   - 형태 및 외관 (예: 둥근 모양, 직사각형, 삼단 접이 등)\n"
        "   - 세부 특징 (예: 스크래치 있음, 캐릭터 스티커 부착, 곰돌이 키링, 금속 버클 등)\n"
        "2. 제공된 텍스트 정보와 이미지를 대조하여, 모순되지 않고 상호 보완적인 특징을 추출하세요.\n"
        "3. 출력 형식 제한 (매우 중요):\n"
        "   - 오직 쉼표 `,` 로만 구분된 단어들의 리스트 형태로만 출력하세요.\n"
        "   - 서론(예: '분석 결과는 다음과 같습니다'), 결론, 부연 설명, 마침표(.) 등은 절대 포함하지 마세요.\n"
        "   - 예시 형식: 검은색, 가죽, 3단지갑, 프라다 로고, 금색 지퍼\n"
    )

    # Wrap prompt in standard chat template messages
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image"},
                {"type": "text", "text": user_prompt}
            ]
        }
    ]

    try:
        formatted_prompt = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    except Exception:
        formatted_prompt = f"<|im_start|>user\n{user_prompt}<|im_end|>\n<|im_start|>assistant\n"

    logger.info("Assembling image and text content for VLM inference context...")

    # Primary check for RDK 2nd photo, fallback to Android 1st raw photo
    target_raw_bytes = img_data["rdk_2nd_raw"] if img_data["rdk_2nd_raw"] else img_data["android_1st_raw"]

    if target_raw_bytes:
        pil_image = Image.open(io.BytesIO(target_raw_bytes))
        if pil_image.mode != "RGB":
            pil_image = pil_image.convert("RGB")
    else:
        pil_image = None

    # Handle MLX Multimodal execution with package safety fallbacks
    if model is not None and processor is not None and pil_image is not None:
        try:
            raw_result = generate(
                model=model,
                processor=processor,
                prompt=formatted_prompt,
                image=pil_image,  # Singular (compliant with latest mlx_vlm spec)
                verbose=False,
                max_tokens=1024,
                repetition_penalty=1.1,
                repetition_context_size=64
            )
        except TypeError:
            logger.warning("Generation signature mismatch. Trying alternative 'images' argument fallback.")
            try:
                # Support deprecated mlx_vlm versions
                raw_result = generate(
                    model=model,
                    processor=processor,
                    prompt=formatted_prompt,
                    images=pil_image,
                    verbose=False,
                    max_tokens=1024,
                    repetition_penalty=1.1,
                    repetition_context_size=64
                )
            except TypeError:
                logger.warning("Multimodal parameter signature error. Falling back to text-only inference.")
                raw_result = generate(
                    model=model,
                    processor=processor,
                    prompt=formatted_prompt,
                    verbose=False,
                    max_tokens=1024,
                    repetition_penalty=1.1,
                    repetition_context_size=64
                )

        # Extract text property from GenerationResult object if applicable
        if hasattr(raw_result, "text"):
            final_text = raw_result.text
        else:
            final_text = str(raw_result)

        # Strip reasoning models' thinking tags if present
        if "</think>" in final_text:
            final_text = final_text.split("</think>", 1)[1]
        elif "<think>" in final_text:
            final_text = final_text.split("<think>", 1)[0]

        # Clean text lines
        lines = [line.strip() for line in final_text.split("\n") if line.strip()]
        cleaned_text = final_text.strip()
        if len(lines) > 1:
            for line in reversed(lines):
                # Filter out system conversational wrappers
                if "," in line and not line.endswith(".") and not any(phrase in line.lower() for phrase in ["user wants", "analyze the", "look closely", "let's check", "therefore"]):
                    cleaned_text = line
                    break
            else:
                cleaned_text = lines[-1]

        # Final sanitization pass
        if "```" in cleaned_text:
            cleaned_text = cleaned_text.replace("```", "")
        cleaned_text = cleaned_text.replace("\n", ", ")
        
        # Strip generic prefixes
        for prefix in ["태그:", "키워드:", "분석 결과:", "추출 결과:", "Tags:", "Keywords:", "결과:"]:
            if cleaned_text.startswith(prefix):
                cleaned_text = cleaned_text[len(prefix):].strip()
                
        # Return cleaned comma-separated list of items
        tags = [tag.strip() for tag in cleaned_text.split(",") if tag.strip()]
        return ", ".join(tags)
    else:
        logger.warning("VLM weights not loaded or image binary missing. Using metadata fallback tagging.")
        return f"{fields['category']}, {fields['item_name']}, {fields['detail']}"