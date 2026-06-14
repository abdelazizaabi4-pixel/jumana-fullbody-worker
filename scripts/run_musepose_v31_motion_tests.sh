#!/usr/bin/env bash
set -e

ROOT="$1"
SOURCE_IMAGE="$2"
MOTION_NAME="$3"
MOTION_JSON="$4"
POSE_TRUTH_JSON="$5"

cd "$ROOT"
mkdir -p assets/images assets/poses/align assets/poses/align/frames
rm -f assets/poses/align/frames/*.png

cp "$SOURCE_IMAGE" assets/images/ref.png

POSE=$(python - "$POSE_TRUTH_JSON" "$SOURCE_IMAGE" <<'PY'
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

echo "[JUMANA] Motion test runner2"
echo "[JUMANA] Motion name: $MOTION_NAME"
echo "[JUMANA] Using pose image: $POSE"

python - "$POSE" "$MOTION_NAME" <<'PY'
import cv2, sys, os, math, numpy as np

pose_path = sys.argv[1]
motion = (sys.argv[2] or "standing_idle").strip().lower()
img = cv2.imread(pose_path, cv2.IMREAD_COLOR)
if img is None:
    raise SystemExit(f"Cannot read pose image: {pose_path}")

base = cv2.resize(img, (512, 512), interpolation=cv2.INTER_AREA)
outdir = "assets/poses/align/frames"
os.makedirs(outdir, exist_ok=True)

def clean_mask(roi):
    return (roi[:,:,0].astype(np.int16) + roi[:,:,1].astype(np.int16) + roi[:,:,2].astype(np.int16)) > 35

def move_roi(frame, source, x1, y1, x2, y2, dx, dy):
    x1=max(0,x1); y1=max(0,y1); x2=min(512,x2); y2=min(512,y2)
    roi = source[y1:y2, x1:x2].copy()
    mask = clean_mask(roi)
    frame[y1:y2, x1:x2][mask] = 0
    h,w = roi.shape[:2]
    M = np.float32([[1,0,dx],[0,1,dy]])
    moved = cv2.warpAffine(roi, M, (w,h), flags=cv2.INTER_LINEAR, borderValue=(0,0,0))
    mask2 = clean_mask(moved)
    target = frame[y1:y2, x1:x2]
    target[mask2] = moved[mask2]

def rotate_roi(frame, source, x1, y1, x2, y2, angle, dy=0):
    x1=max(0,x1); y1=max(0,y1); x2=min(512,x2); y2=min(512,y2)
    roi = source[y1:y2, x1:x2].copy()
    mask = clean_mask(roi)
    frame[y1:y2, x1:x2][mask] = 0
    h,w = roi.shape[:2]
    M = cv2.getRotationMatrix2D((w//2, h//2), angle, 1.0)
    M[1,2] += dy
    moved = cv2.warpAffine(roi, M, (w,h), flags=cv2.INTER_LINEAR, borderValue=(0,0,0))
    mask2 = clean_mask(moved)
    target = frame[y1:y2, x1:x2]
    target[mask2] = moved[mask2]

frames = 150
for i in range(frames):
    t = i / max(1, frames - 1)
    s = math.sin(2 * math.pi * t)
    ramp = math.sin(math.pi * t)
    frame = base.copy()

    if motion in ("head_turn_left", "head_turn", "turn_head_left_01"):
        rotate_roi(frame, base, 160, 20, 355, 185, -10 * ramp, 0)

    elif motion in ("listener_nod", "listener_nod_01", "nod"):
        rotate_roi(frame, base, 160, 20, 355, 185, 0, int(8 * s))

    elif motion in ("right_hand_explain", "speaker_gesture_01", "right_hand"):
        move_roi(frame, base, 0, 115, 270, 410, int(8*s), int(-34*ramp))
        rotate_roi(frame, base, 0, 115, 270, 410, -8*s, int(-8*ramp))

    elif motion in ("both_hands_explain", "speaker_gesture_02", "both_hands"):
        move_roi(frame, base, 0, 115, 260, 410, int(-12*s), int(-24*ramp))
        move_roi(frame, base, 252, 115, 512, 410, int(12*s), int(-24*ramp))

    elif motion in ("raise_hand_greeting", "raise_hand", "raise_hand_01"):
        move_roi(frame, base, 0, 80, 280, 420, int(-6*s), int(-58*ramp))

    elif motion in ("walking_lite", "walking_lite_01", "walk", "walking"):
        move_roi(frame, base, 0, 285, 260, 512, int(14*s), int(5*abs(s)))
        move_roi(frame, base, 252, 285, 512, 512, int(-14*s), int(5*abs(s)))
        move_roi(frame, base, 105, 120, 410, 330, int(4*s), 0)

    else:
        move_roi(frame, base, 95, 80, 420, 360, int(2*s), int(3*s))

    cv2.imwrite(os.path.join(outdir, f"{i:05d}.png"), frame)

print(f"[JUMANA] Generated {frames} dynamic pose frames for motion={motion}")
PY

ffmpeg -y -framerate 30 -i assets/poses/align/frames/%05d.png -r 30 -pix_fmt yuv420p assets/poses/align/img_ref_video_dance.mp4
test -f assets/poses/align/img_ref_video_dance.mp4

python -u test_stage_2.py --config configs/test_stage_2.yaml -W 512 -H 512
