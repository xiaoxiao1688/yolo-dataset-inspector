from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image, UnidentifiedImageError


REPAIR_STRATEGY_MAP = {
    "duplicate_basename": "Rename duplicate files to unique basenames before repair.",
    "missing_image": "Remove orphan label files or recover the matching images.",
    "missing_label": "Create missing labels or exclude unmatched images from export.",
    "empty_label": "Drop empty labels or keep them as explicit background samples.",
    "detect_format": "Delete malformed rows or rewrite them into 5-value YOLO boxes.",
    "detect_nan": "Delete rows containing non-numeric values.",
    "segment_format": "Delete malformed polygons or rewrite them into valid point pairs.",
    "segment_nan": "Delete rows containing non-numeric polygon values.",
    "segment_points": "Delete polygons with fewer than 3 points.",
    "class_id": "Remap negative class ids into the configured class set.",
    "class_range": "Remap out-of-range class ids into the configured class set.",
    "normalized_range": "Clip coordinates into 0..1 or drop invalid rows.",
    "image_load": "Replace unreadable images before export.",
}


def create_issue(level, code, message, entry_key=None, line=None):
    issue = {
        "level": level,
        "code": code,
        "message": message,
        "entry_key": entry_key,
    }
    if line is not None:
        issue["line"] = line
    return issue


def normalize_base_name(filename: str) -> str:
    return Path(str(filename or "")).stem.strip().lower()


def parse_class_names(text: str) -> list[str]:
    return [item.strip() for item in str(text or "").replace(",", "\n").splitlines() if item.strip()]


def collect_duplicate_issues(files, kind: str):
    seen: dict[str, int] = {}
    issues = []
    for file in files:
        key = normalize_base_name(file.filename)
        if not key:
            continue
        seen[key] = seen.get(key, 0) + 1

    for key, count in seen.items():
        if count > 1:
            issues.append(
                create_issue(
                    "warning",
                    "duplicate_basename",
                    f'{kind} basename "{key}" appears {count} times.',
                    entry_key=key,
                )
            )
    return issues


def validate_detect_line(parts, class_count: int, line_number: int):
    if len(parts) != 5:
        return create_issue("error", "detect_format", "Detect label must contain 5 values.", line=line_number), None

    try:
        class_id = int(parts[0])
        x_center = float(parts[1])
        y_center = float(parts[2])
        width = float(parts[3])
        height = float(parts[4])
    except ValueError:
        return create_issue("error", "detect_nan", "Detect label contains non-numeric values.", line=line_number), None

    if class_id < 0:
        return create_issue("error", "class_id", "Class id must be non-negative.", line=line_number), None

    if class_count and class_id >= class_count:
        return create_issue("error", "class_range", "Class id is outside the configured class list.", line=line_number), None

    if any(value < 0 or value > 1 for value in (x_center, y_center, width, height)):
        return create_issue("error", "normalized_range", "Detect coordinates must stay within 0..1.", line=line_number), None

    return None, {
        "type": "detect",
        "class_id": class_id,
        "x_center": x_center,
        "y_center": y_center,
        "width": width,
        "height": height,
        "line": line_number,
    }


def validate_segment_line(parts, class_count: int, line_number: int):
    if len(parts) < 7 or len(parts) % 2 == 0:
        return create_issue("error", "segment_format", "Segment label needs class id plus point pairs.", line=line_number), None

    try:
        class_id = int(parts[0])
    except ValueError:
        return create_issue("error", "segment_nan", "Segment label contains non-numeric values.", line=line_number), None

    if class_id < 0:
        return create_issue("error", "class_id", "Class id must be non-negative.", line=line_number), None

    if class_count and class_id >= class_count:
        return create_issue("error", "class_range", "Class id is outside the configured class list.", line=line_number), None

    try:
        values = [float(value) for value in parts[1:]]
    except ValueError:
        return create_issue("error", "segment_nan", "Segment label contains non-numeric values.", line=line_number), None

    points = []
    for index in range(0, len(values), 2):
        x_value = values[index]
        y_value = values[index + 1]
        if x_value < 0 or x_value > 1 or y_value < 0 or y_value > 1:
            return create_issue("error", "normalized_range", "Segment coordinates must stay within 0..1.", line=line_number), None
        points.append({"x": x_value, "y": y_value})

    if len(points) < 3:
        return create_issue("error", "segment_points", "Segment polygon needs at least 3 points.", line=line_number), None

    return None, {
        "type": "segment",
        "class_id": class_id,
        "point_count": len(points),
        "line": line_number,
    }


def parse_label_text(text: str, task_type: str, class_count: int, entry_key: str):
    issues = []
    records = []
    raw_lines = str(text or "").splitlines()

    if not any(line.strip() for line in raw_lines):
        issues.append(create_issue("warning", "empty_label", "Label file is empty.", entry_key=entry_key))
        return issues, records

    validator = validate_segment_line if task_type == "segment" else validate_detect_line

    for index, raw_line in enumerate(raw_lines, start=1):
        if not raw_line.strip():
            continue
        issue, record = validator(raw_line.strip().split(), class_count, index)
        if issue:
            issue["entry_key"] = entry_key
            issues.append(issue)
        elif record:
            records.append(record)

    return issues, records


def inspect_image(file_storage):
    try:
        raw_bytes = file_storage.read()
        with Image.open(BytesIO(raw_bytes)) as image:
            width, height = image.size
        file_storage.stream.seek(0)
        return {"width": width, "height": height}, None
    except (UnidentifiedImageError, OSError):
        try:
            file_storage.stream.seek(0)
        except Exception:
            pass
        return None, create_issue("error", "image_load", f"Image file {file_storage.filename} could not be opened.")


def build_repair_plan(issues):
    plan = []
    seen_codes = set()
    for issue in issues:
        code = issue["code"]
        if code in seen_codes:
            continue
        seen_codes.add(code)
        message = REPAIR_STRATEGY_MAP.get(code)
        if message:
            plan.append({"code": code, "strategy": message})
    return plan


def scan_dataset(task_type: str, image_files, label_files, classes_text: str):
    class_names = parse_class_names(classes_text)
    image_map = {}
    label_map = {}
    issues = []

    for file in image_files:
        key = normalize_base_name(file.filename)
        if key and key not in image_map:
            image_map[key] = file

    for file in label_files:
        key = normalize_base_name(file.filename)
        if key and key not in label_map:
            label_map[key] = file

    issues.extend(collect_duplicate_issues(image_files, "Image"))
    issues.extend(collect_duplicate_issues(label_files, "Label"))

    entries = []
    all_keys = sorted(set(image_map) | set(label_map))
    for key in all_keys:
        image_file = image_map.get(key)
        label_file = label_map.get(key)
        entry_issues = []
        image_info = None
        records = []

        if image_file is None:
            entry_issues.append(create_issue("warning", "missing_image", "No image matches this label file.", entry_key=key))
        if label_file is None:
            entry_issues.append(create_issue("warning", "missing_label", "No label matches this image file.", entry_key=key))

        if image_file is not None:
            image_info, image_issue = inspect_image(image_file)
            if image_issue:
                image_issue["entry_key"] = key
                entry_issues.append(image_issue)

        if label_file is not None:
            label_text = label_file.read().decode("utf-8", errors="ignore")
            try:
                label_file.stream.seek(0)
            except Exception:
                pass
            label_issues, records = parse_label_text(label_text, task_type, len(class_names), key)
            entry_issues.extend(label_issues)

        issues.extend(entry_issues)
        entries.append(
            {
                "key": key,
                "image_name": image_file.filename if image_file else None,
                "label_name": label_file.filename if label_file else None,
                "image_info": image_info,
                "record_count": len(records),
                "issue_count": len(entry_issues),
                "issues": entry_issues,
            }
        )

    return {
        "task_type": task_type,
        "class_names": class_names,
        "summary": {
            "image_count": len(image_files),
            "label_count": len(label_files),
            "entry_count": len(entries),
            "issue_count": len(issues),
            "error_count": sum(1 for issue in issues if issue["level"] == "error"),
            "warning_count": sum(1 for issue in issues if issue["level"] == "warning"),
        },
        "entries": entries,
        "issues": issues,
        "repair_plan": build_repair_plan(issues),
    }
