# Deployment verification

`scripts/verify_deployment.py` local HTTP app ko test karta hai. Yeh automatically
Docker readiness infer nahi karta; container lifecycle commands separately run honge.
Only loopback HTTP targets accepted hain. Python `httpx` backend's dev extra mein hai.

## What the smoke check verifies

- Phase 6 health, installed OCR and served frontend JavaScript.
- Actual synthetic document/reference uploads and MRZ extraction.
- Face-model match and, by default, trained synthetic CNN availability.
- Liveness remains explicitly unverified.
- Audited scan and secondary-inspection decision, each retried with the same UUID.
- Original events stay identical; a saved external sequence/hash checkpoint verifies.

Checkpoint mein request UUIDs, hashes, model availability and timings store hote hain.
Images, extracted identity fields or embeddings nahi. Two synthetic QA events app
history mein append hote hain. Existing checkpoint ke saath `--record` repeat karne
par same request IDs reuse hote hain. Interrupted run ko same command se resume karein;
failed attempt hide karne ke liye checkpoint/audit delete na karein.

## Existing native app

Start backend using README command, then:

```powershell
.\.venv\Scripts\python.exe scripts/verify_deployment.py --record --checkpoint reports/deployment/native_checkpoint.json
# Stop and restart only this project's Uvicorn process, preserving data/audit.db.
.\.venv\Scripts\python.exe scripts/verify_deployment.py --verify --checkpoint reports/deployment/native_checkpoint.json
```

`--verify` is read-only on the API. It verifies old events and the saved anchor against
the restarted service and refreshes the local checkpoint's verification timestamp.
Model checks refer to the recorded run; verification mode does not re-run inference.

## Docker container (once the host engine works)

Use separate port/checkpoint from native app:

```powershell
$env:DEMO_PORT = "8080"
docker compose config --quiet
docker compose up --build -d --wait --wait-timeout 180
docker compose ps
.\.venv\Scripts\python.exe scripts/verify_deployment.py --url http://127.0.0.1:8080 --record --checkpoint reports/deployment/container_checkpoint.json
docker compose up -d --force-recreate --wait --wait-timeout 180
.\.venv\Scripts\python.exe scripts/verify_deployment.py --url http://127.0.0.1:8080 --verify --checkpoint reports/deployment/container_checkpoint.json
```

The Compose named volume retains audit state across recreation; the second check
must observe the original scan/decision hashes. Keep the checkpoint outside that
volume. Existing weights in `models/` are mounted read-only. Full verification expects
face weights, `tamper_unet.pt` + manifest, and the default `WITH_TORCH=1` image.
For an intentional classical-only image built with `WITH_TORCH=0`, add
`--allow-missing-cnn` to both verifier commands and label the result accordingly.

The check has a 180-second per-request timeout to accommodate cold CPU inference.
A passing health endpoint alone does not prove model availability or persistence.
Build context excludes evaluation outputs, PDF renders and browser test artifacts.

## Host blocker observed on 2026-10-04

Docker Desktop is installed and WSL reports default version 2. The engine failed to
start. Docker's `backend.error.json` reports:

```text
initializing Inference manager
remove C:/Users/User/AppData/Local/Docker/run/dockerInference:
The file cannot be accessed by the system.
```

The failing path is a runtime reparse point dated 2026-07-02. A normal Desktop restart
hung despite a 45-second CLI timeout. After stopping the failed Docker processes,
the narrowly scoped attempt to rename that socket to a backup also failed with the
same system access error. No backup rename succeeded. No containers, images, volumes,
WSL distributions or Docker settings were deleted/reset. The failed Docker processes
were stopped; the native app can continue running.

Container build/run remains **unverified** until Docker's host runtime is repaired.
Keep a backup before considering any data-reset option. Official references:
[Desktop restart CLI](https://docs.docker.com/reference/cli/docker/desktop/restart/),
[Docker troubleshooting](https://docs.docker.com/desktop/troubleshoot-and-support/troubleshoot/)
and [backup/restore](https://docs.docker.com/desktop/settings-and-maintenance/backup-and-restore/).
