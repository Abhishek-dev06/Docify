# Phase 6 handoff verification

Completed evaluation, README updates, three-case executable demo, a five-minute
Hinglish walkthrough, the requested nine-slide PPT outline and a one-page PDF overview.
No model or threshold was retrained/tuned after observing this phase's results.

## Checks completed

- Backend regression: **217 passed**, one upstream Starlette/httpx deprecation warning.
- Frontend regression: **7 passed** across two files.
- TypeScript/Vite production build: passed, JS 254.22 kB (79.43 kB gzip).
- Real Edge browser: new photo-replacement sample loads both images and correct ROI;
  button enabled; **1 test passed** in 4.4 seconds (13.6 seconds runner time).
- Standalone CLI `demo_phase6.py --scenario photo_replaced`: real inference passed,
  face `non_match`, score 18.25, category null, liveness missing, 12.35 s cold pipeline.
- Evaluation completed all four sections; original CNN test confusion reproduced.
- Ruff check and format checks clean; 89 Python files formatted.
- `pip check`: no broken requirements. Dashboard API reports phase 6, OCR available.
- Existing audit chain still valid after server restart. No audit entries deleted.
- One-page PDF page count checked, rendered with Poppler and visually inspected.
- Five evaluation PNG plots inspected; SVG exports supplied for sharing.

## Measured results and limits

See [full evaluation](phase6/evaluation.md) for raw denominators, errors and plots.
VIZ exact field accuracy 96.15%; MRZ 90.38%; valid-document all-check pass 88%.
Fresh synthetic CNN F1 92.99%, but copy-move IoU 0.179 and classical recall 1.25%.
Two generated identities yield illustrative FAR/FRR only, not biometric validation.
Controlled pipeline warm median 4.01 s, n=6; HTTP/audit/UI timing excluded.

Prior Phase 5 full officer-decision/history/audit browser workflow remains recorded
in [Phase 5 verification](phase5_summary.md). Phase 6 browser check focuses on the new
fixture path; full backend audit regressions ran again in the 217-test suite.

Docker configuration validation from Phase 5 passed; container build/runtime remains
unverified because the local Docker engine was unavailable. Production authentication,
verified liveness, real stamp/chip trust validation and independent external-data
accuracy remain outside the implemented prototype capabilities.

## Files to use

- [Run/install guide](../docs/phase6.md)
- [Five-minute script](../docs/demo_walkthrough.md)
- [PPT outline](../docs/presentation_outline.md)
- [One-page PDF](../output/pdf/solution_overview.pdf)
- [Updated README](../README.md)

The local dashboard is served at http://127.0.0.1:8000 while its Uvicorn process runs.
The guide includes restart commands and fixture regeneration.
