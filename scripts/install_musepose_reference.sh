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
huggingface-cli download lambdalabs/sd-image-variations-diffusers --local-dir ./pretrained_weights/sd-image-variations-diffusers --include unet/*
huggingface-cli download lambdalabs/sd-image-variations-diffusers --local-dir ./pretrained_weights --include image_encoder/*
huggingface-cli download yzd-v/DWPose --local-dir ./pretrained_weights/dwpose --include dw-ll_ucoco_384.pth
wget -q -O ./pretrained_weights/dwpose/yolox_l_8x8_300e_coco.pth https://download.openmmlab.com/mmdetection/v2.0/yolox/yolox_l_8x8_300e_coco/yolox_l_8x8_300e_coco_20211126_140236-d3bd2b23.pth
echo [JUMANA] Verifying required MusePose weight files...
test -f ./pretrained_weights/sd-vae-ft-mse/config.json
test -f ./pretrained_weights/sd-vae-ft-mse/diffusion_pytorch_model.bin
test -f ./pretrained_weights/image_encoder/config.json
test -f ./pretrained_weights/image_encoder/pytorch_model.bin
test -f ./pretrained_weights/sd-image-variations-diffusers/unet/config.json
test -f ./pretrained_weights/sd-image-variations-diffusers/unet/diffusion_pytorch_model.bin
test -f ./pretrained_weights/MusePose/denoising_unet.pth
test -f ./pretrained_weights/MusePose/motion_module.pth
test -f ./pretrained_weights/MusePose/pose_guider.pth
test -f ./pretrained_weights/MusePose/reference_unet.pth
test -f ./pretrained_weights/dwpose/dw-ll_ucoco_384.pth
test -f ./pretrained_weights/dwpose/yolox_l_8x8_300e_coco.pth
find ./pretrained_weights -maxdepth 3 -type f | sort | head -200
echo [JUMANA] MusePose REAL weights installed.
