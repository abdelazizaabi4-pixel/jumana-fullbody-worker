from __future__ import annotations
import base64, io, os
from pathlib import Path
from PIL import Image

def decode_image_base64(image_b64: str, out_path: Path) -> Path:
    if not image_b64:
        raise ValueError("image_base64_missing")
    if "," in image_b64 and image_b64[:40].lower().startswith("data:image"):
        image_b64 = image_b64.split(",", 1)[1]
    raw = base64.b64decode(image_b64)
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    return out_path

def image_info(path: Path) -> dict:
    img = Image.open(path)
    return {"width": img.width, "height": img.height, "mode": img.mode, "path": str(path)}
