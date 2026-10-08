# Phase 4 — L5 risk + integrated pipeline

L5 ready hai: configurable weighted score, har signal ke points/reasons, missing
evidence list, coverage aur policy SHA-256. Complete pipeline ab
**L0 → L1 → parallel L2/L3/L4 → L5** run karti hai. L6 dashboard/audit next phase hai.

## Files

- `config/risk_weights.yaml`: versioned development weights, thresholds, required signals.
- `backend/app/schemas/risk.py`: typed inputs, contributions and uncertainty fields.
- `backend/app/layers/l5_risk/engine.py`: `RiskEngine` protocol, policy validation,
  deterministic weighted implementation; future learned engine can implement same interface.
- `backend/app/layers/l5_risk/evidence.py`: existing layer results → canonical signals.
- `backend/app/screening.py`: bounded shared 3-worker pool, layer isolation and quality gate.
- `backend/app/api/risk.py`: policy, standalone score and multipart screening routes.
- `scripts/demo_phase4.py`, `verify_phase4.py`: CLI + reproducible synthetic smoke.
- `backend/tests/test_risk.py`, `test_screening.py`: arithmetic, unknown evidence,
  actual concurrency barrier, failure isolation, portrait coordinates, real-model HTTP test.

## Install/run — PowerShell, project root

No new runtime dependency in this phase. Existing OCR, face and optional PyTorch
setup from Phases 1–3 is reused. Missing models return unavailable evidence.

```powershell
.\.venv\Scripts\python.exe scripts/seed_mock_database.py
.\.venv\Scripts\python.exe scripts/verify_phase4.py
.\.venv\Scripts\python.exe -m pytest backend/tests -q
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/v1/screening/analyze -F "document=@data/synthetic_faces/a_document.png" -F "live=@data/synthetic_faces/a_live.png" -F "reference_date=2026-10-03" -F "document_type=passport" -F "photo_region=[0.75,0.21,0.19375,0.46]"
.\.venv\Scripts\python.exe scripts/demo_phase4.py data/synthetic_faces/a_document.png --live data/synthetic_faces/a_live.png --reference-date 2026-10-03 --document-type passport --photo-region '[0.75,0.21,0.19375,0.46]' --output reports/local_phase4.json
```

CLI output excludes all base64 images. JSON still contains extracted fields; the
explicit export command is meant for synthetic fixtures. API persists no images,
fields, embeddings or decisions. Audit storage is not implemented in this phase.

## Scoring policy

| Signal | Maximum points | Mapping |
|---|---:|---|
| Mock blacklist | 35 | Known hit=1, known no-hit=0, lookup missing=null |
| Synthetic duplicate identity | 15 | Bundled FAISS demo hit; absent from general upload flow |
| Face | 15 | One clear face each; cosine below configured threshold=1 |
| MRZ | 8 | Any failed check=1; per-field/composite failures are not added together |
| Cross-field mismatch | 8 | `min(observed mismatches / 2, 1)` |
| Date rules | 5 | Any expired/invalid date rule=1; uncertain dates stay incomplete |
| Classical tampering | 5 | Maximum spatial classical index; not summed across detectors |
| Liveness | 4 | Positive untrained spoof indicator only; completeness remains false |
| Metadata/compression | 2 | Maximum EXIF/DCT proxy, counted separately from spatial signals |
| Format policy | 3 | Demo country/number-format rule violation |

Weights sum to 100. Each contribution is `weight × value`, rounded to four decimal
places; score is their sum. Category thresholds are inclusive: Medium ≥15, High ≥35.
Below 15 is Low **only when required evidence is complete**. Known score ≥35 retains
High even with gaps, but `status` still reports `insufficient_evidence`.

Required signals: blacklist, face, MRZ, cross-fields, dates, tampering, liveness.
No observed evidence → `score: null`, `category: null`, range `[0,100]`.
Some observed evidence → score contains only observed points. If required evidence
is missing and score <35, category is `null`; missing evidence never earns a Low label.

`score_range` is the mathematical range obtained by allowing each incomplete
signal to use its remaining configured points. It is **not a statistical confidence
interval or fraud probability**. `evidence_coverage` is the fraction of policy weight
whose checks are complete. Coverage measures availability, not reliability or accuracy.
Even complete experimental checks are still experimental.

Every response contains `calibrated:false`, `human_review_required:true`,
`automatic_decision:null`, policy version/hash and each contribution's source.
Rules support review only; no Approve/Reject action exists yet.

## Endpoints and standalone use

`GET /api/v1/risk/policy` returns effective YAML policy and SHA-256. Policy edits
reload on the next score call. Invalid weights, NaN, missing keys, invalid category
thresholds and empty required-signal lists are rejected; no silent fallback.

`POST /api/v1/risk/score` accepts **caller-supplied demo signals**:

```json
{
  "signals": {
    "blacklist": {
      "value": 1,
      "complete": true,
      "explanation": "Fictional blacklist hit for the demonstration.",
      "source": "mock demo",
      "experimental": true
    }
  }
}
```

This returns score 35, category High, range `[35,100]`, coverage 0.35,
`status: insufficient_evidence`, and `evidence_origin: caller_supplied`.
It is an arithmetic demo endpoint, not a trusted alternative to processing evidence.
Unknown signal names, values outside `[0,1]`, NaN and infinities are rejected.

`POST /api/v1/screening/analyze` derives evidence **on the server**:

| Multipart field | Meaning |
|---|---|
| `document` | Required JPEG/PNG/WebP |
| `reference_date` | Required explicit `YYYY-MM-DD`; no hidden machine-date dependency |
| `document_type` | Optional passport/visa/id/license/permit/unknown |
| `live` | Optional single face reference image |
| `frames` | Alternative to live: repeated ordered frame uploads, 1–12 |
| `timestamps_ms` | JSON array for frames; mandatory for multiple frames, strictly increasing within 0–20000 |
| `photo_region` | Optional normalized `[x,y,w,h]` on EXIF-oriented original |

`live` and `frames` are mutually exclusive. When frames are supplied, the first
frame is also the face-comparison reference, tying comparison to that sequence.
No live/frames means face/liveness stay missing. Upload cap is 20 MiB total plus
64 KiB form overhead, 10 MiB per image. Sequence decoded pixels ≤12 MP. L3 accepts
documents ≤4 MP; an L3 failure remains visible while other layers continue.

Response fields: `document_hash`, `reference_date`, `capture`, `ocr`, `validation`,
`tampering`, `face`, `liveness`, `risk`, `failures`, `duration_ms`, `parallel_stage_ms`,
`images_persisted:false`. Risk evidence origin is `server_layers`. Hash is SHA-256
of original upload bytes, not a perceptual identity fingerprint.

```python
from datetime import date
from pathlib import Path
from app.screening import screen_document
from app.layers.l5_risk.engine import score_risk
from app.schemas.risk import RiskInput

unknown = score_risk(RiskInput())
assert unknown.data.score is None

result = screen_document(
    Path("data/synthetic_faces/a_document.png").read_bytes(),
    date(2026, 10, 3), "passport",
    live_payload=Path("data/synthetic_faces/a_live.png").read_bytes(),
    photo_region=(.75, .21, .19375, .46),
)
print(result.risk.data.score, result.risk.data.reasons)
```

## Integration fixes verified in this phase

The first integrated run correctly withheld a category, but portrait artifacts
contaminated printed fields and an MRZ row missed one filler glyph. Mock-blacklist
lookup consequently remained unknown. The fix does not invent missing characters:

1. When a caller supplies the portrait region, its corners are mapped using L0's
   perspective transform and excluded **only from OCR**. A finding records this.
   Face comparison keeps the unmasked L0 image; L3 keeps original bytes/metadata.
2. MRZ row OCR performs one extra segmentation-mode retry only when prior readings
   have unsupported lengths. It preserves every raw reading and still requires
   exact observed TD1/TD2/TD3 lengths; no padding/check-digit forcing.

The supplied portrait region must really cover the portrait. There is no automatic
full-portrait region detector yet. Without that hint, OCR may still be incomplete.
Coordinates in L4 refer to the corrected document; L3 heatmaps refer to the resized
EXIF-oriented original. These frames must not be mixed in the future dashboard.

## Actual end-to-end results

Run used real Tesseract, YuNet/SFace and the installed U-Net on synthetic documents.
Positive portrait pair shares generated source pixels; this is a functionality
smoke test, not held-out identity accuracy or calibrated risk evaluation.

| Synthetic scenario | Observed score | Category | Outcome |
|---|---:|---|---|
| Genuine-looking mock | 3.25 | null | Incomplete liveness; no false Low label |
| Altered printed DOB | 7.25 | null | One MRZ/VIZ mismatch adds 4 |
| Different synthetic face | 18.25 | null | Cosine 0.4519 below 0.6; adds 15 |
| Mock blacklist | 38.25 | High | Known fictional hit adds 35 |
| Blurred scan | null | null | `needs_rescan`; later layers skipped |

First run including lazy model startup: **8.85 s**. Subsequent non-rescan examples:
**3.43–3.74 s**, with parallel portion **0.95–1.16 s**. Rescan case **0.17 s**.
These are local observations, not a throughput SLA or comparative speedup benchmark.
Concurrency itself is independently tested with a 3-party barrier.

All four readable cases had 79% configured-weight coverage. Missing signals were
duplicate identity, liveness and metadata. Same-face cosine was 0.9299. Genuine
mock still accumulated 3.25 classical points from repeated-feature evidence:
**classical false positives remain**, and the weights/thresholds are hand-set.
Synthetic duplicate-identity adapter separately produced 15 observed points.
Controlled arithmetic fixtures verify Low=0, Medium=15, High=35 with all inputs
supplied; those examples are not measured real-world evidence.

Raw results: `reports/phase4_smoke.json`. Summary: `reports/phase4_summary.md`.

## Limits and next phase

- Fixed-layout synthetic CNN map is exposed for inspection but excluded from L5
  aggregation. No calibrated tamper probability exists yet. Stamp weights/templates
  remain unavailable; configured weights do not manufacture their evidence.
- Liveness stays incomplete even if blinking is observed; uploaded frames have
  no trusted live-capture provenance. Current real pipeline therefore cannot
  produce a fully evidenced Low/Medium category. High can represent known signals
  while overall status stays incomplete. This is intentional.
- Duplicate identity remains restricted to bundled synthetic FAISS examples;
  uploaded passenger faces are not enrolled or searched in a persistent gallery.
- A shared pool bounds parallel CPU tasks to three. Individual layer exceptions
  preserve successful results and produce sanitized failures. There is no global
  hard request deadline/process isolation; native inference is not forcibly killed.
- This localhost prototype has no authentication or deployment hardening yet.
- Next: L6 officer dashboard, append-only hash-chain audit and Docker. UI must show
  score, gaps, experimental labels and reasons together; human decisions remain explicit.
