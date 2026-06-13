FROM runpod/pytorch:2.1.0-py3.10-cuda12.1.0-devel

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

# اختياري: يمكن في GitHub Actions البناء مع --build-arg INSTALL_MUSEPOSE=true أو تثبيت MagicAnimate على RunPod Volume
# لكن الأفضل عمليًا وضع MusePose والأوزان على RunPod Volume لتقليل حجم Docker وتسريع التشغيل.
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
