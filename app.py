from flask import Flask, jsonify, render_template, request, send_file, send_from_directory
from io import BytesIO
import json
import uuid
from pathlib import Path

from repair_workbench.scanner import scan_dataset
from repair_workbench.yolo_runtime import environment_summary
from repair_workbench.qa_engine import process_qa_task


app = Flask(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent
SESSION_DATA_DIR = PROJECT_ROOT / "session_data"
SESSION_DATA_DIR.mkdir(parents=True, exist_ok=True)

qa_session_store = {}


def get_session_dir(session_id: str) -> Path:
    return SESSION_DATA_DIR / session_id


def save_session_to_disk(session_id: str, session_data: dict):
    session_dir = get_session_dir(session_id)
    session_dir.mkdir(parents=True, exist_ok=True)

    session_file = session_dir / "session.json"
    with open(session_file, "w", encoding="utf-8") as f:
        json.dump(session_data, f, indent=2, default=str)


def load_session_from_disk(session_id: str) -> dict | None:
    session_file = get_session_dir(session_id) / "session.json"
    if not session_file.exists():
        return None

    with open(session_file, "r", encoding="utf-8") as f:
        return json.load(f)


def save_image(session_id: str, image_key: str, image_data: bytes, filename: str) -> str:
    session_dir = get_session_dir(session_id)
    images_dir = session_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    ext = Path(filename).suffix or ".jpg"
    safe_filename = f"{image_key}{ext}"
    image_path = images_dir / safe_filename

    with open(image_path, "wb") as f:
        f.write(image_data)

    return safe_filename


def generate_session_id():
    return str(uuid.uuid4())[:8]


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "yolo": environment_summary()})


@app.post("/api/scan")
def scan():
    task_type = request.form.get("task_type", "detect").strip().lower() or "detect"
    classes_text = request.form.get("classes_text", "")
    image_files = request.files.getlist("images")
    label_files = request.files.getlist("labels")

    if task_type not in {"detect", "segment"}:
        return jsonify({"error": "task_type must be detect or segment"}), 400

    if not image_files and not label_files:
        return jsonify({"error": "Upload at least one image or label file"}), 400

    result = scan_dataset(
        task_type=task_type,
        image_files=image_files,
        label_files=label_files,
        classes_text=classes_text,
    )
    return jsonify(result)


@app.post("/api/qa/process")
def qa_process():
    classes_text = request.form.get("classes_text", "")
    image_files = request.files.getlist("images")
    label_files = request.files.getlist("labels")
    conf_threshold = float(request.form.get("conf_threshold", 0.25))
    iou_threshold = float(request.form.get("iou_threshold", 0.45))

    if not image_files:
        return jsonify({"error": "Upload at least one image file"}), 400

    label_map = {}
    for label_file in label_files:
        key = label_file.filename.rsplit(".", 1)[0].lower()
        label_map[key] = label_file

    session_id = generate_session_id()
    results = []
    image_filenames = {}

    for image_file in image_files:
        image_key = image_file.filename.rsplit(".", 1)[0].lower()
        label_file = label_map.get(image_key)

        image_data = image_file.read()
        try:
            image_file.stream.seek(0)
        except Exception:
            pass

        saved_filename = save_image(session_id, image_key, image_data, image_file.filename)
        image_filenames[image_key] = saved_filename

        try:
            qa_result = process_qa_task(
                image_file=image_file,
                label_file=label_file,
                classes_text=classes_text,
                conf_threshold=conf_threshold,
                iou_threshold=iou_threshold,
            )
            qa_result["image_key"] = image_key
            qa_result["image_filename"] = saved_filename
            qa_result["decisions"] = []
            results.append(qa_result)
        except Exception as e:
            return jsonify({"error": f"Processing failed for {image_file.filename}: {str(e)}"}), 500

    session_data = {
        "session_id": session_id,
        "results": results,
        "class_names": results[0]["class_names"] if results else [],
        "image_filenames": image_filenames,
    }

    qa_session_store[session_id] = session_data
    save_session_to_disk(session_id, session_data)

    summary = {
        "total_images": len(results),
        "total_ground_truth": sum(r["comparison"]["ground_truth_count"] for r in results),
        "total_detections": sum(r["comparison"]["detection_count"] for r in results),
        "total_issues": sum(len(r["comparison"]["issues"]) for r in results),
    }

    return jsonify({
        "session_id": session_id,
        "summary": summary,
        "results": results,
    })


@app.get("/api/qa/session/<session_id>")
def qa_get_session(session_id):
    if session_id not in qa_session_store:
        return jsonify({"error": "Session not found"}), 404

    return jsonify(qa_session_store[session_id])


@app.post("/api/qa/decision")
def qa_set_decision():
    session_id = request.json.get("session_id")
    image_key = request.json.get("image_key")
    issue_index = request.json.get("issue_index")
    decision = request.json.get("decision")

    if session_id not in qa_session_store:
        return jsonify({"error": "Session not found"}), 404

    session = qa_session_store[session_id]
    result = None
    for r in session["results"]:
        if r["image_key"] == image_key:
            result = r
            break

    if not result:
        return jsonify({"error": "Image not found in session"}), 404

    if issue_index < 0 or issue_index >= len(result["comparison"]["issues"]):
        return jsonify({"error": "Invalid issue index"}), 400

    if decision not in ["accept", "reject", "keep"]:
        return jsonify({"error": "Invalid decision. Use 'accept', 'reject', or 'keep'"}), 400

    existing_idx = None
    for i, d in enumerate(result["decisions"]):
        if d["issue_index"] == issue_index:
            existing_idx = i
            break

    new_decision = {
        "issue_index": issue_index,
        "decision": decision,
        "issue": result["comparison"]["issues"][issue_index],
    }

    if existing_idx is not None:
        result["decisions"][existing_idx] = new_decision
    else:
        result["decisions"].append(new_decision)

    save_session_to_disk(session_id, session)

    return jsonify({"status": "ok", "message": f"Decision '{decision}' recorded"})


@app.get("/api/qa/image/<session_id>/<filename>")
def qa_get_image(session_id, filename):
    session_dir = get_session_dir(session_id)
    images_dir = session_dir / "images"
    if not images_dir.exists():
        return jsonify({"error": "Image not found"}), 404

    return send_from_directory(str(images_dir), filename)


def build_final_labels(session):
    all_labels = {}

    for result in session["results"]:
        image_key = result["image_key"]
        final_boxes = []

        decisions = {d["issue_index"]: d["decision"] for d in result["decisions"]}

        gt_box_issue_map = {}
        class_conflict_map = {}
        missing_label_map = {}

        for issue_idx, issue in enumerate(result["comparison"]["issues"]):
            issue_type = issue.get("type")
            source = issue.get("source")

            if issue_type == "class_conflict":
                gt_box = issue.get("ground_truth", {})
                if "box_index" in gt_box:
                    gt_idx = gt_box["box_index"]
                    gt_box_issue_map[gt_idx] = issue_idx
                    class_conflict_map[gt_idx] = {
                        "issue_idx": issue_idx,
                        "issue": issue,
                    }
            elif issue_type == "missing_label":
                if source == "detection":
                    det_idx = issue.get("box_index")
                    if det_idx is not None:
                        missing_label_map[det_idx] = issue_idx
            elif source == "ground_truth":
                gt_idx = issue.get("box_index")
                if gt_idx is not None and gt_idx not in gt_box_issue_map:
                    gt_box_issue_map[gt_idx] = issue_idx

        for gt_idx, gt_box in enumerate(result["ground_truth"]):
            if gt_idx in class_conflict_map:
                conflict_info = class_conflict_map[gt_idx]
                issue_idx = conflict_info["issue_idx"]
                issue = conflict_info["issue"]

                if issue_idx in decisions:
                    decision = decisions[issue_idx]
                    if decision == "accept":
                        det_info = issue.get("detection", {})
                        box_info = det_info.get("box", {})
                        final_boxes.append({
                            "class_id": det_info.get("class_id", 0),
                            "x_center": box_info.get("x_center", 0),
                            "y_center": box_info.get("y_center", 0),
                            "width": box_info.get("width", 0),
                            "height": box_info.get("height", 0),
                        })
                    elif decision == "reject":
                        pass
                    else:
                        final_boxes.append({
                            "class_id": gt_box["class_id"],
                            "x_center": gt_box["x_center"],
                            "y_center": gt_box["y_center"],
                            "width": gt_box["width"],
                            "height": gt_box["height"],
                        })
                else:
                    final_boxes.append({
                        "class_id": gt_box["class_id"],
                        "x_center": gt_box["x_center"],
                        "y_center": gt_box["y_center"],
                        "width": gt_box["width"],
                        "height": gt_box["height"],
                    })
            else:
                if gt_idx in gt_box_issue_map:
                    issue_idx = gt_box_issue_map[gt_idx]
                    if issue_idx in decisions and decisions[issue_idx] == "reject":
                        continue

                final_boxes.append({
                    "class_id": gt_box["class_id"],
                    "x_center": gt_box["x_center"],
                    "y_center": gt_box["y_center"],
                    "width": gt_box["width"],
                    "height": gt_box["height"],
                })

        for det_idx, det_box in enumerate(result["detections"]):
            if det_idx in missing_label_map:
                issue_idx = missing_label_map[det_idx]
                if issue_idx in decisions and decisions[issue_idx] == "accept":
                    final_boxes.append({
                        "class_id": det_box["class_id"],
                        "x_center": det_box["x_center"],
                        "y_center": det_box["y_center"],
                        "width": det_box["width"],
                        "height": det_box["height"],
                    })

        all_labels[image_key] = {
            "boxes": final_boxes,
            "filename": f"{image_key}.txt",
        }

    return all_labels


@app.get("/api/qa/export/labels/<session_id>")
def qa_export_labels(session_id):
    if session_id not in qa_session_store:
        return jsonify({"error": "Session not found"}), 404

    session = qa_session_store[session_id]
    all_labels = build_final_labels(session)

    import zipfile
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
        for image_key, label_data in all_labels.items():
            lines = []
            for box in label_data["boxes"]:
                line = f"{box['class_id']} {box['x_center']:.6f} {box['y_center']:.6f} {box['width']:.6f} {box['height']:.6f}"
                lines.append(line)
            content = "\n".join(lines)
            zip_file.writestr(label_data["filename"], content)

    zip_buffer.seek(0)
    return send_file(
        zip_buffer,
        mimetype='application/zip',
        as_attachment=True,
        download_name=f'qa_labels_{session_id}.zip'
    )


@app.get("/api/qa/export/audit/<session_id>")
def qa_export_audit(session_id):
    if session_id not in qa_session_store:
        return jsonify({"error": "Session not found"}), 404

    session = qa_session_store[session_id]

    audit_report = {
        "session_id": session_id,
        "summary": {
            "total_images": len(session["results"]),
            "total_ground_truth": sum(r["comparison"]["ground_truth_count"] for r in session["results"]),
            "total_detections": sum(r["comparison"]["detection_count"] for r in session["results"]),
            "total_issues": sum(len(r["comparison"]["issues"]) for r in session["results"]),
            "total_decisions": sum(len(r["decisions"]) for r in session["results"]),
        },
        "images": [],
    }

    for result in session["results"]:
        image_report = {
            "image_key": result["image_key"],
            "image_info": result["image_info"],
            "ground_truth_count": result["comparison"]["ground_truth_count"],
            "detection_count": result["comparison"]["detection_count"],
            "issues": result["comparison"]["issues"],
            "decisions": result["decisions"],
        }
        audit_report["images"].append(image_report)

    json_str = json.dumps(audit_report, indent=2)
    buffer = BytesIO(json_str.encode('utf-8'))
    buffer.seek(0)

    return send_file(
        buffer,
        mimetype='application/json',
        as_attachment=True,
        download_name=f'qa_audit_{session_id}.json'
    )


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
