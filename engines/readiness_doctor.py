from __future__ import annotations
import os, shutil, subprocess, json, time, importlib.util
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .output_contract import ok_output, fail_output

VIDEO_ENGINES = ["musepose", "magicanimate", "animateanyone"]
ENGINE_ORDER = ["musepose", "magicanimate", "animateanyone"]


def _module_exists(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def _run_cmd(cmd: List[str], timeout: int = 8) -> Dict[str, Any]:
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)
        return {"ok": p.returncode == 0, "returncode": p.returncode, "stdout": (p.stdout or "")[-4000:], "stderr": (p.stderr or "")[-4000:]}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _path_info(path: str | Path) -> Dict[str, Any]:
    p = Path(path)
    info = {"path": str(p), "exists": p.exists(), "is_file": p.is_file(), "is_dir": p.is_dir()}
    try:
        if p.exists():
            st = p.stat()
            info["size_bytes"] = st.st_size
            info["mtime"] = st.st_mtime
    except Exception:
        pass
    return info


class EngineReadinessDoctor:
    """V30 Engine Readiness Doctor.

    الهدف: لا نبدأ تشغيل محركات الجسم الثقيلة قبل معرفة هل البيئة جاهزة فعلاً.
    يفحص: GPU، CUDA، PyTorch، المسارات، الأوزان، command template، entrypoints، مساحة القرص، وسبب الحظر.
    """
    def __init__(self, dwpose, musepose, magicanimate, animateanyone):
        self.dwpose = dwpose
        self.engines = {
            "musepose": musepose,
            "magicanimate": magicanimate,
            "animateanyone": animateanyone,
        }

    def system_status(self) -> Dict[str, Any]:
        nvidia_smi = shutil.which("nvidia-smi")
        ffmpeg = shutil.which("ffmpeg")
        disk = shutil.disk_usage(os.environ.get("JUMANA_WORKDIR", "/workspace") if Path(os.environ.get("JUMANA_WORKDIR", "/workspace")).exists() else "/")
        torch_report: Dict[str, Any] = {"torch_available": False, "cuda_available": False, "device_count": 0}
        try:
            import torch  # type: ignore
            torch_report = {
                "torch_available": True,
                "torch_version": getattr(torch, "__version__", None),
                "cuda_available": bool(torch.cuda.is_available()),
                "cuda_version": getattr(torch.version, "cuda", None),
                "device_count": int(torch.cuda.device_count()) if torch.cuda.is_available() else 0,
                "devices": [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())] if torch.cuda.is_available() else [],
            }
        except Exception as e:
            torch_report["torch_error"] = str(e)
        return {
            "python": shutil.which("python") or shutil.which("python3"),
            "ffmpeg_path": ffmpeg,
            "ffmpeg_ready": bool(ffmpeg),
            "nvidia_smi_path": nvidia_smi,
            "nvidia_smi_ready": bool(nvidia_smi),
            "nvidia_smi_query": _run_cmd([nvidia_smi, "--query-gpu=name,memory.total,memory.free,driver_version", "--format=csv,noheader"], timeout=8) if nvidia_smi else {"ok": False, "error": "nvidia-smi not found"},
            "torch": torch_report,
            "disk": {"total_gb": round(disk.total/1024**3, 2), "free_gb": round(disk.free/1024**3, 2), "used_gb": round(disk.used/1024**3, 2)},
            "env_flags": {
                "JUMANA_NO_FAKE_BODY_MOTION": os.environ.get("JUMANA_NO_FAKE_BODY_MOTION"),
                "DWPOSE_ENABLE_REAL": os.environ.get("DWPOSE_ENABLE_REAL"),
                "MUSEPOSE_ROOT": os.environ.get("MUSEPOSE_ROOT"),
                "MUSEPOSE_WEIGHTS": os.environ.get("MUSEPOSE_WEIGHTS"),
                "MUSEPOSE_COMMAND_TEMPLATE_SET": bool(os.environ.get("MUSEPOSE_COMMAND_TEMPLATE", "").strip()),
                "MAGICANIMATE_ROOT": os.environ.get("MAGICANIMATE_ROOT"),
                "MAGICANIMATE_WEIGHTS": os.environ.get("MAGICANIMATE_WEIGHTS"),
                "MAGICANIMATE_COMMAND_TEMPLATE_SET": bool(os.environ.get("MAGICANIMATE_COMMAND_TEMPLATE", "").strip()),
                "ANIMATEANYONE_ROOT": os.environ.get("ANIMATEANYONE_ROOT"),
                "ANIMATEANYONE_WEIGHTS": os.environ.get("ANIMATEANYONE_WEIGHTS"),
                "ANIMATEANYONE_COMMAND_TEMPLATE_SET": bool(os.environ.get("ANIMATEANYONE_COMMAND_TEMPLATE", "").strip()),
            }
        }

    def _score_dwpose(self) -> Dict[str, Any]:
        st = self.dwpose.status()
        blockers: List[str] = []
        score = 0
        if st.get("real_enabled"):
            score += 15
        else:
            blockers.append("DWPOSE_ENABLE_REAL is off")
        if st.get("controlnet_aux_available"):
            score += 45
        else:
            blockers.append("controlnet_aux missing")
        if st.get("torch_available"):
            score += 15
        else:
            blockers.append("torch missing")
        if st.get("onnxruntime_available"):
            score += 10
        else:
            blockers.append("onnxruntime missing")
        if Path(st.get("cache_dir", "/workspace/models/huggingface")).exists():
            score += 15
        else:
            blockers.append("HF cache dir missing; model may download at runtime")
        ready = score >= 60 and not any(b in blockers for b in ["DWPOSE_ENABLE_REAL is off", "controlnet_aux missing"])
        return {
            "engine": "dwpose",
            "score": min(100, score),
            "ready": bool(ready),
            "status": st,
            "blockers": blockers,
            "solution_ar": "ثبّت controlnet-aux وonnxruntime-gpu وتأكد من DWPOSE_ENABLE_REAL=1 وHF_HOME ثابت على RunPod Volume." if blockers else "DWPose جاهز مبدئيًا.",
        }

    def _score_video_engine(self, name: str) -> Dict[str, Any]:
        engine = self.engines[name]
        st = engine.status()
        blockers: List[str] = []
        score = 0
        if st.get("root_exists"):
            score += 25
        else:
            blockers.append(f"{name.upper()}_ROOT_NOT_FOUND")
        if st.get("weights_exist"):
            score += 25
        else:
            blockers.append(f"{name.upper()}_WEIGHTS_NOT_FOUND")
        if st.get("command_template_set"):
            score += 30
        elif st.get("candidate_entrypoints"):
            score += 15
            blockers.append(f"{name.upper()}_COMMAND_TEMPLATE_NOT_SET_USING_GUESSED_ENTRYPOINT")
        else:
            blockers.append(f"{name.upper()}_COMMAND_NOT_CONFIGURED")
        # لا نشترط GPU هنا 100% لأن بعض images لا ترى GPU وقت build، لكن في RunPod يجب أن يظهر.
        configured = bool(st.get("configured"))
        ready = configured and st.get("root_exists") and st.get("weights_exist") and (st.get("command_template_set") or st.get("candidate_entrypoints"))
        if ready:
            score = max(score, 80)
        return {
            "engine": name,
            "score": min(100, score),
            "ready": bool(ready),
            "status": st,
            "blockers": blockers,
            "solution_ar": self._engine_solution_ar(name, blockers),
        }

    @staticmethod
    def _engine_solution_ar(name: str, blockers: List[str]) -> str:
        if not blockers:
            return f"{name} جاهز مبدئيًا. الخطوة التالية: اختبار قصير motion_test للتأكد من أنه يخرج video_base64 أو video_url."
        pretty = "، ".join(blockers)
        return f"الجاني في {name}: {pretty}. الحل: ثبّت المحرك داخل RunPod Volume، ضع الأوزان في مسار ثابت، واضبط COMMAND_TEMPLATE النهائي بدل التخمين."

    def report(self, request: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        request = request or {}
        system = self.system_status()
        dwpose = self._score_dwpose()
        engines = {name: self._score_video_engine(name) for name in ENGINE_ORDER}
        ready_engines = [name for name, r in engines.items() if r.get("ready")]
        gpu_ok = bool(system.get("torch", {}).get("cuda_available") or system.get("nvidia_smi_ready"))
        ffmpeg_ok = bool(system.get("ffmpeg_ready"))
        blockers = []
        if not dwpose.get("ready"):
            blockers.append("DWPose Truth Engine غير جاهز")
        if not ready_engines:
            blockers.append("لا يوجد أي محرك جسم فيديو جاهز: MusePose/MagicAnimate/AnimateAnyone")
        if not gpu_ok:
            blockers.append("GPU/CUDA غير ظاهر داخل البيئة")
        if not ffmpeg_ok:
            blockers.append("ffmpeg غير موجود")
        best = ready_engines[0] if ready_engines else None
        # Reliability estimate: pipeline readiness, not aesthetic quality.
        reliability = 20
        reliability += 20 if dwpose.get("ready") else 0
        reliability += 25 if ready_engines else 0
        reliability += 15 if gpu_ok else 0
        reliability += 10 if ffmpeg_ok else 0
        reliability += 10 if system.get("disk", {}).get("free_gb", 0) >= 10 else 0
        return ok_output(
            "engine_readiness_doctor_report",
            v30_engine_readiness_doctor=True,
            readiness_percent=min(99, reliability),
            production_ready=not blockers,
            best_engine=best,
            ready_video_engines=ready_engines,
            critical_blockers=blockers,
            system=system,
            dwpose_readiness=dwpose,
            video_engine_readiness=engines,
            requested_engine=request.get("engine") or request.get("preferred_engine") or request.get("body_engine") or "auto",
            target_reliability_ar="V30 يستهدف 99.99% موثوقية في معرفة الجاني وعدم ضياع output، وليس 99.99% جمال فيديو لكل صورة.",
            decision_ar=("البيئة جاهزة مبدئيًا لتجربة جسم حقيقي." if not blockers else "لا تبدأ إنتاج الجسم الحقيقي قبل حل الجناة: " + " | ".join(blockers)),
            next_step_ar="بعد readiness=true ننتقل إلى V34 Pose Dataset Benchmark: محرك واحد، أوزان واحدة، أمر واحد، اختبار واحد ناجح.",
        )

    def gate(self, requested_engine: str = "auto", motion_name: str = "standing_idle") -> Dict[str, Any]:
        rep = self.report({"engine": requested_engine, "motion_name": motion_name})
        dwpose_ready = rep.get("dwpose_readiness", {}).get("ready")
        engines = rep.get("video_engine_readiness", {})
        requested_engine = (requested_engine or "auto").lower().strip()
        if requested_engine in {"automatic", ""}:
            requested_engine = "auto"
        if not dwpose_ready:
            return fail_output(
                "ENGINE_READINESS_GATE_BLOCKED_DWPOSE_NOT_READY",
                stage="v30_readiness_gate",
                suspect="dwpose_truth_engine_not_ready",
                solution_ar="أصلح DWPose أولًا. لا يمكن أن نصل لجسم حقيقي موثوق بدون pose truth.",
                readiness_report=rep,
                requested_engine=requested_engine,
                motion_name=motion_name,
            )
        if requested_engine == "auto":
            selected = rep.get("best_engine")
            if selected:
                return ok_output("v30_readiness_gate_passed", selected_engine=selected, readiness_report=rep, motion_name=motion_name)
            return fail_output(
                "NO_REAL_BODY_VIDEO_ENGINE_READY",
                stage="v30_readiness_gate",
                suspect="musepose_magicanimate_animateanyone_not_ready",
                solution_ar="لا يوجد محرك فيديو جسم حقيقي جاهز. ابدأ بإصلاح MusePose: ROOT + WEIGHTS + COMMAND_TEMPLATE ثم اختبر engine_readiness.",
                readiness_report=rep,
                requested_engine=requested_engine,
                motion_name=motion_name,
            )
        if requested_engine not in engines:
            return fail_output(
                f"UNKNOWN_BODY_ENGINE_FOR_READINESS: {requested_engine}",
                stage="v30_readiness_gate",
                suspect="client_requested_unknown_body_engine",
                solution_ar="استعمل engine=auto أو musepose أو magicanimate أو animateanyone.",
                readiness_report=rep,
                requested_engine=requested_engine,
            )
        if not engines[requested_engine].get("ready"):
            return fail_output(
                f"{requested_engine.upper()}_NOT_READY_BEFORE_RUN",
                stage="v30_readiness_gate",
                suspect=f"{requested_engine}_not_ready",
                solution_ar=engines[requested_engine].get("solution_ar") or "أصلح المحرك قبل التشغيل.",
                readiness_report=rep,
                requested_engine=requested_engine,
                motion_name=motion_name,
            )
        return ok_output("v30_readiness_gate_passed", selected_engine=requested_engine, readiness_report=rep, motion_name=motion_name)
