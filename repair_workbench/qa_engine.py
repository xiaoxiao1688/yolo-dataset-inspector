from __future__ import annotations

from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image

from repair_workbench.scanner import parse_class_names
from repair_workbench.yolo_runtime import get_device, load_model


def compute_iou(box1, box2):
    x1_1, y1_1, x2_1, y2_1 = box1
    x1_2, y1_2, x2_2, y2_2 = box2

    xi1 = max(x1_1, x1_2)
    yi1 = max(y1_1, y1_2)
    xi2 = min(x2_1, x2_2)
    yi2 = min(y2_1, y2_2)

    inter_width = max(0, xi2 - xi1)
    inter_height = max(0, yi2 - yi1)
    inter_area = inter_width * inter_height

    box1_area = (x2_1 - x1_1) * (y2_1 - y1_1)
    box2_area = (x2_2 - x1_2) * (y2_2 - y1_2)
    union_area = box1_area + box2_area - inter_area

    if union_area == 0:
        return 0.0
    return inter_area / union_area


def yolo_to_xyxy(box, img_width, img_height):
    x_center, y_center, width, height = box
    x1 = (x_center - width / 2) * img_width
    y1 = (y_center - height / 2) * img_height
    x2 = (x_center + width / 2) * img_width
    y2 = (y_center + height / 2) * img_height
    return [x1, y1, x2, y2]


def xyxy_to_yolo(box, img_width, img_height):
    x1, y1, x2, y2 = box
    x_center = ((x1 + x2) / 2) / img_width
    y_center = ((y1 + y2) / 2) / img_height
    width = (x2 - x1) / img_width
    height = (y2 - y1) / img_height
    return [x_center, y_center, width, height]


def is_anomalous_box(box, img_width, img_height, min_area_ratio=0.0001, max_area_ratio=0.9):
    x_center, y_center, width, height = box

    if width <= 0 or height <= 0:
        return True

    box_area = width * height
    if box_area < min_area_ratio or box_area > max_area_ratio:
        return True

    aspect_ratio = max(width, height) / max(min(width, height), 0.0001)
    if aspect_ratio > 20:
        return True

    return False


def parse_ground_truth_labels(label_text, class_count):
    labels = []
    lines = label_text.strip().splitlines()
    for line in lines:
        parts = line.strip().split()
        if len(parts) != 5:
            continue
        try:
            class_id = int(parts[0])
            x_center = float(parts[1])
            y_center = float(parts[2])
            width = float(parts[3])
            height = float(parts[4])

            if class_id < 0 or (class_count and class_id >= class_count):
                continue
            if any(v < 0 or v > 1 for v in [x_center, y_center, width, height]):
                continue

            labels.append({
                "class_id": class_id,
                "x_center": x_center,
                "y_center": y_center,
                "width": width,
                "height": height,
                "raw": line.strip(),
            })
        except ValueError:
            continue
    return labels


def run_yolo_detection(image_data, conf_threshold=0.25, iou_threshold=0.45):
    model = load_model(download_if_missing=True)
    device = get_device()

    image = Image.open(BytesIO(image_data))
    img_width, img_height = image.size

    image_np = np.array(image)

    results = model.predict(
        image_np,
        conf=conf_threshold,
        iou=iou_threshold,
        device=device,
        verbose=False,
    )

    detections = []
    if results and len(results) > 0:
        result = results[0]
        if hasattr(result, 'boxes') and result.boxes is not None:
            boxes = result.boxes
            for i in range(len(boxes)):
                box_xyxy = boxes.xyxy[i].cpu().numpy().tolist()
                class_id = int(boxes.cls[i].cpu().numpy())
                confidence = float(boxes.conf[i].cpu().numpy())

                x_center = ((box_xyxy[0] + box_xyxy[2]) / 2) / img_width
                y_center = ((box_xyxy[1] + box_xyxy[3]) / 2) / img_height
                width = (box_xyxy[2] - box_xyxy[0]) / img_width
                height = (box_xyxy[3] - box_xyxy[1]) / img_height

                detections.append({
                    "class_id": class_id,
                    "x_center": x_center,
                    "y_center": y_center,
                    "width": width,
                    "height": height,
                    "confidence": confidence,
                    "xyxy": box_xyxy,
                })

    return detections, img_width, img_height


def compare_labels(ground_truth, detections, img_width, img_height, class_names, iou_threshold=0.5):
    issues = []
    matched_gt = set()
    matched_det = set()

    gt_count = len(ground_truth)
    det_count = len(detections)

    for gt_idx, gt_box in enumerate(ground_truth):
        gt_xyxy = yolo_to_xyxy(
            [gt_box["x_center"], gt_box["y_center"], gt_box["width"], gt_box["height"]],
            img_width, img_height
        )

        if is_anomalous_box(
            [gt_box["x_center"], gt_box["y_center"], gt_box["width"], gt_box["height"]],
            img_width, img_height
        ):
            issues.append({
                "type": "anomalous_box",
                "source": "ground_truth",
                "box_index": gt_idx,
                "class_id": gt_box["class_id"],
                "class_name": class_names[gt_box["class_id"]] if gt_box["class_id"] < len(class_names) else f"class_{gt_box['class_id']}",
                "box": {
                    "x_center": gt_box["x_center"],
                    "y_center": gt_box["y_center"],
                    "width": gt_box["width"],
                    "height": gt_box["height"],
                },
                "reason": "异常框：尺寸或比例异常",
            })

        best_iou = 0
        best_det_idx = None
        best_class_match = False

        for det_idx, det_box in enumerate(detections):
            if det_idx in matched_det:
                continue

            det_xyxy = yolo_to_xyxy(
                [det_box["x_center"], det_box["y_center"], det_box["width"], det_box["height"]],
                img_width, img_height
            )

            iou = compute_iou(gt_xyxy, det_xyxy)

            if iou > best_iou:
                best_iou = iou
                best_det_idx = det_idx
                best_class_match = (gt_box["class_id"] == det_box["class_id"])

        if best_iou >= iou_threshold and best_det_idx is not None:
            matched_gt.add(gt_idx)
            matched_det.add(best_det_idx)

            if not best_class_match:
                det_box = detections[best_det_idx]
                issues.append({
                    "type": "class_conflict",
                    "source": "mismatch",
                    "ground_truth": {
                        "class_id": gt_box["class_id"],
                        "class_name": class_names[gt_box["class_id"]] if gt_box["class_id"] < len(class_names) else f"class_{gt_box['class_id']}",
                        "box": {
                            "x_center": gt_box["x_center"],
                            "y_center": gt_box["y_center"],
                            "width": gt_box["width"],
                            "height": gt_box["height"],
                        },
                    },
                    "detection": {
                        "class_id": det_box["class_id"],
                        "class_name": class_names[det_box["class_id"]] if det_box["class_id"] < len(class_names) else f"class_{det_box['class_id']}",
                        "box": {
                            "x_center": det_box["x_center"],
                            "y_center": det_box["y_center"],
                            "width": det_box["width"],
                            "height": det_box["height"],
                        },
                        "confidence": det_box["confidence"],
                    },
                    "iou": best_iou,
                    "reason": f"类别冲突：原标签为 {class_names[gt_box['class_id']] if gt_box['class_id'] < len(class_names) else f'class_{gt_box[\"class_id\"]}'}，模型建议为 {class_names[det_box['class_id']] if det_box['class_id'] < len(class_names) else f'class_{det_box[\"class_id\"]}'}",
                })
        elif best_iou < iou_threshold:
            issues.append({
                "type": "possibly_wrong_label",
                "source": "ground_truth",
                "box_index": gt_idx,
                "class_id": gt_box["class_id"],
                "class_name": class_names[gt_box["class_id"]] if gt_box["class_id"] < len(class_names) else f"class_{gt_box['class_id']}",
                "box": {
                    "x_center": gt_box["x_center"],
                    "y_center": gt_box["y_center"],
                    "width": gt_box["width"],
                    "height": gt_box["height"],
                },
                "best_iou": best_iou,
                "reason": f"可能错标：模型未找到匹配的检测框（最佳 IoU: {best_iou:.3f}）",
            })

    for gt_idx, gt_box in enumerate(ground_truth):
        if gt_idx not in matched_gt:
            issues.append({
                "type": "unmatched_ground_truth",
                "source": "ground_truth",
                "box_index": gt_idx,
                "class_id": gt_box["class_id"],
                "class_name": class_names[gt_box["class_id"]] if gt_box["class_id"] < len(class_names) else f"class_{gt_box['class_id']}",
                "box": {
                    "x_center": gt_box["x_center"],
                    "y_center": gt_box["y_center"],
                    "width": gt_box["width"],
                    "height": gt_box["height"],
                },
                "reason": "原标签框未被模型匹配，可能是错标或模型漏检",
            })

    for det_idx, det_box in enumerate(detections):
        if det_idx not in matched_det:
            issues.append({
                "type": "missing_label",
                "source": "detection",
                "box_index": det_idx,
                "class_id": det_box["class_id"],
                "class_name": class_names[det_box["class_id"]] if det_box["class_id"] < len(class_names) else f"class_{det_box['class_id']}",
                "box": {
                    "x_center": det_box["x_center"],
                    "y_center": det_box["y_center"],
                    "width": det_box["width"],
                    "height": det_box["height"],
                },
                "confidence": det_box["confidence"],
                "reason": f"漏标建议：模型检测到 {class_names[det_box['class_id']] if det_box['class_id'] < len(class_names) else f'class_{det_box[\"class_id\"]}'}（置信度: {det_box['confidence']:.3f}）",
            })

    return {
        "ground_truth_count": gt_count,
        "detection_count": det_count,
        "matched_count": len(matched_gt),
        "issues": issues,
    }


def process_qa_task(image_file, label_file, classes_text, conf_threshold=0.25, iou_threshold=0.45):
    class_names = parse_class_names(classes_text)
    if not class_names:
        class_names = [f"class_{i}" for i in range(80)]

    image_data = image_file.read()
    try:
        image_file.stream.seek(0)
    except Exception:
        pass

    detections, img_width, img_height = run_yolo_detection(
        image_data,
        conf_threshold=conf_threshold,
        iou_threshold=iou_threshold,
    )

    ground_truth = []
    if label_file:
        label_text = label_file.read().decode("utf-8", errors="ignore")
        try:
            label_file.stream.seek(0)
        except Exception:
            pass
        ground_truth = parse_ground_truth_labels(label_text, len(class_names))

    comparison = compare_labels(
        ground_truth,
        detections,
        img_width,
        img_height,
        class_names,
        iou_threshold=iou_threshold,
    )

    return {
        "image_info": {
            "width": img_width,
            "height": img_height,
            "filename": image_file.filename,
        },
        "class_names": class_names,
        "ground_truth": ground_truth,
        "detections": detections,
        "comparison": comparison,
        "config": {
            "conf_threshold": conf_threshold,
            "iou_threshold": iou_threshold,
        },
    }
