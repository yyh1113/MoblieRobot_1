import os
import logging
import requests
from urllib.parse import urlparse
from fastapi import File, UploadFile, Form

# Configure logger
logger = logging.getLogger("vlm_coordination")

# RDK X5 endpoint address configuration via environment variables
RDK_X5_NODE_URL = os.getenv("RDK_X5_NODE_URL", "http://localhost:8000/api/request")


async def handle_android_input(
        category: str = Form(...),
        subCategory: str = Form(...),
        itemName: str = Form(...),
        foundLocation: str = Form(...),
        detail: str = Form(...),
        foundAt: str = Form(...),
        image: UploadFile = File(...)  # Primary snapshot submitted by the client
):
    """
    Parses incoming client metadata, reads the primary snapshot,
    sends control signals to close the Kiosk locker door, and triggers 
    a secondary high-precision capture from the RDK X5 camera.
    """
    logger.info(f"Processing client submission: '{itemName}' in category '{category}'")

    # Read binary bytes of the client's 1st image
    android_1st_bytes = await image.read()

    # Step 1: Send a command to close the Kiosk door before capturing the 2nd photo
    try:
        parsed_node_url = urlparse(RDK_X5_NODE_URL)
        close_url = f"{parsed_node_url.scheme}://{parsed_node_url.netloc}/api/door/close"
        logger.info(f"Sending door close request to Edge Node: {close_url}")
        close_resp = requests.get(close_url, timeout=5.0)
        if close_resp.status_code == 200:
            logger.info("Edge locker door closed successfully.")
        else:
            logger.warning(f"Edge locker door close returned status code: {close_resp.status_code}")
    except Exception as close_err:
        logger.error(f"Failed to send close door request: {close_err}")

    # Step 2: Trigger the high-resolution capture sequence on the RDK X5 embedded board (Sync wait)
    logger.info(f"Triggering 2nd snapshot capture sequence at {RDK_X5_NODE_URL}...")

    rdk_2nd_bytes = None
    try:
        # 20-second timeout to allow BPU YOLO computation and LED exposure stabilization on the edge node
        rdk_response = requests.get(RDK_X5_NODE_URL, timeout=20.0)

        if rdk_response.status_code == 200:
            logger.info("Successfully fetched 2nd high-precision snapshot from RDK X5.")
            rdk_2nd_bytes = rdk_response.content
        else:
            logger.warning(f"RDK X5 capture failed (status: {rdk_response.status_code}). Falling back to primary snapshot.")

    except Exception as hardware_err:
        logger.error(f"Edge Node communication error: {hardware_err}. Proceeding with primary snapshot fallback.")
        rdk_2nd_bytes = None

    return {
        "text_fields": {
            "category": category,
            "sub_category": subCategory,
            "item_name": itemName,
            "found_location": foundLocation,
            "detail": detail,
            "found_at": foundAt
        },
        "images": {
            "android_ raw": android_1st_bytes,  # Keep keys compliant with next stages
            "android_1st_raw": android_1st_bytes,
            "rdk_2nd_raw": rdk_2nd_bytes
        }
    }