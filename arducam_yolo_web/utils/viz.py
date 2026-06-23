"""Visualization helpers — bounding box drawing on BGR frames."""

import cv2
import numpy as np

# 20 BGR colors used to color-code classes. Cycling mod len(colors).
RDK_COLORS = [
    (56, 56, 255), (151, 157, 255), (31, 112, 255), (29, 178, 255),
    (49, 210, 207), (10, 249, 72), (23, 204, 146), (134, 219, 61),
    (52, 147, 26), (187, 212, 0), (168, 153, 44), (255, 194, 0),
    (147, 69, 52), (255, 115, 100), (236, 24, 0), (255, 56, 132),
    (133, 0, 82), (255, 56, 203), (200, 149, 255), (199, 55, 255),
]


def draw_boxes(image: np.ndarray, boxes: np.ndarray, cls_ids, scores,
               class_names, colors=RDK_COLORS,
               box_thickness: int = 2, font_scale: float = 0.5) -> np.ndarray:
    """Draw N bounding boxes and class labels on a copy of the image."""
    for box, cls_id, score in zip(boxes, cls_ids, scores):
        x1, y1, x2, y2 = map(int, box)
        color = colors[int(cls_id) % len(colors)]
        label = f"{class_names[int(cls_id)]} {score:.2f}"

        cv2.rectangle(image, (x1, y1), (x2, y2), color, thickness=box_thickness)
        # Filled background for the label so it's readable on any frame.
        (tw, th), baseline = cv2.getTextSize(
            label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, 1)
        cv2.rectangle(image, (x1, max(y1 - th - baseline - 2, 0)),
                      (x1 + tw, y1), color, thickness=-1)
        cv2.putText(image, label, (x1, y1 - baseline - 1),
                    fontFace=cv2.FONT_HERSHEY_SIMPLEX,
                    fontScale=font_scale, color=(0, 0, 0), thickness=1)
    return image
