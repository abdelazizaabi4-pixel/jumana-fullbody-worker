
from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .output_contract import ok_output, fail_output


def _norm(s: Any) -> str:
    return str(s or "").strip().lower()


def _score_from_quality(q: Dict[str, Any]) -> float:
    for key in ("overall_quality_score", "quality_score", "score", "overall_score"):
        try:
            if key in q:
                return float(q.get(key) or 0)
        except Exception:
            pass
    return 0.0


def _is_strict_pass(q: Dict[str, Any], threshold: float = 76.0) -> bool:
    if bool(q.get("world_class_gate_pass")) or bool(q.get("strict_quality_pass")):
        return True
    return _score_from_quality(q) >= threshold


def _video_from_result(result: Dict[str, Any]) -> Optional[str]:
    if not isinstance(result, dict):
        return None
    for k in ("video_base64", "result_video_base64", "final_video_base64", "composed_video_base64"):
        v = result.get(k)
        if isinstance(v, str) and len(v) > 100:
            return v
    out = result.get("output")
    if isinstance(out, dict):
        return _video_from_result(out)
    return None


class SmartRetryBrainV2:
    """
    V36 Smart Retry 2.0
    This brain does not fake success. It only retries with safer plans and returns the best real video if one exists.
    It can also produce a retry plan from a V35 quality report without running heavy engines.
    """

    VERSION = "V36_SMART_RETRY_2"

    DEFAULT_LADDER: List[Dict[str, Any]] = [
        {
            "level": 1,
            "name": "original_plan",
            "motion_name": None,
            "engine": "auto",
            "why_ar": "المحاولة الأولى بالخطة الأصلية كما طلب المستخدم.",
        },
        {
            "level": 2,
            "name": "safe_speaker_gesture",
            "motion_name": "right_hand_explain",
            "engine": "musepose",
            "why_ar": "إذا تشوهت اليدان أو فشل الجسم الكامل، نجرب حركة شرح بيد واحدة لأنها أسلم من اليدين والمشي.",
        },
        {
            "level": 3,
            "name": "standing_idle",
            "motion_name": "standing_idle",
            "engine": "musepose",
            "why_ar": "إذا بقي التشوه، نخفض الحركة إلى وقوف وتنفس طبيعي للحفاظ على الجسم والهوية.",
        },
        {
            "level": 4,
            "name": "head_and_shoulders_safe",
            "motion_name": "head_turn",
            "engine": "musepose",
            "why_ar": "إذا فشل الجسم الكامل، نجرب حركة رأس وكتفين فقط كإنقاذ جسم آمن.",
        },
    ]

    def status(self) -> Dict[str, Any]:
        return ok_output(
            "v36_smart_retry_status",
            smart_retry_2={
                "enabled": True,
                "uses_v35_quality_report": True,
                "can_execute_real_retries_when_image_is_supplied": True,
                "default_max_attempts": 4,
                "never_fakes_video": True,
                "keeps_best_real_result_only": True,
            },
            rule_ar="V36 لا تعطي نجاحًا وهميًا. إن لم يظهر فيديو حقيقي من محرك حقيقي، ترجع خطة وجانيًا وحلًا.",
        )

    def template(self) -> Dict[str, Any]:
        return ok_output(
            "v36_smart_retry_template",
            example_plan_only={
                "task": "smart_retry_plan",
                "quality_report": {
                    "overall_quality_score": 52,
                    "main_criminal_ar": "hands_deformation",
                    "solution_ar": "أعد المحاولة بحركة يد أبسط",
                },
                "requested_motion": "both_hands_explain",
            },
            example_execute={
                "task": "smart_retry_execute",
                "image_base64": "PUT_IMAGE_BASE64_HERE",
                "motion_name": "both_hands_explain",
                "engine": "auto",
                "max_attempts": 4,
                "quality_threshold": 76,
            },
            outputs=[
                "v36_retry_plan",
                "attempts",
                "best_attempt",
                "best_video_base64 إذا وُجد فيديو حقيقي فقط",
                "v36_retry_report",
            ],
        )

    def _criminal_text(self, quality_report: Dict[str, Any]) -> str:
        parts = []
        for k in ("main_criminal_ar", "main_criminal", "suspect", "error", "stage"):
            if quality_report.get(k):
                parts.append(str(quality_report.get(k)))
        cr = quality_report.get("criminal_report")
        if isinstance(cr, dict):
            parts += [str(v) for v in cr.values() if v]
        return " | ".join(parts).lower()

    def plan(self, request: Dict[str, Any]) -> Dict[str, Any]:
        quality_report = request.get("quality_report") or request.get("v35_quality_report") or {}
        if not isinstance(quality_report, dict):
            quality_report = {}
        requested_motion = str(request.get("motion_name") or request.get("requested_motion") or "standing_idle")
        requested_engine = str(request.get("engine") or request.get("body_engine") or "auto")
        score = _score_from_quality(quality_report)
        criminal = self._criminal_text(quality_report)

        ladder = []
        first = dict(self.DEFAULT_LADDER[0])
        first["motion_name"] = requested_motion
        first["engine"] = requested_engine
        ladder.append(first)

        # Criminal-aware priorities.
        if any(x in criminal for x in ["hand", "hands", "يد", "hands_deformation"]):
            ladder += [
                {"level": 2, "name": "one_hand_instead_of_two", "motion_name": "right_hand_explain", "engine": "musepose", "why_ar": "الجاني هو اليدان؛ نجرب يدًا واحدة بدل اليدين."},
                {"level": 3, "name": "no_hands_standing", "motion_name": "standing_idle", "engine": "musepose", "why_ar": "إذا بقي تشوه اليد، نوقف حركة اليد ونحافظ على الجسم."},
                {"level": 4, "name": "head_shoulders_only", "motion_name": "head_turn", "engine": "musepose", "why_ar": "آخر إنقاذ: رأس وكتف فقط."},
            ]
        elif any(x in criminal for x in ["walk", "feet", "قدم", "مشي", "pose_error"]):
            ladder += [
                {"level": 2, "name": "remove_walking", "motion_name": "standing_idle", "engine": "musepose", "why_ar": "الجاني هو المشي/القدمين؛ نمنع المشي ونثبت الجسم."},
                {"level": 3, "name": "speaker_gesture", "motion_name": "right_hand_explain", "engine": "musepose", "why_ar": "نستبدل المشي بحركة شرح خفيفة."},
                {"level": 4, "name": "head_turn_safe", "motion_name": "head_turn", "engine": "musepose", "why_ar": "حركة رأس بسيطة إذا فشل الجسم."},
            ]
        elif any(x in criminal for x in ["flicker", "وميض", "jitter", "اهتزاز", "head_tracking"]):
            ladder += [
                {"level": 2, "name": "lower_motion_energy", "motion_name": "standing_idle", "engine": "musepose", "why_ar": "الجاني اهتزاز/وميض؛ نقلل الحركة إلى وقوف طبيعي."},
                {"level": 3, "name": "composer_safe_mode", "motion_name": "head_turn", "engine": "musepose", "why_ar": "نحافظ على حركة رأس بسيطة تسهّل التتبع والتركيب."},
            ]
        elif any(x in criminal for x in ["musepose", "command", "weights", "engine", "inference"]):
            ladder += [
                {"level": 2, "name": "retry_musepose_safe_motion", "motion_name": "standing_idle", "engine": "musepose", "why_ar": "نجرب MusePose بحركة أسهل للتأكد هل المشكلة من الحركة أم من المحرك."},
                {"level": 3, "name": "try_magicanimate_if_ready", "motion_name": "standing_idle", "engine": "magicanimate", "why_ar": "إذا فشل MusePose، نجرب MagicAnimate فقط إذا كان جاهزًا."},
                {"level": 4, "name": "try_animateanyone_if_ready", "motion_name": "standing_idle", "engine": "animateanyone", "why_ar": "اختيار ثالث إذا كان جاهزًا ولا نزيف النجاح."},
            ]
        else:
            ladder += self.DEFAULT_LADDER[1:]

        # Deduplicate same engine+motion while keeping order.
        seen = set()
        unique = []
        for item in ladder:
            key = (item.get("engine"), item.get("motion_name"))
            if key in seen:
                continue
            seen.add(key)
            item = dict(item)
            item["level"] = len(unique) + 1
            unique.append(item)

        threshold = float(request.get("quality_threshold") or 76.0)
        should_retry = score < threshold or not quality_report or not _is_strict_pass(quality_report, threshold)
        return ok_output(
            "v36_smart_retry_plan",
            should_retry=should_retry,
            current_quality_score=score,
            quality_threshold=threshold,
            detected_criminal=criminal or "unknown_or_not_supplied",
            v36_retry_ladder=unique,
            best_expected_strategy_ar="اخفض الحركة حسب الجاني بدل تكرار نفس الفشل. لا تنتقل إلى محرك آخر إلا إذا فشل المحرك الأول أو كان غير جاهز.",
            no_fake_success=True,
        )

    def execute(self, router: Any, request: Dict[str, Any], work_root: Path) -> Dict[str, Any]:
        """Run real retries through the router when an image is supplied."""
        plan = self.plan(request)
        image_b64 = request.get("image_base64") or request.get("source_image_base64") or request.get("image")
        if not image_b64:
            plan["execution_skipped"] = True
            plan["solution_ar"] = "أرسل image_base64 لتشغيل Smart Retry فعليًا، أو استعمل smart_retry_plan للحصول على خطة فقط."
            return plan

        from .input_tools import decode_image_base64, image_info

        job_dir = work_root / f"v36_retry_{int(time.time()*1000)}"
        job_dir.mkdir(parents=True, exist_ok=True)
        image_path = decode_image_base64(image_b64, job_dir / "source.png")
        threshold = float(request.get("quality_threshold") or 76.0)
        max_attempts = int(request.get("max_attempts") or 4)
        attempts: List[Dict[str, Any]] = []
        best: Optional[Dict[str, Any]] = None
        best_score = -1.0
        best_video: Optional[str] = None

        for i, step in enumerate(plan.get("v36_retry_ladder", [])[:max_attempts], start=1):
            motion = step.get("motion_name") or request.get("motion_name") or "standing_idle"
            engine = step.get("engine") or request.get("engine") or "auto"
            attempt_req = dict(request)
            attempt_req.update({"motion_name": motion, "engine": engine, "body_engine": engine})
            started = time.time()
            try:
                result = router.run(image_path, motion, attempt_req)
            except Exception as e:
                result = fail_output(str(e), stage="v36_attempt_exception", suspect="smart_retry_attempt_exception", solution_ar="افحص traceback؛ فشلت محاولة داخل Smart Retry.")
            elapsed = round(time.time() - started, 3)
            video_b64 = _video_from_result(result)
            quality_result: Dict[str, Any]
            if video_b64:
                quality_result = router.deep_quality_judge({
                    "video_base64": video_b64,
                    "expected_motion": motion,
                    "talking_expected": bool(request.get("talking_expected")),
                    "strict": bool(request.get("strict", True)),
                })
            else:
                quality_result = fail_output(
                    "ATTEMPT_RETURNED_NO_VIDEO",
                    stage="v36_quality_after_attempt",
                    suspect=result.get("suspect", "body_engine_returned_no_video") if isinstance(result, dict) else "body_engine_returned_no_video",
                    solution_ar="هذه المحاولة لم تنتج فيديو حقيقيًا. سنجرب المحاولة التالية في السلم.",
                    attempt_stage=result.get("stage") if isinstance(result, dict) else None,
                )
            score = _score_from_quality(quality_result)
            attempt_record = {
                "attempt": i,
                "plan_step": step,
                "elapsed_seconds": elapsed,
                "engine_result_ok": bool(result.get("ok")) if isinstance(result, dict) else False,
                "engine_stage": result.get("stage") if isinstance(result, dict) else None,
                "engine_suspect": result.get("suspect") if isinstance(result, dict) else None,
                "has_video": bool(video_b64),
                "quality_score": score,
                "quality_pass": _is_strict_pass(quality_result, threshold),
                "quality_stage": quality_result.get("stage") if isinstance(quality_result, dict) else None,
                "quality_suspect": quality_result.get("suspect") if isinstance(quality_result, dict) else None,
                "quality_main_criminal_ar": quality_result.get("main_criminal_ar") if isinstance(quality_result, dict) else None,
            }
            attempts.append(attempt_record)
            if video_b64 and score > best_score:
                best_score = score
                best = {"attempt": i, "step": step, "engine_result": result, "quality_result": quality_result}
                best_video = video_b64
            if video_b64 and _is_strict_pass(quality_result, threshold):
                break

        report = {
            "version": self.VERSION,
            "image_info": image_info(image_path),
            "quality_threshold": threshold,
            "attempts_count": len(attempts),
            "attempts": attempts,
            "best_score": best_score,
            "best_attempt": best.get("attempt") if best else None,
            "final_pass": bool(best_video and best_score >= threshold),
            "no_fake_success": True,
        }
        try:
            (job_dir / "v36_retry_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

        if best_video:
            return ok_output(
                "v36_smart_retry_finished_with_best_real_video",
                video_base64=best_video,
                v36_retry_report=report,
                best_attempt=best.get("attempt") if best else None,
                best_quality_score=best_score,
                strict_quality_pass=bool(best_score >= threshold),
                solution_ar="تم اختيار أفضل فيديو حقيقي خرج من المحاولات. إذا لم يصل للعتبة، فالتقرير يحدد الجاني التالي.",
            )
        return fail_output(
            "V36_ALL_RETRY_ATTEMPTS_FAILED_NO_REAL_VIDEO",
            stage="v36_smart_retry_finished_without_video",
            suspect="all_body_engines_or_motion_plans_failed",
            solution_ar="لم يخرج أي فيديو حقيقي من المحاولات. افحص readiness وMusePose lock ثم جرب standing_idle بصورة جسم كاملة واضحة.",
            v36_retry_report=report,
            v36_plan=plan,
        )
