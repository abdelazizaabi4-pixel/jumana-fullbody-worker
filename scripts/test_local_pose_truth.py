import base64, json, sys
from pathlib import Path
from handler import handle

if len(sys.argv) < 2:
    print('Usage: python scripts/test_local_pose_truth.py path/to/image.png')
    raise SystemExit(2)
img = Path(sys.argv[1])
b64 = base64.b64encode(img.read_bytes()).decode('utf-8')
print(json.dumps(handle({'input': {'task': 'pose_truth', 'image_base64': b64}}), ensure_ascii=False, indent=2)[:8000])
