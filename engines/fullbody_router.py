from __future__ import annotations
from pathlib import Path
from typing import Dict, Any
from .dwpose_engine import DWPoseTruthEngine
from .musepose_engine import MusePoseEngine
from .magicanimate_engine import MagicAnimateEngine
from .animateanyone_engine import AnimateAnyoneEngine
from .readiness_doctor import EngineReadinessDoctor
from .musepose_lock import MusePoseEndToEndLock
from .pose_dataset_benchmark import PoseDatasetBenchmark
from .head_tracking_engine import RealHeadTrackingEngine
from .face_graft_composer import FaceGraftComposer
from .deep_quality_judge import DeepQualityJudge
from .smart_retry_brain import SmartRetryBrainV2
from .engine_ensemble_router import EngineEnsembleRouterV37
from .motion_library_pro import MotionLibraryProV38
from .character_consistency import CharacterConsistencyV39
from .world_class_director import WorldClassDirectorV40
from .motion_library import get_motion, list_motions
from .output_contract import ok_output, fail_output
from .quality_probe import quality_contract_placeholder

class FullBodyRouter:
    def __init__(self):
        self.dwpose = DWPoseTruthEngine()
        self.musepose = MusePoseEngine()
        self.magicanimate = MagicAnimateEngine()
        self.animateanyone = AnimateAnyoneEngine()
        self.doctor = EngineReadinessDoctor(self.dwpose, self.musepose, self.magicanimate, self.animateanyone)
        self.musepose_lock = MusePoseEndToEndLock(self.musepose)
        self.benchmark = PoseDatasetBenchmark(self.dwpose, self.musepose_lock, self.doctor)
        self.head_tracker = RealHeadTrackingEngine()
        self.face_grafter = FaceGraftComposer(self.head_tracker)
        self.deep_quality = DeepQualityJudge()
        self.smart_retry = SmartRetryBrainV2()
        self.engine_ensemble = EngineEnsembleRouterV37(self.doctor, self.dwpose)
        self.motion_library_pro = MotionLibraryProV38()
        self.character_consistency = CharacterConsistencyV39()
        self.world_director = WorldClassDirectorV40()

    def diagnostic(self) -> Dict[str, Any]:
        readiness = self.doctor.report({"source": "diagnostic"})
        return ok_output(
            "fullbody_worker_diagnostic_v40_world_class_director",
            engines={
                "dwpose": self.dwpose.status(),
                "musepose": self.musepose.status(),
                "magicanimate": self.magicanimate.status(),
                "animateanyone": self.animateanyone.status(),
                "v31_musepose_lock": self.musepose_lock.status(),
                "v34_pose_dataset_benchmark": self.benchmark.template(),
                    "v36_smart_retry_2": self.smart_retry.status(),
                "v38_motion_library_pro": self.motion_library_pro.status(),
                "v39_character_consistency": self.character_consistency.status(),
                "v40_world_class_director": self.world_director.status(),
            },
            engine_readiness_doctor=readiness,
            motion_library=list_motions(),
            contract={
                "video_required_keys": ["video_base64", "video_url"],
                "no_fake_body_motion": True,
                "sad_talker_is_not_body_engine": True,
                "dwpose_must_pass_before_body_engines": True,
                "v30_readiness_gate_before_heavy_inference": True,
                "v31_musepose_end_to_end_lock": True,
                "v34_pose_dataset_benchmark": True,
                "v31_first_goal": "lock_musepose_before_other_engines",
                "musepose_first_engine": True,
                "magicanimate_second_engine": True,
                "animateanyone_third_engine": True,
                "each_engine_returns_real_video_or_explicit_error": True,
                "v38_motion_library_pro": True,
                "v38_motion_validation_before_inference": True,
                "v39_character_consistency": True,
                "v39_character_profile_lock": True,
                "v40_world_class_director": True,
                "v40_story_to_shot_plan": True,
            },
            current_stage_ar="V40 يضيف World-Class Director: فهم القصة، تقسيمها إلى لقطات، اختيار الحركة والكاميرا والمحرك، ثم فحص الجودة.",
            next_steps_ar=["V34: شغّل pose_dataset_benchmark على 20 ثم 100 صورة", "V34: Real Head Tracking", "V34: Face Graft Composer", "V36: Smart Retry 2.0", "V38: Motion Library Pro", "V39: Character Consistency", "V40: World-Class Director"],
        )

    def readiness(self, request: Dict[str, Any] | None = None) -> Dict[str, Any]:
        return self.doctor.report(request or {})

    def pose_truth(self, image_path: Path, request: Dict[str, Any]) -> Dict[str, Any]:
        truth = self.dwpose.analyze(image_path)
        truth["task_completed"] = "pose_truth"
        truth["v30_rule_ar"] = "DWPose Truth Engine هو بوابة الجسم الحقيقي. بعدها يفحص V30 readiness للمحركات قبل التشغيل."
        return truth

    def musepose_lock_status(self) -> Dict[str, Any]:
        pre = self.musepose_lock.preflight()
        st = self.musepose_lock.status()
        if pre.get("ok"):
            pre["v31_status"] = st
            return pre
        return pre

    def musepose_e2e_lock_test(self, image_path: Path, motion_name: str, request: Dict[str, Any]) -> Dict[str, Any]:
        truth = self.dwpose.analyze(image_path)
        if not truth.get("ok"):
            truth["v31_blocked_before_musepose_ar"] = "لا نختبر MusePose قبل نجاح DWPose Truth Engine، لأن الجسم الحقيقي يحتاج pose صحيحًا."
            return truth
        return self.musepose_lock.run_e2e_test(image_path, motion_name, pose_truth=truth)


    def pose_dataset_benchmark(self, request: Dict[str, Any]) -> Dict[str, Any]:
        return self.benchmark.run(request or {})

    def benchmark_template(self) -> Dict[str, Any]:
        return self.benchmark.template()


    def head_tracking_template(self) -> Dict[str, Any]:
        return self.head_tracker.template()

    def head_tracking_status(self) -> Dict[str, Any]:
        return ok_output(
            "v34_head_tracking_status",
            v34_real_head_tracking=self.head_tracker.status(),
            rule_ar="Face Graft ممنوع قبل head_track مستقر. هذه هي بوابة V34.",
        )

    def head_track_video(self, request: Dict[str, Any]) -> Dict[str, Any]:
        work_root = Path(__import__("os").environ.get("JUMANA_WORKDIR", "/workspace/outputs"))
        return self.head_tracker.track_video(request or {}, work_root)



    def face_graft_status(self) -> Dict[str, Any]:
        return ok_output(
            "v34_face_graft_status",
            v34_face_graft_composer=self.face_grafter.status(),
            v33_head_tracking=self.head_tracker.status(),
            rule_ar="Face Graft لا يبدأ إلا بوجود head_tracks صالحة. لا يوجد لصق عشوائي.",
        )

    def face_graft_template(self) -> Dict[str, Any]:
        return self.face_grafter.template()

    def face_graft_video(self, request: Dict[str, Any]) -> Dict[str, Any]:
        work_root = Path(__import__("os").environ.get("JUMANA_WORKDIR", "/workspace/outputs"))
        return self.face_grafter.compose(request or {}, work_root)

    def deep_quality_status(self) -> Dict[str, Any]:
        return self.deep_quality.status()

    def deep_quality_template(self) -> Dict[str, Any]:
        return self.deep_quality.template()

    def deep_quality_judge(self, request: Dict[str, Any]) -> Dict[str, Any]:
        work_root = Path(__import__("os").environ.get("JUMANA_WORKDIR", "/workspace/outputs"))
        return self.deep_quality.judge(request or {}, work_root)

    def smart_retry_status(self) -> Dict[str, Any]:
        return self.smart_retry.status()

    def smart_retry_template(self) -> Dict[str, Any]:
        return self.smart_retry.template()

    def smart_retry_plan(self, request: Dict[str, Any]) -> Dict[str, Any]:
        return self.smart_retry.plan(request or {})

    def smart_retry_execute(self, request: Dict[str, Any]) -> Dict[str, Any]:
        work_root = Path(__import__("os").environ.get("JUMANA_WORKDIR", "/workspace/outputs"))
        return self.smart_retry.execute(self, request or {}, work_root)

    def engine_ensemble_status(self) -> Dict[str, Any]:
        return self.engine_ensemble.status()

    def engine_ensemble_template(self) -> Dict[str, Any]:
        return self.engine_ensemble.template()

    def engine_ensemble_plan(self, request: Dict[str, Any]) -> Dict[str, Any]:
        return self.engine_ensemble.plan(request or {})

    def engine_ensemble_execute(self, request: Dict[str, Any]) -> Dict[str, Any]:
        work_root = Path(__import__("os").environ.get("JUMANA_WORKDIR", "/workspace/outputs"))
        return self.engine_ensemble.execute(self, request or {}, work_root)

    def motion_library_status(self) -> Dict[str, Any]:
        return self.motion_library_pro.status()

    def motion_library_list(self, request: Dict[str, Any]) -> Dict[str, Any]:
        return self.motion_library_pro.list(request or {})

    def motion_library_template(self) -> Dict[str, Any]:
        return self.motion_library_pro.template()

    def motion_library_select(self, request: Dict[str, Any]) -> Dict[str, Any]:
        return self.motion_library_pro.select(request or {})

    def motion_library_validate(self, request: Dict[str, Any]) -> Dict[str, Any]:
        return self.motion_library_pro.validate(request or {})

    def motion_library_execute(self, request: Dict[str, Any]) -> Dict[str, Any]:
        work_root = Path(__import__("os").environ.get("JUMANA_WORKDIR", "/workspace/outputs"))
        return self.motion_library_pro.execute(self, request or {}, work_root)



    def character_consistency_status(self) -> Dict[str, Any]:
        return self.character_consistency.status()

    def character_consistency_template(self) -> Dict[str, Any]:
        return self.character_consistency.template()

    def character_create_profile(self, request: Dict[str, Any]) -> Dict[str, Any]:
        work_root = Path(__import__("os").environ.get("JUMANA_WORKDIR", "/workspace/outputs"))
        return self.character_consistency.create_profile_from_image(request or {}, work_root)

    def character_compare(self, request: Dict[str, Any]) -> Dict[str, Any]:
        work_root = Path(__import__("os").environ.get("JUMANA_WORKDIR", "/workspace/outputs"))
        return self.character_consistency.compare(request or {}, work_root)

    def character_consistency_gate(self, request: Dict[str, Any]) -> Dict[str, Any]:
        work_root = Path(__import__("os").environ.get("JUMANA_WORKDIR", "/workspace/outputs"))
        return self.character_consistency.gate(request or {}, work_root)


    def world_director_status(self) -> Dict[str, Any]:
        return self.world_director.status()

    def world_director_template(self) -> Dict[str, Any]:
        return self.world_director.template()

    def world_director_plan(self, request: Dict[str, Any]) -> Dict[str, Any]:
        return self.world_director.plan(request or {})

    def world_director_execute(self, request: Dict[str, Any]) -> Dict[str, Any]:
        work_root = Path(__import__("os").environ.get("JUMANA_WORKDIR", "/workspace/outputs"))
        return self.world_director.execute(self, request or {}, work_root)

    def _requested_engine(self, request: Dict[str, Any]) -> str:
        engine = str(request.get("engine") or request.get("body_engine") or request.get("preferred_engine") or "auto").strip().lower()
        aliases = {
            "magic": "magicanimate",
            "magic_animate": "magicanimate",
            "muse": "musepose",
            "muse_pose": "musepose",
            "animate_anyone": "animateanyone",
            "animate-anyone": "animateanyone",
            "aa": "animateanyone",
            "automatic": "auto",
            "": "auto",
        }
        return aliases.get(engine, engine)

    def run(self, image_path: Path, motion_name: str, request: Dict[str, Any]) -> Dict[str, Any]:
        motion = get_motion(motion_name)
        motion_name = str(motion.get("name") or motion_name)
        requested_engine = self._requested_engine(request)

        truth = self.dwpose.analyze(image_path)
        if not truth.get("ok"):
            truth["motion_selected"] = motion
            truth["requested_engine"] = requested_engine
            truth["selected_engine_by_v37_ensemble"] = None
            return truth

        body_truth = truth.get("body_truth") or {}

        v38_motion_gate = self.motion_library_pro.validate({"motion_name": motion_name, "pose_truth": truth, "strict": True})
        if not v38_motion_gate.get("motion_allowed", True):
            return fail_output(
                "MOTION_BLOCKED_BY_V38_MOTION_LIBRARY",
                stage="v38_motion_library_gate_before_engine",
                suspect=v38_motion_gate.get("main_criminal_ar") or "unsafe_motion_for_current_pose",
                solution_ar=v38_motion_gate.get("solution_ar") or "اختر حركة أسهل من safe_alternatives.",
                v38_motion_gate=v38_motion_gate,
                motion_selected=motion,
                dwpose_truth=truth,
                requested_engine=requested_engine,
            )

        ensemble_plan = None
        if requested_engine == "auto" or bool(request.get("use_engine_ensemble", True)):
            ensemble_plan = self.engine_ensemble.plan(request, image_path=image_path, pose_truth=truth)
            if not ensemble_plan.get("ok"):
                ensemble_plan["motion_selected"] = motion
                ensemble_plan["image_path"] = str(image_path)
                return ensemble_plan
            engine = ensemble_plan.get("selected_engine") or "musepose"
        else:
            engine = requested_engine

        gate = self.doctor.gate(engine, motion_name)
        if not gate.get("ok"):
            gate["motion_selected"] = motion
            gate["image_path"] = str(image_path)
            gate["v37_engine_ensemble_plan"] = ensemble_plan
            gate["pipeline_truth_ar"] = "V37 اختار محركًا، لكن V30 readiness gate منعه قبل التشغيل بسبب جاهزية ناقصة. لا يوجد نجاح وهمي."
            return gate
        if motion_name == "walking_lite" and not body_truth.get("walking_allowed"):
            return fail_output(
                "WALKING_BLOCKED_BY_DWPOSE_TRUTH",
                stage="motion_guard_before_real_body_engine",
                suspect="feet_not_visible_or_pose_weak",
                solution_ar="DWPose لم يؤكد ظهور القدمين بما يكفي. تم منع المشي. جرّب standing_idle أو right_hand_explain أو صورة كاملة القدمين.",
                dwpose_truth=truth,
                v30_readiness_gate=gate,
                requested_motion=motion_name,
                requested_engine=requested_engine,
                selected_engine_by_v37_ensemble=engine,
                safe_alternatives=["standing_idle", "right_hand_explain", "both_hands_explain"],
            )

        if engine == "animateanyone":
            generated = self.animateanyone.generate(image_path, motion_name, pose_truth=truth)
            generated["engine_router_decision"] = "v37_ensemble_selected_animateanyone"
        elif engine == "magicanimate":
            generated = self.magicanimate.generate(image_path, motion_name, pose_truth=truth)
            generated["engine_router_decision"] = "v37_ensemble_selected_magicanimate"
        elif engine == "musepose":
            generated = self.musepose.generate(image_path, motion_name, pose_truth=truth)
            generated["engine_router_decision"] = "v37_ensemble_selected_musepose"
        else:
            return fail_output(
                f"V30_SELECTED_UNKNOWN_ENGINE: {engine}",
                stage="engine_router_after_readiness",
                suspect="readiness_doctor_selected_unknown_engine",
                solution_ar="افحص readiness_report. يجب أن يكون selected_engine واحدًا من musepose/magicanimate/animateanyone.",
                v30_readiness_gate=gate,
                requested_engine=requested_engine,
                selected_engine=engine,
            )

        generated["v30_readiness_gate"] = gate
        generated["v37_engine_ensemble_plan"] = ensemble_plan
        generated["v38_motion_library_gate"] = v38_motion_gate
        generated["v34_note_ar"] = "بعد نجاح MusePose lock، استعمل pose_dataset_benchmark لقياس النسبة على Dataset حقيقي قبل ادعاء أي تقدم عالمي."
        generated["selected_engine_by_v37_ensemble"] = engine
        if not generated.get("ok"):
            generated["motion_selected"] = motion
            generated["dwpose_truth"] = truth
            generated["quality_contract"] = quality_contract_placeholder()
            generated["pipeline_truth_ar"] = "V30 تأكد أن المحرك كان جاهزًا مبدئيًا، لكن inference نفسه فشل أو لم يخرج فيديو. الآن الجاني داخل تشغيل المحرك أو الأمر أو الأوزان، وليس readiness."
            generated["next_fix_ar"] = "V31 سيغلق MusePose End-to-End: نسخة واحدة، أوزان واحدة، command template واحد، واختبار فيديو ناجح."
            return generated
        generated["dwpose_truth"] = truth
        generated["v38_note_ar"] = "الفيديو جاء من حركة منظمة في Motion Library Pro ثم اختار V37 المحرك قبل التشغيل واجتاز V30 Readiness Gate."
        # V39 optional character consistency lock: if the user passes a profile/reference, verify the generated video.
        if (request.get("character_profile") or request.get("profile_id") or request.get("reference_image_base64")) and generated.get("video_base64"):
            work_root = Path(__import__("os").environ.get("JUMANA_WORKDIR", "/workspace/outputs"))
            try:
                if request.get("character_profile") or request.get("profile_id"):
                    profile_obj = request.get("character_profile") or request.get("profile_id")
                else:
                    created = self.character_consistency.create_profile_from_image({
                        "reference_image_base64": request.get("reference_image_base64"),
                        "character_name": request.get("character_name") or "jumana_character",
                        "save_profile": False,
                    }, work_root)
                    profile_obj = created.get("character_profile")
                cc = self.character_consistency.gate({
                    "character_profile": profile_obj,
                    "target_video_base64": generated.get("video_base64"),
                    "strict": bool(request.get("character_consistency_strict", False)),
                    "sample_frames": int(request.get("character_sample_frames") or 6),
                }, work_root)
                generated["v39_character_consistency_gate"] = cc
                if bool(request.get("character_consistency_strict", False)) and not cc.get("ok"):
                    cc["blocked_generated_video"] = True
                    cc["blocked_reason_ar"] = "تم منع تسليم الفيديو لأن Character Consistency فشل في الوضع strict."
                    return cc
            except Exception as e:
                generated["v39_character_consistency_warning"] = str(e)
                generated["v39_character_consistency_note_ar"] = "لم نستطع فحص الاتساق، لذلك لا ندعي ثبات الشخصية."
        generated["v39_note_ar"] = "V39 يحافظ على هوية الشخصية عبر Character Profile اختياري، ويمنع identity drift عند strict=true."
        generated["v40_note_ar"] = "V40 World-Class Director يستطيع توجيه هذه الحركة ضمن خطة لقطات، لكنه لا يزيف كونه نموذج فيديو أساسي مثل Sora/Veo."
        return generated
