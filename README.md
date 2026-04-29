# YOLO Dataset Repair Workbench

Minimal scaffold for a higher-value project direction:

- upload images, labels, and class names
- scan common YOLO detect/segment problems
- aggregate issues by entry
- generate repair suggestions
- export the raw scan result

Current scope is intentionally narrow: the scan pipeline is real, while batch repair actions and repaired dataset export are the next implementation steps.

YOLO runtime baseline:

- dependencies include `ultralytics`, `torch`, `torchvision`, `torchaudio`
- default model path is `models/yolov8n.pt`
- environment check script: `.\.venv\Scripts\python.exe scripts\check_yolo_env.py`
