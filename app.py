from flask import Flask, jsonify, render_template, request, send_file
from io import BytesIO
import json
import uuid

from repair_workbench.scanner import scan_dataset
from repair_workbench.yolo_runtime import environment_summary
from repair_workbench.qa_engine import process_qa_task


app = Flask(__name__)

qa_session_store = {}


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

    for image_file in image_files:
        image_key = image_file.filename.rsplit(".", 1)[0].lower()
        label_file = label_map.get(image_key)

        try:
            qa_result = process_qa_task(
                image_file=image_file,
                label_file=label_file,
                classes_text=classes_text,
                conf_threshold=conf_threshold,
                iou_threshold=iou_threshold,
            )
            qa_result["image_key"] = image_key
            qa_result["decisions"] = []
            results.append(qa_result)
        except Exception as e:
            return jsonify({"error": f"Processing failed for {image_file.filename}: {str(e)}"}), 500

    qa_session_store[session_id] = {
        "session_id": session_id,
        "results": results,
        "class_names": results[0]["class_names"] if results else [],
    }

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

    return jsonify({"status": "ok", "message": f"Decision '{decision}' recorded"})


def build_final_labels(session):
    all_labels = {}

    for result in session["results"]:
        image_key = result["image_key"]
        final_boxes = []

        decisions = {d["issue_index"]: d["decision"] for d in result["decisions"]}

        class_conflict_gt_indices = set()
        class_conflict_decisions = {}

        for issue_idx, issue in enumerate(result["comparison"]["issues"]):
            if issue.get("type") == "class_conflict":
                if issue_idx in decisions:
                    gt_box = issue.get("ground_truth", {})
                    if "box_index" in gt_box:
                        class_conflict_gt_indices.add(gt_box["box_index"])
                        class_conflict_decisions[gt_box["box_index"]] = {
                            "decision": decisions[issue_idx],
                            "issue": issue,
                        }

        for gt_idx, gt_box in enumerate(result["ground_truth"]):
            if gt_idx in class_conflict_gt_indices:
                continue

            keep_gt = True

            for issue_idx, issue in enumerate(result["comparison"]["issues"]):
                if issue.get("source") == "ground_truth" and issue.get("box_index") == gt_idx:
                    if issue_idx in decisions:
                        if decisions[issue_idx] == "reject":
                            keep_gt = False
                        break

            if keep_gt:
                final_boxes.append({
                    "class_id": gt_box["class_id"],
                    "x_center": gt_box["x_center"],
                    "y_center": gt_box["y_center"],
                    "width": gt_box["width"],
                    "height": gt_box["height"],
                })

        for gt_idx in class_conflict_gt_indices:
            if gt_idx >= len(result["ground_truth"]):
                continue

            gt_box = result["ground_truth"][gt_idx]
            decision_info = class_conflict_decisions.get(gt_idx, {})
            decision = decision_info.get("decision")
            issue = decision_info.get("issue", {})

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
            elif decision == "keep":
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

        for det_idx, det_box in enumerate(result["detections"]):
            add_det = False

            for issue_idx, issue in enumerate(result["comparison"]["issues"]):
                if issue.get("type") == "missing_label" and issue.get("source") == "detection" and issue.get("box_index") == det_idx:
                    if issue_idx in decisions and decisions[issue_idx] == "accept":
                        add_det = True
                        break

            if add_det:
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
