from __future__ import annotations
from typing import Dict, Any, List

# V38 Motion Library Pro
# كل حركة هنا ليست مجرد اسم؛ هي بطاقة قرار: مستوى، متطلبات، مخاطر، بدائل، وتفضيل محركات.
MOTION_LIBRARY: Dict[str, Dict[str, Any]] = {
    "standing_idle": {
        "name": "standing_idle",
        "ar": "وقوف طبيعي مع تنفس خفيف",
        "category": "idle",
        "level": 1,
        "risk": "very_low",
        "requires": ["head", "torso"],
        "forbidden_if": [],
        "engine_preferences": ["magicanimate", "musepose", "animateanyone"],
        "pose_sequence_hint": "idle_breathing_01: shoulder_micro_motion + chest_breathing + tiny_head_stability",
        "duration_seconds": 4,
        "quality_target": 82,
        "safe_alternatives": [],
        "aliases": ["idle_breathing_01", "idle", "breathing", "وقوف", "تنفس"],
    },
    "head_turn_left": {
        "name": "head_turn_left",
        "ar": "التفات الرأس إلى اليسار بلطف",
        "category": "head",
        "level": 1,
        "risk": "low",
        "requires": ["head", "torso"],
        "engine_preferences": ["magicanimate", "musepose", "animateanyone"],
        "pose_sequence_hint": "turn_head_left_01: head yaw left 8-14 degrees, shoulders stable",
        "duration_seconds": 3,
        "quality_target": 82,
        "safe_alternatives": ["standing_idle"],
        "aliases": ["turn_head_left_01", "head_turn", "turn_head", "التفات", "التفات يسار"],
    },
    "listener_nod": {
        "name": "listener_nod",
        "ar": "المستمع يهز رأسه موافقًا بهدوء",
        "category": "listener",
        "level": 1,
        "risk": "low",
        "requires": ["head", "torso"],
        "engine_preferences": ["magicanimate", "musepose", "animateanyone"],
        "pose_sequence_hint": "listener_nod_01: two tiny nods, no hand motion",
        "duration_seconds": 4,
        "quality_target": 82,
        "safe_alternatives": ["standing_idle"],
        "aliases": ["listener_nod_01", "nod", "استماع", "يهز رأسه"],
    },
    "right_hand_explain": {
        "name": "right_hand_explain",
        "ar": "شرح باليد اليمنى",
        "category": "speaker_gesture",
        "level": 2,
        "risk": "medium_low",
        "requires": ["head", "torso", "right_hand"],
        "engine_preferences": ["musepose", "magicanimate", "animateanyone"],
        "pose_sequence_hint": "speaker_gesture_01: right hand rises to chest level then opens slightly",
        "duration_seconds": 5,
        "quality_target": 78,
        "safe_alternatives": ["head_turn_left", "standing_idle"],
        "aliases": ["speaker_gesture_01", "right_hand", "شرح باليد اليمنى", "يد يمنى"],
    },
    "both_hands_explain": {
        "name": "both_hands_explain",
        "ar": "شرح باليدين",
        "category": "speaker_gesture",
        "level": 3,
        "risk": "medium",
        "requires": ["head", "torso", "left_hand", "right_hand"],
        "engine_preferences": ["musepose", "magicanimate", "animateanyone"],
        "pose_sequence_hint": "speaker_gesture_02: both hands move symmetrically inside torso-safe zone",
        "duration_seconds": 5,
        "quality_target": 76,
        "safe_alternatives": ["right_hand_explain", "head_turn_left", "standing_idle"],
        "aliases": ["speaker_gesture_02", "both_hands", "شرح باليدين", "يدين"],
    },
    "raise_hand_greeting": {
        "name": "raise_hand_greeting",
        "ar": "رفع اليد للتحية",
        "category": "greeting",
        "level": 3,
        "risk": "medium",
        "requires": ["head", "torso", "right_hand"],
        "engine_preferences": ["musepose", "magicanimate", "animateanyone"],
        "pose_sequence_hint": "raise_hand_01: right hand raises slowly, no extreme elbow bend",
        "duration_seconds": 4,
        "quality_target": 76,
        "safe_alternatives": ["right_hand_explain", "standing_idle"],
        "aliases": ["raise_hand_01", "raise_hand", "تحية", "رفع اليد"],
    },
    "walking_lite": {
        "name": "walking_lite",
        "ar": "مشي خفيف حقيقي بحذر",
        "category": "walking",
        "level": 5,
        "risk": "high",
        "requires": ["head", "torso", "legs", "feet"],
        "engine_preferences": ["musepose", "magicanimate", "animateanyone"],
        "pose_sequence_hint": "walking_lite_01: small steps only if both feet visible; otherwise blocked",
        "duration_seconds": 6,
        "quality_target": 72,
        "safe_alternatives": ["standing_idle", "right_hand_explain", "head_turn_left"],
        "guard": "feet_visible_required",
        "aliases": ["walking_lite_01", "walk", "walking", "مشي", "يمشي"],
    },
}

ALIASES: Dict[str, str] = {}
for key, data in MOTION_LIBRARY.items():
    ALIASES[key.lower()] = key
    for a in data.get("aliases", []):
        ALIASES[str(a).strip().lower()] = key
# compatibility aliases from older versions
ALIASES.update({
    "idle_breathing_01": "standing_idle",
    "speaker_gesture_01": "right_hand_explain",
    "speaker_gesture_02": "both_hands_explain",
    "turn_head_left_01": "head_turn_left",
    "raise_hand_01": "raise_hand_greeting",
    "walking_lite_01": "walking_lite",
    "listener_nod_01": "listener_nod",
    "head_turn": "head_turn_left",
})

def normalize_motion_name(name: str | None) -> str:
    raw = str(name or "standing_idle").strip().lower()
    return ALIASES.get(raw, raw if raw in MOTION_LIBRARY else "standing_idle")

def get_motion(name: str | None) -> Dict[str, Any]:
    key = normalize_motion_name(name)
    data = dict(MOTION_LIBRARY.get(key) or MOTION_LIBRARY["standing_idle"])
    data["name"] = key
    data["requested_name"] = name
    return data

def list_motions() -> Dict[str, Any]:
    return {k: dict(v, name=k) for k, v in MOTION_LIBRARY.items()}

def list_motion_names() -> List[str]:
    return list(MOTION_LIBRARY.keys())
