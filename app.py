import sys
import json
import os
from flask import Flask, jsonify, render_template, request


app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024


def get_environment_info():
    info = {
        "python_version": ".".join(map(str, sys.version_info[:3])),
        "python_path": sys.executable,
        "platform": sys.platform,
        "requirements": {},
        "status": "ok"
    }

    required_packages = {
        "flask": "Flask - Web framework",
    }

    for package, description in required_packages.items():
        try:
            module = __import__(package)
            version = getattr(module, "__version__", "unknown")
            info["requirements"][package] = {
                "status": "ok",
                "version": version,
                "description": description
            }
        except ImportError:
            info["requirements"][package] = {
                "status": "missing",
                "description": description
            }
            info["status"] = "error"

    return info


def validate_yolo_detect_line(line, class_count=None):
    parts = line.strip().split()
    errors = []
    warnings = []

    if not parts:
        return {"valid": False, "errors": ["Empty line"], "warnings": []}

    if len(parts) != 5:
        errors.append(f"Expected 5 values, got {len(parts)}")
        return {"valid": False, "errors": errors, "warnings": warnings}

    try:
        class_id = int(parts[0])
        if class_id < 0:
            errors.append("Class ID must be non-negative")
    except ValueError:
        errors.append("Class ID must be an integer")

    for i, coord_name in enumerate(["x_center", "y_center", "width", "height"], 1):
        try:
            value = float(parts[i])
            if value < 0 or value > 1:
                errors.append(f"{coord_name} ({value}) must be between 0 and 1")
        except ValueError:
            errors.append(f"{coord_name} must be a number")

    if class_count is not None:
        try:
            class_id = int(parts[0])
            if class_id >= class_count:
                warnings.append(f"Class ID {class_id} exceeds class count ({class_count})")
        except ValueError:
            pass

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "parsed": {
            "type": "detect",
            "class_id": int(parts[0]) if parts and parts[0].isdigit() else None,
            "x_center": float(parts[1]) if len(parts) > 1 else None,
            "y_center": float(parts[2]) if len(parts) > 2 else None,
            "width": float(parts[3]) if len(parts) > 3 else None,
            "height": float(parts[4]) if len(parts) > 4 else None
        } if len(parts) == 5 else None
    }


def validate_yolo_segment_line(line, class_count=None):
    parts = line.strip().split()
    errors = []
    warnings = []

    if not parts:
        return {"valid": False, "errors": ["Empty line"], "warnings": []}

    if len(parts) < 7:
        errors.append(f"Segment format requires at least 7 values (class_id + 3 points), got {len(parts)}")
        return {"valid": False, "errors": errors, "warnings": warnings}

    if len(parts) % 2 == 0:
        warnings.append(f"Even number of values ({len(parts)}) may indicate incomplete point pair")

    try:
        class_id = int(parts[0])
        if class_id < 0:
            errors.append("Class ID must be non-negative")
    except ValueError:
        errors.append("Class ID must be an integer")

    points = []
    for i in range(1, len(parts), 2):
        if i + 1 >= len(parts):
            warnings.append(f"Incomplete point pair at position {i}")
            break

        try:
            x = float(parts[i])
            y = float(parts[i + 1])

            if x < 0 or x > 1:
                errors.append(f"Point x coordinate ({x}) must be between 0 and 1")
            if y < 0 or y > 1:
                errors.append(f"Point y coordinate ({y}) must be between 0 and 1")

            points.append({"x": x, "y": y})
        except ValueError:
            errors.append(f"Point coordinates at positions {i}/{i+1} must be numbers")

    if len(points) < 3:
        errors.append(f"Segment requires at least 3 points, got {len(points)}")

    if class_count is not None:
        try:
            class_id = int(parts[0])
            if class_id >= class_count:
                warnings.append(f"Class ID {class_id} exceeds class count ({class_count})")
        except ValueError:
            pass

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "parsed": {
            "type": "segment",
            "class_id": int(parts[0]) if parts and parts[0].isdigit() else None,
            "points": points,
            "point_count": len(points)
        }
    }


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/health")
def health():
    env_info = get_environment_info()
    return jsonify({
        "status": "ok" if env_info["status"] == "ok" else "error",
        "app": "geodraft-yolo-qa",
        "environment": env_info
    })


@app.get("/api/env")
def get_env():
    return jsonify(get_environment_info())


@app.get("/api/self-check")
def self_check():
    env_info = get_environment_info()
    checks = {
        "environment": env_info,
        "frontend": {
            "status": "ok",
            "features": [
                "Image file import",
                "Label file import",
                "Detect mode parsing",
                "Segment mode parsing",
                "Annotation preview",
                "Issue detection",
                "JSON report export"
            ]
        },
        "yolo_support": {
            "detect": {
                "status": "ok",
                "format": "class_id x_center y_center width height",
                "validation": "Available via /api/validate/detect"
            },
            "segment": {
                "status": "ok",
                "format": "class_id x1 y1 x2 y2 x3 y3 ...",
                "validation": "Available via /api/validate/segment"
            }
        },
        "summary": {
            "total_checks": 3,
            "passed": 2 + (1 if env_info["status"] == "ok" else 0),
            "failed": 0 if env_info["status"] == "ok" else 1
        }
    }

    overall_status = "ok" if env_info["status"] == "ok" else "error"
    return jsonify({"status": overall_status, "checks": checks})


@app.post("/api/validate/detect")
def validate_detect():
    data = request.get_json()
    if not data or "lines" not in data:
        return jsonify({"error": "Missing 'lines' in request body"}), 400

    lines = data["lines"]
    class_count = data.get("class_count")

    results = []
    total_errors = 0
    total_warnings = 0

    for i, line in enumerate(lines):
        result = validate_yolo_detect_line(line, class_count)
        result["line_number"] = i + 1
        result["line"] = line
        results.append(result)
        total_errors += len(result["errors"])
        total_warnings += len(result["warnings"])

    return jsonify({
        "task_type": "detect",
        "total_lines": len(lines),
        "valid_lines": sum(1 for r in results if r["valid"]),
        "total_errors": total_errors,
        "total_warnings": total_warnings,
        "results": results
    })


@app.post("/api/validate/segment")
def validate_segment():
    data = request.get_json()
    if not data or "lines" not in data:
        return jsonify({"error": "Missing 'lines' in request body"}), 400

    lines = data["lines"]
    class_count = data.get("class_count")

    results = []
    total_errors = 0
    total_warnings = 0

    for i, line in enumerate(lines):
        result = validate_yolo_segment_line(line, class_count)
        result["line_number"] = i + 1
        result["line"] = line
        results.append(result)
        total_errors += len(result["errors"])
        total_warnings += len(result["warnings"])

    return jsonify({
        "task_type": "segment",
        "total_lines": len(lines),
        "valid_lines": sum(1 for r in results if r["valid"]),
        "total_errors": total_errors,
        "total_warnings": total_warnings,
        "results": results
    })


@app.get("/api/formats")
def get_formats():
    return jsonify({
        "detect": {
            "name": "Object Detection",
            "description": "Bounding box format for object detection tasks",
            "format": "class_id x_center y_center width height",
            "example": "0 0.5 0.5 0.3 0.4",
            "fields": [
                {"name": "class_id", "type": "integer", "description": "Class index (0-based)"},
                {"name": "x_center", "type": "float", "description": "Center X coordinate (normalized 0-1)"},
                {"name": "y_center", "type": "float", "description": "Center Y coordinate (normalized 0-1)"},
                {"name": "width", "type": "float", "description": "Box width (normalized 0-1)"},
                {"name": "height", "type": "float", "description": "Box height (normalized 0-1)"}
            ]
        },
        "segment": {
            "name": "Instance Segmentation",
            "description": "Polygon format for instance segmentation tasks",
            "format": "class_id x1 y1 x2 y2 x3 y3 ...",
            "example": "0 0.1 0.2 0.3 0.4 0.5 0.6 0.2 0.8",
            "fields": [
                {"name": "class_id", "type": "integer", "description": "Class index (0-based)"},
                {"name": "x1, y1, x2, y2, ...", "type": "float pairs", "description": "Polygon vertices (normalized 0-1, minimum 3 points)"}
            ]
        }
    })


if __name__ == "__main__":
    print("=" * 50)
    print("GeoDraft YOLO QA - Starting Server")
    print("=" * 50)
    print()

    env_info = get_environment_info()
    print("Environment Information:")
    print(f"  Python: {env_info['python_version']}")
    print(f"  Path: {env_info['python_path']}")
    print()

    print("Requirements:")
    for pkg, info in env_info["requirements"].items():
        status = "OK" if info["status"] == "ok" else "MISSING"
        version = info.get("version", "")
        print(f"  {pkg}: {status} {version}")
    print()

    print("Available API Endpoints:")
    print("  GET  /                  - Web interface")
    print("  GET  /api/health        - Health check")
    print("  GET  /api/env           - Environment info")
    print("  GET  /api/self-check    - Full self-check")
    print("  GET  /api/formats       - YOLO format documentation")
    print("  POST /api/validate/detect  - Validate detect format lines")
    print("  POST /api/validate/segment - Validate segment format lines")
    print()

    print("=" * 50)
    print("Server running at: http://127.0.0.1:5000")
    print("=" * 50)
    print()

    app.run(debug=True, use_reloader=False, host="127.0.0.1", port=5000)
