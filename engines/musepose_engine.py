from __future__ import annotations
import base64
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Dict, Any, List

from .output_contract import fail_output, ok_output
from .motion_library import get_motion

VIDEO_EXTS = (".mp4", ".mov", ".mkv", ".avi", ".webm")

class MusePoseEngine:
    """V24.2 MusePose First Real Motion adapter.

    هذه الطبقة لا تزيف الجسم الكامل ولا تستعمل SadTalker كبديل.
    تعمل فقط إذا كان MusePose مثبتًا فعليًا داخل RunPod ومعه الأوزان.

    طريقة التشغيل المرنة:
    - ضع MusePose في MUSEPOSE_ROOT، افتراضيًا /workspace/MusePose
    - ضع النماذج/الأوزان في MUSEPOSE_WEIGHTS، افتراضيًا /workspace/models/musepose
    - إما تضبط MUSEPOSE_COMMAND_TEMPLATE، أو يستعمل المحرك أوامر شائعة ويحفظ التشخيص.

    MUSEPOSE_COMMAND_TEMPLATE يدعم:
    {python} {root} {source_image} {motion_name} {motion_json} {pose_truth_json} {output_dir} {weights}
    مثال:
    python -u {root}/scripts/inference.py --source_image {source_image} --motion {motion_json} --output_dir {output_dir} --weights {weights}
    """
    def __init__(self):
        self.root = Path(os.environ.get("MUSEPOSE_ROOT", "/workspace/MusePose"))
        self.weights = Path(os.environ.get("MUSEPOSE_WEIGHTS", "/workspace/models/musepose"))
        self.python = os.environ.get("MUSEPOSE_PYTHON", "python")
        self.timeout = int(os.environ.get("MUSEPOSE_TIMEOUT_SECONDS", "1800"))
        self.command_template = os.environ.get("MUSEPOSE_COMMAND_TEMPLATE", "").strip()
        self.workdir = Path(os.environ.get("JUMANA_WORKDIR", "/workspace/outputs"))
        self.workdir.mkdir(parents=True, exist_ok=True)

    def status(self) -> Dict[str, Any]:
        root_ok = self.root.exists()
        weights_ok = self.weights.exists()
        candidates = self._candidate_entrypoints()
        return {
            "engine": "musepose",
            "version_stage": "V34 Pose Dataset Benchmark",
            "root": str(self.root),
            "root_exists": root_ok,
            "weights": str(self.weights),
            "weights_exist": weights_ok,
            "command_template_set": bool(self.command_template),
            "candidate_entrypoints": [str(x) for x in candidates],
            "configured": bool(root_ok and weights_ok and (self.command_template or candidates)),
            "v31_strict_command_recommended": True,
            "no_fake_body_motion": True,
            "sad_talker_is_not_body_engine": True,
            "solution_ar": "إذا configured=false: ثبّت MusePose داخل RunPod واضبط MUSEPOSE_ROOT و MUSEPOSE_WEIGHTS ويفضل MUSEPOSE_COMMAND_TEMPLATE.",
        }

    def _candidate_entrypoints(self) -> List[Path]:
        names = [
            "inference.py",
            "test_stage_2.py",
            "scripts/inference.py",
            "scripts/demo.py",
            "pose2video.py",
            "run.py",
        ]
        return [self.root / n for n in names if (self.root / n).exists()]

    def _find_output_video(self, output_dir: Path, since: float) -> Path | None:
        vids = []
        for p in output_dir.rglob("*"):
            if p.is_file() and p.suffix.lower() in VIDEO_EXTS:
                try:
                    if p.stat().st_mtime >= since and p.stat().st_size > 1024:
                        vids.append(p)
                except Exception:
                    pass
        if not vids:
            return None
        vids.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        return vids[0]

    def _video_to_b64(self, path: Path) -> str:
        return base64.b64encode(path.read_bytes()).decode("ascii")

    def _make_command(self, job_dir: Path, source_image: Path, motion_name: str, motion_json: Path, pose_truth_json: Path, output_dir: Path) -> List[str] | str:
        mapping = {
            "python": self.python,
            "root": str(self.root),
            "source_image": str(source_image),
            "motion_name": motion_name,
            "motion_json": str(motion_json),
            "pose_truth_json": str(pose_truth_json),
            "output_dir": str(output_dir),
            "weights": str(self.weights),
            "input_image": str(source_image),
            "source": str(source_image),
            "output": str(output_dir),
            "job_dir": str(job_dir),
        }
        if self.command_template:
            return self.command_template.format(**mapping)
        entries = self._candidate_entrypoints()
        if not entries:
            raise RuntimeError("No MusePose entrypoint found")
        entry = entries[0]
        # أمر عام قابل للتشخيص. إذا كان MusePose المحلي يحتاج أسماء مختلفة، اضبط MUSEPOSE_COMMAND_TEMPLATE.
        return [
            self.python, "-u", str(entry),
            "--source_image", str(source_image),
            "--motion", str(motion_json),
            "--pose_truth", str(pose_truth_json),
            "--output_dir", str(output_dir),
            "--weights", str(self.weights),
        ]

    def generate(self, image_path: Path, motion_name: str, pose_truth: Dict[str, Any] | None = None) -> Dict[str, Any]:
        st = self.status()
        if not st["root_exists"]:
            return fail_output(
                "MUSEPOSE_ROOT_NOT_FOUND",
                stage="musepose_preflight",
                suspect="musepose_installation_missing",
                solution_ar="MusePose غير موجود داخل RunPod. ثبّته في /workspace/MusePose أو اضبط MUSEPOSE_ROOT. لا أستعمل SadTalker كجسم كامل ولا أرجع فيديو وهميًا.",
                musepose_status=st,
                image_path=str(image_path),
                motion_name=motion_name,
                real_video_generated=False,
            )
        if not st["weights_exist"]:
            return fail_output(
                "MUSEPOSE_WEIGHTS_NOT_FOUND",
                stage="musepose_preflight",
                suspect="musepose_weights_missing",
                solution_ar="أوزان MusePose غير موجودة. ضعها في /workspace/models/musepose أو اضبط MUSEPOSE_WEIGHTS. لا يمكن إنتاج جسم حقيقي بدون أوزان.",
                musepose_status=st,
                image_path=str(image_path),
                motion_name=motion_name,
                real_video_generated=False,
            )
        if not (self.command_template or st["candidate_entrypoints"]):
            return fail_output(
                "MUSEPOSE_COMMAND_NOT_CONFIGURED",
                stage="musepose_preflight",
                suspect="musepose_command_missing",
                solution_ar="MusePose موجود لكن لم أجد ملف inference معروفًا. اضبط MUSEPOSE_COMMAND_TEMPLATE بالأمر الصحيح لتشغيل MusePose داخل RunPod.",
                musepose_status=st,
                image_path=str(image_path),
                motion_name=motion_name,
                real_video_generated=False,
            )

        motion = get_motion(motion_name)
        job_dir = self.workdir / f"musepose_job_{int(time.time()*1000)}"
        output_dir = job_dir / "outputs"
        job_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)
        src = job_dir / "source_image.png"
        shutil.copyfile(image_path, src)
        motion_json = job_dir / "motion_request.json"
        pose_truth_json = job_dir / "pose_truth.json"
        motion_json.write_text(json.dumps({"motion_name": motion_name, "motion": motion, "v24_2": True}, ensure_ascii=False, indent=2), encoding="utf-8")
        pose_truth_json.write_text(json.dumps(pose_truth or {}, ensure_ascii=False, indent=2), encoding="utf-8")

        try:
            cmd = self._make_command(job_dir, src, motion_name, motion_json, pose_truth_json, output_dir)
            started = time.time()
            if isinstance(cmd, str):
                proc = subprocess.run(cmd, shell=True, cwd=str(self.root), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=self.timeout)
                cmd_for_report = cmd
            else:
                proc = subprocess.run(cmd, cwd=str(self.root), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=self.timeout)
                cmd_for_report = cmd
            stdout_tail = (proc.stdout or "")[-6000:]
            stderr_tail = (proc.stderr or "")[-6000:]
            if proc.returncode != 0:
                return fail_output(
                    f"MUSEPOSE_COMMAND_FAILED_RETURN_CODE_{proc.returncode}",
                    stage="musepose_inference",
                    suspect="musepose_runtime_error",
                    solution_ar="MusePose بدأ فعليًا لكنه فشل. راجع stderr_tail. غالبًا السبب: أسماء arguments مختلفة، أوزان ناقصة، أو CUDA/ذاكرة GPU. اضبط MUSEPOSE_COMMAND_TEMPLATE حسب نسخة MusePose عندك.",
                    musepose_status=st,
                    command=cmd_for_report,
                    stdout_tail=stdout_tail,
                    stderr_tail=stderr_tail,
                    image_path=str(image_path),
                    motion_name=motion_name,
                    job_dir=str(job_dir),
                    real_video_generated=False,
                )
            video = self._find_output_video(output_dir, started)
            if not video:
                # بعض نسخ MusePose تكتب في مجلدها الداخلي؛ نبحث أيضًا داخل job_dir ومجلد الجذر outputs.
                video = self._find_output_video(job_dir, started) or self._find_output_video(self.root, started)
            if not video:
                return fail_output(
                    "MUSEPOSE_FINISHED_BUT_NO_VIDEO_FOUND",
                    stage="musepose_output_scan",
                    suspect="musepose_output_path_or_command",
                    solution_ar="MusePose انتهى بدون فيديو واضح. اضبط output_dir أو MUSEPOSE_COMMAND_TEMPLATE حتى يخرج mp4 داخل {output_dir}.",
                    musepose_status=st,
                    command=cmd_for_report,
                    stdout_tail=stdout_tail,
                    stderr_tail=stderr_tail,
                    searched_dirs=[str(output_dir), str(job_dir), str(self.root)],
                    image_path=str(image_path),
                    motion_name=motion_name,
                    job_dir=str(job_dir),
                    real_video_generated=False,
                )
            return ok_output(
                "musepose_real_motion_generated",
                message="MusePose أنتج فيديو جسم كامل حقيقي. لم يتم استعمال SadTalker كبديل للجسم.",
                engine="musepose",
                real_video_generated=True,
                motion_name=motion_name,
                video_path=str(video),
                video_base64=self._video_to_b64(video),
                musepose_status=st,
                command=cmd_for_report,
                stdout_tail=stdout_tail,
                stderr_tail=stderr_tail,
                job_dir=str(job_dir),
            )
        except subprocess.TimeoutExpired as e:
            return fail_output(
                "MUSEPOSE_TIMEOUT",
                stage="musepose_inference_timeout",
                suspect="musepose_too_slow_or_stuck",
                solution_ar="MusePose تجاوز مدة الانتظار. زد MUSEPOSE_TIMEOUT_SECONDS أو استعمل GPU أقوى أو قلل عدد الفريمات.",
                musepose_status=st,
                timeout_seconds=self.timeout,
                stdout_tail=(e.stdout or "")[-4000:] if isinstance(e.stdout, str) else "",
                stderr_tail=(e.stderr or "")[-4000:] if isinstance(e.stderr, str) else "",
                real_video_generated=False,
            )
        except Exception as exc:
            return fail_output(
                str(exc),
                stage="musepose_inference_exception",
                suspect="musepose_adapter_exception",
                solution_ar="وقع خطأ في محول MusePose. راجع criminal_report و traceback_tail في RunPod output.",
                musepose_status=st,
                image_path=str(image_path),
                motion_name=motion_name,
                real_video_generated=False,
            )
