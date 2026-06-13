from __future__ import annotations
import os, json, time, traceback
from pathlib import Path
from typing import Any, Dict

try:
    import runpod
except Exception:
    runpod = None

from engines.output_contract import ok_output, fail_output, exception_output, VERSION
from engines.input_tools import decode_image_base64, image_info
from engines.fullbody_router import FullBodyRouter

WORK = Path(os.environ.get("JUMANA_WORKDIR", "/workspace/outputs"))
WORK.mkdir(parents=True, exist_ok=True)

def log(msg: str, **kw: Any):
    print(json.dumps({"event": msg, "version": VERSION, **kw}, ensure_ascii=False), flush=True)

def handle(job: Dict[str, Any]) -> Dict[str, Any]:
    log("FULLBODY_HANDLER_START")
    try:
        inp = job.get("input") if isinstance(job, dict) else {}
        if not isinstance(inp, dict):
            inp = {}
        task = inp.get("task", "diagnostic")
        log("JOB_RECEIVED", task=task, keys=list(inp.keys()))

        router = FullBodyRouter()

        if task == "ping":
            return ok_output("ping", message="jumana-fullbody-worker v40 World-Class Director alive", no_fake_body_motion=True)

        if task == "diagnostic":
            return router.diagnostic()

        if task in {"engine_readiness", "readiness", "preflight", "readiness_gate"}:
            return router.readiness(inp)

        if task in {"musepose_lock_status", "musepose_preflight", "musepose_e2e_preflight"}:
            return router.musepose_lock_status()

        if task in {"benchmark_template", "v34_benchmark_template", "golden_test_suite_template"}:
            return router.benchmark_template()

        if task in {"pose_dataset_benchmark", "v34_benchmark", "dataset_benchmark", "golden_benchmark"}:
            return router.pose_dataset_benchmark(inp)


        if task in {"head_tracking_status", "real_head_tracking_status"}:
            return router.head_tracking_status()

        if task in {"head_tracking_template", "head_track_template"}:
            return router.head_tracking_template()

        if task in {"head_track_video", "real_head_tracking"}:
            return router.head_track_video(inp)

        if task in {"face_graft_status", "v34_face_graft_status"}:
            return router.face_graft_status()

        if task in {"face_graft_template", "v34_face_graft_template"}:
            return router.face_graft_template()

        if task in {"face_graft_video", "v34_face_graft", "face_graft_compose"}:
            return router.face_graft_video(inp)

        if task in {"deep_quality_status", "v35_deep_quality_status"}:
            return router.deep_quality_status()

        if task in {"deep_quality_template", "v35_deep_quality_template"}:
            return router.deep_quality_template()

        if task in {"deep_quality_judge", "v35_deep_quality", "quality_judge", "judge_final_video"}:
            return router.deep_quality_judge(inp)

        if task in {"smart_retry_status", "v36_smart_retry_status"}:
            return router.smart_retry_status()

        if task in {"smart_retry_template", "v36_smart_retry_template"}:
            return router.smart_retry_template()

        if task in {"smart_retry_plan", "v36_smart_retry_plan", "retry_plan"}:
            return router.smart_retry_plan(inp)

        if task in {"smart_retry_execute", "v36_smart_retry", "smart_retry_2", "retry_execute"}:
            return router.smart_retry_execute(inp)

        if task in {"engine_ensemble_status", "v37_engine_ensemble_status"}:
            return router.engine_ensemble_status()

        if task in {"engine_ensemble_template", "v37_engine_ensemble_template"}:
            return router.engine_ensemble_template()

        if task in {"engine_ensemble_plan", "v37_engine_ensemble_plan", "engine_route_plan", "route_engine"}:
            return router.engine_ensemble_plan(inp)

        if task in {"engine_ensemble_execute", "v37_engine_ensemble", "ensemble_execute"}:
            return router.engine_ensemble_execute(inp)

        if task in {"motion_library_status", "v38_motion_library_status"}:
            return router.motion_library_status()

        if task in {"motion_library_list", "v38_motion_library_list", "list_motions"}:
            return router.motion_library_list(inp)

        if task in {"motion_library_template", "v38_motion_library_template"}:
            return router.motion_library_template()

        if task in {"motion_library_select", "v38_motion_library_select", "select_motion"}:
            return router.motion_library_select(inp)

        if task in {"motion_library_validate", "v38_motion_library_validate", "validate_motion"}:
            return router.motion_library_validate(inp)

        if task in {"motion_library_execute", "v38_motion_library_execute", "motion_execute"}:
            return router.motion_library_execute(inp)

        if task in {"character_consistency_status", "v39_character_consistency_status"}:
            return router.character_consistency_status()

        if task in {"character_consistency_template", "character_profile_template", "v39_character_consistency_template"}:
            return router.character_consistency_template()

        if task in {"character_create_profile", "create_character_profile", "v39_character_create_profile"}:
            return router.character_create_profile(inp)

        if task in {"character_compare", "compare_character", "v39_character_compare"}:
            return router.character_compare(inp)

        if task in {"character_consistency_gate", "character_gate", "v39_character_consistency_gate"}:
            return router.character_consistency_gate(inp)

        if task in {"world_director_status", "v40_world_director_status", "world_class_director_status"}:
            return router.world_director_status()

        if task in {"world_director_template", "v40_world_director_template", "world_class_director_template"}:
            return router.world_director_template()

        if task in {"world_director_plan", "v40_world_director_plan", "world_class_director_plan", "story_to_shot_plan"}:
            return router.world_director_plan(inp)

        if task in {"world_director_execute", "v40_world_director", "world_class_director_execute", "story_execute"}:
            return router.world_director_execute(inp)

        supported = {"pose_truth", "dwpose_truth", "real_full_body_video", "fullbody_video", "body_motion", "musepose_motion_test", "magicanimate_motion_test", "animateanyone_motion_test", "engine_readiness", "readiness", "preflight", "readiness_gate", "musepose_lock_status", "musepose_preflight", "musepose_e2e_preflight", "musepose_e2e_lock_test", "pose_dataset_benchmark", "v34_benchmark", "dataset_benchmark", "golden_benchmark", "benchmark_template", "v34_benchmark_template", "golden_test_suite_template", "head_tracking_status", "head_tracking_template", "head_track_video", "real_head_tracking", "face_graft_status", "face_graft_template", "face_graft_video", "v34_face_graft", "face_graft_compose", "deep_quality_status", "deep_quality_template", "deep_quality_judge", "v35_deep_quality", "quality_judge", "judge_final_video", "smart_retry_status", "v36_smart_retry_status", "smart_retry_template", "v36_smart_retry_template", "smart_retry_plan", "v36_smart_retry_plan", "retry_plan", "smart_retry_execute", "v36_smart_retry", "smart_retry_2", "retry_execute", "engine_ensemble_status", "v37_engine_ensemble_status", "engine_ensemble_template", "v37_engine_ensemble_template", "engine_ensemble_plan", "v37_engine_ensemble_plan", "engine_route_plan", "route_engine", "engine_ensemble_execute", "v37_engine_ensemble", "ensemble_execute", "motion_library_status", "v38_motion_library_status", "motion_library_list", "v38_motion_library_list", "list_motions", "motion_library_template", "v38_motion_library_template", "motion_library_select", "v38_motion_library_select", "select_motion", "motion_library_validate", "v38_motion_library_validate", "validate_motion", "motion_library_execute", "v38_motion_library_execute", "motion_execute", "character_consistency_status", "v39_character_consistency_status", "character_consistency_template", "character_profile_template", "v39_character_consistency_template", "character_create_profile", "create_character_profile", "v39_character_create_profile", "character_compare", "compare_character", "v39_character_compare", "character_consistency_gate", "character_gate", "v39_character_consistency_gate", "world_director_status", "v40_world_director_status", "world_class_director_status", "world_director_template", "v40_world_director_template", "world_class_director_template", "world_director_plan", "v40_world_director_plan", "world_class_director_plan", "story_to_shot_plan", "world_director_execute", "v40_world_director", "world_class_director_execute", "story_execute"}
        if task == "musepose_motion_test":
            inp["engine"] = "musepose"
            task = "real_full_body_video"
        if task == "magicanimate_motion_test":
            inp["engine"] = "magicanimate"
            task = "real_full_body_video"
        if task == "animateanyone_motion_test":
            inp["engine"] = "animateanyone"
            task = "real_full_body_video"
        if task not in supported:
            return fail_output(
                f"UNKNOWN_TASK: {task}",
                stage="task_check",
                suspect="client_sent_unknown_task",
                solution_ar="أرسل task=ping أو diagnostic أو pose_truth أو real_full_body_video.",
                supported_tasks=sorted(supported | {"ping", "diagnostic"}),
            )

        image_b64 = inp.get("image_base64") or inp.get("source_image_base64") or inp.get("image")
        motion_name = inp.get("motion_name") or inp.get("motion") or "standing_idle"
        job_dir = WORK / f"job_{int(time.time()*1000)}"
        job_dir.mkdir(parents=True, exist_ok=True)
        img_path = decode_image_base64(image_b64, job_dir / "source.png")
        info = image_info(img_path)
        log("IMAGE_DECODED", info=info, task=task, motion_name=motion_name)

        if task in {"pose_truth", "dwpose_truth"}:
            result = router.pose_truth(img_path, inp)
        elif task == "musepose_e2e_lock_test":
            result = router.musepose_e2e_lock_test(img_path, motion_name, inp)
        else:
            result = router.run(img_path, motion_name, inp)

        result["image_info"] = info
        result["requested_motion"] = motion_name
        result["worker_contract"] = {
            "must_return_video_when_ok_for_video_tasks": True,
            "allowed_video_keys": ["video_base64", "video_url"],
            "no_sadtalker_fallback_for_body": True,
            "dwpose_truth_before_body_engines": True,
            "musepose_first_magicanimate_second_animateanyone_third": True,
            "v30_readiness_gate_before_heavy_inference": True,
            "v31_musepose_end_to_end_lock": True,
            "v32_pose_dataset_benchmark": True,
            "v33_real_head_tracking": True,
            "v34_face_graft_composer": True,
            "v35_deep_quality_judge": True,
            "v36_smart_retry_2": True,
            "v38_motion_library_pro": True,
            "v37_selects_engine_before_run": True,
            "v38_motion_library_pro": True,
            "v38_motion_validation_before_engine": True,
            "v39_character_consistency": True,
            "v39_character_profile_lock": True,
            "v40_world_class_director": True,
            "v40_story_to_shot_plan": True,
            "v40_does_not_fake_foundation_model": True,
        }
        log("FULLBODY_RETURNING_OUTPUT", ok=result.get("ok"), stage=result.get("stage"), suspect=result.get("suspect"))
        return result

    except Exception as e:
        log("FULLBODY_EXCEPTION", error=str(e), traceback_tail=traceback.format_exc()[-2000:])
        return exception_output(e, stage="handler_exception", suspect="fullbody_worker_handler", solution_ar="افحص Logs؛ V40 يرجع traceback_tail ولا يصمت.")

if __name__ == "__main__":
    if runpod is None:
        print(json.dumps(handle({"input": {"task": "diagnostic"}}), ensure_ascii=False, indent=2))
    else:
        runpod.serverless.start({"handler": handle})
