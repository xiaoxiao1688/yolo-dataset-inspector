from flask import Flask, jsonify, render_template, request

from repair_workbench.scanner import scan_dataset
from repair_workbench.yolo_runtime import environment_summary


app = Flask(__name__)


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


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
