# GeoDraft YOLO QA

A lightweight Flask app for importing YOLO datasets in the browser and running a first-pass quality check.

## Current scope

- Import image files and YOLO label files separately
- Switch between `detect` and `segment` parsing modes
- Build a dataset inventory by basename
- Detect common issues:
  - missing image
  - missing label
  - duplicate basename
  - malformed label line
  - class id out of range
  - normalized coordinate out of range
- Preview the selected image with parsed annotations
- Export a JSON quality report

## Run

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python app.py
```

Open `http://127.0.0.1:5000`.

## Next steps

- Zip/folder-level dataset import
- More segment-specific validations
- COCO and YOLOv8 conversion helpers
- Save and reload QA sessions
