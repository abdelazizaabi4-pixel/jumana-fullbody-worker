
from __future__ import annotations
import base64, json, math, os, shutil, statistics, subprocess, tempfile, time
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .output_contract import ok_output, fail_output


def _safe_int(x: Any, default: int = 0) -> int:
    try:
        return int(float(x))
    except Exception:
        return default


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def _write_b64_to_file(data: str | None, path: Path) -> Path | None:
    if not data:
        return None
    raw = data
    if "," in raw and raw.strip().lower().startswith("data:"):
        raw = raw.split(",", 1)[1]
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(base64.b64decode(raw))
        return path
    except Exception:
        try:
            path.write_bytes(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
            return path
        except Exception:
            return None


def _read_file_b64(path: Path) -> str | None:
    try:
        if path.exists() and path.is_file():
            return base64.b64encode(path.read_bytes()).decode("ascii")
    except Exception:
        pass
    return None


def _ffprobe(path: Path) -> Dict[str, Any]:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return {"available": False, "error": "ffprobe_not_found"}
    try:
        p = subprocess.run(
            [ffprobe, "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(path)],
            capture_output=True,
            text=True,
            timeout=40,
        )
        if p.returncode != 0:
            return {"available": True, "ok": False, "error": p.stderr[-1500:]}
        data = json.loads(p.stdout or "{}")
        streams = data.get("streams") or []
        vstream = next((s for s in streams if s.get("codec_type") == "video"), {})
        astream = next((s for s in streams if s.get("codec_type") == "audio"), {})
        fps_text = vstream.get("avg_frame_rate") or vstream.get("r_frame_rate") or "0/1"
        try:
            a, b = fps_text.split("/")
            fps = float(a) / max(float(b), 1.0)
        except Exception:
            fps = 0.0
        duration = _safe_float(vstream.get("duration") or data.get("format", {}).get("duration"), 0.0)
        return {
            "available": True,
            "ok": True,
            "width": _safe_int(vstream.get("width"), 0),
            "height": _safe_int(vstream.get("height"), 0),
            "duration_seconds": round(duration, 3),
            "fps": round(fps, 3),
            "frame_count": _safe_int(vstream.get("nb_frames"), 0),
            "has_audio": bool(astream),
            "video_codec": vstream.get("codec_name"),
            "audio_codec": astream.get("codec_name"),
            "format_size": _safe_int(data.get("format", {}).get("size"), 0),
        }
    except Exception as e:
        return {"available": True, "ok": False, "exception": str(e)}


def _sample_frames(path: Path, max_samples: int = 40) -> Dict[str, Any]:
    try:
        import cv2
        import numpy as np
    except Exception as e:
        return {"available": False, "error": f"cv2_not_available: {e}"}

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return {"available": True, "opened": False, "error": "cv2_cannot_open_video"}

    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    if total <= 0:
        total = max_samples
    indices = sorted(set(int(i * max(total - 1, 1) / max(max_samples - 1, 1)) for i in range(max_samples)))

    brightness: List[float] = []
    blur: List[float] = []
    diffs: List[float] = []
    histogram_diffs: List[float] = []
    black_frames = 0
    prev_gray = None
    prev_hist = None
    face_centers: List[Tuple[float, float, float, float]] = []
    face_found = 0
    read_count = 0

    face_cascade = None
    try:
        cascade_path = str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml")
        face_cascade = cv2.CascadeClassifier(cascade_path)
        if face_cascade.empty():
            face_cascade = None
    except Exception:
        face_cascade = None

    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, frame = cap.read()
        if not ok or frame is None:
            continue
        read_count += 1
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        mean_b = float(gray.mean())
        brightness.append(mean_b)
        if mean_b < 8:
            black_frames += 1
        try:
            blur.append(float(cv2.Laplacian(gray, cv2.CV_64F).var()))
        except Exception:
            pass
        try:
            hist = cv2.calcHist([gray], [0], None, [32], [0, 256])
            cv2.normalize(hist, hist)
            if prev_hist is not None:
                histogram_diffs.append(float(cv2.compareHist(prev_hist, hist, cv2.HISTCMP_BHATTACHARYYA)))
            prev_hist = hist
        except Exception:
            pass
        if prev_gray is not None:
            try:
                small1 = cv2.resize(prev_gray, (96, 96))
                small2 = cv2.resize(gray, (96, 96))
                diffs.append(float(np.mean(np.abs(small2.astype("float32") - small1.astype("float32")))))
            except Exception:
                pass
        prev_gray = gray
        if face_cascade is not None:
            try:
                faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(24, 24))
                if len(faces) > 0:
                    # اختر أكبر وجه
                    x, y, w, h = max(faces, key=lambda r: r[2] * r[3])
                    face_found += 1
                    face_centers.append((x + w / 2.0, y + h / 2.0, float(w), float(h)))
            except Exception:
                pass
    cap.release()

    motion_energy = statistics.mean(diffs) if diffs else 0.0
    freeze_ratio = (len([d for d in diffs if d < 1.0]) / len(diffs)) if diffs else 0.0
    flicker = 0.0
    if len(brightness) >= 2:
        flicker = statistics.pstdev(brightness) / max(statistics.mean(brightness), 1.0)
    hist_flicker = statistics.mean(histogram_diffs) if histogram_diffs else 0.0

    face_found_ratio = face_found / max(read_count, 1)
    face_jitter_px = None
    face_scale_stability = None
    if len(face_centers) >= 2:
        xs = [c[0] for c in face_centers]
        ys = [c[1] for c in face_centers]
        ws = [c[2] for c in face_centers]
        hs = [c[3] for c in face_centers]
        face_jitter_px = round((statistics.pstdev(xs) + statistics.pstdev(ys)) / 2.0, 3)
        mean_size = max((statistics.mean(ws) + statistics.mean(hs)) / 2.0, 1.0)
        face_scale_stability = round(1.0 - min((statistics.pstdev(ws) + statistics.pstdev(hs)) / (2 * mean_size), 1.0), 4)

    return {
        "available": True,
        "opened": True,
        "sampled_frames": read_count,
        "width_cv2": width,
        "height_cv2": height,
        "fps_cv2": round(fps, 3),
        "frame_count_cv2": total,
        "black_frame_ratio": round(black_frames / max(read_count, 1), 4),
        "brightness_mean": round(statistics.mean(brightness), 3) if brightness else 0,
        "brightness_flicker_ratio": round(flicker, 4),
        "histogram_flicker_score": round(hist_flicker, 4),
        "freeze_ratio": round(freeze_ratio, 4),
        "motion_energy": round(motion_energy, 3),
        "blur_score": round(statistics.mean(blur), 3) if blur else 0,
        "face_detection_available": face_cascade is not None,
        "face_found_ratio": round(face_found_ratio, 4),
        "face_jitter_px": face_jitter_px,
        "face_scale_stability": face_scale_stability,
    }


def _component_scores(report: Dict[str, Any], request: Dict[str, Any]) -> Dict[str, Any]:
    probe = report.get("probe", {})
    frames = report.get("frames", {})
    expected = str(request.get("expected_motion") or request.get("motion_name") or request.get("mode") or "").lower()
    talking_expected = bool(request.get("talking_expected")) or "talk" in expected or "كلام" in expected or "face_graft" in expected
    hand_expected = "hand" in expected or "gesture" in expected or "شرح" in expected or bool(request.get("hands_expected"))
    identity_expected = bool(request.get("identity_expected", True))

    file_score = 0 if not report.get("file_exists") else 100
    if report.get("file_size_bytes", 0) < 50_000:
        file_score = min(file_score, 45)
    elif report.get("file_size_bytes", 0) < 150_000:
        file_score = min(file_score, 70)

    duration = probe.get("duration_seconds", 0) or 0
    duration_score = 100 if duration >= 2.0 else 70 if duration >= 1.0 else 35 if duration > 0 else 0
    width = probe.get("width", 0) or frames.get("width_cv2", 0) or 0
    height = probe.get("height", 0) or frames.get("height_cv2", 0) or 0
    resolution_score = 100 if width >= 768 and height >= 768 else 85 if width >= 512 and height >= 512 else 60 if width >= 256 and height >= 256 else 20

    freeze = frames.get("freeze_ratio", 1.0)
    motion_energy = frames.get("motion_energy", 0.0)
    motion_score = max(0, min(100, int(100 - freeze * 90)))
    if motion_energy < 1.2:
        motion_score = min(motion_score, 45)
    elif motion_energy < 2.2:
        motion_score = min(motion_score, 70)

    black = frames.get("black_frame_ratio", 1.0)
    black_score = max(0, min(100, int(100 - black * 160)))
    flicker = frames.get("brightness_flicker_ratio", 1.0)
    hist_flicker = frames.get("histogram_flicker_score", 1.0)
    flicker_score = max(0, min(100, int(100 - flicker * 180 - hist_flicker * 50)))
    blur = frames.get("blur_score", 0.0)
    sharpness_score = 100 if blur >= 120 else 85 if blur >= 60 else 65 if blur >= 25 else 35 if blur > 0 else 45

    face_ratio = frames.get("face_found_ratio", 0.0)
    face_stability = frames.get("face_scale_stability")
    face_jitter = frames.get("face_jitter_px")
    if not identity_expected:
        identity_score = None
    elif face_ratio >= 0.65:
        identity_score = 85
        if face_stability is not None:
            identity_score = int(min(100, max(40, 55 + face_stability * 45)))
        if face_jitter is not None and face_jitter > 70:
            identity_score -= 15
    elif face_ratio > 0:
        identity_score = 55
    else:
        identity_score = 0

    audio_score = 100 if probe.get("has_audio") else (35 if talking_expected else 80)
    lip_sync_score = None
    lip_sync_note = "lip_sync_model_not_installed"
    if talking_expected:
        # لا ندعي مزامنة شفاه عميقة بدون نموذج؛ نعطي درجة ثقة مؤقتة مبنية على وجود صوت ووجه مستقر.
        base = 0
        if probe.get("has_audio"):
            base += 45
        if face_ratio >= 0.55:
            base += 35
        if frames.get("motion_energy", 0) > 1.0:
            base += 20
        lip_sync_score = min(100, base)

    hand_score = None
    hand_note = "hand_deformation_model_not_installed"
    if hand_expected:
        pose_truth = request.get("pose_truth") or request.get("dwpose_truth") or request.get("body_truth") or {}
        if isinstance(pose_truth, dict):
            body_truth = pose_truth.get("body_truth") if isinstance(pose_truth.get("body_truth"), dict) else pose_truth
            if body_truth.get("hands_visible") is True or body_truth.get("hands_motion_allowed") is True:
                hand_score = 65
            elif body_truth.get("hands_visible") is False:
                hand_score = 20
            else:
                hand_score = 45
        else:
            hand_score = 45

    return {
        "file_score": file_score,
        "duration_score": duration_score,
        "resolution_score": resolution_score,
        "motion_score": motion_score,
        "black_frame_score": black_score,
        "flicker_score": flicker_score,
        "sharpness_score": sharpness_score,
        "audio_score": audio_score,
        "identity_score": identity_score,
        "mouth_sync_score": lip_sync_score,
        "hand_quality_score": hand_score,
        "body_deformation_proxy_score": min(motion_score, flicker_score, sharpness_score),
        "lip_sync_truth_note": lip_sync_note if talking_expected else "not_required",
        "hand_quality_truth_note": hand_note if hand_expected else "not_required",
    }


def _weighted_score(scores: Dict[str, Any], request: Dict[str, Any]) -> Tuple[int, List[str]]:
    weights = {
        "file_score": 0.10,
        "duration_score": 0.08,
        "resolution_score": 0.08,
        "motion_score": 0.14,
        "black_frame_score": 0.10,
        "flicker_score": 0.12,
        "sharpness_score": 0.08,
        "audio_score": 0.08,
        "identity_score": 0.10,
        "mouth_sync_score": 0.07,
        "hand_quality_score": 0.05,
    }
    total = 0.0
    wsum = 0.0
    for k, w in weights.items():
        val = scores.get(k)
        if val is None:
            continue
        total += float(val) * w
        wsum += w
    overall = int(round(total / max(wsum, 0.001)))
    criminals = []
    checks = [
        ("file_score", "video_missing_or_too_small", 55),
        ("duration_score", "duration_too_short", 50),
        ("resolution_score", "low_resolution", 55),
        ("motion_score", "video_freeze_or_no_real_motion", 55),
        ("black_frame_score", "black_frames", 70),
        ("flicker_score", "flicker_or_temporal_instability", 65),
        ("sharpness_score", "blur_or_low_detail", 55),
        ("audio_score", "audio_missing_for_talking_video", 50),
        ("identity_score", "identity_or_face_not_stable", 50),
        ("mouth_sync_score", "mouth_sync_low_or_unverified", 55),
        ("hand_quality_score", "hands_uncertain_or_deformed", 45),
    ]
    for k, name, threshold in checks:
        val = scores.get(k)
        if val is not None and val < threshold:
            criminals.append(name)
    return max(0, min(100, overall)), criminals


def _solution(criminals: List[str]) -> str:
    c = criminals[0] if criminals else "no_major_criminal"
    if c == "video_missing_or_too_small":
        return "الفيديو غير موجود أو صغير جدًا. راجع output للمحرك أو Composer قبل حكم الجودة."
    if c == "video_freeze_or_no_real_motion":
        return "الحركة ضعيفة أو الفيديو متجمد. جرّب حركة أبسط أو تأكد أن MusePose/MagicAnimate أخرج فيديو حقيقيًا."
    if c == "black_frames":
        return "هناك إطارات سوداء. راجع مسار التشفير أو الدمج أو output_path."
    if c == "flicker_or_temporal_instability":
        return "هناك وميض أو عدم استقرار زمني. جرّب محركًا آخر أو فعّل تثبيت الإضاءة/الهوية."
    if c == "identity_or_face_not_stable":
        return "الوجه غير مستقر أو غير ظاهر كفاية. نحتاج V33 head tracking أقوى أو Face Graft أدق."
    if c == "mouth_sync_low_or_unverified":
        return "مزامنة الفم ضعيفة أو غير مؤكدة. شغّل SadTalker/Face Graft بوجه أوضح ثم أعد الفحص."
    if c == "hands_uncertain_or_deformed":
        return "اليدين غير مؤكدة أو معرضة للتشوه. أعد المحاولة بحركة يد واحدة أو رأس وكتفين."
    return "الفيديو مقبول حسب المؤشرات الحالية. للنتائج العالمية أضف نماذج فحص الهوية واليدين والشفاه في مراحل لاحقة."


class DeepQualityJudge:
    def status(self) -> Dict[str, Any]:
        return ok_output(
            "v35_deep_quality_judge_status",
            v35_deep_quality_judge={
                "enabled": True,
                "checks": [
                    "video_exists", "duration", "resolution", "black_frames", "freeze_ratio", "motion_energy",
                    "flicker", "blur", "audio_presence", "face_presence", "face_stability_proxy",
                    "mouth_sync_proxy", "hand_quality_proxy", "body_deformation_proxy"
                ],
                "truth_ar": "V35 يفحص مؤشرات فيديو حقيقية. لا يدّعي فحص هوية/يدين عميق بنموذج عصبي إذا لم تكن النماذج مركبة.",
            },
        )

    def template(self) -> Dict[str, Any]:
        return ok_output(
            "v35_deep_quality_template",
            template={
                "task": "deep_quality_judge",
                "video_base64": "PUT_FINAL_VIDEO_BASE64_HERE",
                "expected_motion": "real_full_body_talk | standing_idle | right_hand_explain",
                "talking_expected": True,
                "hands_expected": False,
                "strict": True,
                "pose_truth": {"body_truth": {"hands_visible": True, "walking_allowed": False}},
            },
        )

    def judge(self, request: Dict[str, Any], work_root: Path) -> Dict[str, Any]:
        job_dir = work_root / f"v35_quality_{int(time.time()*1000)}"
        job_dir.mkdir(parents=True, exist_ok=True)
        video_path = None
        if request.get("video_base64"):
            video_path = _write_b64_to_file(request.get("video_base64"), job_dir / "input_video.mp4")
        elif request.get("final_video_base64"):
            video_path = _write_b64_to_file(request.get("final_video_base64"), job_dir / "input_video.mp4")
        elif request.get("video_path"):
            video_path = Path(str(request.get("video_path")))
        elif request.get("final_video_path"):
            video_path = Path(str(request.get("final_video_path")))

        if not video_path:
            return fail_output(
                "VIDEO_REQUIRED_FOR_DEEP_QUALITY_JUDGE",
                stage="v35_deep_quality_input",
                suspect="missing_video_input",
                solution_ar="أرسل video_base64 أو video_path داخل input. V35 لا يحكم على فيديو غير موجود.",
                template=self.template(),
            )

        report: Dict[str, Any] = {
            "file_exists": video_path.exists(),
            "video_path": str(video_path),
            "file_size_bytes": video_path.stat().st_size if video_path.exists() else 0,
            "created_at_ms": int(time.time()*1000),
        }
        if video_path.exists():
            report["probe"] = _ffprobe(video_path)
            report["frames"] = _sample_frames(video_path, max_samples=int(request.get("max_samples", 40) or 40))
        else:
            report["probe"] = {"ok": False, "error": "file_not_found"}
            report["frames"] = {"available": False, "error": "file_not_found"}

        scores = _component_scores(report, request)
        overall, criminals = _weighted_score(scores, request)
        strict = bool(request.get("strict", True))
        strict_quality_pass = overall >= (82 if strict else 70) and not any(c in criminals for c in ["video_missing_or_too_small", "black_frames"])
        world_class_gate = overall >= 90 and strict_quality_pass and scores.get("mouth_sync_score", 100) >= 70

        deep_report = {
            "version": "V36_SMART_RETRY_2",
            "overall_quality_score": overall,
            "quality_grade_ar": "عالمي مبدئي" if overall >= 90 else "ممتاز" if overall >= 82 else "جيد" if overall >= 70 else "متوسط" if overall >= 55 else "ضعيف",
            "strict_quality_pass": strict_quality_pass,
            "world_class_gate_pass": world_class_gate,
            "component_scores": scores,
            "criminals": criminals,
            "main_criminal": criminals[0] if criminals else "no_major_criminal",
            "main_criminal_ar": self._criminal_ar(criminals[0] if criminals else "no_major_criminal"),
            "solution_ar": _solution(criminals),
            "next_retry_recommendation_ar": self._retry(criminals),
            "video_report": report,
            "truth_note_ar": "V35 يرفع الحكم من فحص سطحي إلى Deep Quality Proxy. لكنه لا يدعي 99.99% ولا يدعي فحصًا عصبيًا للهوية/اليدين إذا لم تكن نماذجها مركبة.",
            "future_deep_models_needed": ["face_identity_embedding", "lip_sync_model", "hand_pose_quality_model", "person_reid", "temporal_consistency_model"],
        }
        out_path = job_dir / "v35_deep_quality_report.json"
        out_path.write_text(json.dumps(deep_report, ensure_ascii=False, indent=2), encoding="utf-8")
        return ok_output(
            "v35_deep_quality_judge",
            v35_deep_quality_report=deep_report,
            report_path=str(out_path),
            strict_quality_pass=strict_quality_pass,
            overall_quality_score=overall,
            main_criminal=deep_report["main_criminal"],
            solution_ar=deep_report["solution_ar"],
        )

    def _criminal_ar(self, c: str) -> str:
        m = {
            "no_major_criminal": "لا يوجد جاني كبير",
            "video_missing_or_too_small": "الفيديو مفقود أو صغير جدًا",
            "duration_too_short": "مدة الفيديو قصيرة",
            "low_resolution": "الدقة منخفضة",
            "video_freeze_or_no_real_motion": "الفيديو متجمد أو الحركة غير حقيقية",
            "black_frames": "إطارات سوداء",
            "flicker_or_temporal_instability": "وميض أو عدم استقرار زمني",
            "blur_or_low_detail": "ضبابية أو تفاصيل ضعيفة",
            "audio_missing_for_talking_video": "الصوت مفقود في فيديو ناطق",
            "identity_or_face_not_stable": "الهوية أو الوجه غير مستقر",
            "mouth_sync_low_or_unverified": "مزامنة الفم ضعيفة أو غير مؤكدة",
            "hands_uncertain_or_deformed": "اليدان غير مؤكدة أو مشوهة",
        }
        return m.get(c, c)

    def _retry(self, criminals: List[str]) -> str:
        p = set(criminals or [])
        if "hands_uncertain_or_deformed" in p:
            return "أعد المحاولة بحركة يد واحدة أو رأس وكتفين فقط."
        if "video_freeze_or_no_real_motion" in p:
            return "أعد المحاولة بمحرك آخر أو motion أبسط: standing_idle ثم right_hand_explain."
        if "identity_or_face_not_stable" in p or "mouth_sync_low_or_unverified" in p:
            return "أعد Face Graft بعد تحسين head tracking أو استعمل وجهًا أوضح."
        if "flicker_or_temporal_instability" in p:
            return "جرّب MagicAnimate أو فعّل تثبيت الإضاءة/الهوية في Composer."
        if "black_frames" in p or "video_missing_or_too_small" in p:
            return "لا تعيد الجودة؛ أصلح worker output أو encoder أولًا."
        return "احتفظ بالنتيجة، ثم انتقل إلى Benchmark على Dataset قبل الادعاء بنسبة عالمية."
