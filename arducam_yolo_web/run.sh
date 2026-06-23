#!/bin/bash
# Arducam USB + BPU YOLO web streamer — launcher.
#
# Usage:
#   ./run.sh                    # start on 0.0.0.0:8000 with defaults
#   HTTP_PORT=9000 ./run.sh     # override port
#   CAMERA_DEVICE=/dev/video1 ./run.sh
set -euo pipefail

cd "$(dirname "$0")"

PY="${PYTHON:-python3}"

if ! "$PY" -c "import flask, cv2, numpy, scipy, hbm_runtime" 2>/dev/null; then
  echo "[run.sh] installing missing Python dependencies..."
  "$PY" -m pip install --no-cache-dir -r requirements.txt
fi

PYTHONPATH="..:${PYTHONPATH:-}" exec "$PY" -m arducam_yolo_web.server
