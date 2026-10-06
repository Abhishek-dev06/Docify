# Phase 5 verification — 2026-10-03

L6 React dashboard + SQLite audit local Windows runtime mein implemented aur verified
hain. Docker files delivered hain; container runtime verification host engine par blocked hai.

| Check | Observed result |
|---|---|
| Complete Python regression suite | **211 passed**, including **19 new audit tests** |
| Frontend unit tests | **7 passed** across 2 files |
| TypeScript + Vite production build | Passed; JS 254.14 kB / gzip 79.41 kB |
| Real Edge browser workflow | **1 passed**, test 33.7 s / runner 43.1 s |
| Mobile 390 px | Full workflow reached mobile screen; no horizontal overflow |
| Python dependency consistency | `pip check`: no broken requirements |
| npm dependency audit after Vitest update | 0 reported vulnerabilities at install time |
| Compose configuration | `docker compose config --quiet`: passed |
| Docker image build / Linux runtime | **Not verified**: Docker Desktop Linux engine named pipe unavailable |

Browser test uses actual local API, actual OCR/face/tampering inference and fictional
document/images. It loads a sample, analyzes, opens classical tamper overlay, records
Secondary inspection with a note, searches history, reloads metadata without images,
verifies the chain, and opens mobile intake. No mocked network responses in this test.
Unit/API tests use isolated temporary databases; no real personal data was used.

## Timing and failures preserved

First browser attempt's 90-second report wait expired; scan completed at **92.22 s**.
After server restart, another cold scan took **123.83 s**; functional desktop steps
passed but mobile test failed due a non-exact selector matching both file input and
remove button. Selector fixed to exact match. Final warm run completed with
**22.50 s server pipeline time**, 33.7 s complete browser workflow. These are single
observations on a loaded development laptop, not a benchmark or a promised SLA.
Few-seconds latency target is **not demonstrated by Phase 5's browser run**.
Phase 6 evaluation should measure cold/warm latency under controlled load.

Each observed genuine-looking synthetic sample scored **3.25 policy points**,
category **null / Incomplete evidence**, face cosine about **0.9299**, and evidence
coverage **79%**. Liveness remains missing; this is not verified authenticity.

## Audit evidence

After browser verification the default demo database held **5 events**: 3 scan events
and 2 secondary-inspection decisions. The first timed-out scan remains pending;
entries were not erased after test failures. Chain verification returned `valid: true`.

Observed head at sequence 5:
`c42c07e8158888cbe9ef682219564de68dbac80514f26a695b135fdd8466a18d`

Further local reviews will append events and change the head. This file is a local
verification artifact, not an independently protected external anchor.

Audit tests cover hashes, revisions, duplicate retries, changed-payload key conflicts,
concurrent appends, optimistic decision conflicts, approval acknowledgement, SQL
UPDATE/DELETE rejection, content/tail/head tampering, external anchors, history filters,
metadata minimization, and API validation. A database owner can still rewrite the
entire chain/head; exported checkpoints need an independent trusted location.

## Screenshots and review notes

- [Upload workspace](phase5_dashboard.png)
- [Evidence + officer review](phase5_review.png)
- [Audit verification](phase5_audit.png)
- [Mobile intake](phase5_mobile.png)

Dashboard labels absent evidence explicitly, separates synthetic CNN from classical
overlay, and preserves raw/corrected OCR for current-session review. History stores
scores and review metadata only; full revision events are exposed in the detail API.
Officer labels are unverified local labels. SQLite is tested; PostgreSQL runtime is not.
There is no production authentication or automatic retention lifecycle.

Run guide and implementation paths: [Phase 5](../docs/phase5.md).
Phase 6 evaluation/presentation deliverables have not started.
