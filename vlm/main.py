from fastapi import FastAPI, File, UploadFile, Form, status
import uvicorn
import logging

# Import architecture layers
import network_input
import vlm_server
import network_output

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("vlm_coordination")

app = FastAPI(title="Distributed VLM Coordination Server Instance")


@app.on_event("startup")
def startup_event():
    """Load the VLM weights on startup."""
    vlm_server.initialize_vlm_model()


@app.post("/api/found-items", status_code=status.HTTP_200_OK)
async def unified_found_items_pipeline(
        category: str = Form(...),
        subCategory: str = Form(...),
        itemName: str = Form(...),
        foundLocation: str = Form(...),
        detail: str = Form(...),
        foundAt: str = Form(...),
        image: UploadFile = File(...)  # Client's 1st photo
):
    """
    Coordinates Kiosk deposit requests:
    1. Receive Android deposit and trigger RDK X5 close-door + 2nd photo sequence.
    2. Run local MLX VLM (Qwen 3.5 9B) to extract visual keyword tags.
    3. Generate JPEG thumbnail and forward to Main DB server (Port 8000).
    """
    try:
        logger.info(f"Received deposit registration request for: {itemName}")
        
        # Step 1: Trigger RDK hardware close/capture sequence
        collected_data_packet = await network_input.handle_android_input(
            category=category, subCategory=subCategory, itemName=itemName,
            foundLocation=foundLocation, detail=detail, foundAt=foundAt, image=image
        )

        # Step 2: Run local VLM Multimodal Inference to extract features
        vlm_analysis_output_tags = vlm_server.run_mlx_vlm_inference(collected_data_packet)
        logger.info(f"VLM tag extraction completed: {vlm_analysis_output_tags}")

        # Step 3: Resize image and forward payload to Main Database Server
        is_success = network_output.process_and_forward_to_main_db(
            data_packet=collected_data_packet,
            vlm_keywords=vlm_analysis_output_tags
        )

        if is_success:
            return {
                "status": "success",
                "message": "Data processed by VLM and forwarded to the main server successfully."
            }
        else:
            logger.error("Main DB forwarding rejected.")
            return {
                "status": "error",
                "message": "VLM analysis completed, but the main database server rejected forwarding."
            }

    except Exception as pipeline_err:
        logger.error(f"VLM coordination pipeline failed: {str(pipeline_err)}", exc_info=True)
        return {"status": "error", "message": f"Pipeline execution failed: {str(pipeline_err)}"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)