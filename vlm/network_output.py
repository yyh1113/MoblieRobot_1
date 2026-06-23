import io
import os
import logging
import requests
from PIL import Image

# Configure logger
logger = logging.getLogger("vlm_coordination")

# Main database endpoint address configuration via environment variables
MAIN_SERVER_DB_URL = os.getenv("MAIN_SERVER_DB_URL", "http://localhost:8000/api/save-found-item")


def process_and_forward_to_main_db(data_packet: dict, vlm_keywords: str) -> bool:
    """
    Combines collected metadata, crops/resizes the 2nd image into a lightweight
    JPEG thumbnail, and forwards the final record to the central web database server.
    """
    logger.info("Starting database output forwarding pipeline...")

    fields = data_packet["text_fields"]
    img_data = data_packet["images"]

    try:
        # Use 2nd camera capture if available, otherwise fallback to the client's 1st photo
        raw_img_bytes = img_data["rdk_2nd_raw"] if img_data["rdk_2nd_raw"] else img_data["android_1st_raw"]
        src_image = Image.open(io.BytesIO(raw_img_bytes))

        # Downscale image to a lightweight 400px width thumbnail to optimize bandwidth
        THUMB_WIDTH = 400
        thumb_ratio = THUMB_WIDTH / float(src_image.width)
        thumb_h = int((float(src_image.height) * float(thumb_ratio)))
        thumbnail_image = src_image.resize((THUMB_WIDTH, thumb_h), Image.Resampling.LANCZOS)

        # Compress to JPEG format with 80% quality
        thumb_io = io.BytesIO()
        thumbnail_image.save(thumb_io, format="JPEG", quality=80)
        thumb_bytes = thumb_io.getvalue()

        # Parse locations into building/detail fields (first word split)
        location_raw = fields.get("found_location") or ""
        loc_parts = location_raw.strip().split(" ", 1)
        building = loc_parts[0] if loc_parts[0] else "Unknown"
        detail_loc = loc_parts[1] if len(loc_parts) > 1 else "No detail"

        form_data = {
            "category": fields["category"],
            "sub_category": fields["sub_category"],
            "item_name": fields["item_name"],
            "found_date": fields["found_at"],
            "found_location_building": building,
            "found_location_detail": detail_loc,
            "detail_memo": fields["detail"],
            "vlm_keywords": vlm_keywords
        }

        files = {
            "thumbnail": ("refined_kiosk_capture.jpg", thumb_bytes, "image/jpeg")
        }

        logger.info(f"Forwarding payload to Main Database: {MAIN_SERVER_DB_URL}")
        main_response = requests.post(MAIN_SERVER_DB_URL, data=form_data, files=files, timeout=25)

        if main_response.status_code == 200:
            logger.info("Successfully registered the item on the central Database Server.")
            return True
        else:
            logger.error(f"Central Database Server rejected the registration (status code: {main_response.status_code})")
            return False

    except Exception as e:
        logger.error(f"Failed to forward data to the main server: {str(e)}", exc_info=True)
        return False