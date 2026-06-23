"""
BPU YOLOv8 detection pipeline for the Arducam USB webcam.

Three concurrent threads keep the latency low and the frame rate steady:
  1. capture    — V4L2 grabber, reads frames synchronously at hardware FPS, saving reference to the latest.
  2. worker     — runs BPU YOLOv8 inference using fast reference swapping, coordinates LEDs, and encodes JPEGs.
  3. (caller)   — Flask handlers read the latest JPEG + detection list.

Optimized to minimize Lock Contention and eliminate blocking grab() delays.
"""

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass

import cv2
import numpy as np

try:
    import hbm_runtime
    HAS_BPU = True
except ImportError:
    HAS_BPU = False

from . import config
from .led_controller import ScannerLEDController, LightState
from .motor import ServoMotorController
from .utils.preprocess import bgr_to_nv12_planes, resized_image
from .utils.postprocess import postprocess
from .utils.viz import draw_boxes

log = logging.getLogger("arducam_yolo_web")


# ---------------------------------------------------------------------------
# Detection record (lightweight, JSON-serializable)
# ---------------------------------------------------------------------------
@dataclass
class Detection:
    cls_id: int
    cls_name: str
    score: float
    x1: float
    y1: float
    x2: float
    y2: float

    def to_dict(self) -> dict:
        return {
            "class_id": int(self.cls_id),
            "class_name": self.cls_name,
            "score": round(float(self.score), 4),
            "bbox": [round(float(self.x1), 1), round(float(self.y1), 1),
                     round(float(self.x2), 1), round(float(self.y2), 1)],
        }


@dataclass(frozen=True)
class FrameSample:
    frame_id: int
    frame: np.ndarray
    captured_at: float


@dataclass(frozen=True)
class JPEGSample:
    frame_id: int
    jpeg: bytes
    published_at: float


# ---------------------------------------------------------------------------
# Camera capture thread
# ---------------------------------------------------------------------------
class WebcamSource:
    """Owns the OpenCV VideoCapture and keeps only the newest frame reference.

    Runs in a dedicated thread locked to camera hardware FPS without artificial sleep or grab delays.
    """

    def __init__(self, device: str, width: int, height: int,
                 fps: int, fourcc: str = "MJPG"):
        self.device = device
        self.width = width
        self.height = height
        self.fps = fps
        self.fourcc = fourcc
        self.cap: cv2.VideoCapture | None = None
        self.latest: np.ndarray | None = None
        self.latest_id: int = 0
        self.latest_captured_at: float = 0.0
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.actual_fps: float = 0.0
        self._read_ms: deque[float] = deque(maxlen=60)
        self.is_mock_cam = False

    def open(self) -> None:
        self.is_mock_cam = False
        log.info("Opening camera %s @ %dx%d %d fps (%s)",
                 self.device, self.width, self.height, self.fps, self.fourcc)
        
        device_arg = self.device
        if isinstance(device_arg, str):
            if device_arg.startswith("/dev/video"):
                try:
                    device_arg = int(device_arg[len("/dev/video"):])
                except ValueError:
                    pass
            elif device_arg.isdigit():
                device_arg = int(device_arg)

        try:
            cap = cv2.VideoCapture(device_arg, cv2.CAP_V4L2) if hasattr(cv2, 'CAP_V4L2') else cv2.VideoCapture(device_arg)
            if not cap.isOpened():
                cap = cv2.VideoCapture(device_arg)
            if not cap.isOpened() and isinstance(device_arg, str) and not device_arg.isdigit():
                cap = cv2.VideoCapture(0)
                
            if not cap.isOpened():
                raise RuntimeError("OpenCV VideoCapture failed to open.")
                
            self.cap = cap
            log.info("Camera opened successfully.")
        except Exception as e:
            log.warning("PHYSICAL WEBCAM INITIALIZATION FAILED: %s", e)
            log.warning("Falling back to Virtual Mock Camera (Dummy image loop).")
            log.warning("Allows visual/functional testing without camera device permissions.")
            self.is_mock_cam = True
            self.cap = None

        if not self.is_mock_cam and self.cap is not None:
            if sys_platform := getattr(cv2, 'CAP_PROP_FOURCC', None):
                try:
                    self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*self.fourcc))
                    self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                    self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                    self.cap.set(cv2.CAP_PROP_FPS, self.fps)
                    self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                except Exception as ex:
                    log.warning("Failed setting V4L2 capture properties: %s", ex)
            log.info("Physical camera configuration finished.")

    def _loop(self) -> None:
        last = time.monotonic()
        frames = 0
        while not self.stop_event.is_set():
            t0 = time.perf_counter()
            
            if self.is_mock_cam:
                frame = np.zeros((self.height, self.width, 3), dtype=np.uint8)
                for x in range(0, self.width, 40):
                    cv2.line(frame, (x, 0), (x, self.height), (30, 30, 30), 1)
                for y in range(0, self.height, 40):
                    cv2.line(frame, (0, y), (self.width, y), (30, 30, 30), 1)
                
                cv2.putText(frame, f"MOCK WEBCAM - {time.strftime('%X')}", (30, self.height // 2 - 20),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (240, 240, 240), 2)
                
                time.sleep(1.0 / self.fps)
                ok = True
            else:
                # Synchronous read blocked by camera sensor hardware clock (e.g. 33.3ms)
                # No blocking grab() loops here to prevent cumulative frame skipping.
                ok, frame = self.cap.read()

            self._read_ms.append((time.perf_counter() - t0) * 1000.0)
            if not ok or frame is None:
                time.sleep(0.005)
                continue
                
            # Quick reference swap to minimize thread lock hold time (under 1us)
            with self.lock:
                self.latest = frame
                self.latest_id += 1
                self.latest_captured_at = time.perf_counter()
                
            frames += 1
            now = time.monotonic()
            if now - last >= 1.0:
                self.actual_fps = frames / (now - last)
                frames = 0
                last = now

    def start(self) -> None:
        self.open()
        self.thread = threading.Thread(target=self._loop, name="capture", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=2.0)
        if self.cap is not None:
            self.cap.release()

    def get_latest(self) -> FrameSample | None:
        """Returns the latest frame reference directly to eliminate CPU overhead."""
        with self.lock:
            if self.latest is None:
                return None
            return FrameSample(self.latest_id, self.latest, self.latest_captured_at)

    def flush_frames(self) -> None:
        """Clear the latest frame buffer so the pipeline waits for a fresh frame."""
        with self.lock:
            self.latest = None

    def read_ms_avg(self) -> float:
        return (sum(self._read_ms) / len(self._read_ms)) if self._read_ms else 0.0


# ---------------------------------------------------------------------------
# BPU YOLO detector — wraps the heavy hbm_runtime model
# ---------------------------------------------------------------------------
class BPUYOLODetector:
    """Thin wrapper around ``hbm_runtime.HB_HBMRuntime`` for YOLOv8."""

    def __init__(self, model_path: str, class_names: list,
                 bpu_cores: list[int], priority: int,
                 score_thres: float, nms_thres: float,
                 resize_type: int = 0):
        self.class_names = class_names
        self.classes_num = len(class_names)
        self.score_thres = score_thres
        self.nms_thres = nms_thres
        self.resize_type = resize_type
        
        self.input_h = 640
        self.input_w = 640

        if not HAS_BPU:
            log.warning("BPU RUNTIME (hbm_runtime) IS MISSING.")
            log.warning("Detector will run in MOCK BYPASS mode (no actual inference).")
            log.warning("Allows visual/functional testing without camera device permissions on host OS.")
            return

        log.info("Loading BPU model: %s", model_path)
        self.model = hbm_runtime.HB_HBMRuntime(model_path)
        self.model_name = self.model.model_names[0]
        self.input_names = self.model.input_names[self.model_name]
        self.output_names = self.model.output_names[self.model_name]
        self.input_shapes = self.model.input_shapes[self.model_name]
        self.output_quants = self.model.output_quants[self.model_name]
        self.input_h, self.input_w = (
            self.input_shapes[self.input_names[0]][2],
            self.input_shapes[self.input_names[0]][3],
        )

        if bpu_cores or priority:
            self.model.set_scheduling_params(
                priority={self.model_name: priority} if priority is not None else None,
                bpu_cores={self.model_name: bpu_cores} if bpu_cores else None,
            )
        log.info("BPU ready: input=%dx%d, classes=%d",
                 self.input_w, self.input_h, self.classes_num)

    def infer(self, frame_bgr: np.ndarray):
        """Run BPU YOLOv8 on a BGR frame and return (xyxy, cls, score)."""
        if not HAS_BPU:
            img_h, img_w = frame_bgr.shape[:2]
            if int(time.time()) % 8 in [1, 2, 3]: 
                mock_boxes = np.array([[img_w * 0.25, img_h * 0.25, img_w * 0.75, img_h * 0.75]], dtype=np.float32)
                mock_cls = np.array([0], dtype=np.int32)
                mock_score = np.array([0.88], dtype=np.float32)
                return mock_boxes, mock_cls, mock_score
            return np.empty((0, 4), dtype=np.float32), np.empty((0,), dtype=np.int32), np.empty((0,), dtype=np.float32)

        img_h, img_w = frame_bgr.shape[:2]
        resized = resized_image(frame_bgr, self.input_w, self.input_h, self.resize_type)
        y, uv = bgr_to_nv12_planes(resized)
        nv12 = np.concatenate((y.reshape(-1), uv.reshape(-1)), axis=0)
        nv12 = nv12.reshape((1, self.input_h * 3 // 2, self.input_w, 1))

        outputs = self.model.run({self.model_name: {self.input_names[0]: nv12}})
        outputs = outputs[self.model_name]
        return postprocess(
            outputs, self.output_quants, self.output_names,
            img_w, img_h, self.input_w, self.input_h, self.resize_type,
            self.score_thres, self.nms_thres, self.classes_num,
        )


# ---------------------------------------------------------------------------
# Top-level pipeline
# ---------------------------------------------------------------------------
class DetectionPipeline:
    """Manages thread-safe interaction between Flask handlers and camera/worker threads."""

    def __init__(self):
        self.class_names = self._load_classes(config.CLASSES_PATH)
        self.detector = BPUYOLODetector(
            model_path=config.MODEL_PATH,
            class_names=self.class_names,
            bpu_cores=config.BPU_CORES,
            priority=config.BPU_PRIORITY,
            score_thres=config.SCORE_THRESHOLD,
            nms_thres=config.NMS_THRESHOLD,
            resize_type=0,  # direct resize
        )
        self.camera = WebcamSource(
            device=config.CAMERA_DEVICE,
            width=config.CAMERA_WIDTH, height=config.CAMERA_HEIGHT,
            fps=config.CAMERA_FPS, fourcc=config.CAMERA_FOURCC,
        )
        
        # Hardware SPI LED Controller
        self.led_controller = ScannerLEDController(
            bus=config.SPI_BUS,
            device=config.SPI_DEVICE,
            num_leds=config.LED_COUNT,
            speed_hz=config.SPI_SPEED_HZ,
        )
        self.led_controller.set_state(LightState.READY)

        # Hardware PWM Motor Controller
        self.motor_controller = ServoMotorController()
        self.motor_controller.set_angle(config.MOTOR_STOP_ANGLE)

        self._jpeg_lock = threading.Lock()
        self._det_lock = threading.Lock()
        self.latest_jpeg: bytes | None = None
        self.latest_jpeg_id: int = 0
        self.latest_jpeg_published_at: float = 0.0
        self.latest_detections: list[Detection] = []
        self.worker_thread: threading.Thread | None = None
        self.stop_event = threading.Event()

        self.last_detection_time = 0.0
        self.is_sequence_active = False
        self._last_processed_frame_id = 0
        self._exposure_ready_at = 0.0
        
        # Auto-closing logic state
        self.scanning_start_time = None
        self.is_auto_closing = False
        self.is_door_open = True
        self._skip_detection_until = 0.0

        # Rolling statistics (ms)
        self._bpu_ms: deque[float] = deque(maxlen=30)
        self._post_ms: deque[float] = deque(maxlen=30)
        self._draw_ms: deque[float] = deque(maxlen=30)
        self._enc_ms: deque[float] = deque(maxlen=30)
        self._total_ms: deque[float] = deque(maxlen=30)
        self._capture_to_publish_ms: deque[float] = deque(maxlen=30)

    @staticmethod
    def _load_classes(path: str) -> list:
        try:
            with open(path) as f:
                names = [line.strip() for line in f if line.strip()]
        except FileNotFoundError:
            log.warning("COCO Classes names file not found. Generating default names.")
            names = [f"Class {i}" for i in range(80)]
            names[0] = "person"
            
        if len(names) != 80:
            log.warning("Expected 80 COCO classes, got %d", len(names))
        return names

    def trigger_complete(self) -> None:
        """Trigger visual feedback for snapshot complete (Pulse Blue)."""
        self.led_controller.set_state(LightState.COMPLETE)

        def reset_timer():
            time.sleep(1.0)
            with self.led_controller.lock:
                if self.led_controller.current_state == LightState.COMPLETE:
                    self.led_controller.set_state(LightState.READY)

        threading.Thread(target=reset_timer, name="led-reset-timer", daemon=True).start()

    def run_scan_sequence(self) -> bytes | None:
        """Execute the simplified scan sequence since the door is already closed:
        1. Turn LED to SCANNING (White) for final photo.
        2. Wait for exposure stabilization (LED_STABILIZE_SECONDS).
        3. Capture a fresh frame, run YOLO detection, draw boxes, encode to JPEG, and return.
        """
        self.is_sequence_active = True
        log.info("[Sequence] Starting simplified scan sequence since door is already closed.")
        
        try:
            # 1. Turn LED to SCANNING (White)
            log.info("[Sequence] Setting LED to SCANNING (White) for final photo")
            self.led_controller.set_state(LightState.SCANNING)
            
            # 2. Wait for exposure stabilization
            if config.LED_STABILIZE_SECONDS > 0:
                time.sleep(config.LED_STABILIZE_SECONDS)
            self.camera.flush_frames()
            
            # 3. Capture a fresh frame
            sample = None
            for _ in range(60):  # Wait up to 300ms
                sample = self.camera.get_latest()
                if sample is not None:
                    break
                time.sleep(0.005)
                
            if sample is None:
                log.error("[Sequence] Timeout waiting for fresh camera frame for final photo.")
                return None
                
            frame = sample.frame
            
            # Inference on final frame
            xyxy, cls, score = self.detector.infer(frame)
            detections = [
                Detection(
                    cls_id=int(c), cls_name=self.class_names[int(c)],
                    score=float(s),
                    x1=float(b[0]), y1=float(b[1]),
                    x2=float(b[2]), y2=float(b[3]),
                )
                for c, s, b in zip(cls, score, xyxy)
            ]
            
            with self._det_lock:
                self.latest_detections = detections
                
            vis = frame if not detections else draw_boxes(
                frame.copy(), xyxy, cls, score, self.class_names,
            )
            
            encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), config.JPEG_QUALITY]
            ok, buf = cv2.imencode(".jpg", vis, encode_params)
            if not ok:
                return None
                
            jpeg_bytes = buf.tobytes()
            
            with self._jpeg_lock:
                self.latest_jpeg = jpeg_bytes
                self.latest_jpeg_id = sample.frame_id
                self.latest_jpeg_published_at = time.perf_counter()
            self._capture_to_publish_ms.append(
                (time.perf_counter() - sample.captured_at) * 1000.0
            )
            
            # Reset LED back to READY (Green)
            self.led_controller.set_state(LightState.READY)
            return jpeg_bytes
            
        finally:
            self.is_sequence_active = False

    # --- worker thread ------------------------------------------------------
    def _worker_loop(self) -> None:
        encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), config.JPEG_QUALITY]
        last_inference_time = 0.0
        inference_interval = 1.0 / config.INFERENCE_FPS if config.INFERENCE_FPS > 0 else 0.0
        
        while not self.stop_event.is_set():
            if self.is_sequence_active or self.is_auto_closing:
                time.sleep(0.01)
                continue

            sample = self.camera.get_latest()
            if sample is None:
                time.sleep(0.005)
                continue
            if time.monotonic() < self._exposure_ready_at:
                time.sleep(0.001)
                continue
            if sample.frame_id == self._last_processed_frame_id:
                time.sleep(0.001)
                continue

            # Limit inference rate to prevent CPU/BPU overloading & overheating
            now_time = time.monotonic()
            if now_time - last_inference_time < inference_interval:
                time.sleep(0.005)
                continue

            frame = sample.frame
            self._last_processed_frame_id = sample.frame_id
            last_inference_time = now_time
            t_total = time.perf_counter()

            # --- BPU Inference ---------------------------------------------
            t_bpu = time.perf_counter()
            try:
                # We pass the read-only frame reference directly to BPU to save memory copy overhead
                if time.monotonic() < self._skip_detection_until:
                    xyxy, cls, score = (
                        np.empty((0, 4), dtype=np.float32),
                        np.empty((0,), dtype=np.int32),
                        np.empty((0,), dtype=np.float32)
                    )
                else:
                    xyxy, cls, score = self.detector.infer(frame)
            except Exception:
                log.exception("BPU inference failed")
                continue
            self._bpu_ms.append((time.perf_counter() - t_bpu) * 1000.0)

            # --- Parse Detections -------------------------------------------
            t_post = time.perf_counter()
            detections = [
                Detection(
                    cls_id=int(c), cls_name=self.class_names[int(c)],
                    score=float(s),
                    x1=float(b[0]), y1=float(b[1]),
                    x2=float(b[2]), y2=float(b[3]),
                )
                for c, s, b in zip(cls, score, xyxy)
            ]
            self._post_ms.append((time.perf_counter() - t_post) * 1000.0)

            # --- State-Driven Lighting logic (with Hysteresis) --------------
            now_time = time.monotonic()
            if len(detections) > 0 and self.is_door_open:
                self.last_detection_time = now_time
                state_changed = self.led_controller.set_state(LightState.SCANNING)
                
                # Door auto-closing based on YOLO detection is disabled to prevent safety issues.
                # The door is now explicitly closed via external control requests from the VLM coordinator.
                if state_changed and config.LED_STABILIZE_SECONDS > 0:
                    log.info(
                        "[Exposure Control] LED scanning activated; exposure settle configured at %.3fs.",
                        config.LED_STABILIZE_SECONDS,
                    )
                    self.camera.flush_frames()
                    self._exposure_ready_at = now_time + config.LED_STABILIZE_SECONDS
            else:
                if self.led_controller.current_state != LightState.COMPLETE:
                    if now_time - self.last_detection_time > 1.5:
                        if self.led_controller.set_state(LightState.READY):
                            self.scanning_start_time = None

            # --- Drawing --------------------------------------------------
            t_draw = time.perf_counter()
            # Draw boxes on a copy to avoid corrupting the camera thread reference
            vis = frame if not detections else draw_boxes(
                frame.copy(), xyxy, cls, score, self.class_names,
            )
            self._draw_ms.append((time.perf_counter() - t_draw) * 1000.0)

            # --- JPEG encode ---------------------------------------------
            t_enc = time.perf_counter()
            ok, buf = cv2.imencode(".jpg", vis, encode_params)
            if not ok:
                continue
            jpeg_bytes = buf.tobytes()
            self._enc_ms.append((time.perf_counter() - t_enc) * 1000.0)

            # --- Publish latest -------------------------------------------
            with self._jpeg_lock:
                self.latest_jpeg = jpeg_bytes
                self.latest_jpeg_id = sample.frame_id
                self.latest_jpeg_published_at = time.perf_counter()
            with self._det_lock:
                self.latest_detections = detections

            self._total_ms.append((time.perf_counter() - t_total) * 1000.0)
            self._capture_to_publish_ms.append(
                (time.perf_counter() - sample.captured_at) * 1000.0
            )

    # --- public API ---------------------------------------------------------
    def start(self) -> None:
        self.camera.start()
        self.worker_thread = threading.Thread(
            target=self._worker_loop, name="yolo-worker", daemon=True)
        self.worker_thread.start()
        log.info("Pipeline started — stream @ %d fps target", config.STREAM_FPS)

    def stop(self) -> None:
        self.stop_event.set()
        if self.worker_thread is not None:
            self.worker_thread.join(timeout=2.0)
        self.camera.stop()
        self.led_controller.close()
        self.motor_controller.close()

    def get_jpeg(self) -> bytes | None:
        with self._jpeg_lock:
            return self.latest_jpeg

    def get_jpeg_sample(self) -> JPEGSample | None:
        with self._jpeg_lock:
            if self.latest_jpeg is None:
                return None
            return JPEGSample(
                self.latest_jpeg_id,
                self.latest_jpeg,
                self.latest_jpeg_published_at,
            )

    def get_detections(self) -> list[dict]:
        with self._det_lock:
            return [d.to_dict() for d in self.latest_detections]

    def run_return_sequence(self) -> bool:
        """Execute the return sequence: open door and light LED in blue."""
        log.info("[Sequence] Starting return sequence.")
        try:
            # 1. Open door
            log.info("[Sequence] Opening door for return")
            self.set_door_state(True)
            
            # 2. Set LED to COMPLETE (Blue)
            log.info("[Sequence] Setting LED to COMPLETE (Blue) for return")
            self.led_controller.set_state(LightState.COMPLETE)
            
            # 3. Reset LED to READY (Green) after 5 seconds to await next deposit
            def reset_led_to_green():
                time.sleep(5.0)
                if self.led_controller.current_state == LightState.COMPLETE:
                    log.info("[Sequence] Return complete. Resetting LED to READY (Green) for next deposit.")
                    self.led_controller.set_state(LightState.READY)
                        
            threading.Thread(target=reset_led_to_green, name="return-reset-timer", daemon=True).start()
            return True
        except Exception as e:
            log.error("[Sequence] Failed to execute return sequence: %s", e)
            return False

    def run_close_sequence(self) -> bool:
        """Execute the door close sequence with visual feedback:
        1. Set LED to COMPLETE (Blue)
        2. Close door
        3. Reset LED to READY (Green) after 2 seconds in a background thread
        """
        log.info("[Sequence] Starting close sequence.")
        try:
            # 1. Set LED to COMPLETE (Blue)
            log.info("[Sequence] Setting LED to COMPLETE (Blue) for door closing")
            self.led_controller.set_state(LightState.COMPLETE)
            
            # 2. Close door
            log.info("[Sequence] Closing door")
            self.set_door_state(False)
            
            # 3. Reset LED to READY (Green) after 2 seconds
            def reset_led_to_green():
                time.sleep(2.0)
                if self.led_controller.current_state == LightState.COMPLETE:
                    log.info("[Sequence] Door closed and settled. Resetting LED to READY (Green).")
                    self.led_controller.set_state(LightState.READY)
                        
            threading.Thread(target=reset_led_to_green, name="close-reset-timer", daemon=True).start()
            return True
        except Exception as e:
            log.error("[Sequence] Failed to execute close sequence: %s", e)
            return False

    def set_door_state(self, open_state: bool) -> bool:
        """Set the door motor state directly (True for open, False for closed).
        Runs the continuous rotation servo CW or CCW for config.MOTOR_OPEN/CLOSE_DURATION_SECONDS
        and then stops it (by setting config.MOTOR_STOP_ANGLE).
        """
        try:
            dir_angle = config.MOTOR_OPEN_DIR_ANGLE if open_state else config.MOTOR_CLOSE_DIR_ANGLE
            duration = config.MOTOR_OPEN_DURATION_SECONDS if open_state else config.MOTOR_CLOSE_DURATION_SECONDS
            log.info("[Manual Control] Rotating motor for door %s (angle: %s for %s seconds)",
                     "OPEN" if open_state else "CLOSE", dir_angle, duration)
            self.motor_controller.set_angle(dir_angle)
            time.sleep(duration)
            log.info("[Manual Control] Stopping motor (angle: %s)", config.MOTOR_STOP_ANGLE)
            self.motor_controller.set_angle(config.MOTOR_STOP_ANGLE)
            self.is_door_open = open_state
            if open_state:
                self._skip_detection_until = time.monotonic() + 10.0
                log.info("[Automation] Door opened. Pausing object detection for 10.0 seconds.")
            return True
        except Exception as e:
            log.error("[Manual Control] Failed to set door state: %s", e)
            return False

    def set_door_angle(self, angle: float) -> bool:
        """Set the door motor angle directly."""
        try:
            log.info("[Manual Control] Setting door angle directly to %.1f degrees", angle)
            self.motor_controller.set_angle(angle)
            return True
        except Exception as e:
            log.error("[Manual Control] Failed to set door angle: %s", e)
            return False

    @staticmethod
    def _avg(buf) -> float:
        return (sum(buf) / len(buf)) if buf else 0.0

    def stats(self) -> dict:
        bpu = self._avg(self._bpu_ms)
        post = self._avg(self._post_ms)
        draw = self._avg(self._draw_ms)
        enc = self._avg(self._enc_ms)
        total = self._avg(self._total_ms)
        capture_to_publish = self._avg(self._capture_to_publish_ms)
        est_fps = (1000.0 / total) if total > 0 else 0.0
        return {
            "model": config.MODEL_PATH,
            "camera": config.CAMERA_DEVICE,
            "camera_fps": round(self.camera.actual_fps, 2),
            "camera_read_ms": round(self.camera.read_ms_avg(), 2),
            "bpu_infer_ms": round(bpu, 2),
            "build_det_ms": round(post, 2),
            "draw_ms": round(draw, 2),
            "encode_ms": round(enc, 2),
            "worker_total_ms": round(total, 2),
            "capture_to_publish_ms": round(capture_to_publish, 2),
            "inference_fps": round(est_fps, 2),
            "inference_ms": round(total, 2),
            "stream_fps": config.STREAM_FPS,
            "jpeg_quality": config.JPEG_QUALITY,
            "score_threshold": config.SCORE_THRESHOLD,
            "nms_threshold": config.NMS_THRESHOLD,
            "image_size": [config.CAMERA_WIDTH, config.CAMERA_HEIGHT],
            "input_size": [self.detector.input_w, self.detector.input_h],
            "detection_count": len(self.get_detections()),
            "led_state": self.led_controller.current_state.name if self.led_controller.current_state else "UNKNOWN",
            "led_is_mock": self.led_controller.is_mock,
            "is_sequence_active": self.is_sequence_active,
            "is_door_open": self.is_door_open
        }
