#!/usr/bin/env bash
set -e
cd /workspace
if [ ! -d /workspace/MusePose ]; then
  git clone --depth 1 https://github.com/TMElyralab/MusePose.git /workspace/MusePose || true
fi
if [ -f /workspace/MusePose/requirements.txt ]; then
  pip install -r /workspace/MusePose/requirements.txt || true
fi
mkdir -p /workspace/models/musepose
cat > /workspace/models/musepose/PUT_WEIGHTS_HERE.txt <<'TXT'
ضع أوزان MusePose هنا أو اضبط MUSEPOSE_WEIGHTS إلى مسار الأوزان على RunPod Volume.
TXT
