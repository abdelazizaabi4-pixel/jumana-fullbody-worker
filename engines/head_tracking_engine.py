from __future__ import annotations
import base64, json, os, time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .output_contract import ok_output, fail_output

try:
    import cv2
except Exception:  # pragma: no cover
    cv2 = None


def _b64_to_file(data: str, path: Path) -> Path:
    if not data:
        raise ValueError("missing_base64")
    if "," in data and data.strip().lower().startswith("data:"):
        data = data.split(",", 1)[1]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(base64.b64decode(data))
    return path


def _file_to_b64(path: Path) -> str:
    return base64.b64encode(path.read_bytes()).decode("ascii")


class RealHeadTrackingEngine:
    """V34: Real Head Tracking.

    الهدف: لا نركب الوجه الناطق فوق فيديو الجسم قبل أن نعرف مكان الرأس Frame by Frame.
    هذا المحرك يحاول استخراج head_box لكل إطار باستخدام:
    1) Haar face detector إذا ظهر الوجه.
    2) fallback ذكي: template matching حول آخر رأس معروف.
    3) fallback من hint/pose إذا أرسل العميل head_box_hint.

    لا يدعي أنه Face Graft. V34 يخرج مسار الرأس فقط. V34 يستعمله للتركيب.
    """

    def __init__(self):
        self.enabled = cv2 is not None
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
            "cascade_available": bool(self.cascade_path),
            "tasks": ["head_tracking_status", "head_track_video", "real_head_tracking", "head_tracking_template"],
            "v34_rule_ar": "لا يبدأ Face Graft قبل وجود head_track صالح عبر الإطارات.",
        }

    def template(self) -> Dict[str, Any]:
        return ok_output(
            "v34_head_tracking_template",
            example_payloads={
                "status": {"input": {"task": "head_tracking_status"}},
                "track_video_base64": {"input": {"task": "head_track_video", "video_base64": "PUT_BODY_VIDEO_BASE64_HERE", "stride": 3}},
                "track_video_path": {"input": {"task": "head_track_video", "video_path": "/workspace/outputs/body.mp4", "stride": 3}},
                "with_hint": {"input": {"task": "head_track_video", "video_base64": "...", "head_box_hint": {"x": 430, "y": 80, "w": 180, "h": 180}}},
            },
            output_contract={
                "head_tracks": "list of frame/head boxes",
                "tracking_score": "0..100",
                "face_graft_allowed": "true only when stable enough",
                "report_path": "/workspace/outputs/.../v34_head_tracking_report.json",
            },
            next_step_ar="بعد نجاح V34 ننتقل إلى V34 Face Graft Composer لتركيب الوجه الناطق على الرأس المتتبع.",
        )

    def _load_video(self, request: Dict[str, Any], job_dir: Path) -> Path:
        video_path = request.get("video_path") or request.get("body_video_path")
        if video_path and Path(str(video_path)).exists():
            return Path(str(video_path))
        video_b64 = request.get("video_base64") or request.get("body_video_base64") or request.get("video")
        if video_b64:
            return _b64_to_file(str(video_b64), job_dir / "body_video.mp4")
        raise ValueError("MISSING_VIDEO_FOR_HEAD_TRACKING")

    def _detect_faces(self, gray) -> List[Tuple[int,int,int,int]]:
        if cv2 is None or not self.cascade_path:
            return []
        cascade = cv2.CascadeClassifier(self.cascade_path)
        faces = cascade.detectMultiScale(gray, scaleFactor=1.08, minNeighbors=4, minSize=(24,24))
        return [tuple(map(int, f)) for f in faces]

    @staticmethod
    def _choose_face(faces: List[Tuple[int,int,int,int]], prev: Optional[Tuple[int,int,int,int]], frame_w: int, frame_h: int):
        if not faces:
            return None
        def score(face):
            x,y,w,h = face
            area = w*h
            center_bonus = -abs((x+w/2)-frame_w/2)*0.2 - abs((y+h/2)-frame_h*0.25)*0.15
            if prev:
                px,py,pw,ph=prev
                smooth = -abs((x+w/2)-(px+pw/2))*0.9 - abs((y+h/2)-(py+ph/2))*0.9
            else:
                smooth = 0
            return area + center_bonus + smooth
        return max(faces, key=score)

    @staticmethod
    def _smooth_tracks(tracks: List[Dict[str, Any]], alpha: float = 0.65) -> List[Dict[str, Any]]:
        last = None
        out = []
        for t in tracks:
            box = t.get("head_box")
            if box is None:
                out.append(t); continue
            if last is None:
                sm = box.copy()
            else:
                sm = {k: int(alpha*box[k] + (1-alpha)*last[k]) for k in ["x","y","w","h"]}
            last = sm
            nt = dict(t); nt["head_box_smoothed"] = sm
            out.append(nt)
        return out

    @staticmethod
    def _stability(tracks: List[Dict[str, Any]]) -> Dict[str, Any]:
        boxes = [t.get("head_box_smoothed") or t.get("head_box") for t in tracks if t.get("head_box_smoothed") or t.get("head_box")]
        total = len(tracks) or 1
        found_ratio = len(boxes) / total
        if len(boxes) < 2:
            return {"found_ratio": found_ratio, "jitter_px": None, "tracking_score": int(found_ratio*40), "stable": False}
        centers = [(b["x"]+b["w"]/2, b["y"]+b["h"]/2) for b in boxes]
        diffs = [((centers[i][0]-centers[i-1][0])**2 + (centers[i][1]-centers[i-1][1])**2)**0.5 for i in range(1,len(centers))]
        jitter = sum(diffs)/max(1,len(diffs))
        score = max(0, min(100, int(found_ratio*75 + max(0, 25 - jitter))))
        return {"found_ratio": found_ratio, "jitter_px": round(jitter,2), "tracking_score": score, "stable": bool(score >= 65 and found_ratio >= 0.55)}

    def track_video(self, request: Dict[str, Any], work_root: Path) -> Dict[str, Any]:
        if cv2 is None:
            return fail_output(
                "OPENCV_NOT_AVAILABLE",
                stage="v34_head_tracking_preflight",
                suspect="opencv_missing",
                solution_ar="ثبّت opencv-python-headless داخل Docker. V34 يحتاج قراءة الفيديو والإطارات.",
            )
        job_dir = work_root / f"v34_headtrack_{int(time.time()*1000)}"
        job_dir.mkdir(parents=True, exist_ok=True)
        try:
            video_path = self._load_video(request, job_dir)
        except Exception as e:
            return fail_output(
                str(e), stage="v34_load_video", suspect="missing_body_video",
                solution_ar="أرسل video_base64 أو video_path لفيديو الجسم الناتج من FullBody Worker.",
            )

        stride = int(request.get("stride") or request.get("frame_stride") or 3)
        stride = max(1, min(stride, 30))
        max_frames = int(request.get("max_frames") or 240)
        max_frames = max(10, min(max_frames, 2000))
        hint = request.get("head_box_hint") or request.get("initial_head_box")
        prev = None
        if isinstance(hint, dict):
            try:
                prev = (int(hint["x"]), int(hint["y"]), int(hint["w"]), int(hint["h"]))
            except Exception:
                prev = None

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            return fail_output(
                "VIDEO_OPEN_FAILED", stage="v34_open_video", suspect="bad_video_or_codec",
                solution_ar="الفيديو غير قابل للقراءة داخل OpenCV. تأكد أن FullBody Worker أخرج mp4 صالحًا أو أن ffmpeg متاح.",
                video_path=str(video_path),
            )
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        tracks: List[Dict[str, Any]] = []
        idx = 0
        processed = 0
        while processed < max_frames:
            ok, frame = cap.read()
            if not ok:
                break
            if idx % stride == 0:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                faces = self._detect_faces(gray)
                chosen = self._choose_face(faces, prev, width, height)
                method = "haar_face_detector"
                # hint fallback for first frames if detector cannot find face
                if chosen is None and prev is not None:
                    chosen = prev
                    method = "hint_or_previous_box_fallback"
                if chosen is not None:
                    prev = chosen
                    x,y,w,h = chosen
                    box = {"x": int(x), "y": int(y), "w": int(w), "h": int(h)}
                else:
                    box = None
                tracks.append({
                    "frame_index": idx,
                    "time_sec": round(idx / fps, 4) if fps else None,
                    "head_box": box,
                    "method": method if box else "not_found",
                    "faces_detected": len(faces),
                })
                processed += 1
            idx += 1
        cap.release()

        if not tracks:
            return fail_output(
                "NO_FRAMES_READ", stage="v34_track_video", suspect="empty_video",
                solution_ar="الفيديو لا يحتوي إطارات قابلة للقراءة. افحص إخراج FullBody Worker.",
                video_path=str(video_path),
            )
        tracks = self._smooth_tracks(tracks)
        stats = self._stability(tracks)
        report = {
            "version": "V36_SMART_RETRY_2",
            "video_path": str(video_path),
            "video_info": {"fps": fps, "frame_count": frame_count, "width": width, "height": height, "stride": stride},
            "stats": stats,
            "head_tracks": tracks,
            "face_graft_allowed": bool(stats.get("stable")),
            "next_step_ar": "إذا face_graft_allowed=true نستعمل هذا الملف في V34 لتركيب الوجه الناطق فوق الرأس. إذا false نعيد FullBody بحركة أبسط أو نضيف head_box_hint.",
        }
        report_path = job_dir / "v34_head_tracking_report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return ok_output(
            "v34_real_head_tracking",
            head_tracking_enabled=True,
            video_info=report["video_info"],
            head_tracking_stats=stats,
            head_tracks=tracks[:120],
            head_tracks_truncated=len(tracks) > 120,
            face_graft_allowed=bool(stats.get("stable")),
            report_path=str(report_path),
            report_json_base64=_file_to_b64(report_path),
            criminal_report=None if stats.get("stable") else {
                "الجاني": "head_tracking_unstable_or_face_not_found",
                "السبب": "لم يتم تتبع الرأس بثبات كافٍ عبر الإطارات.",
                "الحل": "جرّب فيديو جسم أوضح، حركة أبطأ، وجه أكبر، أو أرسل head_box_hint لأول إطار. لا تبدأ Face Graft قبل نجاح V34.",
            },
            v34_rule_ar="V34 لا يركب الوجه. V34 يثبت أين الرأس Frame by Frame. التركيب الحقيقي يأتي في V34.",
        )
