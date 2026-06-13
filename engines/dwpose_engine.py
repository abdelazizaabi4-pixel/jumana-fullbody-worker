from __future__ import annotations
import base64, importlib.util, io, json, os, traceback
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

import numpy as np
from PIL import Image

from .output_contract import fail_output, ok_output, exception_output


def _module_exists(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def _img_to_b64(img: Image.Image, fmt: str = "PNG") -> str:
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def _file_to_b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("utf-8")


class DWPoseTruthEngine:
    """V24.2 real DWPose Truth Engine.

    الهدف: لا نسمح للجسم/المشي إلا بعد رؤية pose حقيقي.
    يعتمد أولاً على controlnet_aux.DWposeDetector إن كان متوفرًا.
    يرجع pose render + scores + سبب منع/سماح الحركات.
    """

    def __init__(self):
        self.enable_real = os.environ.get("DWPOSE_ENABLE_REAL", "1") != "0"
        self.model_id = os.environ.get("DWPOSE_MODEL_ID", "lllyasviel/Annotators")
        self.cache_dir = Path(os.environ.get("HF_HOME", "/workspace/models/huggingface"))
        self.output_dir = Path(os.environ.get("JUMANA_WORKDIR", "/workspace/outputs")) / "dwpose_truth"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._detector = None
        self._detector_error: Optional[str] = None

    def status(self) -> Dict[str, Any]:
        return {
            "engine": "dwpose",
            "stage": "v24_1_real_dwpose_truth_engine",
            "real_enabled": self.enable_real,
            "controlnet_aux_available": _module_exists("controlnet_aux"),
            "torch_available": _module_exists("torch"),
            "onnxruntime_available": _module_exists("onnxruntime"),
            "model_id": self.model_id,
            "cache_dir": str(self.cache_dir),
            "configured": bool(self.enable_real and _module_exists("controlnet_aux")),
            "purpose_ar": "استخراج pose حقيقي وتقرير: هل اليدان/القدمان/الجسم تصلح للحركة؟",
        }

    def _load_detector(self):
        if self._detector is not None:
            return self._detector
        if not self.enable_real:
            raise RuntimeError("DWPOSE_REAL_DISABLED_BY_ENV")
        try:
            # أكثر الصيغ شيوعًا في controlnet-aux.
            try:
                from controlnet_aux import DWposeDetector  # type: ignore
            except Exception:
                from controlnet_aux.dwpose import DWposeDetector  # type: ignore
            self._detector = DWposeDetector.from_pretrained(self.model_id)
            return self._detector
        except Exception as e:
            self._detector_error = traceback.format_exc()[-4000:]
            raise RuntimeError(f"DWPOSE_DETECTOR_LOAD_FAILED: {e}") from e

    def _run_detector(self, image: Image.Image) -> Image.Image:
        detector = self._load_detector()
        try:
            pose = detector(image)
        except TypeError:
            pose = detector(image, detect_resolution=768, image_resolution=768)
        if not isinstance(pose, Image.Image):
            try:
                pose = Image.fromarray(np.array(pose).astype("uint8"))
            except Exception as e:
                raise RuntimeError(f"DWPOSE_OUTPUT_NOT_IMAGE: {type(pose)} {e}")
        return pose.convert("RGB")

    @staticmethod
    def _estimate_truth_from_pose(pose_img: Image.Image) -> Dict[str, Any]:
        arr = np.array(pose_img.convert("RGB"))
        h, w = arr.shape[:2]
        # DWPose render غالبًا خطوط ملونة على خلفية سوداء/داكنة.
        mask = arr.max(axis=2) > 30
        count = int(mask.sum())
        coverage = float(count / max(1, h * w))
        if count < 20:
            return {
                "person_detected": False,
                "pose_coverage": coverage,
                "body_bbox_norm": None,
                "head_visible": False,
                "torso_visible": False,
                "hands_visible": False,
                "feet_visible": False,
                "walking_allowed": False,
                "hands_motion_allowed": False,
                "standing_motion_allowed": False,
                "scores": {
                    "body_score": 0,
                    "hands_score": 0,
                    "feet_score": 0,
                    "walking_score": 0,
                },
                "reason_ar": "لم يظهر أي pose واضح من DWPose. الصورة لا تصلح للجسم الحقيقي بهذه الحالة.",
            }

        ys, xs = np.where(mask)
        x1, y1, x2, y2 = int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())
        bw, bh = x2 - x1 + 1, y2 - y1 + 1
        bbox = {
            "x1": round(x1 / w, 4), "y1": round(y1 / h, 4),
            "x2": round(x2 / w, 4), "y2": round(y2 / h, 4),
            "width": round(bw / w, 4), "height": round(bh / h, 4),
        }

        # تقسيمات تقريبية من pose render. هذه ليست keypoints خام لكنها تعطي قرارًا عمليًا لحراسة الحركة.
        top = mask[: int(h * 0.28), :].sum()
        mid = mask[int(h * 0.28): int(h * 0.72), :].sum()
        bottom = mask[int(h * 0.72):, :].sum()
        left_mid = mask[int(h * 0.25): int(h * 0.75), : int(w * 0.38)].sum()
        right_mid = mask[int(h * 0.25): int(h * 0.75), int(w * 0.62):].sum()
        lower_extreme = mask[int(h * 0.82):, :].sum()

        body_score = min(100, int((bh / h) * 120 + coverage * 700))
        head_score = min(100, int((top / max(1, count)) * 250))
        torso_score = min(100, int((mid / max(1, count)) * 180))
        hands_score = min(100, int(((left_mid + right_mid) / max(1, count)) * 220))
        feet_score = min(100, int((lower_extreme / max(1, count)) * 280 + (1 if y2 > h * 0.78 else 0) * 30))

        head_visible = head_score >= 10 or y1 < h * 0.35
        torso_visible = torso_score >= 20 and bh > h * 0.32
        hands_visible = hands_score >= 18 and (left_mid > 10 or right_mid > 10)
        feet_visible = feet_score >= 18 and y2 > h * 0.75
        standing_allowed = bool(head_visible and torso_visible and bh > h * 0.42)
        hands_allowed = bool(standing_allowed and hands_visible)
        walking_allowed = bool(standing_allowed and feet_visible and bh > h * 0.62)

        reasons = []
        if not head_visible:
            reasons.append("الرأس غير واضح في pose.")
        if not torso_visible:
            reasons.append("الجذع غير واضح بما يكفي.")
        if not hands_visible:
            reasons.append("اليدان غير واضحتين؛ حركة اليدين قد تتشوه.")
        if not feet_visible:
            reasons.append("القدمان غير واضحتين؛ المشي ممنوع الآن.")
        if not reasons:
            reasons.append("الصورة صالحة لحركة جسم واقف، والمشي مسموح مبدئيًا إذا كان محرك MusePose جاهزًا.")

        return {
            "person_detected": True,
            "pose_coverage": round(coverage, 6),
            "body_bbox_norm": bbox,
            "head_visible": bool(head_visible),
            "torso_visible": bool(torso_visible),
            "hands_visible": bool(hands_visible),
            "feet_visible": bool(feet_visible),
            "standing_motion_allowed": bool(standing_allowed),
            "hands_motion_allowed": bool(hands_allowed),
            "walking_allowed": bool(walking_allowed),
            "scores": {
                "body_score": int(body_score),
                "head_score": int(head_score),
                "torso_score": int(torso_score),
                "hands_score": int(hands_score),
                "feet_score": int(feet_score),
                "walking_score": int(min(100, (body_score + feet_score) / 2)),
            },
            "reason_ar": " ".join(reasons),
        }

    def analyze(self, image_path: Path) -> Dict[str, Any]:
        st = self.status()
        if not st["configured"]:
            return fail_output(
                "DWPOSE_RUNTIME_NOT_READY",
                stage="dwpose_truth_engine_not_ready",
                suspect="dwpose_engine_installation",
                solution_ar="ابنِ Docker tag v24-2 الذي يثبت controlnet-aux، أو فعّل DWPOSE_ENABLE_REAL=1. لا نسمح بحركة جسم حقيقية بلا DWPose.",
                dwpose_status=st,
                body_truth={
                    "walking_allowed": False,
                    "hands_motion_allowed": False,
                    "standing_motion_allowed": False,
                    "reason_ar": "DWPose غير جاهز في البيئة الحالية.",
                },
            )
        try:
            image = Image.open(image_path).convert("RGB")
            pose_img = self._run_detector(image)
            truth = self._estimate_truth_from_pose(pose_img)

            job_dir = image_path.parent
            pose_path = job_dir / "dwpose_pose_render.png"
            report_path = job_dir / "dwpose_truth_report.json"
            pose_img.save(pose_path)

            report = {
                "dwpose_status": st,
                "source_image": {"width": image.width, "height": image.height, "path": str(image_path)},
                "pose_render_path": str(pose_path),
                "body_truth": truth,
                "motion_decision_ar": self.motion_decision_ar(truth),
            }
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

            return ok_output(
                "dwpose_truth_extracted",
                dwpose_status=st,
                source_image={"width": image.width, "height": image.height, "path": str(image_path)},
                pose_render_path=str(pose_path),
                pose_render_base64=_file_to_b64(pose_path),
                body_truth=truth,
                motion_decision_ar=self.motion_decision_ar(truth),
                report_path=str(report_path),
                next_step_ar="V24.2 سيرسل هذا pose إلى MusePose لإنتاج أول فيديو جسم حقيقي.",
            )
        except Exception as e:
            return exception_output(
                e,
                stage="dwpose_inference_failed",
                suspect="dwpose_runtime_or_model",
                solution_ar="افحص Logs و traceback_tail. غالبًا فشل تحميل نموذج DWPose أو نقص ملف/ذاكرة GPU. لا نسمح بالانتقال إلى MusePose قبل نجاح DWPose.",
                dwpose_status=st,
                detector_error_tail=self._detector_error,
                image_path=str(image_path),
            )

    @staticmethod
    def motion_decision_ar(truth: Dict[str, Any]) -> str:
        if not truth.get("person_detected"):
            return "لا توجد هيئة إنسان واضحة؛ لا نبدأ الجسم الحقيقي."
        if truth.get("walking_allowed"):
            return "المشي الخفيف مسموح مبدئيًا، لكن نبدأ أولًا بحركة وقوف آمنة."
        if truth.get("hands_motion_allowed"):
            return "حركة اليدين مسموحة، لكن المشي ممنوع لأن القدمين غير كافيتين."
        if truth.get("standing_motion_allowed"):
            return "حركة رأس وكتفين/وقوف مسموحة، وحركة اليدين أو المشي غير آمنة."
        return "الصورة ضعيفة للجسم؛ الأفضل استخدام وجه وكلام أو صورة أوضح للجسم."
