from __future__ import annotations
import json, re, time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .output_contract import ok_output, fail_output

_SAFE_DEFAULT_IMAGE_NOTE_AR = "V40 يستطيع التخطيط بلا صورة، لكن التنفيذ الحقيقي يحتاج image_base64 أو shots[].image_base64."

_MOTION_KEYWORDS = [
    ("شرح", "right_hand_explain"),
    ("يفسر", "right_hand_explain"),
    ("يتحدث", "right_hand_explain"),
    ("كلام", "right_hand_explain"),
    ("تحية", "raise_hand_greeting"),
    ("يسلم", "raise_hand_greeting"),
    ("يلتفت", "head_turn_left"),
    ("ينظر", "head_turn_left"),
    ("يمشي", "walking_lite"),
    ("مشي", "walking_lite"),
    ("واقف", "standing_idle"),
    ("يقف", "standing_idle"),
    ("ينصت", "listener_nod"),
    ("يستمع", "listener_nod"),
]

_CAMERA_BY_MOTION = {
    "standing_idle": {"shot_type": "medium shot", "camera_motion": "slow_push_in", "risk": "low"},
    "idle_breathing_01": {"shot_type": "medium shot", "camera_motion": "locked_or_slow_push", "risk": "low"},
    "right_hand_explain": {"shot_type": "medium shot", "camera_motion": "subtle_hand_room", "risk": "medium"},
    "speaker_gesture_01": {"shot_type": "medium shot", "camera_motion": "subtle_hand_room", "risk": "medium"},
    "both_hands_explain": {"shot_type": "medium wide", "camera_motion": "stable_no_crop_hands", "risk": "medium_high"},
    "speaker_gesture_02": {"shot_type": "medium wide", "camera_motion": "stable_no_crop_hands", "risk": "medium_high"},
    "head_turn_left": {"shot_type": "close medium", "camera_motion": "locked", "risk": "low"},
    "turn_head_left_01": {"shot_type": "close medium", "camera_motion": "locked", "risk": "low"},
    "raise_hand_greeting": {"shot_type": "medium shot", "camera_motion": "locked", "risk": "medium"},
    "raise_hand_01": {"shot_type": "medium shot", "camera_motion": "locked", "risk": "medium"},
    "listener_nod": {"shot_type": "close medium", "camera_motion": "locked", "risk": "low"},
    "walking_lite": {"shot_type": "wide full body", "camera_motion": "stable_follow_light", "risk": "high"},
}

class WorldClassDirectorV40:
    """V40 planning/director layer.

    It is intentionally honest: it creates a shot plan and may execute through the existing
    Motion Library + Engine Ensemble + Quality Judge stack, but it does not claim to be a
    foundation text-to-video model like Sora/Veo/Runway.
    """
    version = "V40_WORLD_CLASS_DIRECTOR"

    def status(self) -> Dict[str, Any]:
        return ok_output(
            "v40_world_class_director_status",
            v40_world_class_director={
                "enabled": True,
                "mode": "story_to_shot_plan_plus_optional_execution",
                "not_a_foundation_video_model": True,
                "uses_existing_stack": [
                    "V38 Motion Library Pro",
                    "V37 Engine Ensemble Router",
                    "V30 Engine Readiness Doctor",
                    "V35 Deep Quality Judge",
                    "V36 Smart Retry 2.0",
                    "V39 Character Consistency",
                ],
                "capabilities": [
                    "understand_story_text_ar_or_fr_or_en",
                    "split_to_shots",
                    "select_motion_per_shot",
                    "select_camera_intent_per_shot",
                    "build_execution_payloads",
                    "quality_gate_strategy",
                    "character_consistency_strategy",
                ],
            },
            truth_ar="V40 هي مخرج عالمي ذكي، لا تزعم أنها Sora/Veo. التنفيذ الحقيقي يبقى عبر Workers والمحركات المركبة فعليًا.",
        )

    def template(self) -> Dict[str, Any]:
        return ok_output(
            "v40_world_class_director_template",
            request_template={
                "task": "world_director_plan",
                "story_ar": "شخص يقف أمام الكاميرا ويرحب بالجمهور ثم يشرح بيده اليمنى ثم يلتفت قليلا.",
                "target_duration_seconds": 12,
                "max_shots": 3,
                "style": "realistic_clean_social_video",
                "character_name": "Main Character",
                "reference_image_base64": "OPTIONAL_REFERENCE_IMAGE_BASE64",
                "image_base64": "OPTIONAL_GLOBAL_IMAGE_FOR_ALL_SHOTS",
                "strict_character_consistency": True,
                "quality_threshold": 76,
                "execute": False
            },
            execute_template={
                "task": "world_director_execute",
                "story_ar": "شخص يشرح فكرة مهمة بيده اليمنى ثم يختم بتحية.",
                "image_base64": "PUT_IMAGE_BASE64_HERE",
                "max_shots": 2,
                "quality_threshold": 76,
                "engine": "auto"
            },
        )

    def _split_story(self, story: str, max_shots: int) -> List[str]:
        story = (story or "").strip()
        if not story:
            return ["شخص واقف أمام الكاميرا بحركة طبيعية هادئة"]
        parts = re.split(r"[\.\n؛;،]+| ثم | وبعد ذلك | بعد ذلك | afterwards | then ", story)
        parts = [p.strip(" -\t") for p in parts if p and p.strip()]
        if not parts:
            parts = [story]
        # merge very short trailing parts
        merged: List[str] = []
        for p in parts:
            if merged and len(p) < 12:
                merged[-1] = merged[-1] + "، " + p
            else:
                merged.append(p)
        return merged[:max(1, int(max_shots or 3))]

    def _motion_for_text(self, text: str, index: int) -> str:
        t = text.lower()
        for key, motion in _MOTION_KEYWORDS:
            if key in t:
                return motion
        # cinematic default: first shot calm, middle explanation, last nod/greeting
        if index == 0:
            return "standing_idle"
        return "right_hand_explain"

    def _shot_plan(self, story: str, request: Dict[str, Any]) -> List[Dict[str, Any]]:
        max_shots = int(request.get("max_shots") or request.get("scene_count") or 4)
        target_duration = float(request.get("target_duration_seconds") or request.get("duration") or max(8, max_shots * 4))
        parts = self._split_story(story, max_shots)
        per = max(2.5, target_duration / max(1, len(parts)))
        shots: List[Dict[str, Any]] = []
        for i, text in enumerate(parts, start=1):
            forced = None
            req_shots = request.get("shots") if isinstance(request.get("shots"), list) else []
            if i - 1 < len(req_shots) and isinstance(req_shots[i-1], dict):
                forced = req_shots[i-1].get("motion_name") or req_shots[i-1].get("motion")
            motion = forced or self._motion_for_text(text, i-1)
            cam = dict(_CAMERA_BY_MOTION.get(motion, _CAMERA_BY_MOTION["standing_idle"]))
            shots.append({
                "shot_id": f"shot_{i:02d}",
                "story_piece_ar": text,
                "duration_seconds": round(per, 2),
                "motion_name": motion,
                "camera": cam,
                "director_intent_ar": self._director_intent(text, motion),
                "quality_gate": {
                    "deep_quality_required": True,
                    "minimum_score": int(request.get("quality_threshold") or 76),
                    "retry_if_below_threshold": True,
                },
                "character_gate": {
                    "enabled": bool(request.get("strict_character_consistency", True)),
                    "strict": bool(request.get("strict_character_consistency", True)),
                },
                "execution_payload": {
                    "task": "motion_library_execute",
                    "intent_ar": text,
                    "motion_name": motion,
                    "engine": request.get("engine") or "auto",
                    "quality_threshold": int(request.get("quality_threshold") or 76),
                },
            })
        return shots

    def _director_intent(self, text: str, motion: str) -> str:
        if motion == "walking_lite":
            return "لقطة جسم كامل بحركة مشي خفيفة، ممنوعة إذا القدمين غير واضحتين."
        if "hand" in motion or "gesture" in motion or "شرح" in text:
            return "لقطة شرح واضحة تترك مساحة لليدين وتمنع قص الأصابع."
        if "greeting" in motion:
            return "لقطة تحية قصيرة بثبات كاميرا وحركة يد بسيطة."
        if "head" in motion or "nod" in motion:
            return "لقطة قريبة متوسطة تركز على الوجه والرأس مع حركة قليلة."
        return "لقطة تأسيسية هادئة بثبات بصري وحركة جسم طبيعية."

    def plan(self, request: Dict[str, Any]) -> Dict[str, Any]:
        story = str(request.get("story_ar") or request.get("story") or request.get("script") or request.get("prompt") or "").strip()
        shots = self._shot_plan(story, request or {})
        missing_inputs = []
        if not (request.get("image_base64") or request.get("reference_image_base64") or any(isinstance(s, dict) and s.get("image_base64") for s in request.get("shots", []) if isinstance(request.get("shots"), list))):
            missing_inputs.append("image_base64_or_per_shot_image_base64")
        return ok_output(
            "v40_world_class_director_plan",
            story_ar=story or "شخصية تقف وتتحرك بهدوء أمام الكاميرا.",
            shot_count=len(shots),
            shot_plan=shots,
            pipeline_order=[
                "character_profile_if_reference_image_exists",
                "motion_library_validate_each_shot",
                "engine_ensemble_plan_each_shot",
                "readiness_gate_before_inference",
                "generate_or_return_plan",
                "deep_quality_judge",
                "smart_retry_if_needed",
                "character_consistency_gate",
            ],
            missing_inputs_for_real_execution=missing_inputs,
            plan_only=not bool(request.get("execute", False)),
            truth_ar="هذه خطة إخراج ذكية. لا يتم ادعاء فيديو حقيقي إلا إذا نفذنا اللقطات بمحركات جاهزة وأرجعت video_base64.",
            next_step_ar="ضع image_base64 وشغّل world_director_execute للتنفيذ الحقيقي، أو استعمل هذه الخطة لتوجيه جمانة.",
        )

    def execute(self, router: Any, request: Dict[str, Any], work_root: Path) -> Dict[str, Any]:
        plan = self.plan({**(request or {}), "execute": False})
        if not plan.get("ok"):
            return plan
        global_image = request.get("image_base64") or request.get("source_image_base64") or request.get("reference_image_base64")
        shots_in = request.get("shots") if isinstance(request.get("shots"), list) else []
        if not global_image and not any(isinstance(s, dict) and s.get("image_base64") for s in shots_in):
            return fail_output(
                "V40_EXECUTION_NEEDS_IMAGE_BASE64",
                stage="v40_world_director_pre_execution",
                suspect="missing_image_for_real_video_execution",
                solution_ar="أرسل image_base64 عام لكل اللقطات أو image_base64 داخل كل لقطة. التخطيط يعمل بلا صورة، لكن الفيديو الحقيقي يحتاج صورة.",
                v40_plan=plan,
                note_ar=_SAFE_DEFAULT_IMAGE_NOTE_AR,
            )

        max_execute_shots = int(request.get("max_execute_shots") or request.get("max_shots") or 3)
        quality_threshold = int(request.get("quality_threshold") or 76)
        character_profile = request.get("character_profile")
        if not character_profile and request.get("reference_image_base64"):
            try:
                created = router.character_consistency.create_profile_from_image({
                    "reference_image_base64": request.get("reference_image_base64"),
                    "character_name": request.get("character_name") or "v40_character",
                    "save_profile": False,
                }, work_root)
                character_profile = created.get("character_profile")
            except Exception as e:
                character_profile = None

        results: List[Dict[str, Any]] = []
        best_score = -1
        best_result: Optional[Dict[str, Any]] = None
        for idx, shot in enumerate(plan.get("shot_plan", [])[:max_execute_shots]):
            shot_req = shots_in[idx] if idx < len(shots_in) and isinstance(shots_in[idx], dict) else {}
            img = shot_req.get("image_base64") or global_image
            payload = dict(shot.get("execution_payload") or {})
            payload.update({
                "image_base64": img,
                "motion_name": shot_req.get("motion_name") or shot.get("motion_name"),
                "intent_ar": shot_req.get("intent_ar") or shot.get("story_piece_ar"),
                "engine": shot_req.get("engine") or request.get("engine") or "auto",
                "quality_threshold": quality_threshold,
            })
            if character_profile:
                payload["character_profile"] = character_profile
                payload["character_consistency_strict"] = bool(request.get("strict_character_consistency", False))
            generated = router.motion_library_execute(payload)
            judge = None
            if generated.get("ok") and generated.get("video_base64"):
                try:
                    judge = router.deep_quality_judge({
                        "video_base64": generated.get("video_base64"),
                        "expected_motion": shot.get("motion_name"),
                        "talking_expected": bool(request.get("talking_expected", False)),
                        "strict": bool(request.get("strict_quality", True)),
                    })
                except Exception as e:
                    judge = {"ok": False, "error": str(e), "stage": "v40_deep_quality_exception"}
            item = {"shot": shot, "generated": generated, "deep_quality": judge}
            results.append(item)
            score = -1
            if isinstance(judge, dict):
                score = int(judge.get("overall_quality_score") or judge.get("score") or (-1))
            elif generated.get("ok"):
                score = 50
            if score > best_score:
                best_score = score
                best_result = generated
            if generated.get("ok") and isinstance(judge, dict) and int(judge.get("overall_quality_score") or 0) >= quality_threshold:
                break

        any_video = any(r.get("generated", {}).get("video_base64") for r in results)
        if not any_video:
            return fail_output(
                "V40_NO_REAL_VIDEO_PRODUCED",
                stage="v40_world_director_execute",
                suspect="all_shots_failed_or_engines_not_ready",
                solution_ar="افحص نتائج كل لقطة: غالبًا المحركات غير جاهزة أو الصورة لا تسمح بالحركة. استعمل world_director_plan ثم engine_readiness و motion_library_validate.",
                v40_plan=plan,
                shot_results=results,
            )
        final_video = None
        if best_result:
            final_video = best_result.get("video_base64")
        return ok_output(
            "v40_world_class_director_execute",
            v40_plan=plan,
            shot_results=results,
            selected_best_score=best_score,
            video_base64=final_video,
            final_output_kind="best_single_shot_video_until_v41_timeline_composer",
            truth_ar="V40 نفذ اللقطات عبر المحركات الموجودة واختار أفضل لقطة. دمج عدة لقطات في فيديو واحد يأتي لاحقًا في Timeline Composer.",
        )
