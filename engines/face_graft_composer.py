from __future__ import annotations
import base64, json, os, shutil, subprocess, time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .output_contract import ok_output, fail_output
from .head_tracking_engine import RealHeadTrackingEngine

try:
    import cv2
    import numpy as np
except Exception:  # pragma: no cover
    cv2 = None
    np = None


def _strip_data_uri(data: str) -> str:
    if data and "," in data and data.strip().lower().startswith("data:"):
        return data.split(",", 1)[1]
    return data


def _b64_to_file(data: str, path: Path) -> Path:
    if not data:
        raise ValueError("missing_base64")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(base64.b64decode(_strip_data_uri(data)))
    return path


def _file_to_b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


def _which(name: str) -> Optional[str]:
    return shutil.which(name)


class FaceGraftComposer:
    """V34 Face Graft Composer.

    هذه مرحلة تركيب حقيقية مبنية على V33 Real Head Tracking:
    - تقرأ فيديو الجسم الحقيقي.
    - تقرأ فيديو الوجه الناطق.
    - تستعمل head_tracks أو تشغل V33 لتحديد الرأس Frame by Frame.
    - تقص الوجه الناطق من فيديو الوجه، وتدمجه داخل head_box بتنعيم alpha mask.

    مبدأ الصدق:
    هذه ليست DeepFaceLab ولا inpainting diffusion. هي Face-Graft عملي وصريح.
    إذا head tracking غير صالح لا تزيف النجاح ولا تركب الوجه عشوائيًا.
    """

    def __init__(self, head_tracker: Optional[RealHeadTrackingEngine] = None):
        self.head_tracker = head_tracker or RealHeadTrackingEngine()
        self.enabled = cv2 is not None and np is not None
        self.cascade_path = None
        if cv2 is not None:
            try:
                p = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
                if p.exists():
                    self.cascade_path = str(p)
            except Exception:
                self.cascade_path = None

    def status(self) -> Dict[str, Any]:
        return {
            "enabled": bool(self.enabled),
            "opencv_available": cv2 is not None,
            "numpy_available": np is not None,
            "ffmpeg_available": _which("ffmpeg") is not None,
            "haar_face_cascade_available": bool(self.cascade_path),
            "requires_v33_head_tracking": True,
            "tasks": ["face_graft_status", "face_graft_template", "face_graft_video", "v34_face_graft"],
            "truth_contract_ar": "V34 يركب الوجه فقط إذا وجد head_tracks صالحًا أو نجح V33 في تتبع الرأس. لا يوجد تركيب عشوائي.",
        }

    def template(self) -> Dict[str, Any]:
        return ok_output(
            "v34_face_graft_template",
            example_payloads={
                "status": {"input": {"task": "face_graft_status"}},
                "compose_with_base64": {
                    "input": {
                        "task": "face_graft_video",
                        "body_video_base64": "PUT_FULLBODY_VIDEO_BASE64_HERE",
                        "talking_face_video_base64": "PUT_SADTALKER_FACE_VIDEO_BASE64_HERE",
                        "head_tracks": "OPTIONAL_FROM_V33_HEAD_TRACKING",
                        "strict": True,
                    }
                },
                "compose_with_paths": {
                    "input": {
                        "task": "face_graft_video",
                        "body_video_path": "/workspace/outputs/body.mp4",
                        "talking_face_video_path": "/workspace/outputs/face.mp4",
                        "head_tracking_report_path": "/workspace/outputs/v33_head_tracking_report.json",
                    }
                },
            },
            output_contract={
                "video_base64": "final face-grafted video when ok=true",
                "v34_face_graft_report": "truthful report with head tracking source and frame count",
                "face_graft_mode": "head_track_alpha_blend_face_graft_lite",
            },
            next_step_ar="بعد V34 ننتقل إلى V35 Deep Quality Judge لقياس الهوية واليدين والشفاه والتشوهات.",
        )

    def _load_video(self, request: Dict[str, Any], job_dir: Path, kind: str) -> Path:
        aliases = {
            "body": ["body_video_path", "fullbody_video_path", "video_path"],
            "face": ["talking_face_video_path", "face_video_path", "sadtalker_video_path", "talking_video_path"],
        }[kind]
        for k in aliases:
            v = request.get(k)
            if v and Path(str(v)).exists():
                return Path(str(v))
        b64_aliases = {
            "body": ["body_video_base64", "fullbody_video_base64", "video_base64", "body_video"],
            "face": ["talking_face_video_base64", "face_video_base64", "sadtalker_video_base64", "talking_video_base64", "face_video"],
        }[kind]
        for k in b64_aliases:
            v = request.get(k)
            if v:
                return _b64_to_file(str(v), job_dir / f"{kind}_video.mp4")
        raise ValueError(f"MISSING_{kind.upper()}_VIDEO_FOR_V34_FACE_GRAFT")

    def _load_head_tracks(self, request: Dict[str, Any], body_video: Path, job_dir: Path) -> Dict[str, Any]:
        if isinstance(request.get("head_tracks"), list):
            return {"ok": True, "source": "payload_head_tracks", "head_tracks": request["head_tracks"], "face_graft_allowed": True}
        if isinstance(request.get("head_tracking_report"), dict):
            r = request["head_tracking_report"]
            return {"ok": True, "source": "payload_head_tracking_report", "head_tracks": r.get("head_tracks") or [], "face_graft_allowed": bool(r.get("face_graft_allowed", True))}
        rp = request.get("head_tracking_report_path") or request.get("v33_report_path")
        if rp and Path(str(rp)).exists():
            r = json.loads(Path(str(rp)).read_text(encoding="utf-8"))
            return {"ok": True, "source": "head_tracking_report_path", "head_tracks": r.get("head_tracks") or [], "face_graft_allowed": bool(r.get("face_graft_allowed", True)), "stats": r.get("stats")}
        rb64 = request.get("head_tracking_report_base64") or request.get("v33_report_base64")
        if rb64:
            report_path = _b64_to_file(str(rb64), job_dir / "v33_head_tracking_report.json")
            r = json.loads(report_path.read_text(encoding="utf-8"))
            return {"ok": True, "source": "head_tracking_report_base64", "head_tracks": r.get("head_tracks") or [], "face_graft_allowed": bool(r.get("face_graft_allowed", True)), "stats": r.get("stats")}
        # Run V33 internally, but only if allowed.
        if request.get("run_head_tracking_if_missing", True) is False:
            return {"ok": False, "error": "HEAD_TRACKS_REQUIRED", "source": "none"}
        tr = self.head_tracker.track_video({"video_path": str(body_video), "stride": int(request.get("stride", 3)), "head_box_hint": request.get("head_box_hint")}, job_dir)
        if not tr.get("ok"):
            return {"ok": False, "error": "V33_HEAD_TRACKING_FAILED", "source": "internal_v33", "v33_result": tr}
        return {
            "ok": True,
            "source": "internal_v33_head_tracking",
            "head_tracks": tr.get("head_tracks") or [],
            "face_graft_allowed": bool(tr.get("face_graft_allowed")),
            "stats": tr.get("head_tracking_stats"),
            "v33_result": tr,
        }

    @staticmethod
    def _nearest_box(tracks: List[Dict[str, Any]], frame_index: int) -> Optional[Dict[str, int]]:
        candidates = [t for t in tracks if t.get("head_box")]
        if not candidates:
            return None
        best = min(candidates, key=lambda t: abs(int(t.get("frame_index", 0)) - frame_index))
        b = best.get("head_box") or {}
        try:
            return {"x": int(b["x"]), "y": int(b["y"]), "w": int(b["w"]), "h": int(b["h"])}
        except Exception:
            return None

    def _detect_face_in_frame(self, frame) -> Optional[Tuple[int, int, int, int]]:
        if cv2 is None or not self.cascade_path:
            return None
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        cascade = cv2.CascadeClassifier(self.cascade_path)
        faces = cascade.detectMultiScale(gray, scaleFactor=1.08, minNeighbors=4, minSize=(30, 30))
        faces = [tuple(map(int, f)) for f in faces]
        if not faces:
            return None
        h, w = gray.shape[:2]
        def score(f):
            x, y, fw, fh = f
            return fw * fh - abs((x + fw / 2) - w / 2) * 0.25 - abs((y + fh / 2) - h * 0.38) * 0.2
        return max(faces, key=score)

    def _face_crop(self, frame):
        h, w = frame.shape[:2]
        det = self._detect_face_in_frame(frame)
        if det:
            x, y, fw, fh = det
            pad_x = int(fw * 0.45)
            pad_y_top = int(fh * 0.55)
            pad_y_bot = int(fh * 0.35)
            x0 = max(0, x - pad_x); x1 = min(w, x + fw + pad_x)
            y0 = max(0, y - pad_y_top); y1 = min(h, y + fh + pad_y_bot)
            crop = frame[y0:y1, x0:x1].copy()
            return crop, {"method": "haar_face_crop", "box": {"x": x, "y": y, "w": fw, "h": fh}}
        # fallback: central upper crop
        side = min(w, h)
        cx, cy = w // 2, int(h * 0.42)
        r = int(side * 0.32)
        x0 = max(0, cx - r); x1 = min(w, cx + r)
        y0 = max(0, cy - r); y1 = min(h, cy + r)
        return frame[y0:y1, x0:x1].copy(), {"method": "center_upper_crop_fallback"}

    @staticmethod
    def _alpha_mask(h: int, w: int):
        mask = np.zeros((h, w), dtype=np.float32)
        center = (w // 2, h // 2)
        axes = (max(1, int(w * 0.48)), max(1, int(h * 0.48)))
        cv2.ellipse(mask, center, axes, 0, 0, 360, 1.0, -1)
        k = max(5, (min(w, h) // 8) | 1)
        mask = cv2.GaussianBlur(mask, (k, k), 0)
        mask = np.clip(mask, 0.0, 1.0)
        return mask[..., None]

    @staticmethod
    def _overlay(base, overlay, x: int, y: int, alpha):
        H, W = base.shape[:2]
        h, w = overlay.shape[:2]
        x0 = max(0, x); y0 = max(0, y)
        x1 = min(W, x + w); y1 = min(H, y + h)
        if x1 <= x0 or y1 <= y0:
            return base
        ox0 = x0 - x; oy0 = y0 - y
        ox1 = ox0 + (x1 - x0); oy1 = oy0 + (y1 - y0)
        a = alpha[oy0:oy1, ox0:ox1]
        base_roi = base[y0:y1, x0:x1].astype(np.float32)
        ov_roi = overlay[oy0:oy1, ox0:ox1].astype(np.float32)
        blended = ov_roi * a + base_roi * (1.0 - a)
        base[y0:y1, x0:x1] = blended.astype(np.uint8)
        return base

    def _mux_audio(self, video_no_audio: Path, audio_source: Path, out_path: Path) -> Path:
        ffmpeg = _which("ffmpeg")
        if not ffmpeg:
            shutil.copy2(video_no_audio, out_path)
            return out_path
        cmd = [ffmpeg, "-y", "-i", str(video_no_audio), "-i", str(audio_source), "-map", "0:v:0", "-map", "1:a?", "-c:v", "copy", "-c:a", "aac", "-shortest", str(out_path)]
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=600)
        if p.returncode != 0 or not out_path.exists() or out_path.stat().st_size < 1000:
            shutil.copy2(video_no_audio, out_path)
        return out_path

    def compose(self, request: Dict[str, Any], work_root: Path) -> Dict[str, Any]:
        if not self.enabled:
            return fail_output(
                "OPENCV_OR_NUMPY_NOT_AVAILABLE",
                stage="v34_face_graft_preflight",
                suspect="composer_environment",
                solution_ar="ثبّت opencv-python-headless و numpy داخل FullBody Worker أو Composer Worker.",
                face_graft_status=self.status(),
            )
        job_dir = work_root / f"v34_face_graft_{int(time.time()*1000)}"
        job_dir.mkdir(parents=True, exist_ok=True)
        try:
            body_video = self._load_video(request, job_dir, "body")
            face_video = self._load_video(request, job_dir, "face")
        except Exception as e:
            return fail_output(str(e), stage="v34_load_inputs", suspect="missing_video_input", solution_ar="أرسل body_video_base64 و talking_face_video_base64 أو مسارات صحيحة للفيديوهات.")

        track_pack = self._load_head_tracks(request, body_video, job_dir)
        if not track_pack.get("ok"):
            return fail_output(
                track_pack.get("error", "HEAD_TRACKING_REQUIRED"),
                stage="v34_head_tracking_gate",
                suspect="missing_or_failed_head_tracking",
                solution_ar="شغّل V33 head_track_video أولًا أو أرسل head_tracks أو اجعل run_head_tracking_if_missing=true.",
                head_tracking_result=track_pack,
            )
        if not track_pack.get("face_graft_allowed", True) and request.get("strict", True):
            return fail_output(
                "FACE_GRAFT_BLOCKED_BY_UNSTABLE_HEAD_TRACKING",
                stage="v34_head_tracking_gate",
                suspect="head_tracking_unstable",
                solution_ar="لا نركب الوجه إذا كان تتبع الرأس غير مستقر. أعد إنتاج فيديو جسم أبسط أو أرسل head_box_hint.",
                head_tracking_result=track_pack,
            )
        tracks = track_pack.get("head_tracks") or []
        if not tracks:
            return fail_output("EMPTY_HEAD_TRACKS", stage="v34_head_tracking_gate", suspect="no_head_boxes", solution_ar="لا توجد head_box في تقرير V33. أعد تتبع الرأس أو أرسل head_box_hint.")

        cap_body = cv2.VideoCapture(str(body_video))
        cap_face = cv2.VideoCapture(str(face_video))
        if not cap_body.isOpened() or not cap_face.isOpened():
            return fail_output("VIDEO_OPEN_FAILED", stage="v34_video_open", suspect="invalid_video_file", solution_ar="أحد الفيديوهات غير قابل للقراءة. افحص body_video و talking_face_video.", body_video=str(body_video), face_video=str(face_video))
        fps = cap_body.get(cv2.CAP_PROP_FPS) or 24.0
        width = int(cap_body.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(cap_body.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        frame_count = int(cap_body.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if width <= 0 or height <= 0:
            return fail_output("INVALID_BODY_VIDEO_DIMENSIONS", stage="v34_video_open", suspect="body_video_invalid", solution_ar="فيديو الجسم لا يملك أبعادًا صحيحة.")
        tmp = job_dir / "v34_grafted_no_audio.mp4"
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(tmp), fourcc, float(fps), (width, height))
        if not writer.isOpened():
            return fail_output("VIDEO_WRITER_FAILED", stage="v34_writer_open", suspect="opencv_video_writer", solution_ar="OpenCV لم يستطع فتح VideoWriter. جرّب ffmpeg أو codec مختلف داخل Docker.")

        face_frames = []
        face_meta = []
        max_face_cache = int(request.get("max_face_cache_frames", 600))
        while len(face_frames) < max_face_cache:
            ok, ff = cap_face.read()
            if not ok:
                break
            crop, meta = self._face_crop(ff)
            if crop is not None and crop.size:
                face_frames.append(crop)
                face_meta.append(meta)
        cap_face.release()
        if not face_frames:
            writer.release(); cap_body.release()
            return fail_output("NO_FACE_FRAMES_READ", stage="v34_face_crop", suspect="talking_face_video_empty", solution_ar="فيديو الوجه الناطق لا يحتوي إطارات صالحة.")

        processed = 0; grafted = 0; missed = 0
        sample_logs = []
        scale = float(request.get("head_scale", 1.12))
        y_shift = float(request.get("y_shift", -0.06))
        while True:
            ok, frame = cap_body.read()
            if not ok:
                break
            box = self._nearest_box(tracks, processed)
            if box:
                fc = face_frames[processed % len(face_frames)]
                tw = max(8, int(box["w"] * scale))
                th = max(8, int(box["h"] * scale))
                resized = cv2.resize(fc, (tw, th), interpolation=cv2.INTER_AREA)
                alpha = self._alpha_mask(th, tw)
                x = int(box["x"] + box["w"] / 2 - tw / 2)
                y = int(box["y"] + box["h"] / 2 - th / 2 + box["h"] * y_shift)
                frame = self._overlay(frame, resized, x, y, alpha)
                grafted += 1
                if len(sample_logs) < 5:
                    sample_logs.append({"frame": processed, "head_box": box, "overlay": {"x": x, "y": y, "w": tw, "h": th}})
            else:
                missed += 1
            writer.write(frame)
            processed += 1
        cap_body.release(); writer.release()
        if processed == 0 or not tmp.exists() or tmp.stat().st_size < 1000:
            return fail_output("NO_OUTPUT_FRAMES_WRITTEN", stage="v34_render", suspect="body_video_empty_or_writer_failed", solution_ar="لم يتم إخراج إطارات. افحص فيديو الجسم و OpenCV codec.")
        out = job_dir / "v34_face_grafted_final.mp4"
        self._mux_audio(tmp, face_video, out)
        if not out.exists() or out.stat().st_size < 1000:
            return fail_output("V34_OUTPUT_VIDEO_MISSING", stage="v34_mux_audio", suspect="ffmpeg_or_writer_output", solution_ar="فشل إخراج الفيديو النهائي. افحص ffmpeg وملفات الفيديو.")

        graft_ratio = (grafted / max(1, processed)) * 100.0
        strict_quality = bool(graft_ratio >= 70.0)
        report = {
            "version": "V36_SMART_RETRY_2",
            "ok": True,
            "mode": "head_track_alpha_blend_face_graft_lite",
            "body_video": str(body_video),
            "talking_face_video": str(face_video),
            "output_video": str(out),
            "frames_processed": processed,
            "frames_grafted": grafted,
            "frames_without_head_box": missed,
            "graft_ratio_percent": round(graft_ratio, 2),
            "head_tracking_source": track_pack.get("source"),
            "face_crop_methods_seen": sorted(set(m.get("method") for m in face_meta if isinstance(m, dict)))[:5],
            "sample_overlay_logs": sample_logs,
            "strict_quality_pass": strict_quality,
            "truth_contract_ar": "هذا Face Graft عملي مبني على head tracking وalpha blend. ليس deep inpainting. إذا كانت النسبة منخفضة فلا ندعي جودة عالمية.",
            "next_step_ar": "V35 Deep Quality Judge سيقيس الهوية والشفاه واليدين والفليكر ويقرر هل النتيجة مقبولة أو تحتاج retry.",
        }
        report_path = job_dir / "v34_face_graft_report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return ok_output(
            "v34_face_graft_done",
            video_path=str(out),
            video_base64=_file_to_b64(out),
            report_path=str(report_path),
            report_json_base64=_file_to_b64(report_path),
            v34_face_graft_report=report,
            face_graft_mode="head_track_alpha_blend_face_graft_lite",
            face_graft_allowed=True,
            graft_ratio_percent=round(graft_ratio, 2),
            strict_quality_pass=strict_quality,
            warning_ar="V34 ركّب الوجه فعليًا باستعمال head tracking. جودة الدمج العميقة والهوية الدقيقة تقاس في V35، ولا ندعي 99% قبل Benchmark.",
        )
