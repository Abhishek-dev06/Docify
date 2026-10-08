# Phase 6 — evaluation aur demo handoff

L0-L6 prototype ab evaluation aur presentation material ke saath available hai.
Yeh **synthetic hackathon demo** hai; production border deployment ready nahi hai.

## Deliverables

| Artifact | Path |
|---|---|
| Measured report, errors, charts | `reports/phase6/evaluation.md` |
| Raw results and provenance | `reports/phase6/{ocr,tamper,face,system}.json` |
| Frozen sample/threshold protocol | `config/evaluation_protocol.json` |
| One-page solution overview | `output/pdf/solution_overview.pdf` |
| PPT outline + speaking notes | `docs/presentation_outline.md` |
| Five-minute walkthrough | `docs/demo_walkthrough.md` |
| Executable three-case demo | `scripts/demo_phase6.py` |
| Generated fictional demo inputs | `data/phase6_demo/` (reproducible, git-ignored) |

## Install aur reproduce

Existing workspace mein dependencies/models ready hain. Fresh machine par README
setup aur Phase 3 training prerequisites complete karein. Project root se:

```powershell
.\.venv\Scripts\python.exe -m pip install -e "./backend[dev,face,evaluation]"
.\.venv\Scripts\python.exe -m pip install "torch>=2.6,<3" --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe scripts/download_face_models.py
.\.venv\Scripts\python.exe scripts/generate_mock_documents.py
# If data/tampering/manifest.json or trained checkpoint is missing:
.\.venv\Scripts\python.exe scripts/generate_tamper_dataset.py
.\.venv\Scripts\python.exe scripts/train_tamper_model.py
# Keep the existing checkpoint when reproducing the published measurements.
.\.venv\Scripts\python.exe scripts/evaluate_phase6.py
.\.venv\Scripts\python.exe scripts/report_phase6.py
```

Evaluation intentionally requires the original training manifest to match the
checkpoint's recorded hash. Missing/mismatched assets fail explicitly. It does not
download private data, retrain models, or tune thresholds. `--section ocr|tamper|face|system`
runs a single section. `--output reports/another_run` preserves earlier raw measurements;
`report_phase6.py` currently renders the default `reports/phase6` directory.
Default evaluation order runs system timing first, before warming models in other stages.

PDF builder uses `reportlab` and `pypdf`, separate from inference dependencies:
`python scripts/create_solution_overview.py` with those packages installed. This session
used the bundled document Python runtime. PNG/SVG plots use Matplotlib. No custom
biometric metric library is needed: formulas and denominator handling are in
`backend/app/evaluation.py`, with hand-calculated metric tests.

## Results aur honest interpretation

| Measurement | Observed |
|---|---|
| VIZ exact fields | 150/156 = **96.15%** |
| MRZ exact fields | 141/156 = **90.38%** |
| Valid-document all-check pass | 22/25 = **88.00%**; parsed-only 22/24 |
| Fresh synthetic CNN precision / recall / F1 | **94.81% / 91.25% / 92.99%** |
| Fresh CNN confusion TN / FP / FN / TP | **16 / 4 / 7 / 73** |
| Copy-move mean IoU | **0.179**, weakest attack |
| Classical recall at fixed 0.55 index | **1.25%**, 1/80 attacks |
| Illustrative face FAR / FRR | **0/16 / 0/16**, two known generated identities only |
| Controlled pipeline cold / warm median | **12.51 s / 4.01 s** |
| Warm descriptive p95 | **5.57 s**, only six samples |

OCR uses 26 same-layout TD3 document images, including one quality-gated blur case
whose absent fields count as incorrect. Seven extra trailing `K` characters in names
and two `Z`/`7` number confusions explain the MRZ gap. Names lack their own MRZ checksum,
so valid digits cannot establish every field is correct. TD1/TD2 parsing is unit-tested,
but this image evaluation does not measure those layouts.

Original frozen CNN test replay exactly reproduced TN=6, FP=1, FN=4, TP=24 on 35
images. The new 100-image set has disjoint source groups but shares layouts and attack
generation with training. Four clean cards falsely flagged; seven copy-move attacks
missed. Per-attack precision compares against the same 20 clean controls, which must
not be counted repeatedly in pooled metrics. Baseline PNG inputs lack JPEG/ELA evidence.

Face transforms share source pixels; the threshold was already chosen using the
same two identities. Zero observed errors is **not** a biometric guarantee or an
independent ROC benchmark. All 32 comparisons were eligible; unavailable comparisons
would be reported separately. No liveness accuracy metric is claimed.

Timing runs one sequential process with OpenCV/Tesseract limited to two threads;
PyTorch inference uses its existing two-thread setting. Cold means first pipeline call
after module imports, with no OS cache flush. HTTP, audit, browser rendering and fixture
generation are excluded. The Phase 5 browser's slower observations remain documented.
Do not claim checkpoint throughput or a guaranteed four-second response.

## Demo commands

```powershell
.\.venv\Scripts\python.exe scripts/demo_phase6.py --prepare-only
.\.venv\Scripts\python.exe scripts/demo_phase6.py --scenario photo_replaced
# Run all three actual analyses:
.\.venv\Scripts\python.exe scripts/demo_phase6.py
```

Observed scenarios: genuine-looking mock score 3.25 / face match; replaced photo
score 18.25 / face non-match; DOB altered score 7.25 / one field mismatch. All categories
remain null because required liveness evidence is missing. These are policy points,
not fraud probabilities. CLI explicitly exports synthetic fixtures and image-free
result JSON. It does not append to the officer audit; use the dashboard for that step.

Dashboard now includes **Replaced document photo** in its sample selector. The
replaced case changes only the document's portrait region; reference remains synthetic A.

## What to verify before judging

- Open the evaluation report and inspect failures as well as headline scores.
- Use the three generated cases in the dashboard; inspect raw/corrected fields and
  separate classical/CNN maps. Avoid presenting an inconclusive overlay as proof.
- Record a reasoned decision, reopen history, and verify/export its chain checkpoint.
- Rehearse the five-minute script on the actual laptop after a warm-up scan.

Docker configuration is supplied and validated; container runtime remains unverified
because the host Docker engine was unavailable. PostgreSQL runtime, production auth,
genuine stamp weights, verified liveness and e-passport trust validation remain gaps.
These are declared limits, not hidden TODO implementations.
