from __future__ import annotations
import json, time, os, traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .output_contract import ok_output, fail_output
from .input_tools import decode_image_base64, image_info

DEFAULT_MOTIONS = ["standing_idle", "right_hand_explain", "both_hands_explain"]

def _now_ms() -> int:
    return int(time.time() * 1000)

def _pct(n: int, d: int) -> float:
    return round((n / d) * 100.0, 2) if d else 0.0

class PoseDatasetBenchmark:
    """V34 Pose Dataset Benchmark: يقيس DWPose وMusePose بالأرقام بدل التخمين."""
    def __init__(self, dwpose, musepose_lock, doctor, workdir: Optional[Path] = None):
        self.dwpose = dwpose
        self.musepose_lock = musepose_lock
        self.doctor = doctor
        self.workdir = workdir or Path(os.environ.get("JUMANA_WORKDIR", "/workspace/outputs"))
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.min_cases_warning = int(os.environ.get("JUMANA_BENCHMARK_MIN_CASES", "20"))
        self.target_cases = int(os.environ.get("JUMANA_BENCHMARK_TARGET_CASES", "100"))

    def template(self) -> Dict[str, Any]:
        return ok_output(
            "v34_benchmark_template",
            v34_pose_dataset_benchmark=True,
            purpose_ar="V34 تقيس النجاح بالأرقام: DWPose، MusePose، output، وجود فيديو، وأكبر جاني.",
            recommended_dataset=[
                {"type":"face_close", "count":10},
                {"type":"upper_body_hands", "count":20},
                {"type":"full_body_feet_visible", "count":30},
                {"type":"full_body_feet_partial", "count":20},
                {"type":"two_person", "count":10},
                {"type":"complex_background", "count":10},
            ],
            default_motions=DEFAULT_MOTIONS,
            acceptance_targets={
                "pipeline_reliability_percent": 99.99,
                "musepose_e2e_lock_required_before_benchmark": True,
                "minimum_real_e2e_cases_before_claiming_progress": self.min_cases_warning,
                "target_cases_for_world_class_claim": self.target_cases,
                "minimum_pose_success_percent_phase_1": 90,
                "minimum_musepose_success_percent_phase_1": 70,
            },
            no_fake_success_rule_ar="إذا لم نجد فيديو حقيقيًا، لا نحتسب الاختبار ناجحًا ولو انتهى RunPod بـ COMPLETED.",
            next_step_ar="املأ cases بصور base64 أو ضع dataset_dir داخل RunPod ثم شغّل task=pose_dataset_benchmark.",
        )

    def _load_cases_from_dataset_dir(self, dataset_dir: str) -> List[Dict[str, Any]]:
        root = Path(dataset_dir)
        cases: List[Dict[str, Any]] = []
        if not root.exists():
            return cases
        exts = {".png", ".jpg", ".jpeg", ".webp"}
        for idx, p in enumerate(sorted([x for x in root.rglob("*") if x.suffix.lower() in exts])):
            cases.append({"id": p.stem or f"case_{idx+1:03d}", "image_path": str(p), "type": p.parent.name})
        return cases

    def _normalize_cases(self, request: Dict[str, Any]) -> List[Dict[str, Any]]:
        raw = request.get("cases") or request.get("images") or []
        cases: List[Dict[str, Any]] = []
        if isinstance(raw, list):
            for i, item in enumerate(raw):
                if isinstance(item, str):
                    cases.append({"id": f"case_{i+1:03d}", "image_base64": item})
                elif isinstance(item, dict):
                    item = dict(item); item.setdefault("id", f"case_{i+1:03d}"); cases.append(item)
        dataset_dir = request.get("dataset_dir") or os.environ.get("JUMANA_BENCHMARK_DATASET_DIR")
        if dataset_dir:
            cases.extend(self._load_cases_from_dataset_dir(str(dataset_dir)))
        try:
            if request.get("max_cases"):
                cases = cases[:int(request.get("max_cases"))]
        except Exception:
            pass
        return cases

    def _materialize_case_image(self, case: Dict[str, Any], case_dir: Path) -> Tuple[Optional[Path], Optional[Dict[str, Any]]]:
        try:
            if case.get("image_path"):
                p = Path(str(case["image_path"]))
                if p.exists(): return p, None
                return None, {"error":"IMAGE_PATH_NOT_FOUND", "path":str(p)}
            b64 = case.get("image_base64") or case.get("source_image_base64") or case.get("image")
            if b64:
                return decode_image_base64(b64, case_dir / "source.png"), None
            return None, {"error":"IMAGE_MISSING", "solution_ar":"ضع image_base64 أو image_path داخل case."}
        except Exception as e:
            return None, {"error":"IMAGE_DECODE_FAILED", "details":str(e), "traceback_tail":traceback.format_exc()[-1200:]}

    def run(self, request: Dict[str, Any]) -> Dict[str, Any]:
        request = request or {}
        dry_run = bool(request.get("dry_run", False))
        run_e2e = bool(request.get("run_e2e", not dry_run))
        engine = str(request.get("engine") or "musepose").lower().strip()
        motions = request.get("motions") or DEFAULT_MOTIONS
        if isinstance(motions, str): motions = [motions]
        motions = [str(m).strip() for m in motions if str(m).strip()] or DEFAULT_MOTIONS
        cases = self._normalize_cases(request)
        run_id = f"v34_benchmark_{_now_ms()}"
        out_dir = self.workdir / run_id
        out_dir.mkdir(parents=True, exist_ok=True)
        readiness = self.doctor.report({"engine": engine, "source":"v34_benchmark"})
        lock_status = self.musepose_lock.status()

        if not cases:
            report = ok_output("v34_benchmark_no_cases_yet", v34_pose_dataset_benchmark=True, dry_run=True, cases_count=0, motions=motions, engine=engine, readiness=readiness, musepose_lock_status=lock_status, benchmark_template=self.template(), solution_ar="لم تُرسل صور اختبار. أرسل cases تحتوي image_base64 أو ضع JUMANA_BENCHMARK_DATASET_DIR داخل RunPod.")
            report_path = out_dir / "v34_benchmark_report.json"
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            report["report_path"] = str(report_path)
            return report

        if engine != "musepose":
            return fail_output("V34_FIRST_BENCHMARK_SUPPORTS_MUSEPOSE_ONLY", stage="v34_benchmark_engine_check", suspect="wrong_engine_for_phase_v34", solution_ar="V34 هدفها تثبيت MusePose بالأرقام أولًا. بعد نجاحه نضيف MagicAnimate وAnimateAnyone للـ benchmark.", requested_engine=engine, supported_engine="musepose")

        if not dry_run:
            pre = self.musepose_lock.preflight()
            if not pre.get("ok"):
                pre["v34_blocked_ar"] = "V34 لا يبدأ Benchmark حقيقي قبل نجاح V31 MusePose Lock. أصلح الجناة ثم أعد الاختبار."
                pre["readiness"] = readiness
                return pre

        case_results: List[Dict[str, Any]] = []
        totals = {"cases":0, "pose_ok":0, "motion_tests":0, "motion_ok":0, "video_ok":0, "image_fail":0}
        criminals: Dict[str,int] = {}
        for idx, case in enumerate(cases):
            case_id = str(case.get("id") or f"case_{idx+1:03d}")
            case_dir = out_dir / case_id; case_dir.mkdir(parents=True, exist_ok=True)
            img_path, err = self._materialize_case_image(case, case_dir)
            one: Dict[str, Any] = {"case_id": case_id, "case_type": case.get("type"), "motions": []}
            totals["cases"] += 1
            if err or img_path is None:
                totals["image_fail"] += 1
                suspect = (err or {}).get("error", "image_missing")
                criminals[suspect] = criminals.get(suspect,0) + 1
                one.update({"ok":False, "stage":"image", "criminal":suspect, "error":err}); case_results.append(one); continue
            try: one["image_info"] = image_info(img_path)
            except Exception: one["image_info"] = {"path": str(img_path)}
            truth = self.dwpose.analyze(img_path)
            one["dwpose_ok"] = bool(truth.get("ok")); one["body_truth"] = truth.get("body_truth"); one["dwpose_stage"] = truth.get("stage")
            if truth.get("ok"):
                totals["pose_ok"] += 1
            else:
                suspect = str(truth.get("suspect") or truth.get("error") or "dwpose_failed")
                criminals[suspect] = criminals.get(suspect,0) + 1
                one.update({"ok":False, "criminal":suspect, "dwpose_result":truth}); case_results.append(one); continue
            if dry_run or not run_e2e:
                one.update({"ok":True, "dry_run":True, "decision_ar":"DWPose نجح. لم يتم تشغيل MusePose لأن dry_run=true أو run_e2e=false."}); case_results.append(one); continue
            all_motion_ok = True
            for motion in motions:
                totals["motion_tests"] += 1
                res = self.musepose_lock.run_e2e_test(img_path, motion, pose_truth=truth)
                video_ok = bool(res.get("ok") and (res.get("video_base64") or res.get("video_url")))
                if video_ok:
                    totals["motion_ok"] += 1; totals["video_ok"] += 1
                else:
                    all_motion_ok = False
                    suspect = str(res.get("suspect") or res.get("error") or "musepose_motion_failed")
                    criminals[suspect] = criminals.get(suspect,0) + 1
                one["motions"].append({"motion":motion, "ok":bool(res.get("ok")), "video_ok":video_ok, "stage":res.get("stage"), "suspect":res.get("suspect"), "error":res.get("error"), "video_path":res.get("video_path"), "has_video_base64":bool(res.get("video_base64")), "has_video_url":bool(res.get("video_url"))})
            one["ok"] = all_motion_ok; case_results.append(one)

        pose_rate = _pct(totals["pose_ok"], totals["cases"])
        e2e_rate = _pct(totals["video_ok"], totals["motion_tests"])
        image_rate = _pct(totals["cases"]-totals["image_fail"], totals["cases"])
        sorted_criminals = sorted(criminals.items(), key=lambda kv: kv[1], reverse=True)
        production = totals["cases"] >= self.min_cases_warning and pose_rate >= 90 and (dry_run or e2e_rate >= 70)
        world = totals["cases"] >= self.target_cases and pose_rate >= 95 and (dry_run or e2e_rate >= 90)
        report = ok_output("v34_pose_dataset_benchmark_report", v34_pose_dataset_benchmark=True, engine=engine, dry_run=dry_run, run_e2e=run_e2e, motions=motions, totals=totals, rates={"image_success_percent":image_rate, "pose_success_percent":pose_rate, "musepose_e2e_video_success_percent":e2e_rate}, production_claim_allowed=production, world_class_claim_allowed=world, main_criminal=(sorted_criminals[0][0] if sorted_criminals else None), criminal_counts=dict(sorted_criminals), readiness=readiness, musepose_lock_status=lock_status, cases=case_results, report_dir=str(out_dir), verdict_ar=self._verdict_ar(totals["cases"], pose_rate, e2e_rate, dry_run, production, world), next_step_ar="إذا نجح Benchmark على 20 حالة ننتقل إلى 100 صورة، ثم V34 Head Tracking. إذا فشل، أصلح الجاني الأعلى في criminal_counts فقط.")
        report_path = out_dir / "v34_benchmark_report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        report["report_path"] = str(report_path)
        return report

    def _verdict_ar(self, cases: int, pose_rate: float, e2e_rate: float, dry_run: bool, production: bool, world: bool) -> str:
        if cases < self.min_cases_warning:
            return f"الاختبار صغير ({cases} حالة). لا نحكم عالميًا قبل {self.min_cases_warning} حالة على الأقل."
        if dry_run:
            return "هذا Dry Run: أثبتنا قابلية الفحص فقط، وليس نجاح الفيديو الحقيقي. شغّل run_e2e=true بعد قفل MusePose."
        if world: return "ممتاز جدًا: dataset كبير ونسب قوية. يمكن الانتقال إلى V34 بثقة."
        if production: return "جيد كبداية عملية: MusePose قابل للاعتماد في الحالات المدعومة، لكن لا ندعي مستوى عالمي قبل 100 حالة."
        return f"لا ننتقل بعد. pose_success={pose_rate}% و musepose_e2e={e2e_rate}%. أصلح الجاني الأكبر وأعد نفس الاختبار."
