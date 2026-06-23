"""
Optimized YOLOv8 postprocessing for the D-Robotics BPU.

Implements Dequantize-on-Demand to avoid heavy CPU math on massive output tensors.
Groups quantized tensors, maps threshold to quantization space, filters candidates
first, and dequantizes only active boxes. Safe for both quantized (INT8/INT16)
and unquantized (FP32) BPU output tensors.

Includes top-K candidate partitioning to prevent CPU degradation under noisy/low-light inputs.
"""

import logging
import numpy as np

log = logging.getLogger("arducam_yolo_web")

_logged_shapes = False


def _decode_yolov8_scale_optimized(cls_tensor: np.ndarray, reg_tensor: np.ndarray,
                                   cls_quant, reg_quant, stride: int,
                                   score_thres: float, classes_num: int = 80) -> tuple:
    """Dequantize-on-demand and decode predictions for a single feature scale."""
    global _logged_shapes
    # Remove batch dimension if present
    if cls_tensor.ndim == 4:
        cls_tensor = cls_tensor[0]
    if reg_tensor.ndim == 4:
        reg_tensor = reg_tensor[0]

    h, w, c_num = cls_tensor.shape
    
    # 1. Check if the model outputs are quantized
    cls_quant_type = cls_quant.quant_type
    logit_thres = -np.log(1.0 / max(score_thres, 1e-5) - 1.0)
    
    # Check if tensor is actually integer (quantized) or already float (dequantized by runtime)
    is_cls_quant = (cls_quant_type == 1 and np.issubdtype(cls_tensor.dtype, np.integer))
    
    if not _logged_shapes:
        log.info("[Postprocess Debug] scale=%d: cls shape=%s, dtype=%s, quant_type=%s, is_cls_quant=%s, scale=%s, zp=%s",
                 stride, cls_tensor.shape, cls_tensor.dtype, cls_quant_type, is_cls_quant, 
                 getattr(cls_quant, "scale", None), getattr(cls_quant, "zero_point", None))
        log.info("[Postprocess Debug] scale=%d: reg shape=%s, dtype=%s, quant_type=%s, scale=%s, zp=%s",
                 stride, reg_tensor.shape, reg_tensor.dtype, reg_quant.quant_type, 
                 getattr(reg_quant, "scale", None), getattr(reg_quant, "zero_point", None))
    
    if not is_cls_quant:
        # Unquantized path
        q_thres = logit_thres
        y_idx, x_idx, cls_idx = np.where(cls_tensor > q_thres)
    else:
        # Quantized path: reverse map threshold to quantization space
        cls_scale = cls_quant.scale
        cls_zp = cls_quant.zero_point
        
        if cls_scale.ndim == 0 or cls_scale.size == 1:
            s_val = float(cls_scale)
            z_val = float(cls_zp)
            q_thres = (logit_thres / s_val) + z_val
            y_idx, x_idx, cls_idx = np.where(cls_tensor > q_thres)
        else:
            q_thres = (logit_thres / cls_scale.reshape(-1)) + cls_zp.reshape(-1)
            y_idx, x_idx, cls_idx = np.where(cls_tensor > q_thres)

    if not _logged_shapes:
        log.info("[Postprocess Debug] scale=%d: raw candidate pixel matches (above logit threshold)=%d", stride, y_idx.size)

    if y_idx.size == 0:
        return (np.empty((0, 4), dtype=np.float32),
                np.empty((0,), dtype=np.float32),
                np.empty((0,), dtype=np.int32))

    # [Embedded Performance Optimization: Candidate Limit]
    # Under low-light conditions or camera sensor noise, the number of raw candidate pixels 
    # exceeding the score threshold can explode (e.g. >2000 boxes).
    # Processing heavy exponential math (Softmax) and DFL on all of them degrades latency.
    # We restrict processing to the top 200 candidates with the highest raw logits using fast O(N) partitioning.
    if y_idx.size > 200:
        candidate_logits = cls_tensor[y_idx, x_idx, cls_idx]
        top_k_indices = np.argpartition(candidate_logits, -200)[-200:]
        y_idx = y_idx[top_k_indices]
        x_idx = x_idx[top_k_indices]
        cls_idx = cls_idx[top_k_indices]

    # 2. Dequantize only the filtered candidate elements
    if not is_cls_quant:
        cls_dequant = cls_tensor[y_idx, x_idx, cls_idx].astype(np.float32)
    else:
        cls_scale = cls_quant.scale
        cls_zp = cls_quant.zero_point
        cls_q_selected = cls_tensor[y_idx, x_idx, cls_idx].astype(np.float32)
        if cls_scale.ndim == 0 or cls_scale.size == 1:
            cls_dequant = (cls_q_selected - float(cls_zp)) * float(cls_scale)
        else:
            cls_dequant = (cls_q_selected - cls_zp[cls_idx].astype(np.float32)) * cls_scale[cls_idx]
        
    scores = 1.0 / (1.0 + np.exp(-cls_dequant))
    
    # Precise float filtering
    valid_mask = scores > score_thres
    if not np.any(valid_mask):
        return (np.empty((0, 4), dtype=np.float32),
                np.empty((0,), dtype=np.float32),
                np.empty((0,), dtype=np.int32))

    y_idx = y_idx[valid_mask]
    x_idx = x_idx[valid_mask]
    cls_idx = cls_idx[valid_mask]
    scores = scores[valid_mask]

    # 3. Dequantize only the associated reg/bbox elements
    reg_quant_type = reg_quant.quant_type
    is_reg_quant = (reg_quant_type == 1 and np.issubdtype(reg_tensor.dtype, np.integer))
    if not is_reg_quant:
        reg_dequant = reg_tensor[y_idx, x_idx].astype(np.float32)
    else:
        reg_scale = reg_quant.scale
        reg_zp = reg_quant.zero_point
        reg_q_selected = reg_tensor[y_idx, x_idx].astype(np.float32)
        if reg_scale.ndim == 0 or reg_scale.size == 1:
            reg_dequant = (reg_q_selected - float(reg_zp)) * float(reg_scale)
        else:
            reg_dequant = (reg_q_selected - reg_zp.astype(np.float32)) * reg_scale

    # DFL conversion on valid subsets
    # shape: (num_valid, 4, 16)
    reg_selected = reg_dequant.reshape(-1, 4, 16)
    reg_max = np.max(reg_selected, axis=-1, keepdims=True)
    exp_reg = np.exp(reg_selected - reg_max)
    softmax_reg = exp_reg / np.sum(exp_reg, axis=-1, keepdims=True)
    
    dfl_weights = np.arange(16, dtype=np.float32)
    distances = np.sum(softmax_reg * dfl_weights, axis=-1)
    
    grid_x = x_idx.astype(np.float32)
    grid_y = y_idx.astype(np.float32)
    
    # Bbox coordinates
    x1 = (grid_x - distances[:, 0]) * stride
    y1 = (grid_y - distances[:, 1]) * stride
    x2 = (grid_x + distances[:, 2]) * stride
    y2 = (grid_y + distances[:, 3]) * stride
    
    boxes = np.stack([x1, y1, x2, y2], axis=-1)
    return boxes, scores, cls_idx.astype(np.int32)


def decode_outputs_optimized(outputs: dict, output_quants: dict,
                             score_thres: float, classes_num: int = 80) -> tuple:
    """Group quantized outputs by resolution and decode on-demand."""
    global _logged_shapes
    grouped = {}
    for name, tensor in outputs.items():
        if tensor.ndim == 4:
            h, w, c = tensor.shape[1:4]
        else:
            h, w, c = tensor.shape[0:3]
        
        res = (h, w)
        if res not in grouped:
            grouped[res] = {}
            
        if c == classes_num:
            grouped[res]["cls"] = (name, tensor)
        elif c == 64:
            grouped[res]["reg"] = (name, tensor)

    all_boxes = []
    all_scores = []
    all_classes = []

    # Iterate through resolutions (P3 -> P4 -> P5)
    for (h, w), layers in sorted(grouped.items(), key=lambda x: x[0][0], reverse=True):
        if "cls" not in layers or "reg" not in layers:
            continue
            
        cls_name, cls_tensor = layers["cls"]
        reg_name, reg_tensor = layers["reg"]
        
        cls_quant = output_quants[cls_name]
        reg_quant = output_quants[reg_name]
        
        stride = 640 // h
        
        boxes, scores, classes = _decode_yolov8_scale_optimized(
            cls_tensor, reg_tensor, cls_quant, reg_quant, stride, score_thres, classes_num
        )
        if len(boxes) > 0:
            all_boxes.append(boxes)
            all_scores.append(scores)
            all_classes.append(classes)

    if not all_boxes:
        if not _logged_shapes:
            _logged_shapes = True
        return (np.empty((0, 4), dtype=np.float32),
                np.empty((0,), dtype=np.float32),
                np.empty((0,), dtype=np.int32))

    if not _logged_shapes:
        _logged_shapes = True

    return (np.concatenate(all_boxes, axis=0),
            np.concatenate(all_scores, axis=0),
            np.concatenate(all_classes, axis=0))


# ---------------------------------------------------------------------------
# Filter / NMS / scale-back
# ---------------------------------------------------------------------------
def nms(boxes: np.ndarray, scores: np.ndarray, classes: np.ndarray,
        iou_thresh: float = 0.45) -> list:
    """Vectorized class-wise Non-Maximum Suppression."""
    if boxes.shape[0] == 0:
        return []
    x1 = boxes[:, 0]
    y1 = boxes[:, 1]
    x2 = boxes[:, 2]
    y2 = boxes[:, 3]
    areas = (x2 - x1) * (y2 - y1)

    keep: list[int] = []
    for c in np.unique(classes):
        cls_mask = classes == c
        idx = np.flatnonzero(cls_mask)
        if idx.size == 0:
            continue
        order = idx[scores[idx].argsort()[::-1]]

        while order.size > 0:
            i = order[0]
            keep.append(int(i))
            if order.size == 1:
                break
            xx1 = np.maximum(x1[i], x1[order[1:]])
            yy1 = np.maximum(y1[i], y1[order[1:]])
            xx2 = np.minimum(x2[i], x2[order[1:]])
            yy2 = np.minimum(y2[i], y2[order[1:]])
            w = np.maximum(0.0, xx2 - xx1)
            h = np.maximum(0.0, yy2 - yy1)
            inter = w * h
            iou = inter / (areas[i] + areas[order[1:]] - inter + 1e-9)
            order = order[1:][iou < iou_thresh]
    return keep


def scale_coords_back(xyxy: np.ndarray, img_w: int, img_h: int,
                      input_w: int, input_h: int,
                      resize_type: int = 0) -> np.ndarray:
    """Map boxes from model input space back to original image space."""
    if resize_type == 0:
        scale_x = img_w / input_w
        scale_y = img_h / input_h
        xyxy[:, [0, 2]] *= scale_x
        xyxy[:, [1, 3]] *= scale_y
    else:  # letterbox
        scale = min(input_w / img_w, input_h / img_h)
        pad_w = (input_w - img_w * scale) / 2
        pad_h = (input_h - img_h * scale) / 2
        xyxy[:, [0, 2]] = (xyxy[:, [0, 2]] - pad_w) / scale
        xyxy[:, [1, 3]] = (xyxy[:, [1, 3]] - pad_h) / scale

    xyxy[:, [0, 2]] = np.clip(xyxy[:, [0, 2]], 0, img_w)
    xyxy[:, [1, 3]] = np.clip(xyxy[:, [1, 3]], 0, img_h)
    return xyxy


# ---------------------------------------------------------------------------
# Top-level postprocess routine
# ---------------------------------------------------------------------------
def postprocess(outputs: dict, output_quants: dict, output_names,
                img_w: int, img_h: int,
                input_w: int, input_h: int,
                resize_type: int,
                score_thres: float, nms_thres: float,
                classes_num: int = 80):
    """Run optimized decode → NMS → rescale."""
    # Decode quantized outputs on-demand
    boxes, scores, classes = decode_outputs_optimized(
        outputs, output_quants, score_thres, classes_num
    )
    if len(boxes) == 0:
        return boxes, classes, scores
        
    # Class-wise Non-Maximum Suppression
    keep = nms(boxes, scores, classes, nms_thres)
    if len(keep) == 0:
        return np.empty((0, 4), dtype=np.float32), np.empty((0,), dtype=np.int32), np.empty((0,), dtype=np.float32)
        
    # Scale boxes back to source dimensions
    xyxy = scale_coords_back(boxes[keep], img_w, img_h, input_w, input_h, resize_type)
    return xyxy, classes[keep], scores[keep]
