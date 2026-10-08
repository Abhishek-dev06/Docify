# Phase 4 verification

L5 weighted policy aur L0→L1→parallel L2/L3/L4→L5 pipeline implemented.

- 192 tests passed, no skips, 33.58 seconds. Ruff clean; pip check clean.
- One existing upstream Starlette/httpx deprecation warning remains.
- New tests verify policy validation, exact contributions, inclusive thresholds,
  missing evidence, mathematical score bounds, actual three-way concurrency,
  rescan gating, stage failure isolation, OCR-only portrait masking and real-model HTTP.
- No new dependency; existing Tesseract, OpenCV YuNet/SFace, PyTorch reused.
- API: GET `/api/v1/risk/policy`, POST `/api/v1/risk/score`,
  POST `/api/v1/screening/analyze`. Health reports Phase 4/L0–L5.

| Actual synthetic pipeline run | Score | Category | Total ms |
|---|---:|---|---:|
| Genuine-looking mock | 3.25 | null (incomplete) | 8849.94 |
| Altered DOB | 7.25 | null (incomplete) | 3743.37 |
| Wrong synthetic face | 18.25 | null (incomplete) | 3526.75 |
| Mock blacklist | 38.25 | High | 3434.96 |
| Blurred scan | null | null; needs_rescan | 173.28 |

First scan includes lazy model startup; warm non-rescan examples are 3.43–3.74 s.
Parallel stage is 0.95–1.16 s warm. This is a local functionality smoke run,
not a throughput benchmark, speedup claim or risk accuracy evaluation.

All readable examples have 79% configured-weight coverage: duplicate identity,
liveness and metadata remain missing/incomplete. Coverage is availability, not
accuracy. Same-source synthetic face cosine 0.9299; different face 0.4519 at a
development threshold of 0.6. Positive pair shares portrait source pixels.

Genuine example's 3.25 points arise from classical repeated-feature evidence;
false positives remain. DOB adds 4, wrong face adds 15, mock blacklist adds 35.
The initial integration missed MRZ/VIZ evidence when the portrait confused OCR.
Observed-row retry and correctly transformed portrait exclusion fixed these
samples while preserving raw OCR readings and unmasked L3/L4 evidence.

Controlled arithmetic cases separately verify Low=0, Medium=15, High=35 with
all inputs explicitly supplied. Bundled synthetic duplicate-identity evidence
adds 15 observed points. These are not empirical accuracy measurements.

Policy sums to 100 and is versioned plus hashed. Missing required evidence blocks
Low/Medium categories; known High remains visible with incomplete status. Scores
are uncalibrated indices, never fraud probabilities or automatic officer decisions.
No positive live-person certification, real issuer stamp verification, persistent
face gallery or authenticated officer interface is claimed. The synthetic CNN
heatmap is inspectable but excluded from risk aggregation.

API images, fields and embeddings remain transient. CLI report export is explicit
and image-free. Shared worker pool is bounded to three, with no hard global timeout.
Audit storage, dashboard and Docker remain Phase 5.

Files: `reports/phase4_smoke.json`, `config/risk_weights.yaml`, `docs/phase4.md`.
