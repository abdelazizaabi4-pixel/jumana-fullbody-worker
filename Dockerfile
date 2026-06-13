FROM runpod/pytorch:2.1.1-py3.10-cuda12.1.1-devel-ubuntu22.04

WORKDIR /workspace
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV JUMANA_FULLBODY_WORKER_VERSION=V40_WORLD_CLASS_DIRECTOR
ENV JUMANA_NO_FAKE_BODY_MOTION=1
ENV DWPOSE_ENABLE_REAL=1
ENV DWPOSE_MODEL_ID=lllyasviel/Annotators
ENV HF_HOME=/workspace/models/huggingface
ENV MUSEPOSE_ROOT=/workspace/MusePose
ENV MUSEPOSE_WEIGHTS=/workspace/MusePose/pretrained_weights
ENV MUSEPOSE_TIMEOUT_SECONDS=1800
ENV MAGICANIMATE_ROOT=/workspace/MagicAnimate
ENV MAGICANIMATE_WEIGHTS=/workspace/models/magicanimate
ENV MAGICANIMATE_TIMEOUT_SECONDS=1800
ENV ANIMATEANYONE_ROOT=/workspace/AnimateAnyone
ENV ANIMATEANYONE_WEIGHTS=/workspace/models/animateanyone
ENV ANIMATEANYONE_TIMEOUT_SECONDS=1800
ENV JUMANA_ENGINE_READINESS_DOCTOR=1
ENV JUMANA_MUSEPOSE_E2E_LOCK=1
ENV MUSEPOSE_REQUIRE_COMMAND_TEMPLATE=1
ENV MUSEPOSE_MIN_OUTPUT_BYTES=100000
ENV JUMANA_MIN_FREE_DISK_GB=10

RUN apt-get update && apt-get install -y --no-install-recommends \
    git wget curl ffmpeg unzip libgl1 libglib2.0-0 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /workspace/requirements.txt
RUN pip install --upgrade pip && pip install -r /workspace/requirements.txt

COPY . /workspace

# ط§ط®طھظٹط§ط±ظٹ: ظٹظ…ظƒظ† ظپظٹ GitHub Actions ط§ظ„ط¨ظ†ط§ط، ظ…ط¹ --build-arg INSTALL_MUSEPOSE=true ط£ظˆ طھط«ط¨ظٹطھ MagicAnimate ط¹ظ„ظ‰ RunPod Volume
# ظ„ظƒظ† ط§ظ„ط£ظپط¶ظ„ ط¹ظ…ظ„ظٹظ‹ط§ ظˆط¶ط¹ MusePose ظˆط§ظ„ط£ظˆط²ط§ظ† ط¹ظ„ظ‰ RunPod Volume ظ„طھظ‚ظ„ظٹظ„ ط­ط¬ظ… Docker ظˆطھط³ط±ظٹط¹ ط§ظ„طھط´ط؛ظٹظ„.
ARG INSTALL_MUSEPOSE=false
RUN if [ "$INSTALL_MUSEPOSE" = "true" ]; then bash /workspace/scripts/install_musepose_reference.sh; fi

CMD ["python", "-u", "/workspace/handler.py"]

ENV JUMANA_FACE_GRAFT_COMPOSER=1

ENV JUMANA_DEEP_QUALITY_JUDGE=1
ENV JUMANA_QUALITY_STRICT_DEFAULT=1

ENV JUMANA_ENGINE_ENSEMBLE_ROUTER=1
ENV JUMANA_ENGINE_SELECTION_BEFORE_RUN=1

ENV JUMANA_MOTION_LIBRARY_PRO=1
ENV JUMANA_MOTION_VALIDATION_BEFORE_INFERENCE=1

ENV JUMANA_CHARACTER_CONSISTENCY=1
ENV JUMANA_CHARACTER_PROFILE_LOCK=1
