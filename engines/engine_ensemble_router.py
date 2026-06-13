from __future__ import annotations
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .output_contract import ok_output, fail_output
from .motion_library import get_motion, list_motions

ENGINE_ORDER = ["musepose", "magicanimate", "animateanyone"]


def _norm_engine(name: Any) -> str:
    s = str(name or "auto").strip().lower()
    aliases = {
        "": "auto",
        "automatic": "auto",
        "muse": "musepose",
        "muse_pose": "musepose",
        "magic": "magicanimate",
        "magic_animate": "magicanimate",
        "animate_anyone": "animateanyone",
        "animate-anyone": "animateanyone",
        "aa": "animateanyone",
    }
    return aliases.get(s, s)


def _number(v: Any, default: float = 0.0) -> float:
    try:
        if v is None:
            return default
        return float(v)
    except Exception:
        return default


def _quality_score(report: Dict[str, Any]) -> float:
    if not isinstance(report, dict):
        return 0.0
    for key in ("overall_quality_score", "quality_score", "score", "best_quality_score"):
        if key in report:
            return max(0.0, min(100.0, _number(report.get(key))))
    return 0.0


def _criminal_text(report: Dict[str, Any]) -> str:
    if not isinstance(report, dict):
        return ""
    parts: List[str] = []
    for k in ("main_criminal_ar", "main_criminal", "suspect", "error", "stage", "solution_ar"):
        if report.get(k):
            parts.append(str(report.get(k)))
    cr = report.get("criminal_report")
    if isinstance(cr, dict):
        parts += [str(v) for v in cr.values() if v]
    return " | ".join(parts).lower()


class EngineEnsembleRouterV37:
    """V37 Engine Ensemble Router.

    الهدف: اختيار المحرك الأفضل قبل التشغيل، لا بعد الفشل فقط.
    يعتمد على: V30 readiness + DWPose truth + motion type + V35 quality history + V36 retry context.
    لا ينتج فيديو بنفسه إلا عبر FullBodyRouter.run بعد تحديد engine صريح.
    """

    VERSION = "V38_MOTION_LIBRARY_PRO"

    def __init__(self, doctor: Any, dwpose: Any):
        self.doctor = doctor
        self.dwpose = dwpose

    def status(self) -> Dict[str, Any]:
        return ok_output(
            "v37_engine_ensemble_status",
            engine_ensemble_router={
                "enabled": True,
                "selects_before_heavy_run": True,
                "uses_v30_readiness": True,
                "uses_dwpose_truth": True,
                "uses_v35_quality_history": True,
                "uses_v36_retry_context": True,
                "engine_order_when_equal": ENGINE_ORDER,
                "no_fake_success": True,
                "uses_v38_motion_library_pro": True,
            },
            rule_ar="V37 لا تجرّب المحركات عشوائيًا. تختار المحرك الأنسب قبل التشغيل، وإذا لا يوجد محرك جاهز ترجع الجاني ولا تضيع الرصيد.",
        )

    def template(self) -> Dict[str, Any]:
        return ok_output(
            "v37_engine_ensemble_template",
            example_plan={
                "task": "engine_ensemble_plan",
                "motion_name": "both_hands_explain",
                "engine": "auto",
                "quality_history": {"musepose": {"overall_quality_score": 72}, "magicanimate": {"overall_quality_score": 66}},
            },
            example_execute={
                "task": "engine_ensemble_execute",
                "image_base64": "PUT_IMAGE_BASE64_HERE",
                "motion_name": "right_hand_explain",
                "engine": "auto",
                "quality_threshold": 76,
            },
            outputs=[
                "selected_engine",
                "engine_ranking",
                "blocked_engines",
                "decision_ar",
                "if_execute: video_base64 only if real engine produced video",
            ],
        )

    def _motion_compatibility(self, engine: str, motion_name: str, body_truth: Dict[str, Any]) -> Tuple[float, List[str], List[str]]:
        reasons: List[str] = []
        blockers: List[str] = []
        motion = get_motion(motion_name)
        requires = set(motion.get("requires") or [])
        level = int(motion.get("level") or 1)
        score = 45.0

        # Engine natural strengths.
        if engine == "musepose":
            score += 24
            reasons.append("MusePose هو الاختيار الأول لحركة pose-controlled وجسم كامل.")
        elif engine == "magicanimate":
            score += 16
            reasons.append("MagicAnimate مناسب للثبات الزمني والحركة الناعمة كاختيار ثانٍ.")
        elif engine == "animateanyone":
            score += 12
            reasons.append("AnimateAnyone مناسب كاختيار ثالث للحفاظ على الشخصية إذا كان مركبًا.")

        # V38 Motion Library Pro preferences.
        prefs = list(motion.get("engine_preferences") or [])
        if engine in prefs:
            bonus = max(3, 12 - prefs.index(engine) * 3)
            score += bonus
            reasons.append(f"V38 Motion Library Pro يفضل {engine} لهذه الحركة (+{bonus}).")

        # Motion-specific scoring.
        if motion_name in {"standing_idle", "head_turn", "head_turn_left", "listener_nod"}:
            if engine == "magicanimate": score += 8
            if engine == "musepose": score += 6
            reasons.append("الحركة آمنة؛ يمكن اختيار المحرك الأكثر جاهزية وثباتًا.")
        if motion_name in {"right_hand_explain", "both_hands_explain", "raise_hand_greeting"}:
            if engine == "musepose": score += 12
            if engine == "magicanimate": score += 5
            reasons.append("حركة اليد تحتاج pose control، لذلك MusePose يأخذ أفضلية.")
        if motion_name == "walking_lite" or "feet" in requires:
            if engine == "musepose": score += 16
            else: score -= 12
            reasons.append("المشي يحتاج أقدام وpose واضح؛ MusePose يأخذ أفضلية قوية.")

        # Pose truth gates.
        if not body_truth.get("standing_motion_allowed"):
            blockers.append("standing_motion_not_allowed_by_dwpose")
            score -= 50
        if ({"left_hand", "right_hand"} & requires) and not body_truth.get("hands_motion_allowed"):
            blockers.append("hands_motion_not_allowed_by_dwpose")
            score -= 35
        if ("feet" in requires or motion_name == "walking_lite") and not body_truth.get("walking_allowed"):
            blockers.append("walking_not_allowed_by_dwpose")
            score -= 60

        scores = body_truth.get("scores") if isinstance(body_truth.get("scores"), dict) else {}
        score += min(10.0, _number(scores.get("body_score")) / 12.0)
        if "feet" in requires:
            score += min(8.0, _number(scores.get("feet_score")) / 14.0)
        if {"left_hand", "right_hand"} & requires:
            score += min(8.0, _number(scores.get("hands_score")) / 14.0)

        # Higher motion level is risky; prefer robust engine.
        if level >= 4 and engine != "musepose":
            score -= 8
            reasons.append("الحركة صعبة؛ غير MusePose يحصل على عقوبة مخاطرة.")

        return max(0.0, min(100.0, score)), blockers, reasons

    def _history_adjustment(self, engine: str, request: Dict[str, Any]) -> Tuple[float, List[str]]:
        notes: List[str] = []
        adjustment = 0.0
        hist = request.get("quality_history") or request.get("engine_quality_history") or {}
        if isinstance(hist, dict):
            rep = hist.get(engine) or {}
            if isinstance(rep, dict) and rep:
                q = _quality_score(rep)
                cr = _criminal_text(rep)
                if q >= 80:
                    adjustment += 10
                    notes.append(f"history: {engine} أعطى نتيجة جيدة سابقًا ({q}).")
                elif 1 <= q < 55:
                    adjustment -= 14
                    notes.append(f"history: {engine} ضعيف سابقًا ({q}).")
                if engine in cr and any(x in cr for x in ["failed", "فشل", "weights", "command", "not_ready", "runtime"]):
                    adjustment -= 25
                    notes.append(f"history: جاني سابق مرتبط بـ {engine}.")
        qrep = request.get("quality_report") or request.get("v35_quality_report") or {}
        cr2 = _criminal_text(qrep if isinstance(qrep, dict) else {})
        if engine == "musepose" and "musepose" in cr2:
            adjustment -= 18
            notes.append("تقرير V35/V36 يشير إلى MusePose كجاني؛ نقلل أفضليته.")
        if engine == "magicanimate" and "flicker" in cr2:
            adjustment -= 8
            notes.append("الفليكر موجود؛ لا نعطي MagicAnimate أفضلية زائدة.")
        return adjustment, notes

    def plan(self, request: Dict[str, Any], image_path: Optional[Path] = None, pose_truth: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        request = request or {}
        motion_name = str(request.get("motion_name") or request.get("motion") or "standing_idle")
        requested_engine = _norm_engine(request.get("engine") or request.get("body_engine") or request.get("preferred_engine") or "auto")
        readiness = self.doctor.report({"engine": requested_engine, "motion_name": motion_name, "source": "v37_ensemble_plan"})
        engine_readiness = readiness.get("video_engine_readiness") if isinstance(readiness.get("video_engine_readiness"), dict) else {}

        if pose_truth is None and image_path is not None:
            try:
                pose_truth = self.dwpose.analyze(image_path)
            except Exception as e:
                pose_truth = fail_output(str(e), stage="v37_dwpose_analyze_exception", suspect="dwpose_exception", solution_ar="فشل DWPose داخل V37. أصلح DWPose قبل اختيار محرك الجسم.")
        if pose_truth is None:
            pose_truth = {"ok": True, "body_truth": {"standing_motion_allowed": True, "hands_motion_allowed": True, "walking_allowed": False, "scores": {}}, "v37_pose_truth_supplied": False}
        body_truth = pose_truth.get("body_truth") if isinstance(pose_truth, dict) and isinstance(pose_truth.get("body_truth"), dict) else {}

        candidates = ENGINE_ORDER if requested_engine == "auto" else [requested_engine]
        ranking: List[Dict[str, Any]] = []
        blocked: List[Dict[str, Any]] = []
        for eng in candidates:
            if eng not in ENGINE_ORDER:
                blocked.append({"engine": eng, "reason": "unknown_engine", "solution_ar": "استعمل auto أو musepose أو magicanimate أو animateanyone."})
                continue
            er = engine_readiness.get(eng) if isinstance(engine_readiness, dict) else {}
            ready = bool(er.get("ready"))
            readiness_score = _number(er.get("score"))
            compat_score, compat_blockers, compat_reasons = self._motion_compatibility(eng, motion_name, body_truth)
            hist_adj, hist_notes = self._history_adjustment(eng, request)
            final_score = max(0.0, min(100.0, readiness_score * 0.42 + compat_score * 0.48 + hist_adj + 5.0))
            item = {
                "engine": eng,
                "ready": ready,
                "readiness_score": readiness_score,
                "motion_compatibility_score": round(compat_score, 2),
                "history_adjustment": round(hist_adj, 2),
                "final_score": round(final_score, 2),
                "compatibility_blockers": compat_blockers,
                "reasons_ar": compat_reasons + hist_notes,
                "readiness_blockers": er.get("blockers") or [],
                "solution_ar": er.get("solution_ar") or "افحص readiness لهذا المحرك.",
            }
            hard_block = (not ready) or bool(compat_blockers)
            if hard_block:
                item["blocked"] = True
                blocked.append(item)
            else:
                item["blocked"] = False
                ranking.append(item)

        ranking.sort(key=lambda x: x.get("final_score", 0), reverse=True)
        selected = ranking[0]["engine"] if ranking else None
        if not selected:
            return fail_output(
                "V37_NO_ENGINE_SELECTED",
                stage="v37_engine_ensemble_plan",
                suspect="no_ready_compatible_engine",
                solution_ar="لا يوجد محرك جاهز ومناسب لهذه الحركة والصورة. أصلح readiness أو استعمل حركة أسهل مثل standing_idle أو أرسل صورة جسم أوضح.",
                requested_engine=requested_engine,
                requested_motion=motion_name,
                readiness_report=readiness,
                pose_truth=pose_truth,
                engine_ranking=ranking,
                blocked_engines=blocked,
                v37_no_fake_success=True,
            )
        return ok_output(
            "v37_engine_ensemble_plan",
            selected_engine=selected,
            requested_engine=requested_engine,
            requested_motion=motion_name,
            engine_ranking=ranking,
            blocked_engines=blocked,
            readiness_report=readiness,
            pose_truth=pose_truth,
            decision_ar=f"V37 اختارت {selected} قبل التشغيل لأنه أفضل محرك جاهز ومناسب للصورة والحركة الحالية.",
            v37_rule_ar="الاختيار تم قبل inference الثقيل. إذا فشل التنفيذ لاحقًا، يستعمل V36 Smart Retry خطة إنقاذ.",
            no_fake_success=True,
        )

    def execute(self, router: Any, request: Dict[str, Any], work_root: Path) -> Dict[str, Any]:
        request = request or {}
        image_b64 = request.get("image_base64") or request.get("source_image_base64") or request.get("image")
        if not image_b64:
            return fail_output(
                "IMAGE_BASE64_REQUIRED_FOR_V37_EXECUTE",
                stage="v37_engine_ensemble_execute",
                suspect="missing_image_base64",
                solution_ar="أرسل image_base64 للتنفيذ. إذا أردت خطة فقط استعمل engine_ensemble_plan.",
            )
        from .input_tools import decode_image_base64, image_info
        job_dir = work_root / f"v37_ensemble_{int(time.time()*1000)}"
        job_dir.mkdir(parents=True, exist_ok=True)
        image_path = decode_image_base64(image_b64, job_dir / "source.png")
        motion_name = str(request.get("motion_name") or request.get("motion") or "standing_idle")
        pose_truth = self.dwpose.analyze(image_path)
        plan = self.plan(request, image_path=image_path, pose_truth=pose_truth)
        if not plan.get("ok"):
            return plan
        selected = plan.get("selected_engine")
        run_request = dict(request)
        run_request["engine"] = selected
        run_request["body_engine"] = selected
        run_request["v37_selected_engine"] = selected
        result = router.run(image_path, motion_name, run_request)
        if isinstance(result, dict):
            result["v37_engine_ensemble_plan"] = {k: v for k, v in plan.items() if k not in {"readiness_report", "pose_truth"}}
            result["v37_selected_engine_before_run"] = selected
            result["v37_image_info"] = image_info(image_path)
        return result
