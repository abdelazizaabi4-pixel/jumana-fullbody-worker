from __future__ import annotations
import os, shutil, subprocess, json, time
from pathlib import Path
from typing import Any, Dict, Optional

from .output_contract import ok_output, fail_output
from .musepose_engine import MusePoseEngine

class MusePoseEndToEndLock:
    """V34 Pose Dataset Benchmark.

    الهدف: تثبيت MusePose فقط قبل الانتقال إلى Benchmark.
    لا نقبل التخمين كنجاح عالمي: يجب ضبط MUSEPOSE_COMMAND_TEMPLATE أو يظهر تشخيص صريح.
    """
    def __init__(self, musepose: MusePoseEngine):
        self.musepose = musepose
        self.root = Path(os.environ.get("MUSEPOSE_ROOT", "/workspace/MusePose"))
        self.weights = Path(os.environ.get("MUSEPOSE_WEIGHTS", "/workspace/models/musepose"))
        self.command_template = os.environ.get("MUSEPOSE_COMMAND_TEMPLATE", "").strip()
        self.timeout = int(os.environ.get("MUSEPOSE_TIMEOUT_SECONDS", "1800"))
        self.min_video_bytes = int(os.environ.get("MUSEPOSE_MIN_OUTPUT_BYTES", "100000"))
        self.strict_command = os.environ.get("MUSEPOSE_REQUIRE_COMMAND_TEMPLATE", "1").strip().lower() not in {"0", "false", "no"}
        self.workdir = Path(os.environ.get("JUMANA_WORKDIR", "/workspace/outputs"))
        self.workdir.mkdir(parents=True, exist_ok=True)

    def _gpu_report(self) -> Dict[str, Any]:
        report: Dict[str, Any] = {"torch_available": False, "cuda_available": False, "device_count": 0}
        try:
            import torch  # type: ignore
            report.update({
                "torch_available": True,
                "torch_version": getattr(torch, "__version__", None),
                "cuda_available": bool(torch.cuda.is_available()),
                "device_count": int(torch.cuda.device_count()) if torch.cuda.is_available() else 0,
                "devices": [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())] if torch.cuda.is_available() else [],
            })
        except Exception as e:
            report["torch_error"] = str(e)
        nvidia = shutil.which("nvidia-smi")
        report["nvidia_smi_path"] = nvidia
        if nvidia:
            try:
                p = subprocess.run([nvidia, "--query-gpu=name,memory.total,memory.free", "--format=csv,noheader"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=8)
                report["nvidia_smi_ok"] = p.returncode == 0
                report["nvidia_smi_stdout"] = (p.stdout or "")[-3000:]
                report["nvidia_smi_stderr"] = (p.stderr or "")[-3000:]
            except Exception as e:
                report["nvidia_smi_error"] = str(e)
        return report

    def status(self) -> Dict[str, Any]:
        muse_status = self.musepose.status()
        ffmpeg = shutil.which("ffmpeg")
        blockers = []
        score = 0
        if self.root.exists(): score += 20
        else: blockers.append("MUSEPOSE_ROOT_NOT_FOUND")
        if self.weights.exists(): score += 20
        else: blockers.append("MUSEPOSE_WEIGHTS_NOT_FOUND")
        if self.command_template:
            score += 30
        else:
            blockers.append("MUSEPOSE_COMMAND_TEMPLATE_REQUIRED_BY_V31")
        if ffmpeg:
            score += 10
        else:
            blockers.append("FFMPEG_NOT_FOUND")
        gpu = self._gpu_report()
        if gpu.get("cuda_available") or gpu.get("nvidia_smi_path"):
            score += 20
        else:
            blockers.append("GPU_CUDA_NOT_VISIBLE")
        ready = not blockers
        return {
            "engine": "musepose",
            "v31_musepose_end_to_end_lock": True,
            "ready": ready,
            "score": min(100, score),
            "root": str(self.root),
            "root_exists": self.root.exists(),
            "weights": str(self.weights),
            "weights_exist": self.weights.exists(),
            "command_template_set": bool(self.command_template),
            "strict_command_template_required": self.strict_command,
            "ffmpeg_path": ffmpeg,
            "min_video_bytes": self.min_video_bytes,
            "timeout_seconds": self.timeout,
            "gpu": gpu,
            "musepose_status": muse_status,
            "critical_blockers": blockers,
            "solution_ar": "جاهز لاختبار MusePose End-to-End." if ready else "حل الجناة بالترتيب: ROOT ثم WEIGHTS ثم COMMAND_TEMPLATE ثم GPU/ffmpeg. V31 لا تقبل التخمين كنجاح.",
        }

    def preflight(self) -> Dict[str, Any]:
        st = self.status()
        if not st["ready"]:
            return fail_output(
                "V31_MUSEPOSE_LOCK_NOT_READY",
                stage="v31_musepose_lock_preflight",
                suspect="musepose_environment_or_command_not_locked",
                solution_ar=st["solution_ar"],
                v31_musepose_lock_status=st,
                next_step_ar="ضع MusePose والأوزان على RunPod Volume واضبط MUSEPOSE_COMMAND_TEMPLATE ثم أعد task=musepose_lock_status.",
            )
        return ok_output(
            "v31_musepose_lock_preflight_passed",
            v31_musepose_lock_status=st,
            decision_ar="MusePose جاهز مبدئيًا لاختبار End-to-End قصير. الآن شغّل task=musepose_e2e_lock_test بصورة جسم كاملة واضحة.",
        )

    def run_e2e_test(self, image_path: Path, motion_name: str, pose_truth: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        pre = self.preflight()
        if not pre.get("ok"):
            return pre
        manifest_dir = self.workdir / f"v31_musepose_lock_{int(time.time()*1000)}"
        manifest_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "version": "V36_SMART_RETRY_2",
            "engine": "musepose",
            "motion_name": motion_name,
            "image_path": str(image_path),
            "root": str(self.root),
            "weights": str(self.weights),
            "strict_command_template_required": self.strict_command,
            "started_ms": int(time.time()*1000),
            "goal_ar": "إثبات أن MusePose ينتج فيديو جسم حقيقي End-to-End من صورة + motion، بدون SadTalker وبدون فيديو وهمي.",
        }
        manifest_path = manifest_dir / "v31_musepose_lock_manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        result = self.musepose.generate(image_path, motion_name, pose_truth=pose_truth or {})
        result["v31_musepose_lock_manifest_path"] = str(manifest_path)
        result["v31_lock_preflight"] = pre
        result["v31_lock_rule_ar"] = "إذا ok=true ومعه video_base64 أو video_url وفيديو حجمه منطقي، نعتبر MusePose مقفلًا End-to-End كبداية. إذا فشل، الجاني في output يحدد المسار بدقة."
        if result.get("ok"):
            video_path = result.get("video_path")
            size = 0
            try:
                if video_path:
                    size = Path(video_path).stat().st_size
            except Exception:
                size = 0
            if not (result.get("video_base64") or result.get("video_url")):
                return fail_output(
                    "V31_MUSEPOSE_OK_BUT_NO_VIDEO_OUTPUT_KEY",
                    stage="v31_musepose_output_contract",
                    suspect="musepose_adapter_output_contract",
                    solution_ar="MusePose قال نجاحًا لكن لم يرجع video_base64 أو video_url. أصلح output contract قبل اعتبار الاختبار ناجحًا.",
                    previous_result=result,
                    real_video_generated=False,
                )
            if video_path and size and size < self.min_video_bytes:
                return fail_output(
                    "V31_MUSEPOSE_VIDEO_TOO_SMALL",
                    stage="v31_musepose_output_quality_gate",
                    suspect="musepose_output_too_small_or_corrupt",
                    solution_ar="خرج ملف فيديو لكنه صغير جدًا. افحص command template وعدد الفريمات والأوزان.",
                    previous_result=result,
                    video_size_bytes=size,
                    min_video_bytes=self.min_video_bytes,
                    real_video_generated=False,
                )
            result["v31_musepose_end_to_end_locked"] = True
            result["v31_success_ar"] = "تم إثبات MusePose End-to-End: صورة + pose/motion -> فيديو جسم حقيقي. الآن يمكن الانتقال إلى V34 Benchmark."
        else:
            result["v31_musepose_end_to_end_locked"] = False
            result["v31_failure_ar"] = "لم نغلق MusePose بعد. أصلح الجاني الظاهر ثم أعد نفس الاختبار، ولا تنتقل إلى Benchmark قبل نجاح هذا الاختبار."
        return result
