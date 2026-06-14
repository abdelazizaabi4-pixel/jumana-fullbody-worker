#!/usr/bin/env bash
set -e
cd /workspace
echo [JUMANA] Installing MusePose ROOT only...
if [ ! -d /workspace/MusePose ]; then
  git clone --depth 1 https://github.com/TMElyralab/MusePose.git /workspace/MusePose
fi
mkdir -p /workspace/MusePose/pretrained_weights
echo PUT_MUSEPOSE_WEIGHTS_HERE_/workspace/MusePose/pretrained_weights > /workspace/MusePose/pretrained_weights/PUT_WEIGHTS_HERE.txt
echo [JUMANA] MusePose ROOT installed at /workspace/MusePose
ls -la /workspace/MusePose | head -50
