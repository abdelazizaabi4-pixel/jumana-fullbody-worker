#!/usr/bin/env bash
set -e
ROOT="$1"
SOURCE_IMAGE="$2"
POSE_TRUTH_JSON="$3"
cd "$ROOT"
mkdir -p assets/images assets/poses/align
cp "$SOURCE_IMAGE" assets/images/ref.png
POSE=$(python - "$POSE_TRUTH_JSON" "$SOURCE_IMAGE" <<PY
import json, sys, os
pose_truth_json=sys.argv[1]
source_image=sys.argv[2]
pose=""
try:
    with open(pose_truth_json,"r",encoding="utf-8") as f:
        d=json.load(f)
    pose=d.get("pose_render_path") or d.get("pose_image_path") or d.get("render_path") or ""
except Exception:
    pose=""
print(pose if pose and os.path.exists(pose) else source_image)
PY
)
echo "[JUMANA] Using pose image: $POSE"
ffmpeg -y -loop 1 -i "$POSE" -t 10 -r 30 -vf "scale=512:512,format=yuv420p" assets/poses/align/img_ref_video_dance.mp4
test -f assets/poses/align/img_ref_video_dance.mp4
python -u test_stage_2.py --config configs/test_stage_2.yaml -W 512 -H 512
