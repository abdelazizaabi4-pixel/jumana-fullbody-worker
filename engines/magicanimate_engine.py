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

class MagicAnimateEngine:
    """V29 AnimateAnyone Third Engine adapter.

    هذا المحرك ليس بديلًا وهميًا. يعمل فقط إذا كان MagicAnimate مثبتًا فعليًا داخل RunPod ومعه الأوزان.

    الهدف من V28:
    - MusePose يبقى المحرك الأول للجسم الحقيقي.
    - MagicAnimate يصبح اختيارًا ثانيًا للثبات الزمني وتحريك الصورة المرجعية بواسطة motion sequence.
    - إذا لم يكن MagicAnimate مركبًا، يرجع تشخيصًا صريحًا ولا يدعي النجاح.

    متغيرات البيئة:
    MAGICANIMATE_ROOT=/workspace/MagicAnimate
    MAGICANIMATE_WEIGHTS=/workspace/models/magicanimate
    MAGICANIMATE_PYTHON=python
    MAGICANIMATE_TIMEOUT_SECONDS=1800
    MAGICANIMATE_COMMAND_TEMPLATE="python -u {root}/... --source_image {source_image} --motion {motion_json} --output_dir {output_dir} --pretrained_model {weights}"

    يدعم القالب:
    {python} {root} {source_image} {motion_name} {motion_json} {pose_truth_json} {output_dir} {weights}
    """
    def __init__(self):
        self.root = Path(os.environ.get("MAGICANIMATE_ROOT", "/workspace/MagicAnimate"))
        self.weights = Path(os.environ.get("MAGICANIMATE_WEIGHTS", "/workspace/models/magicanimate"))
        self.python = os.environ.get("MAGICANIMATE_PYTHON", "python")
        self.timeout = int(os.environ.get("MAGICANIMATE_TIMEOUT_SECONDS", "1800"))
        self.command_template = os.environ.get("MAGICANIMATE_COMMAND_TEMPLATE", "").strip()
        self.workdir = Path(os.environ.get("JUMANA_WORKDIR", "/workspace/outputs"))
        self.workdir.mkdir(parents=True, exist_ok=True)

    def status(self) -> Dict[str, Any]:
        root_ok = self.root.exists()
        weights_ok = self.weights.exists()
        candidates = self._candidate_entrypoints()
        return {
            "engine": "magicanimate",
            "version_stage": "V29 AnimateAnyone Third Engine",
            "root": str(self.root),
            "root_exists": root_ok,
            "weights": str(self.weights),
            "weights_exist": weights_ok,
            "command_template_set": bool(self.command_template),
            "candidate_entrypoints": [str(x) for x in candidates],
            "configured": bool(root_ok and weights_ok and (self.command_template or candidates)),
            "no_fake_body_motion": True,
            "sad_talker_is_not_body_engine": True,
            "engine_role_ar": "محرك ثانٍ للجسم الحقيقي والثبات الزمني بعد MusePose، وليس بديلًا وهميًا.",
            "solution_ar": "إذا configured=false: ثبّت MagicAnimate داخل RunPod واضبط MAGICANIMATE_ROOT وMAGICANIMATE_WEIGHTS ويفضل MAGICANIMATE_COMMAND_TEMPLATE.",
        }

    def _candidate_entrypoints(self) -> List[Path]:
        names = [
            "inference.py",
            "demo/animate.py",
            "scripts/inference.py",
            "scripts/animate.py",
            "magicanimate/pipelines/animation.py",
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
        }
        if self.command_template:
            return self.command_template.format(**mapping)
        entries = self._candidate_entrypoints()
        if not entries:
            raise RuntimeError("No MagicAnimate entrypoint found")
        entry = entries[0]
        # أمر عام قابل للتشخيص. أغلب نسخ MagicAnimate تحتاج قالبًا مخصصًا، لذلك الأفضل ضبط MAGICANIMATE_COMMAND_TEMPLATE.
        return [
            self.python, "-u", str(entry),
            "--source_image", str(source_image),
            "--motion", str(motion_json),
            "--pose_truth", str(pose_truth_json),
            "--output_dir", str(output_dir),
            "--pretrained_model", str(self.weights),
        ]

    def generate(self, image_path: Path, motion_name: str, pose_truth: Dict[str, Any] | None = None, previous_engine_error: Dict[str, Any] | None = None) -> Dict[str, Any]:
        st = self.status()
        if not st["root_exists"]:
            return fail_output(
                "MAGICANIMATE_ROOT_NOT_FOUND",
                stage="magicanimate_preflight",
                suspect="magicanimate_installation_missing",
                solution_ar="MagicAnimate غير موجود داخل RunPod. ثبّته في /workspace/MagicAnimate أو اضبط MAGICANIMATE_ROOT. لا أرجع فيديو وهميًا.",
                magicanimate_status=st,
                previous_engine_error=previous_engine_error,
                image_path=str(image_path),
                motion_name=motion_name,
                real_video_generated=False,
            )
        if not st["weights_exist"]:
            return fail_output(
                "MAGICANIMATE_WEIGHTS_NOT_FOUND",
                stage="magicanimate_preflight",
                suspect="magicanimate_weights_missing",
                solution_ar="أوزان MagicAnimate غير موجودة. ضعها في /workspace/models/magicanimate أو اضبط MAGICANIMATE_WEIGHTS.",
                magicanimate_status=st,
                previous_engine_error=previous_engine_error,
                image_path=str(image_path),
                motion_name=motion_name,
                real_video_generated=False,
            )
        if not (self.command_template or st["candidate_entrypoints"]):
            return fail_output(
                "MAGICANIMATE_COMMAND_NOT_CONFIGURED",
                stage="magicanimate_preflight",
                suspect="magicanimate_command_missing",
                solution_ar="MagicAnimate موجود لكن لم أجد ملف inference معروفًا. اضبط MAGICANIMATE_COMMAND_TEMPLATE بالأمر الصحيح.",
                magicanimate_status=st,
                previous_engine_error=previous_engine_error,
                image_path=str(image_path),
                motion_name=motion_name,
                real_video_generated=False,
            )

        motion = get_motion(motion_name)
        job_dir = self.workdir / f"magicanimate_job_{int(time.time()*1000)}"
        output_dir = job_dir / "outputs"
        job_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)
        src = job_dir / "source_image.png"
        shutil.copyfile(image_path, src)
        motion_json = job_dir / "motion_request.json"
        pose_truth_json = job_dir / "pose_truth.json"
        motion_json.write_text(json.dumps({"motion_name": motion_name, "motion": motion, "v29": True, "engine": "magicanimate"}, ensure_ascii=False, indent=2), encoding="utf-8")
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
                    f"MAGICANIMATE_COMMAND_FAILED_RETURN_CODE_{proc.returncode}",
                    stage="magicanimate_inference",
                    suspect="magicanimate_runtime_error",
                    solution_ar="MagicAnimate بدأ فعليًا لكنه فشل. راجع stderr_tail. غالبًا تحتاج تعديل MAGICANIMATE_COMMAND_TEMPLATE حسب نسخة MagicAnimate والأوزان.",
                    magicanimate_status=st,
                    previous_engine_error=previous_engine_error,
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
                video = self._find_output_video(job_dir, started) or self._find_output_video(self.root, started)
            if not video:
                return fail_output(
                    "MAGICANIMATE_FINISHED_BUT_NO_VIDEO_FOUND",
                    stage="magicanimate_output_scan",
                    suspect="magicanimate_output_path_or_command",
                    solution_ar="MagicAnimate انتهى بدون فيديو واضح. اضبط output_dir أو MAGICANIMATE_COMMAND_TEMPLATE حتى يخرج mp4 داخل {output_dir}.",
                    magicanimate_status=st,
                    previous_engine_error=previous_engine_error,
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
                "magicanimate_real_motion_generated",
                message="MagicAnimate أنتج فيديو جسم كامل/زمني حقيقي. لم يتم استعمال SadTalker كبديل للجسم.",
                engine="magicanimate",
                v29_second_engine=True,
                real_video_generated=True,
                motion_name=motion_name,
                video_path=str(video),
                video_base64=self._video_to_b64(video),
                magicanimate_status=st,
                previous_engine_error=previous_engine_error,
                command=cmd_for_report,
                stdout_tail=stdout_tail,
                stderr_tail=stderr_tail,
                job_dir=str(job_dir),
            )
        except subprocess.TimeoutExpired as e:
            return fail_output(
                "MAGICANIMATE_TIMEOUT",
                stage="magicanimate_inference_timeout",
                suspect="magicanimate_too_slow_or_stuck",
                solution_ar="MagicAnimate تجاوز مدة الانتظار. زد MAGICANIMATE_TIMEOUT_SECONDS أو استعمل GPU أقوى أو قلل عدد الفريمات.",
                magicanimate_status=st,
                previous_engine_error=previous_engine_error,
                timeout_seconds=self.timeout,
                stdout_tail=(e.stdout or "")[-4000:] if isinstance(e.stdout, str) else "",
                stderr_tail=(e.stderr or "")[-4000:] if isinstance(e.stderr, str) else "",
                real_video_generated=False,
            )
        except Exception as exc:
            return fail_output(
                str(exc),
                stage="magicanimate_inference_exception",
                suspect="magicanimate_adapter_exception",
                solution_ar="وقع خطأ في محول MagicAnimate. راجع criminal_report و traceback_tail في RunPod output.",
                magicanimate_status=st,
                previous_engine_error=previous_engine_error,
                image_path=str(image_path),
                motion_name=motion_name,
                real_video_generated=False,
            )
