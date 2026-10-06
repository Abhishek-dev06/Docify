# Phase 2 verification — 2026-10-03

**L4 implemented aur real pretrained models ke saath tested.** YuNet detection,
five-landmark alignment, 128-dimensional SFace embedding, cosine verification,
limited liveness evidence aur fixed synthetic FAISS alias-rule demo available hain.

## Executed checks

- Full suite: **101 passed**, no skipped tests in this run, **28.74 seconds**.
- Phase 2 subset: **41 passed**; Phase 1 regression coverage retained.
- Ruff lint and formatting passed; 47 Python files formatted.
- `pip check`: no broken requirements.
- One existing upstream Starlette/httpx deprecation warning remains.
- Model bytes verified against pinned SHA-256 digests; CPU inference executed.
- Pair uploads >1 MiB stayed in memory; no image-file rollover permitted by tests.
- Concurrent model access, invalid embeddings/thresholds, missing/corrupt models,
  API contracts and restricted synthetic index inputs tested.

## Actual synthetic smoke outcomes

| Case | Observed outcome |
|---|---|
| Same generated identity, transformed capture | Cosine **0.9649**, match at 0.60 |
| Different generated identity | Cosine **0.4562**, non-match at 0.60 |
| No face | Undetermined; no similarity score |
| Multiple faces | Undetermined; no first/largest-face shortcut |
| Blurred face | Undetermined; insufficient evidence |
| Still-image liveness | No live-person score/certification |
| Five identical frames | Repetition flagged; liveness not verified |
| Same synthetic claim | Duplicate-rule flag false |
| Changed synthetic name/document | Duplicate-rule flag true |

**Important error analysis:** Original OpenCV LFW reference threshold **0.363**
produced a false match for the different generated identity (0.4562). Final 0.60
default was chosen after inspecting these development examples. It is therefore
sample-tuned and **not independent calibration**. The original false-match case is
retained in [phase2_smoke.json](phase2_smoke.json), with `threshold_source=request_override`.

Positive pair shares source pixels. Only two AI-generated identities are used;
these results cannot estimate FAR, FRR, ROC, demographic performance or operational
border-checkpoint accuracy. Benchmark model results are not presented as our metrics.

## Liveness limits

Texture heuristics, eye-detection patterns and repeated-frame checks are implemented.
Blink pattern control-flow tests use synthetic eye observations. Real blink/print/
replay performance has not been evaluated. Even a blink candidate stays inconclusive;
`liveness_score=null` and `review_required=true` are intentional.

## Deliverables and next gate

- [Phase 2 run/API guide](../docs/phase2.md)
- [Model manifest](../models/manifest.json) and retained upstream licenses
- [Synthetic asset + exact prompt provenance](../docs/face_asset_provenance.md)
- [Measured outputs and per-call timings](phase2_smoke.json)

Next phase se pehle API explorer mein same/different/no-face examples aur null
liveness score inspect karein. Next implementation phase L3 tampering baseline,
localization heatmap aur training pipeline hai.
