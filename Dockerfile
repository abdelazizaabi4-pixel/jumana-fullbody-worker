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
ENV MUSEPOSE_COMMAND_TEMPLATE="bash /workspace/scripts/run_musepose_v31_motion_tests.sh {root} {source_image} {motion_name} {motion_json} {pose_truth_json}"
ENV JUMANA_MIN_FREE_DISK_GB=10

RUN apt-get update && apt-get install -y --no-install-recommends \
    git wget curl ffmpeg unzip libgl1 libglib2.0-0 ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /workspace/requirements.txt
RUN pip install --upgrade pip && pip install -r /workspace/requirements.txt
RUN pip install --no-cache-dir --no-deps easy-dwpose

COPY . /workspace
RUN chmod +x /workspace/scripts/run_musepose_v31_pose_video.sh
RUN chmod +x /workspace/scripts/run_musepose_v31_motion_tests.sh

# ط·آ·ط¢آ§ط·آ·ط¢آ®ط·آ·ط¹آ¾ط·آ¸ط¸آ¹ط·آ·ط¢آ§ط·آ·ط¢آ±ط·آ¸ط¸آ¹: ط·آ¸ط¸آ¹ط·آ¸أ¢â‚¬آ¦ط·آ¸ط¦â€™ط·آ¸أ¢â‚¬آ  ط·آ¸ط¸آ¾ط·آ¸ط¸آ¹ GitHub Actions ط·آ·ط¢آ§ط·آ¸أ¢â‚¬â€چط·آ·ط¢آ¨ط·آ¸أ¢â‚¬آ ط·آ·ط¢آ§ط·آ·ط·إ’ ط·آ¸أ¢â‚¬آ¦ط·آ·ط¢آ¹ --build-arg INSTALL_MUSEPOSE=true ط·آ·ط¢آ£ط·آ¸ط«â€  ط·آ·ط¹آ¾ط·آ·ط¢آ«ط·آ·ط¢آ¨ط·آ¸ط¸آ¹ط·آ·ط¹آ¾ MagicAnimate ط·آ·ط¢آ¹ط·آ¸أ¢â‚¬â€چط·آ¸أ¢â‚¬آ° RunPod Volume
# ط·آ¸أ¢â‚¬â€چط·آ¸ط¦â€™ط·آ¸أ¢â‚¬آ  ط·آ·ط¢آ§ط·آ¸أ¢â‚¬â€چط·آ·ط¢آ£ط·آ¸ط¸آ¾ط·آ·ط¢آ¶ط·آ¸أ¢â‚¬â€چ ط·آ·ط¢آ¹ط·آ¸أ¢â‚¬آ¦ط·آ¸أ¢â‚¬â€چط·آ¸ط¸آ¹ط·آ¸أ¢â‚¬آ¹ط·آ·ط¢آ§ ط·آ¸ط«â€ ط·آ·ط¢آ¶ط·آ·ط¢آ¹ MusePose ط·آ¸ط«â€ ط·آ·ط¢آ§ط·آ¸أ¢â‚¬â€چط·آ·ط¢آ£ط·آ¸ط«â€ ط·آ·ط¢آ²ط·آ·ط¢آ§ط·آ¸أ¢â‚¬آ  ط·آ·ط¢آ¹ط·آ¸أ¢â‚¬â€چط·آ¸أ¢â‚¬آ° RunPod Volume ط·آ¸أ¢â‚¬â€چط·آ·ط¹آ¾ط·آ¸أ¢â‚¬ع‘ط·آ¸أ¢â‚¬â€چط·آ¸ط¸آ¹ط·آ¸أ¢â‚¬â€چ ط·آ·ط¢آ­ط·آ·ط¢آ¬ط·آ¸أ¢â‚¬آ¦ Docker ط·آ¸ط«â€ ط·آ·ط¹آ¾ط·آ·ط¢آ³ط·آ·ط¢آ±ط·آ¸ط¸آ¹ط·آ·ط¢آ¹ ط·آ·ط¢آ§ط·آ¸أ¢â‚¬â€چط·آ·ط¹آ¾ط·آ·ط¢آ´ط·آ·ط·â€؛ط·آ¸ط¸آ¹ط·آ¸أ¢â‚¬â€چ.
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
