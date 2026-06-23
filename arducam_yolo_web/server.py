"""
Flask-based web server exposing a BPU YOLO detection stream.

Endpoints
---------
  GET /                 — single-page viewer (static/index.html)
  GET /video_feed       — MJPEG stream at STREAM_FPS
  GET /api/stats        — JSON: pipeline stats (FPS, thresholds, ...)
  GET /api/detections   — JSON: latest detection list
  GET /api/snapshot     — single JPEG frame
"""

import logging
import time

from flask import Flask, Response, jsonify, send_from_directory

from . import config
from .pipeline import DetectionPipeline

log = logging.getLogger("arducam_yolo_web")


def _create_app() -> Flask:
    static_dir = config.STATIC_DIR
    app = Flask(__name__, static_folder=static_dir, static_url_path="/static")
    pipeline = DetectionPipeline()
    pipeline.start()

    # ----------------------------------------------------------------- views
    @app.route("/")
    def index():
        return send_from_directory(static_dir, "index.html")

    @app.route("/healthz")
    def healthz():
        return jsonify({"ok": True, "ts": time.time()})

    # ------------------------------------------------------------ streaming
    MJPEG_BOUNDARY = b"--frame"

    @app.route("/video_feed")
    def video_feed():
        boundary = MJPEG_BOUNDARY

        def generate():
            last_frame_id = -1
            while True:
                sample = pipeline.get_jpeg_sample()
                if sample is None or sample.frame_id == last_frame_id:
                    time.sleep(0.002)
                    continue
                last_frame_id = sample.frame_id
                jpeg = sample.jpeg
                yield (boundary + b"\r\n"
                       b"Content-Type: image/jpeg\r\n"
                       b"Cache-Control: no-store, no-cache, must-revalidate, max-age=0\r\n"
                       b"Pragma: no-cache\r\n"
                       b"Content-Length: " + str(len(jpeg)).encode() + b"\r\n\r\n"
                       + jpeg + b"\r\n")

        return Response(
            generate(),
            mimetype="multipart/x-mixed-replace; boundary=frame",
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "X-Accel-Buffering": "no",
            },
            direct_passthrough=True,
        )

    @app.route("/api/snapshot")
    def snapshot():
        jpeg = pipeline.get_jpeg()
        if jpeg is None:
            return Response(status=503, response=b"no frame yet")
        # Trigger the complete visual feedback (Blue LEDs)
        pipeline.trigger_complete()
        return Response(jpeg, mimetype="image/jpeg")

    @app.route("/api/request")
    def request_scan():
        jpeg = pipeline.run_scan_sequence()
        if jpeg is None:
            return Response(status=500, response=b"Failed to capture frame in scan sequence")
        return Response(jpeg, mimetype="image/jpeg")

    @app.route("/api/return")
    def request_return():
        success = pipeline.run_return_sequence()
        if not success:
            return jsonify({"ok": False, "error": "Failed to run return sequence"}), 500
        return jsonify({"ok": True, "status": "door_opened", "led": "blue"})

    @app.route("/api/door/open")
    def door_open():
        success = pipeline.set_door_state(True)
        if not success:
            return jsonify({"ok": False, "error": "Failed to open door"}), 500
        return jsonify({"ok": True, "status": "open"})

    @app.route("/api/door/close")
    def door_close():
        success = pipeline.run_close_sequence()
        if not success:
            return jsonify({"ok": False, "error": "Failed to close door"}), 500
        return jsonify({"ok": True, "status": "closed"})

    @app.route("/api/door/angle/<int:angle>")
    def door_angle(angle):
        if angle < 0 or angle > 180:
            return jsonify({"ok": False, "error": "Angle must be between 0 and 180"}), 400
        success = pipeline.set_door_angle(angle)
        if not success:
            return jsonify({"ok": False, "error": "Failed to set door angle"}), 500
        return jsonify({"ok": True, "angle": angle})

    @app.route("/api/stats")
    def stats():
        return jsonify(pipeline.stats())

    @app.route("/api/detections")
    def detections():
        return jsonify({
            "ts": time.time(),
            "detections": pipeline.get_detections(),
            "stats": pipeline.stats(),
        })

    # Attach the pipeline so external code (e.g. tests) can grab it.
    app.pipeline = pipeline  # type: ignore[attr-defined]
    return app


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    log.info("Arducam BPU YOLO web server starting on %s:%d",
             config.HTTP_HOST, config.HTTP_PORT)
    app = _create_app()
    try:
        # threaded=True so multiple MJPEG clients don't block each other.
        app.run(host=config.HTTP_HOST, port=config.HTTP_PORT,
                threaded=True, debug=False, use_reloader=False)
    finally:
        app.pipeline.stop()


if __name__ == "__main__":
    main()
