# Deployment follow-up — 2026-10-04

**Native deployment verified. Docker image build/runtime remains blocked by the host.**

## Completed

- Added `scripts/verify_deployment.py` with real HTTP checks and a saved audit anchor.
- Verified Phase 6 health, Tesseract and the served dashboard JavaScript.
- Actual synthetic scan extracted MRZ, matched the reference face, and ran the CNN.
- Liveness remained unverified, risk score 3.25 and category null.
- Cold pipeline observation: 26.31 seconds, not a controlled benchmark.
- Repeated scan and decision requests returned identical events, with metadata-only
  scan replay. The checker retains request IDs to resume uncertain writes safely.
- Restarted this project's Uvicorn process (PID 12176 to PID 16332).
- Re-verified the saved sequence-8 anchor and both original events after restart.
  Audit head remained sequence 8. Other existing demonstration entries were preserved.
- Ruff checks passed for the new checker; Compose configuration validation passed.
- Build context now excludes generated PDFs, scratch renders and browser artifacts.

Raw checkpoint: [native_checkpoint.json](native_checkpoint.json). It contains synthetic
QA IDs, hashes, model-check results and verification times, with no images or OCR values.
This project-local checkpoint demonstrates anchoring; it is not independently protected
against an owner who can rewrite both the database and workspace.

## Docker diagnosis and recovery attempts

Docker Desktop was initially stopped. Starting it produced a backend error while
initializing the inference manager: Docker could not access/remove its
`AppData/Local/Docker/run/dockerInference` runtime socket. The file is an old reparse
point dated 2026-07-02. WSL reports default distribution Ubuntu and default version 2.

A bounded engine query timed out. The supported normal Desktop restart also hung,
despite its requested timeout. After stopping the failed Docker processes, a narrow
attempt to rename only the stale socket to a backup failed with the same Windows
system access error. No rename succeeded. No Docker data reset, WSL unregister,
container/image/volume deletion or OS virtualization change was performed.

The Docker host needs repair before container verification can proceed. App source
changes cannot fix this runtime file-system problem. Container build, Linux model
loading and persistence across container recreation are explicitly **not verified**.

Exact commands for native and container checks, including a separate port/checkpoint:
[deployment guide](../../docs/deployment_verification.md).
