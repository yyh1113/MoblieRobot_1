"""
Preprocessing helpers for the RDK X5 BPU YOLO pipeline.

The D-Robotics BPU expects NV12-formatted, fixed-size inputs. This module
converts BGR (OpenCV) frames to the layout ``HB_HBMRuntime`` consumes.
"""

import cv2
import numpy as np


def bgr_to_nv12_planes(image: np.ndarray) -> tuple:
    """Convert a BGR image to the (Y, UV) plane layout the BPU expects.

    Parameters
    ----------
    image : np.ndarray
        BGR image, shape (H, W, 3), dtype uint8.

    Returns
    -------
    (y, uv) : tuple
        y  : (1, H, W, 1) uint8
        uv : (1, H/2, W/2, 2) uint8
    """
    height, width = image.shape[:2]
    area = height * width

    # I420 = YYYY...UU...VV...;  NV12 swaps the chroma to interleaved UV.
    yuv420p = cv2.cvtColor(image, cv2.COLOR_BGR2YUV_I420)
    yuv420p = yuv420p.reshape((area * 3 // 2,))

    y = yuv420p[:area].reshape((height, width))
    u = yuv420p[area:area + area // 4].reshape((height // 2, width // 2))
    v = yuv420p[area + area // 4:].reshape((height // 2, width // 2))

    uv = np.stack((u, v), axis=-1)

    y = y[np.newaxis, :, :, np.newaxis]
    uv = uv[np.newaxis, :, :, :]
    return y, uv


def resized_image(img: np.ndarray, input_W: int, input_H: int,
                  resize_type: int = 0) -> np.ndarray:
    """Resize an image to the model's input resolution.

    resize_type=0 : direct stretch.  Fast, but distorts aspect ratio.
    resize_type=1 : letterbox padding.  Preserves aspect ratio, better
                     accuracy on non-square inputs.
    """
    if resize_type == 0:
        return cv2.resize(img, (input_W, input_H), interpolation=cv2.INTER_LINEAR)
    if resize_type == 1:
        img_h, img_w = img.shape[:2]
        scale = min(input_H / img_h, input_W / img_w)
        new_w, new_h = int(img_w * scale), int(img_h * scale)
        # Force even dimensions — required by NV12 layout.
        new_w = (new_w // 2) * 2
        new_h = (new_h // 2) * 2
        resized = cv2.resize(img, (new_w, new_h))
        pad_w = input_W - new_w
        pad_h = input_H - new_h
        left, right = pad_w // 2, pad_w - pad_w // 2
        top, bottom = pad_h // 2, pad_h - pad_h // 2
        return cv2.copyMakeBorder(
            resized, top, bottom, left, right,
            borderType=cv2.BORDER_CONSTANT, value=(127, 127, 127),
        )
    raise ValueError(f"resize_type must be 0 or 1, got {resize_type}")
