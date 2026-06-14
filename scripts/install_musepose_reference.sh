#!/usr/bin/env bash
set -e
cd /workspace
echo [JUMANA] Installing MusePose ROOT and REAL weights...
if [ ! -d /workspace/MusePose ]; then
  git clone --depth 1 https://github.com/TMElyralab/MusePose.git /workspace/MusePose
fi
cd /workspace/MusePose
mkdir -p ./pretrained_weights ./pretrained_weights/dwpose
huggingface-cli download TMElyralab/MusePose --local-dir ./pretrained_weights --include MusePose/*.pth
huggingface-cli download stabilityai/sd-vae-ft-mse --local-dir ./pretrained_weights/sd-vae-ft-mse --include config.json --include diffusion_pytorch_model.bin
wget -q -O ./pretrained_weights/sd-vae-ft-mse/config.json https://huggingface.co/stabilityai/sd-vae-ft-mse/resolve/main/config.json
huggingface-cli download lambdalabs/sd-image-variations-diffusers --local-dir ./pretrained_weights/sd-image-variations-diffusers --include unet/*
huggingface-cli download lambdalabs/sd-image-variations-diffusers --local-dir ./pretrained_weights --include image_encoder/*
huggingface-cli download yzd-v/DWPose --local-dir ./pretrained_weights/dwpose --include dw-ll_ucoco_384.pth
wget -q -O ./pretrained_weights/dwpose/yolox_l_8x8_300e_coco.pth https://download.openmmlab.com/mmdetection/v2.0/yolox/yolox_l_8x8_300e_coco/yolox_l_8x8_300e_coco_20211126_140236-d3bd2b23.pth
echo [JUMANA] Verifying required MusePose weight files...
MISSING=0
check_file() {
  if [ -f "$1" ]; then
    echo "[OK] $1"
  else
    echo "[MISSING] $1"
    MISSING=1
  fi
}
check_file ./pretrained_weights/sd-vae-ft-mse/config.json
check_file ./pretrained_weights/sd-vae-ft-mse/diffusion_pytorch_model.bin
check_file ./pretrained_weights/image_encoder/config.json
check_file ./pretrained_weights/image_encoder/pytorch_model.bin
check_file ./pretrained_weights/sd-image-variations-diffusers/unet/config.json
check_file ./pretrained_weights/sd-image-variations-diffusers/unet/diffusion_pytorch_model.bin
check_file ./pretrained_weights/MusePose/denoising_unet.pth
check_file ./pretrained_weights/MusePose/motion_module.pth
check_file ./pretrained_weights/MusePose/pose_guider.pth
check_file ./pretrained_weights/MusePose/reference_unet.pth
check_file ./pretrained_weights/dwpose/dw-ll_ucoco_384.pth
check_file ./pretrained_weights/dwpose/yolox_l_8x8_300e_coco.pth
if [ "$MISSING" = "1" ]; then
  echo [JUMANA] Some MusePose required files are missing.
  find ./pretrained_weights -maxdepth 4 -type f | sort | head -300
  exit 1
fi
find ./pretrained_weights -maxdepth 3 -type f | sort | head -200
echo [JUMANA] MusePose REAL weights installed.
