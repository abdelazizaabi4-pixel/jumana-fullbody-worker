from __future__ import annotations
import base64, hashlib, io, json, math, os, time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageStat

from .output_contract import ok_output, fail_output

try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover
    cv2 = None


def _strip_data_prefix(b64: str) -> str:
    if isinstance(b64, str) and "," in b64 and b64[:80].lower().startswith("data:"):
        return b64.split(",", 1)[1]
    return b64


def _decode_image_b64_to_pil(b64: str) -> Image.Image:
    if not b64:
        raise ValueError("image_base64_missing")
    raw = base64.b64decode(_strip_data_prefix(str(b64)))
    return Image.open(io.BytesIO(raw)).convert("RGB")


def _decode_video_b64_to_path(b64: str, out_path: Path) -> Path:
    if not b64:
        raise ValueError("video_base64_missing")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    raw = base64.b64decode(_strip_data_prefix(str(b64)))
    out_path.write_bytes(raw)
    return out_path


def _image_to_b64_png(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _average_hash(img: Image.Image, size: int = 16) -> str:
    # 16x16 = 256-bit hash; stronger than the classic 64-bit hash but still lightweight.
    g = img.convert("L").resize((size, size), Image.Resampling.LANCZOS)
    arr = np.asarray(g, dtype=np.float32)
    mean = float(arr.mean())
    bits = (arr >= mean).astype(np.uint8).reshape(-1)
    # Pack bits into hex.
    out = []
    for i in range(0, len(bits), 4):
        nibble = 0
        for b in bits[i:i+4]:
            nibble = (nibble << 1) | int(b)
        out.append(format(nibble, "x"))
    return "".join(out)


def _hamming_similarity(hex_a: str, hex_b: str) -> float:
    if not hex_a or not hex_b:
        return 0.0
    n = min(len(hex_a), len(hex_b))
    if n == 0:
        return 0.0
    a = bin(int(hex_a[:n], 16))[2:].zfill(n * 4)
    b = bin(int(hex_b[:n], 16))[2:].zfill(n * 4)
    diff = sum(1 for x, y in zip(a, b) if x != y)
    return max(0.0, 1.0 - diff / max(1, len(a)))


def _region(img: Image.Image, box: Tuple[int, int, int, int]) -> Image.Image:
    w, h = img.size
    x1, y1, x2, y2 = box
    x1 = max(0, min(w - 1, int(x1)))
    y1 = max(0, min(h - 1, int(y1)))
    x2 = max(x1 + 1, min(w, int(x2)))
    y2 = max(y1 + 1, min(h, int(y2)))
    return img.crop((x1, y1, x2, y2))


def _detect_face_box(img: Image.Image) -> Dict[str, Any]:
    w, h = img.size
    # Default fallback: upper-center region. This is explicit and not claimed as deep identity.
    fallback = {
        "box": [int(w * 0.28), int(h * 0.06), int(w * 0.72), int(h * 0.46)],
        "source": "fallback_upper_center",
        "confidence": 0.35,
    }
    if cv2 is None:
        return fallback
    try:
        arr = np.asarray(img.convert("RGB"))
        gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
        cascade_path = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
        face_cascade = cv2.CascadeClassifier(cascade_path)
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(24, 24))
        if faces is None or len(faces) == 0:
            return fallback
        # choose biggest face
        x, y, fw, fh = max(faces, key=lambda r: int(r[2]) * int(r[3]))
        pad_x = int(fw * 0.25)
        pad_y = int(fh * 0.28)
        box = [x - pad_x, y - pad_y, x + fw + pad_x, y + fh + pad_y]
        return {"box": [int(v) for v in box], "source": "opencv_haar", "confidence": 0.68}
    except Exception as e:
        fallback["warning"] = str(e)[:160]
        return fallback


def _mean_rgb(img: Image.Image) -> List[float]:
    stat = ImageStat.Stat(img.convert("RGB"))
    return [round(float(x), 3) for x in stat.mean[:3]]


def _std_rgb(img: Image.Image) -> List[float]:
    stat = ImageStat.Stat(img.convert("RGB"))
    return [round(float(x), 3) for x in stat.stddev[:3]]


def _color_similarity(a: List[float], b: List[float]) -> float:
    if not a or not b:
        return 0.0
    dist = math.sqrt(sum((float(x) - float(y)) ** 2 for x, y in zip(a[:3], b[:3])))
    # Max RGB distance approx 441.67.
    return max(0.0, 1.0 - dist / 441.67295593)


def _make_fingerprint(img: Image.Image) -> Dict[str, Any]:
    w, h = img.size
    face = _detect_face_box(img)
    face_img = _region(img, tuple(face["box"]))
    # Clothing/body region: below face down to lower torso.
    x1, y1, x2, y2 = face["box"]
    clothing_top = min(h - 1, int(y2 + h * 0.03))
    clothing_bottom = min(h, int(max(clothing_top + 10, h * 0.88)))
    clothing_box = [int(w * 0.18), clothing_top, int(w * 0.82), clothing_bottom]
    clothing_img = _region(img, tuple(clothing_box))
    full_hash = _average_hash(img)
    face_hash = _average_hash(face_img)
    clothing_hash = _average_hash(clothing_img)
    fp = {
        "image_size": [w, h],
        "face_box": face["box"],
        "face_box_source": face.get("source"),
        "face_detection_confidence": face.get("confidence"),
        "clothing_box": clothing_box,
        "full_hash": full_hash,
        "face_hash": face_hash,
        "clothing_hash": clothing_hash,
        "face_mean_rgb": _mean_rgb(face_img),
        "face_std_rgb": _std_rgb(face_img),
        "clothing_mean_rgb": _mean_rgb(clothing_img),
        "clothing_std_rgb": _std_rgb(clothing_img),
        "full_mean_rgb": _mean_rgb(img),
    }
    fp["fingerprint_sha256"] = hashlib.sha256(json.dumps(fp, sort_keys=True).encode("utf-8")).hexdigest()
    return fp


def _compare_fingerprints(ref: Dict[str, Any], target: Dict[str, Any]) -> Dict[str, Any]:
    face_hash_sim = _hamming_similarity(str(ref.get("face_hash") or ""), str(target.get("face_hash") or ""))
    clothing_hash_sim = _hamming_similarity(str(ref.get("clothing_hash") or ""), str(target.get("clothing_hash") or ""))
    full_hash_sim = _hamming_similarity(str(ref.get("full_hash") or ""), str(target.get("full_hash") or ""))
    face_color_sim = _color_similarity(ref.get("face_mean_rgb") or [], target.get("face_mean_rgb") or [])
    clothing_color_sim = _color_similarity(ref.get("clothing_mean_rgb") or [], target.get("clothing_mean_rgb") or [])
    # Weighted score: face identity most important, clothing next, full hash less important due to background changes.
    score = (
        face_hash_sim * 0.34 + face_color_sim * 0.18 +
        clothing_hash_sim * 0.18 + clothing_color_sim * 0.18 +
        full_hash_sim * 0.12
    ) * 100.0
    metrics = {
        "face_hash_similarity_percent": round(face_hash_sim * 100, 2),
        "face_color_similarity_percent": round(face_color_sim * 100, 2),
        "clothing_hash_similarity_percent": round(clothing_hash_sim * 100, 2),
        "clothing_color_similarity_percent": round(clothing_color_sim * 100, 2),
        "full_image_hash_similarity_percent": round(full_hash_sim * 100, 2),
        "character_consistency_score": round(score, 2),
    }
    return metrics


class CharacterConsistencyV39:
    """V39 Character Consistency.

    الهدف: منع تغيّر الشخصية والملابس والوجه بين المشاهد.
    هذا ليس FaceID عميقًا؛ هو قفل عملي أولي يعتمد على face/cloth fingerprints.
    إذا لم يتم تركيب نموذج هوية عميق لاحقًا، نصرّح بذلك بدل ادعاء 99%.
    """

    VERSION = "V39_CHARACTER_CONSISTENCY"

    def status(self) -> Dict[str, Any]:
        return ok_output(
            "v39_character_consistency_status",
            v39_character_consistency={
                "enabled": True,
                "profile_create": True,
                "profile_compare": True,
                "video_consistency_gate": True,
                "profile_persistence": True,
                "deep_face_identity_model_installed": False,
                "truth_ar": "V39 يحفظ بصمة عملية للشخصية والملابس والوجه. لا يدعي FaceID عميقًا حتى نضيف نموذج هوية متخصص لاحقًا.",
            },
            rule_ar="لا ننتقل إلى مشاهد متعددة بلا Character Profile. إذا تغيّر الوجه أو الملابس كثيرًا، الجاني identity_drift.",
        )

    def template(self) -> Dict[str, Any]:
        return ok_output(
            "v39_character_consistency_template",
            create_profile={
                "task": "character_create_profile",
                "reference_image_base64": "PUT_REFERENCE_IMAGE_BASE64_HERE",
                "character_name": "Adam",
                "save_profile": True,
            },
            compare_image={
                "task": "character_compare",
                "character_profile": "PROFILE_JSON_OR_OBJECT",
                "target_image_base64": "PUT_TARGET_IMAGE_BASE64_HERE",
                "strict": True,
            },
            compare_video={
                "task": "character_consistency_gate",
                "character_profile": "PROFILE_JSON_OR_OBJECT",
                "target_video_base64": "PUT_VIDEO_BASE64_HERE",
                "strict": True,
                "sample_frames": 8,
            },
            execute_with_lock={
                "task": "motion_library_execute",
                "image_base64": "PUT_IMAGE_BASE64_HERE",
                "intent_ar": "شرح باليد اليمنى",
                "character_profile": "PROFILE_JSON_OR_OBJECT",
                "character_consistency_strict": True,
            },
        )

    def _profiles_dir(self, work_root: Path) -> Path:
        d = work_root / "character_profiles"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _load_profile(self, profile: Any, work_root: Path) -> Dict[str, Any]:
        if isinstance(profile, dict):
            return profile
        if isinstance(profile, str) and profile.strip():
            s = profile.strip()
            if s.startswith("{"):
                return json.loads(s)
            # Treat as id or path.
            p = Path(s)
            if not p.exists():
                p = self._profiles_dir(work_root) / f"{s}.json"
            if p.exists():
                return json.loads(p.read_text(encoding="utf-8"))
        raise ValueError("character_profile_missing_or_unreadable")

    def create_profile_from_image(self, request: Dict[str, Any], work_root: Path) -> Dict[str, Any]:
        img_b64 = request.get("reference_image_base64") or request.get("image_base64") or request.get("source_image_base64")
        img = _decode_image_b64_to_pil(str(img_b64 or ""))
        fp = _make_fingerprint(img)
        name = str(request.get("character_name") or request.get("name") or "jumana_character").strip() or "jumana_character"
        profile_id = hashlib.sha256((name + fp["fingerprint_sha256"]).encode("utf-8")).hexdigest()[:16]
        profile = {
            "version": self.VERSION,
            "profile_id": profile_id,
            "character_name": name,
            "created_at_ms": int(time.time() * 1000),
            "fingerprint": fp,
            "locked_features": {
                "face_hash": True,
                "face_color": True,
                "clothing_hash": True,
                "clothing_color": True,
                "full_hash_soft": True,
            },
            "honesty_note_ar": "هذه بصمة عملية خفيفة، وليست نموذج FaceID عميق. V39 تمنع الانحراف الواضح، وV39.5/V40 يمكن أن يضيفا نموذج هوية أقوى.",
        }
        saved_path = None
        if bool(request.get("save_profile", True)):
            p = self._profiles_dir(work_root) / f"{profile_id}.json"
            p.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
            saved_path = str(p)
        return ok_output(
            "v39_character_profile_created",
            character_profile=profile,
            profile_id=profile_id,
            saved_path=saved_path,
            face_detection_source=fp.get("face_box_source"),
            face_detection_confidence=fp.get("face_detection_confidence"),
            next_step_ar="استعمل profile_id أو character_profile في character_consistency_gate أو أثناء motion_library_execute.",
        )

    def _sample_video_frames(self, video_b64: str, work_root: Path, sample_frames: int = 8) -> List[Image.Image]:
        if cv2 is None:
            raise RuntimeError("opencv_not_available_for_video_sampling")
        vid_path = _decode_video_b64_to_path(video_b64, work_root / f"v39_video_{int(time.time()*1000)}.mp4")
        cap = cv2.VideoCapture(str(vid_path))
        if not cap.isOpened():
            raise RuntimeError("video_open_failed")
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        frames: List[Image.Image] = []
        if total <= 0:
            # fallback sequential first frames
            step_indices = list(range(max(1, sample_frames)))
        else:
            step_indices = np.linspace(0, max(0, total - 1), num=max(1, sample_frames), dtype=int).tolist()
        for idx in step_indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
            ok, frame = cap.read()
            if not ok or frame is None:
                continue
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frames.append(Image.fromarray(rgb).convert("RGB"))
        cap.release()
        if not frames:
            raise RuntimeError("video_frame_sampling_failed")
        return frames

    def compare(self, request: Dict[str, Any], work_root: Path) -> Dict[str, Any]:
        profile = self._load_profile(request.get("character_profile") or request.get("profile") or request.get("profile_id"), work_root)
        ref_fp = profile.get("fingerprint") or {}
        threshold = float(request.get("threshold") or (78 if request.get("strict") else 68))
        sample_frames = int(request.get("sample_frames") or 8)
        details: List[Dict[str, Any]] = []

        if request.get("target_video_base64") or request.get("video_base64"):
            frames = self._sample_video_frames(str(request.get("target_video_base64") or request.get("video_base64")), work_root, sample_frames)
            for i, img in enumerate(frames):
                target_fp = _make_fingerprint(img)
                metrics = _compare_fingerprints(ref_fp, target_fp)
                details.append({"sample_index": i, **metrics, "face_box_source": target_fp.get("face_box_source")})
            score = sum(d["character_consistency_score"] for d in details) / max(1, len(details))
            min_score = min(d["character_consistency_score"] for d in details)
            stage = "v39_character_video_consistency_compared"
            target_kind = "video"
        else:
            img_b64 = request.get("target_image_base64") or request.get("image_base64") or request.get("source_image_base64")
            img = _decode_image_b64_to_pil(str(img_b64 or ""))
            target_fp = _make_fingerprint(img)
            metrics = _compare_fingerprints(ref_fp, target_fp)
            details.append({"sample_index": 0, **metrics, "face_box_source": target_fp.get("face_box_source")})
            score = metrics["character_consistency_score"]
            min_score = score
            stage = "v39_character_image_consistency_compared"
            target_kind = "image"

        pass_gate = score >= threshold and min_score >= max(0, threshold - 12)
        suspect = None if pass_gate else "identity_drift_or_clothing_drift"
        solution = "يمكن المتابعة؛ الشخصية ثابتة حسب قفل V39." if pass_gate else "الجاني: تغيّر الهوية أو الملابس. استعمل نفس الصورة المرجعية، أو ثبّت Character Profile، أو اختر حركة أبسط/محركًا يحفظ الاتساق أكثر."
        payload = {
            "target_kind": target_kind,
            "profile_id": profile.get("profile_id"),
            "character_name": profile.get("character_name"),
            "threshold": threshold,
            "character_consistency_pass": pass_gate,
            "character_consistency_score": round(float(score), 2),
            "minimum_sample_score": round(float(min_score), 2),
            "details": details,
            "main_criminal_ar": suspect,
            "solution_ar": solution,
            "deep_identity_model_installed": False,
            "honesty_note_ar": "V39 فحص عملي للاتساق وليس ضمان هوية عميق مثل نماذج الشركات الكبرى. لكنه يمنع تغيّرًا واضحًا في الوجه/الملابس بين المشاهد.",
        }
        if pass_gate:
            return ok_output(stage, **payload)
        return fail_output(
            "CHARACTER_CONSISTENCY_GATE_FAILED",
            stage="v39_character_consistency_gate",
            suspect=suspect or "identity_drift",
            solution_ar=solution,
            **payload,
        )

    def gate(self, request: Dict[str, Any], work_root: Path) -> Dict[str, Any]:
        return self.compare(request or {}, work_root)
