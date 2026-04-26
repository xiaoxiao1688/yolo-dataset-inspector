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


def _check_frontend_files():
    base_dir = os.path.dirname(__file__)
    expected_files = {
        "static/css/styles.css": "Frontend stylesheet",
        "static/js/app.js": "Frontend application (YOLO parser)",
        "templates/index.html": "Main HTML template"
    }

    results = []
    all_ok = True

    for rel_path, description in expected_files.items():
        abs_path = os.path.join(base_dir, rel_path)
        exists = os.path.exists(abs_path)
        file_size = os.path.getsize(abs_path) if exists else 0

        results.append({
            "path": rel_path,
            "description": description,
            "exists": exists,
            "size_bytes": file_size,
            "status": "ok" if exists and file_size > 0 else "warning"
        })

        if not exists or file_size == 0:
            all_ok = False

    return {
        "check_type": "static_file_existence",
        "note": "This only verifies file existence, not runtime behavior",
        "files": results,
        "overall": "ok" if all_ok else "warning"
    }


def _run_yolo_validation_self_test():
    tests = {
        "detect": [
            {
                "label": "valid_bbox",
                "input": "0 0.5 0.5 0.3 0.4",
                "expected_valid": True
            },
            {
                "label": "invalid_coord_out_of_range",
                "input": "0 1.5 0.5 0.3 0.4",
                "expected_valid": False
            }
        ],
        "segment": [
            {
                "label": "valid_polygon",
                "input": "0 0.1 0.2 0.3 0.4 0.5 0.6 0.2 0.8",
                "expected_valid": True
            },
            {
                "label": "insufficient_points",
                "input": "0 0.1 0.2 0.3 0.4",
                "expected_valid": False
            }
        ]
    }

    results = {}
    all_passed = True

    for task_type, test_cases in tests.items():
        task_results = []
        task_passed = True

        for test_case in test_cases:
            if task_type == "detect":
                result = validate_yolo_detect_line(test_case["input"])
            else:
                result = validate_yolo_segment_line(test_case["input"])

            passed = result["valid"] == test_case["expected_valid"]

            task_results.append({
                "test_label": test_case["label"],
                "input": test_case["input"],
                "expected_valid": test_case["expected_valid"],
                "actual_valid": result["valid"],
                "passed": passed
            })

            if not passed:
                task_passed = False
                all_passed = False

        results[task_type] = {
            "tests": task_results,
            "all_passed": task_passed
        }

    return {
        "check_type": "runtime_validation_test",
        "note": "This runs actual validation logic against known-good and known-bad inputs",
        "results": results,
        "overall": "ok" if all_passed else "error"
    }


@app.get("/api/self-check")
def self_check():
    env_info = get_environment_info()

    frontend_check = _check_frontend_files()
    yolo_validation_check = _run_yolo_validation_self_test()

    verified_ok = (
        env_info["status"] == "ok" and
        yolo_validation_check["overall"] == "ok"
    )

    overall_status = "ok" if verified_ok else "error"

    checks = {
        "verified_checks": {
            "description": "These checks are actually verified at runtime",
            "environment": {
                "check_type": "runtime_environment",
                "status": env_info["status"],
                "python_version": env_info["python_version"],
                "python_path": env_info["python_path"],
                "platform": env_info["platform"],
                "requirements": env_info["requirements"]
            },
            "yolo_validation_functions": {
                "check_type": "runtime_function_test",
                "status": yolo_validation_check["overall"],
                "details": yolo_validation_check
            }
        },
        "static_declarations": {
            "description": "These are static declarations or existence checks, not full runtime verification",
            "frontend_files": {
                "note": "Only verifies file existence, not that JavaScript runs correctly",
                "status": frontend_check["overall"],
                "details": frontend_check
            },
            "declared_features": {
                "note": "These features are implemented in static/js/app.js but not verified by this API",
                "frontend": [
                    "Image file import",
                    "Label file import",
                    "Detect mode parsing",
                    "Segment mode parsing",
                    "Annotation preview",
                    "Issue detection",
                    "JSON report export"
                ],
                "yolo_formats": {
                    "detect": {
                        "format": "class_id x_center y_center width height",
                        "validation_api": "/api/validate/detect"
                    },
                    "segment": {
                        "format": "class_id x1 y1 x2 y2 x3 y3 ...",
                        "validation_api": "/api/validate/segment"
                    }
                }
            }
        },
        "summary": {
            "verified_checks_total": 2,
            "verified_checks_passed": sum([
                1 if env_info["status"] == "ok" else 0,
                1 if yolo_validation_check["overall"] == "ok" else 0
            ]),
            "verified_checks_failed": sum([
                0 if env_info["status"] == "ok" else 1,
                0 if yolo_validation_check["overall"] == "ok" else 1
            ]),
            "static_declarations_count": 2,
            "note": "Only 'verified_checks' are actually validated; 'static_declarations' are informational only"
        }
    }

    return jsonify({
        "status": overall_status,
        "checks": checks,
        "critical_note": "This API distinguishes between VERIFIED checks (actually run and validated) and STATIC declarations (just stated to exist). Do not assume 'ok' status means full end-to-end functionality is tested."
    })


@app.post("/api/validate/detect")
def validate_detect():
    try:
        data = request.get_json()
    except Exception:
        return jsonify({
            "error": "Invalid JSON request body",
            "expected": {"lines": ["string", "..."], "class_count": "optional integer"}
        }), 400

    if not isinstance(data, dict):
        return jsonify({
            "error": "Request body must be a JSON object",
            "expected": "object",
            "received": type(data).__name__
        }), 400

    if "lines" not in data:
        return jsonify({
            "error": "Missing required field: 'lines'",
            "expected": {"lines": ["string", "..."]}
        }), 400

    lines = data["lines"]

    if not isinstance(lines, list):
        return jsonify({
            "error": "'lines' must be an array",
            "expected": "array",
            "received": type(lines).__name__
        }), 400

    if len(lines) == 0:
        return jsonify({
            "error": "'lines' array cannot be empty",
            "expected": "at least one label line"
        }), 400

    for i, line in enumerate(lines):
        if not isinstance(line, str):
            return jsonify({
                "error": f"Line at index {i} is not a string",
                "expected": "string",
                "received": type(line).__name__,
                "line_index": i
            }), 400

    class_count = data.get("class_count")
    if class_count is not None:
        if not isinstance(class_count, int):
            return jsonify({
                "error": "'class_count' must be an integer",
                "expected": "integer",
                "received": type(class_count).__name__
            }), 400
        if class_count < 0:
            return jsonify({
                "error": "'class_count' must be non-negative",
                "received": class_count
            }), 400

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
    try:
        data = request.get_json()
    except Exception:
        return jsonify({
            "error": "Invalid JSON request body",
            "expected": {"lines": ["string", "..."], "class_count": "optional integer"}
        }), 400

    if not isinstance(data, dict):
        return jsonify({
            "error": "Request body must be a JSON object",
            "expected": "object",
            "received": type(data).__name__
        }), 400

    if "lines" not in data:
        return jsonify({
            "error": "Missing required field: 'lines'",
            "expected": {"lines": ["string", "..."]}
        }), 400

    lines = data["lines"]

    if not isinstance(lines, list):
        return jsonify({
            "error": "'lines' must be an array",
            "expected": "array",
            "received": type(lines).__name__
        }), 400

    if len(lines) == 0:
        return jsonify({
            "error": "'lines' array cannot be empty",
            "expected": "at least one label line"
        }), 400

    for i, line in enumerate(lines):
        if not isinstance(line, str):
            return jsonify({
                "error": f"Line at index {i} is not a string",
                "expected": "string",
                "received": type(line).__name__,
                "line_index": i
            }), 400

    class_count = data.get("class_count")
    if class_count is not None:
        if not isinstance(class_count, int):
            return jsonify({
                "error": "'class_count' must be an integer",
                "expected": "integer",
                "received": type(class_count).__name__
            }), 400
        if class_count < 0:
            return jsonify({
                "error": "'class_count' must be non-negative",
                "received": class_count
            }), 400

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
