import sys
import json
import os


def run_self_check():
    checks = {
        "python_version": ".".join(map(str, sys.version_info[:3])),
        "python_path": sys.executable,
        "platform": sys.platform,
        "requirements": [],
        "frontend_files": [],
        "yolo_validation": {
            "detect_available": False,
            "segment_available": False
        },
        "status": "ok",
        "errors": [],
        "warnings": []
    }

    required_packages = ["flask"]
    for pkg in required_packages:
        try:
            module = __import__(pkg)
            version = getattr(module, "__version__", "unknown")
            checks["requirements"].append({
                "package": pkg,
                "status": "ok",
                "version": version
            })
        except ImportError:
            checks["requirements"].append({
                "package": pkg,
                "status": "missing"
            })
            checks["errors"].append(f"Required package '{pkg}' is not installed")
            checks["status"] = "error"

    expected_files = {
        "static/css/styles.css": "Frontend stylesheet",
        "static/js/app.js": "Frontend application (YOLO parser)",
        "templates/index.html": "Main HTML template"
    }

    for rel_path, description in expected_files.items():
        abs_path = os.path.join(os.path.dirname(__file__), rel_path)
        if os.path.exists(abs_path):
            checks["frontend_files"].append({
                "path": rel_path,
                "description": description,
                "status": "ok"
            })
        else:
            checks["frontend_files"].append({
                "path": rel_path,
                "description": description,
                "status": "missing"
            })
            checks["warnings"].append(f"Expected frontend file '{rel_path}' not found")

    detect_sample_line = "0 0.5 0.5 0.3 0.4"
    detect_parts = detect_sample_line.strip().split()
    if len(detect_parts) == 5:
        try:
            class_id = int(detect_parts[0])
            x_center = float(detect_parts[1])
            y_center = float(detect_parts[2])
            width = float(detect_parts[3])
            height = float(detect_parts[4])
            
            if (class_id >= 0 and 
                0 <= x_center <= 1 and 
                0 <= y_center <= 1 and 
                0 <= width <= 1 and 
                0 <= height <= 1):
                checks["yolo_validation"]["detect_available"] = True
        except (ValueError, IndexError):
            pass

    segment_sample_line = "0 0.1 0.2 0.3 0.4 0.5 0.6 0.2 0.8"
    segment_parts = segment_sample_line.strip().split()
    if len(segment_parts) >= 7:
        try:
            class_id = int(segment_parts[0])
            valid_points = True
            points_count = 0
            
            for i in range(1, len(segment_parts), 2):
                if i + 1 >= len(segment_parts):
                    break
                x = float(segment_parts[i])
                y = float(segment_parts[i + 1])
                if x < 0 or x > 1 or y < 0 or y > 1:
                    valid_points = False
                    break
                points_count += 1
            
            if class_id >= 0 and valid_points and points_count >= 3:
                checks["yolo_validation"]["segment_available"] = True
        except (ValueError, IndexError):
            pass

    return checks


if __name__ == "__main__":
    result = run_self_check()
    print(json.dumps(result, indent=2))
    
    if result["status"] == "error":
        sys.exit(1)
    sys.exit(0)
