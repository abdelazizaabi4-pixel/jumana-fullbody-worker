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
RUN pip install --no-cache-dir --no-deps easy-dwpose

COPY . /workspace

# ط·آ§ط·آ®ط·ع¾ط¸ظ¹ط·آ§ط·آ±ط¸ظ¹: ط¸ظ¹ط¸â€¦ط¸ئ’ط¸â€  ط¸ظ¾ط¸ظ¹ GitHub Actions ط·آ§ط¸â€‍ط·آ¨ط¸â€ ط·آ§ط·طŒ ط¸â€¦ط·آ¹ --build-arg INSTALL_MUSEPOSE=true ط·آ£ط¸ث† ط·ع¾ط·آ«ط·آ¨ط¸ظ¹ط·ع¾ MagicAnimate ط·آ¹ط¸â€‍ط¸â€° RunPod Volume
# ط¸â€‍ط¸ئ’ط¸â€  ط·آ§ط¸â€‍ط·آ£ط¸ظ¾ط·آ¶ط¸â€‍ ط·آ¹ط¸â€¦ط¸â€‍ط¸ظ¹ط¸â€¹ط·آ§ ط¸ث†ط·آ¶ط·آ¹ MusePose ط¸ث†ط·آ§ط¸â€‍ط·آ£ط¸ث†ط·آ²ط·آ§ط¸â€  ط·آ¹ط¸â€‍ط¸â€° RunPod Volume ط¸â€‍ط·ع¾ط¸â€ڑط¸â€‍ط¸ظ¹ط¸â€‍ ط·آ­ط·آ¬ط¸â€¦ Docker ط¸ث†ط·ع¾ط·آ³ط·آ±ط¸ظ¹ط·آ¹ ط·آ§ط¸â€‍ط·ع¾ط·آ´ط·ط›ط¸ظ¹ط¸â€‍.
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
