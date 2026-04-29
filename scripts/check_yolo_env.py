from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from repair_workbench.yolo_runtime import environment_summary, get_device, get_model_path, load_model  # noqa: E402


def main() -> int:
    summary = environment_summary()
    print(json.dumps({"phase": "environment", **summary}, indent=2))

    model = load_model(download_if_missing=True)
    model_path = get_model_path()
    if not Path(model_path).exists():
        raise FileNotFoundError(f"Model expected at {model_path} after load, but it is missing.")

    dummy_image = np.zeros((640, 640, 3), dtype=np.uint8)
    results = model.predict(dummy_image, device=get_device(), verbose=False)
    first = results[0]
    output = {
        "phase": "inference",
        "model_name": getattr(model, "ckpt_path", str(model_path)),
        "boxes": int(len(first.boxes)) if getattr(first, "boxes", None) is not None else 0,
        "masks": int(len(first.masks)) if getattr(first, "masks", None) is not None else 0,
        "probs": bool(getattr(first, "probs", None) is not None),
    }
    print(json.dumps(output, indent=2))
    print("YOLO environment check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
