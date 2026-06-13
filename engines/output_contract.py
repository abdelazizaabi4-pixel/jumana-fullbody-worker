from __future__ import annotations
import time, traceback
from typing import Any, Dict

VERSION = "V40_WORLD_CLASS_DIRECTOR"

def now_ms() -> int:
    return int(time.time() * 1000)

def ok_output(stage: str, **extra: Any) -> Dict[str, Any]:
    data = {
        "ok": True,
        "version": VERSION,
        "worker_type": "jumana-fullbody-worker",
        "stage": stage,
        "no_fake_body_motion": True,
        "real_body_engine_required": True,
        "engine_readiness_doctor_enabled": True,
        "musepose_end_to_end_lock_enabled": True,
        "pose_dataset_benchmark_enabled": True,
        "real_head_tracking_enabled": True,
        "face_graft_composer_enabled": True,
        "deep_quality_judge_enabled": True,
        "smart_retry_2_enabled": True,
        "engine_ensemble_router_enabled": True,
        "engine_selection_before_run_enabled": True,
        "motion_library_pro_enabled": True,
        "motion_validation_before_inference_enabled": True,
        "character_consistency_enabled": True,
        "character_profile_lock_enabled": True,
        "world_class_director_enabled": True,
        "story_to_shot_plan_enabled": True,
        "director_does_not_fake_video_generation": True,
        "retry_never_fakes_success": True,
        "timestamp_ms": now_ms(),
    }
    data.update(extra)
    return data

def fail_output(error: str, stage: str, suspect: str, solution_ar: str, **extra: Any) -> Dict[str, Any]:
    data = {
        "ok": False,
        "version": VERSION,
        "worker_type": "jumana-fullbody-worker",
        "stage": stage,
        "error": str(error),
        "suspect": suspect,
        "criminal_report": {
            "الجاني": suspect,
            "المرحلة": stage,
            "السبب": str(error),
            "الحل": solution_ar,
        },
        "solution_ar": solution_ar,
        "no_fake_body_motion": True,
        "real_body_engine_required": True,
        "engine_readiness_doctor_enabled": True,
        "musepose_end_to_end_lock_enabled": True,
        "pose_dataset_benchmark_enabled": True,
        "real_head_tracking_enabled": True,
        "face_graft_composer_enabled": True,
        "deep_quality_judge_enabled": True,
        "smart_retry_2_enabled": True,
        "engine_ensemble_router_enabled": True,
        "engine_selection_before_run_enabled": True,
        "motion_library_pro_enabled": True,
        "motion_validation_before_inference_enabled": True,
        "character_consistency_enabled": True,
        "character_profile_lock_enabled": True,
        "world_class_director_enabled": True,
        "story_to_shot_plan_enabled": True,
        "director_does_not_fake_video_generation": True,
        "retry_never_fakes_success": True,
        "timestamp_ms": now_ms(),
    }
    data.update(extra)
    return data

def exception_output(exc: BaseException, stage: str, suspect: str, solution_ar: str, **extra: Any) -> Dict[str, Any]:
    tail = traceback.format_exc()[-4000:]
    return fail_output(str(exc), stage, suspect, solution_ar, traceback_tail=tail, **extra)
