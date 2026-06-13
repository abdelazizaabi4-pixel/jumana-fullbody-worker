V34 — Real Head Tracking

هدف هذه النسخة: لا نقول إن MusePose قوي بالتخمين.
نقيسه على Dataset: صور + حركات + نسب نجاح + أكبر جاني.

المراحل:
1) شغّل task=benchmark_template لترى القالب.
2) شغّل dry_run=true للتأكد من الصور وDWPose دون صرف كبير.
3) بعد نجاح V31 MusePose Lock، شغّل run_e2e=true على 20 صورة.
4) إذا نجح: وسّع إلى 100 صورة.

لا تدّعي أن جمانة عالمية قبل تقرير v34_benchmark_report.json على dataset حقيقي.
