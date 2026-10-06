# Phase 1 verification — 2026-10-03

**L0 + L1 + L2 implemented aur locally verified.** Scope synthetic development
fixtures hai; held-out evaluation aur real-world accuracy claim nahi hai.

## Checks executed

- `pytest backend/tests -q`: **60 passed**, one upstream Starlette/httpx deprecation warning.
- Ruff lint: all checks passed.
- Ruff formatting: 32 Python files already formatted.
- `pip check`: no broken requirements found.
- Actual Tesseract **5.5.3** OCR executed; no OCR-test skips in this run.
- Windows / Python 3.11 virtual environment; Linux runtime not verified here.

## Eight synthetic scenarios

| Fixture | Observed result |
|---|---|
| Genuine synthetic | 5/5 checks passed; 0 field mismatches |
| DOB altered | 5/5 checks passed; 1 DOB mismatch |
| Composite checksum altered | Composite failed; other 4 checks passed |
| Blurred | `needs_rescan`; OCR and validation skipped |
| Expired | `DOCUMENT_EXPIRED` |
| Mock blacklisted | `MOCK_BLACKLIST_HIT`; 2 prior mock sightings |
| Previously seen | `PREVIOUSLY_SEEN`; 3 prior mock sightings |
| Perspective capture | Geometry corrected, but document-number OCR caused 1 false mismatch and 2 failed checks |

Perspective result baseline ki limitation hai. Checksum fail ko document fraud proof
nahi maana ja sakta; raw OCR/manual inspection important hai.

Six VIZ fields compared per readable sample: name, number, nationality, DOB,
expiry and sex marker. All six matched expected printed values on the seven
non-blurred fixtures. Yeh deliberately small development set hai, accuracy benchmark nahi.

## Measured Phase 1 latency

Latest eight-fixture run: mean **5.59 s**, median **6.78 s**, range **0.20–9.02 s**.
Mean/median mein fast blurred-image quality rejection included hai. Separate clean
demo invocation **5.48 s** tha. Earlier runs faster the; host load aur OCR subprocess
passes timing ko affect karte hain. Few-seconds target abhi consistently achieve nahi hua.

Source measurements: [phase1_smoke.json](phase1_smoke.json).
Full clean sample response, without image payload: [phase1_genuine.json](phase1_genuine.json).

## Next gate

Swagger ya standalone demo se clean/DOB-altered/blurred examples inspect karein.
Next implementation phase L4 face verification and limited liveness hai; synthetic
geometric avatar ko real face-verification accuracy test nahi maana jayega.
