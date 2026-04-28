from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ULTRALYTICS_CONFIG_ROOT = PROJECT_ROOT / ".ultralytics"
ULTRALYTICS_CONFIG_ROOT.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("YOLO_CONFIG_DIR", str(ULTRALYTICS_CONFIG_ROOT))

import torch  # noqa: E402
from ultralytics import YOLO  # noqa: E402

DEFAULT_MODEL_PATH = PROJECT_ROOT / "models" / "yolov8n.pt"


def get_model_path() -> Path:
    configured = os.getenv("YOLO_MODEL_PATH", "").strip()
    if configured:
        path = Path(configured)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return path
    return DEFAULT_MODEL_PATH


def get_device() -> str:
    configured = os.getenv("YOLO_DEVICE", "").strip().lower()
    if configured:
        return configured
    return "cuda" if torch.cuda.is_available() else "cpu"


def ensure_model_dir() -> Path:
    model_path = get_model_path()
    model_path.parent.mkdir(parents=True, exist_ok=True)
    return model_path


def load_model(download_if_missing: bool = True):
    model_path = ensure_model_dir()
    if model_path.exists():
        return YOLO(str(model_path))

    if not download_if_missing:
        raise FileNotFoundError(f"YOLO model not found at {model_path}")

    model = YOLO("yolov8n.pt")
    downloaded_source = Path(model.ckpt_path) if getattr(model, "ckpt_path", None) else None
    if downloaded_source and downloaded_source.exists() and downloaded_source.resolve() != model_path.resolve():
        model_path.write_bytes(downloaded_source.read_bytes())
        model = YOLO(str(model_path))
    return model


def environment_summary() -> dict:
    return {
        "device": get_device(),
        "cuda_available": torch.cuda.is_available(),
        "torch_version": torch.__version__,
        "model_path": str(get_model_path()),
    }
