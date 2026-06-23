"""
Arducam USB Webcam + BPU YOLO Web Streamer — Configuration

All tunables for the RDK X5 BPU YOLO web streaming pipeline.
Edit values here instead of touching the runtime code.
"""

import os

# --- Project paths ------------------------------------------------------------
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(PROJECT_ROOT, "static")

# --- Camera -------------------------------------------------------------------
# V4L2 device node. Most Arducam USB webcams enumerate as /dev/video0.
# Use `v4l2-ctl --list-devices` to confirm.
CAMERA_DEVICE = os.environ.get("CAMERA_DEVICE", "/dev/video0")

# Capture width/height in pixels. The Arducam USB cam supports MJPG at
# 640x480, 800x600, 1280x720, 1920x1080 @ 30fps. 640x480 is the sweet spot
# for 30 FPS end-to-end: small enough for fast JPEG encoding, big enough for
# readable detections.
CAMERA_WIDTH = int(os.environ.get("CAMERA_WIDTH", "640"))
CAMERA_HEIGHT = int(os.environ.get("CAMERA_HEIGHT", "480"))
CAMERA_FPS = int(os.environ.get("CAMERA_FPS", "30"))
# MJPG is the only format the Arducam exposes at 30 FPS for 640x480.
CAMERA_FOURCC = os.environ.get("CAMERA_FOURCC", "MJPG")

# --- BPU YOLO model -----------------------------------------------------------
# Path to a D-Robotics BPU-compiled YOLOv8 .bin model.
# The system ships several; yolov8n is extremely lightweight and easily reaches
# 30+ FPS end-to-end.
MODEL_PATH = os.environ.get(
    "MODEL_PATH",
    "/app/pydev_demo/models/yolov8_640x640_nv12.bin",
)

# COCO class names. Must have 80 lines, one per class.
CLASSES_PATH = os.environ.get(
    "CLASSES_PATH",
    os.path.join(PROJECT_ROOT, "coco_classes.names"),
)

# --- Inference / visualization ----------------------------------------------
# Confidence threshold for emitting a detection.
SCORE_THRESHOLD = float(os.environ.get("SCORE_THRESHOLD", "0.25"))
# IoU threshold for NMS.
NMS_THRESHOLD = float(os.environ.get("NMS_THRESHOLD", "0.45"))
# Target BPU YOLO inference FPS. Lowering this reduces CPU/BPU load and prevents overheating.
INFERENCE_FPS = float(os.environ.get("INFERENCE_FPS", "10.0"))

# --- Web server ---------------------------------------------------------------
# Bind address. 0.0.0.0 listens on every interface (incl. USB/RNDIS at
# 192.168.128.10 on the RDK X5 dev image).
HTTP_HOST = os.environ.get("HTTP_HOST", "0.0.0.0")
HTTP_PORT = int(os.environ.get("HTTP_PORT", "8000"))

# MJPEG streaming target rate. With a fast BPU and 640x480 capture this
# easily clears 30 FPS. Lower if the network or clients struggle.
STREAM_FPS = int(os.environ.get("STREAM_FPS", "30"))
JPEG_QUALITY = int(os.environ.get("JPEG_QUALITY", "75"))

# When LEDs switch on, camera auto-exposure can take a moment to settle.
# Keep this at 0 for lowest live latency; increase only if captures are unstable.
LED_STABILIZE_SECONDS = float(os.environ.get("LED_STABILIZE_SECONDS", "0"))

# Optional wait before /api/request captures a still frame. Keep at 0 for a
# responsive trigger; set to 5 to restore the old countdown-like behavior.
SCAN_READY_SECONDS = float(os.environ.get("SCAN_READY_SECONDS", "0"))

# BPU core to bind. X5 exposes 1 BPU core; valid value: [0].
BPU_CORES = [0]
# Inference priority. 0..255. Default 0 is fine; bump if the system is busy.
BPU_PRIORITY = 0

# --- Hardware WS2812B LED & SPI Configuration ---------------------------------
SPI_BUS = int(os.environ.get("SPI_BUS", "1"))
SPI_DEVICE = int(os.environ.get("SPI_DEVICE", "0"))
LED_COUNT = int(os.environ.get("LED_COUNT", "12"))
SPI_SPEED_HZ = int(os.environ.get("SPI_SPEED_HZ", "6400000"))

# --- Hardware PWM Servo Motor Configuration ----------------------------------
MOTOR_OPEN_DIR_ANGLE = float(os.environ.get("MOTOR_OPEN_DIR_ANGLE", "0.0"))
MOTOR_CLOSE_DIR_ANGLE = float(os.environ.get("MOTOR_CLOSE_DIR_ANGLE", "180.0"))
MOTOR_STOP_ANGLE = float(os.environ.get("MOTOR_STOP_ANGLE", "90.0"))
MOTOR_OPEN_DURATION_SECONDS = float(os.environ.get("MOTOR_OPEN_DURATION_SECONDS", "1.2"))
MOTOR_CLOSE_DURATION_SECONDS = float(os.environ.get("MOTOR_CLOSE_DURATION_SECONDS", "1.8"))
SCAN_TIMEOUT_SECONDS = float(os.environ.get("SCAN_TIMEOUT_SECONDS", "15.0"))
