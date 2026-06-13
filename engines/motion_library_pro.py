from __future__ import annotations
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .output_contract import ok_output, fail_output
from .motion_library import get_motion, list_motions, normalize_motion_name


def _body_truth_from(data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(data, dict):
        return {}
    if isinstance(data.get("body_truth"), dict):
        return data["body_truth"]
    pose = data.get("pose_truth") or data.get("dwpose_truth") or {}
    if isinstance(pose, dict) and isinstance(pose.get("body_truth"), dict):
        return pose["body_truth"]
    return {}


class MotionLibraryProV38:
    """V38 Motion Library Pro.

    ليست قائمة أسماء فقط؛ هي بوابة قرار قبل تشغيل المحرك:
    الحركة → متطلباتها → هل الصورة تسمح بها؟ → البدائل الآمنة → المحرك الأنسب.
    """

    VERSION = "V38_MOTION_LIBRARY_PRO"

    def status(self) -> Dict[str, Any]:
        motions = list_motions()
        return ok_output(
            "v38_motion_library_status",
            v38_motion_library_pro={
                "enabled": True,
                "motion_count": len(motions),
                "motions": list(motions.keys()),
                "has_pose_requirements": True,
                "has_safe_alternatives": True,
                "has_engine_preferences": True,
                "blocks_unsafe_motion_before_inference": True,
                "no_fake_success": True,
            },
            rule_ar="V38 لا تعتبر الحركة كلمة فقط. كل حركة لها شروط وبدائل ومحرك مفضل، وتُمنع إذا كانت الصورة لا تسمح بها.",
        )

    def list(self, request: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        request = request or {}
        category = str(request.get("category") or "").strip().lower()
        max_level = request.get("max_level")
        motions = list_motions()
        if category:
            motions = {k: v for k, v in motions.items() if str(v.get("category", "")).lower() == category}
        if max_level is not None:
            try:
                ml = int(max_level)
                motions = {k: v for k, v in motions.items() if int(v.get("level") or 1) <= ml}
            except Exception:
                pass
        return ok_output(
            "v38_motion_library_list",
            motions=motions,
            count=len(motions),
            categories=sorted(set(str(v.get("category")) for v in list_motions().values())),
        )

    def template(self) -> Dict[str, Any]:
        return ok_output(
            "v38_motion_library_template",
            example_select={
                "task": "motion_library_select",
                "intent_ar": "أريد شخصا يشرح بيده اليمنى بهدوء",
                "max_level": 3,
            },
            example_validate={
                "task": "motion_library_validate",
                "motion_name": "both_hands_explain",
                "pose_truth": {"body_truth": {"standing_motion_allowed": True, "hands_motion_allowed": True, "walking_allowed": False}},
            },
            example_execute={
                "task": "motion_library_execute",
                "image_base64": "PUT_IMAGE_BASE64_HERE",
                "intent_ar": "شرح باليدين",
                "engine": "auto",
            },
            recommended_safe_order=["standing_idle", "head_turn_left", "right_hand_explain", "both_hands_explain", "raise_hand_greeting", "walking_lite"],
        )

    def select(self, request: Dict[str, Any]) -> Dict[str, Any]:
        request = request or {}
        explicit = request.get("motion_name") or request.get("motion")
        intent = str(request.get("intent_ar") or request.get("prompt") or request.get("description") or "").lower()
        if explicit:
            key = normalize_motion_name(str(explicit))
            reason = "تم اختيار الحركة من motion_name الصريح."
        else:
            text = intent
            if any(w in text for w in ["مشي", "يمشي", "walk", "walking"]):
                key = "walking_lite"; reason = "النص يطلب المشي."
            elif any(w in text for w in ["يدين", "باليدين", "both", "two hands"]):
                key = "both_hands_explain"; reason = "النص يطلب حركة اليدين."
            elif any(w in text for w in ["تحية", "يرفع", "رفع اليد", "raise"]):
                key = "raise_hand_greeting"; reason = "النص يطلب رفع اليد أو التحية."
            elif any(w in text for w in ["يد", "يشرح", "شرح", "right hand", "اليمنى"]):
                key = "right_hand_explain"; reason = "النص يطلب شرحًا باليد."
            elif any(w in text for w in ["التفات", "يسار", "turn", "head"]):
                key = "head_turn_left"; reason = "النص يطلب التفات الرأس."
            elif any(w in text for w in ["استماع", "يهز", "nod", "موافق"]):
                key = "listener_nod"; reason = "النص يطلب إيماءة استماع."
            else:
                key = "standing_idle"; reason = "لم تظهر حركة خطرة؛ اخترنا وقوفًا طبيعيًا آمنًا."
        motion = get_motion(key)
        # Optional max level clamp.
        max_level = request.get("max_level")
        if max_level is not None:
            try:
                if int(motion.get("level") or 1) > int(max_level):
                    alt = (motion.get("safe_alternatives") or ["standing_idle"])[0]
                    return ok_output(
                        "v38_motion_selected_with_level_clamp",
                        selected_motion=get_motion(alt),
                        originally_requested=motion,
                        decision_ar=f"الحركة المطلوبة مستواها أعلى من max_level. اخترنا البديل الآمن: {alt}.",
                        reason_ar=reason,
                        no_fake_success=True,
                    )
            except Exception:
                pass
        return ok_output(
            "v38_motion_selected",
            selected_motion=motion,
            selected_motion_name=motion.get("name"),
            decision_ar=f"V38 اختارت الحركة: {motion.get('ar')}.",
            reason_ar=reason,
            no_fake_success=True,
        )

    def validate(self, request: Dict[str, Any]) -> Dict[str, Any]:
        request = request or {}
        selected = self.select(request)
        motion = selected.get("selected_motion") if isinstance(selected, dict) else None
        if not isinstance(motion, dict):
            motion = get_motion(request.get("motion_name") or "standing_idle")
        body_truth = _body_truth_from(request)
        requires = set(motion.get("requires") or [])
        blockers: List[str] = []
        notes: List[str] = []

        # إذا لم يأتِ pose_truth نسمح في التخطيط فقط، لكن نطلب فحص DWPose قبل التنفيذ.
        has_truth = bool(body_truth)
        if not has_truth:
            notes.append("لم يتم تمرير pose_truth؛ هذا فحص تخطيطي فقط. عند التنفيذ يجب أن يمر DWPose أولًا.")
        else:
            if not body_truth.get("standing_motion_allowed") and {"head", "torso"} & requires:
                blockers.append("standing_motion_not_allowed_by_pose_truth")
            if ({"left_hand", "right_hand"} & requires) and not body_truth.get("hands_motion_allowed"):
                blockers.append("hands_not_clear_for_requested_motion")
            if ({"legs", "feet"} & requires) and not body_truth.get("walking_allowed"):
                blockers.append("feet_or_legs_not_clear_for_walking")

        max_level = request.get("max_level")
        if max_level is not None:
            try:
                if int(motion.get("level") or 1) > int(max_level):
                    blockers.append("motion_level_above_allowed_max_level")
            except Exception:
                pass

        allowed = not blockers
        alternatives = motion.get("safe_alternatives") or []
        return ok_output(
            "v38_motion_library_validate",
            motion_allowed=allowed,
            selected_motion=motion,
            blockers=blockers,
            notes_ar=notes,
            safe_alternatives=alternatives,
            decision_ar=(
                "الحركة مسموحة لهذه الصورة حسب شروط V38."
                if allowed else
                "الحركة ممنوعة قبل تشغيل المحرك لأن الصورة لا تحقق شروطها. استعمل بديلًا آمنًا."
            ),
            main_criminal_ar=(blockers[0] if blockers else None),
            solution_ar=(
                "استعمل: " + ", ".join(alternatives[:3])
                if blockers and alternatives else
                "يمكن المتابعة إلى Engine Ensemble Router."
            ),
            no_fake_success=True,
        )

    def execute(self, router: Any, request: Dict[str, Any], work_root: Path) -> Dict[str, Any]:
        # اختيار الحركة ثم تمريرها إلى V37 Ensemble Execute. التحقق الحقيقي سيحدث بعد DWPose داخل router.run.
        request = dict(request or {})
        selected = self.select(request)
        motion = selected.get("selected_motion") if isinstance(selected, dict) else None
        if isinstance(motion, dict):
            request["motion_name"] = motion.get("name") or "standing_idle"
            request["v38_selected_motion"] = motion
        request["use_engine_ensemble"] = True
        result = router.engine_ensemble_execute(request)
        if isinstance(result, dict):
            result["v38_motion_library_selection"] = selected
            result["v38_motion_library_pro_used"] = True
        return result
