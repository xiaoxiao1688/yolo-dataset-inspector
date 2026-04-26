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

## System Requirements

- Python 3.10+ (3.12 recommended)
- Windows (tested on Windows 10/11)
- Modern web browser (Chrome, Edge, Firefox)

## Quick Start

### Option 1: Use startup scripts (Recommended)

Double-click or run one of the following scripts:

```powershell
# PowerShell
.\start.ps1
```

```batch
# Command Prompt
start.bat
```

The scripts will:
1. Automatically detect Python installation (even if not in PATH)
2. Skip Windows Store Python shortcuts
3. Create virtual environment if not exists
4. Install all dependencies
5. Run environment self-check
6. Start the Flask server

### Option 2: Manual setup

```powershell
# Create virtual environment
python -m venv .venv

# Activate and install dependencies
.venv\Scripts\python -m pip install -r requirements.txt

# Run self-check
.venv\Scripts\python -c "import sys, json; print(json.dumps({'python': sys.version, 'flask_ok': __import__('flask').__version__}, indent=2))"

# Start the application
.venv\Scripts\python app.py
```

Open `http://127.0.0.1:5000` in your browser.

## Environment Self-Check

The application includes built-in environment self-check:

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Basic health check with environment info |
| `/api/env` | GET | Detailed environment information |
| `/api/self-check` | GET | Full self-check including frontend features |
| `/api/formats` | GET | YOLO format documentation |
| `/api/validate/detect` | POST | Validate YOLO detect format lines |
| `/api/validate/segment` | POST | Validate YOLO segment format lines |

### Self-Check Example

```
GET /api/self-check
```

Response:
```json
{
  "status": "ok",
  "checks": {
    "environment": {
      "python_version": "3.12.0",
      "python_path": "...",
      "requirements": {
        "flask": {
          "status": "ok",
          "version": "3.0.3",
          "description": "Flask - Web framework"
        }
      }
    },
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
    }
  }
}
```

## YOLO Format Support

### Detect (Object Detection)

Format: `class_id x_center y_center width height`

Example:
```
0 0.5 0.5 0.3 0.4
1 0.2 0.3 0.15 0.2
```

- All coordinates are normalized (0.0 to 1.0)
- class_id: 0-based integer
- x_center, y_center: Center point of the bounding box
- width, height: Dimensions of the bounding box

### Segment (Instance Segmentation)

Format: `class_id x1 y1 x2 y2 x3 y3 ...`

Example:
```
0 0.1 0.2 0.3 0.4 0.5 0.6 0.2 0.8
1 0.5 0.1 0.6 0.2 0.7 0.1 0.6 0.05
```

- All coordinates are normalized (0.0 to 1.0)
- class_id: 0-based integer
- Pairs of x, y coordinates forming a polygon
- Minimum 3 points required (7 values total)

## Validation API Usage

### Validate Detect Format

```
POST /api/validate/detect
Content-Type: application/json

{
  "lines": [
    "0 0.5 0.5 0.3 0.4",
    "1 1.5 0.5 0.3 0.4"
  ],
  "class_count": 2
}
```

### Validate Segment Format

```
POST /api/validate/segment
Content-Type: application/json

{
  "lines": [
    "0 0.1 0.2 0.3 0.4 0.5 0.6 0.2 0.8",
    "1 0.5 0.1 0.6 0.2"
  ],
  "class_count": 2
}
```

## Troubleshooting

### Python Not Found

If you see "Python not found" error:

1. **Install Python**: Download from https://www.python.org/downloads/
   - Check "Add Python to PATH" during installation
   - Recommended version: Python 3.10+

2. **Or use existing installation**: The startup scripts automatically search in:
   - `%LOCALAPPDATA%\Programs\Python\Python312\`
   - `%LOCALAPPDATA%\Programs\Python\Python311\`
   - `%LOCALAPPDATA%\Programs\Python\Python310\`
   - `C:\Program Files\Python3*\`
   - `C:\Python3*\`

### Windows Store Python Shortcut

The scripts automatically skip Windows Store Python shortcuts. If Python was installed via Windows Store:

1. Uninstall Windows Store Python
2. Install Python from python.org (official installer)
3. Or enable "App execution aliases" for Python in Windows Settings

### Virtual Environment Issues

If `.venv` is corrupted:

```powershell
# Delete and recreate
Remove-Item -Recurse -Force .venv
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

## Project Structure

```
geodraft/
├── app.py                 # Flask application (enhanced with self-check APIs)
├── requirements.txt       # Python dependencies
├── start.bat             # Windows batch startup script (enhanced)
├── start.ps1             # PowerShell startup script (enhanced)
├── README.md             # This file
├── static/
│   ├── css/
│   │   └── styles.css    # Application styles
│   └── js/
│       └── app.js        # Frontend application (YOLO parsing, preview, export)
├── templates/
│   └── index.html        # Main HTML template
└── data/                 # Data directory (for future use)
```

## Frontend Features

The frontend (`static/js/app.js`) provides:

1. **File Import**
   - Image files (multiple selection)
   - Label files (multiple selection)
   - Class names configuration

2. **Task Modes**
   - **Detect**: Bounding box format
   - **Segment**: Polygon format

3. **Analysis**
   - Dataset inventory by basename
   - Issue detection (missing files, duplicates, format errors)
   - Severity-based sorting

4. **Preview**
   - Image display with annotation overlay
   - Bounding boxes for detect mode
   - Polygons for segment mode

5. **Report Export**
   - JSON format
   - Includes all dataset entries and issues
   - Task type and class name metadata

## Next steps

- Zip/folder-level dataset import
- More segment-specific validations
- COCO and YOLOv8 conversion helpers
- Save and reload QA sessions
- Real-time validation feedback
- Batch annotation editing
