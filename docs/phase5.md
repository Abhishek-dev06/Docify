# Phase 5 — L6 dashboard, audit trail, Docker

Is phase mein React/Vite/Tailwind dashboard actual FastAPI pipeline ko call karta hai.
Synthetic sample load karo, evidence inspect karo, phir human decision record karo.
Model approval/rejection automatically nahi karta. Liveness incomplete hone par UI
`Incomplete evidence` dikhata hai; score ko authenticity probability nahi bolta.

## Run locally (Windows PowerShell)

Existing Phase 1–4 workspace mein Python dependencies, OCR aur model weights ready hain.
Fresh checkout ke liye pehle Phase 1–3 setup run karein. Node 22.18+ use karein.

```powershell
# Project root
.\.venv\Scripts\python.exe -m pip install -e "./backend[dev,face]"
.\.venv\Scripts\python.exe scripts/download_face_models.py
.\.venv\Scripts\python.exe scripts/bootstrap.py
cd frontend
npm ci
npm run build
cd ..
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open [dashboard](http://127.0.0.1:8000) or [Swagger](http://127.0.0.1:8000/docs).
Built frontend same FastAPI origin se serve hota hai. Development mein second terminal
se `cd frontend` then `npm run dev`; Vite `/api` requests localhost:8000 ko proxy karta hai.
Optional synthetic CNN ke liye Phase 3 trained weights + CPU PyTorch chahiye;
unavailable CNN ko UI unavailable rakhta hai, fabricated output nahi deta.

## Quick demo aur expected behavior

1. Demo officer label set karein; yeh authenticated identity nahi hai.
2. **Load synthetic sample → Analyze & record**. First inference slower ho sakta hai.
3. MRZ/VIZ raw/corrected values, mismatches, classical overlay, experimental CNN map,
   cosine similarity aur risk contributions inspect karein.
4. **Secondary inspection**, minimum eight-character review note, **Record decision**.
   Incomplete evidence par Approve ke liye explicit acknowledgement mandatory hai.
5. **Review history** mein scan ID, document hash ya scan/latest-decision officer search
   karein. Decision filter aur pagination available hain. Open se metadata reload hota hai;
   images/identity values retain nahi hote.
6. **Audit integrity → Verify chain → Export checkpoint**. Checkpoint ko database se
   alag trusted location mein rakhein. Full decision revision history detail API mein hai.

Bundled scenarios: genuine-looking mock, DOB altered, wrong face, mock blacklist, blur.
All fictional UTO documents/generated portraits hain. Example genuine scan in this
environment: 3.25 policy points, category null, missing liveness; exact score is
development evidence, real-world accuracy metric nahi hai.

## Audit works kaise karta hai

`backend/app/storage/audit.py` mein standalone `AuditStore` methods `record_scan`,
`decide`, `history`, `get_scan`, `verify` available hain. Every event mein sequential
number, UUID, UTC timestamp, document SHA-256, officer label, payload, previous hash
aur SHA-256 content hash hota hai. Scan aur decision separate linked events hain.

SQLite `BEGIN IMMEDIATE` writer ko serialize karta hai; event + chain head ek atomic
transaction mein save hote hain. UPDATE/DELETE triggers accidental mutation block
karte hain. Every read/write chain verify karta hai. Changed event, missing tail or
head mismatch par history/writes block hote hain. Decision's expected latest hash
stale concurrent review ko HTTP 409 deta hai. UUID idempotency keys network retry ko
duplicate audit entries banane se rokti hain; changed content with same key 409 hai.

Database owner triggers hata kar poori chain/head rewrite kar sakta hai. Hash chain
tamper-evident hai, tamper-proof nahi. Exported trusted checkpoint validate karein:
`GET /api/v1/audit/verify?anchor_seq=N&anchor_hash=HASH`.
Checkpoint zero events par future rewrite detection provide nahi karta.

SQLAlchemy schema aur row locks PostgreSQL ke liye structured hain, lekin PostgreSQL
runtime/permissions/append-only triggers is session mein verified nahi hain. SQLite
is tested demo backend. Full chain scan O(n) hai; high-throughput production storage
ke liye external anchoring, indexing and incremental verification design chahiye.

## API

| Route | Input / output |
|---|---|
| `POST /api/v1/scans/analyze` | Same multipart fields as `/screening/analyze`; required `X-Officer-ID` + UUID `Idempotency-Key`; returns `{analysis, scan_event, replayed}` |
| `GET /api/v1/scans` | `q`, `decision`, `limit` (1–100), `offset`; returns paginated scan/latest-decision metadata |
| `GET /api/v1/scans/{scan_id}` | All immutable events for the scan plus latest event hash |
| `POST /api/v1/scans/{scan_id}/decisions` | `X-Officer-ID`, JSON below; returns appended event |
| `GET /api/v1/audit/verify` | Optional paired trusted anchor parameters; validity + head |
| `GET /api/v1/demo/fixtures/{scenario}/{kind}` | In-memory synthetic `document` or `live` PNG |

```json
{
  "decision": "secondary_inspection",
  "note": "Synthetic review: liveness evidence incomplete.",
  "expected_event_hash": "<latest_event_hash from scan/detail response>",
  "request_id": "<new UUID; reuse unchanged on retry>",
  "acknowledge_incomplete": false
}
```

Decision choices `approve`, `secondary_inspection`, `reject`. Notes 8–500 characters.
Actor labels 3–64 letters/digits/underscore/hyphen. Successful scan retry returns
`analysis: null` because images/identity fields are not stored. Old transient routes
remain available and do not append audit records. Privacy details: [privacy.md](privacy.md).

## Docker

Multi-stage Dockerfile builds React and installs Python, Tesseract, CPU face/optional
PyTorch dependencies. Runtime is non-root, one Uvicorn worker, read-only root filesystem,
writable `/tmp` and named database volume, read-only host model mount, localhost port.

```powershell
docker compose config --quiet
docker compose up --build -d
docker compose ps
docker compose logs --tail 50 app
# If native server is already using port 8000:
$env:DEMO_PORT = "8080"
docker compose up --build -d
```

`WITH_TORCH=0` environment variable before build skips optional CNN dependency;
default is `1`. Download face weights into `models/` before launching. Synthetic CNN
weights stay in that same host directory; large weights are excluded from build context.
`docker compose down` stops containers and preserves audit volume; do not erase the
volume to hide demonstration events. Dependencies need network on the first build.

**Verification limit:** Compose configuration passed, but installed Docker Desktop's
Linux engine did not become usable: `dockerDesktopLinuxEngine` named pipe unavailable.
Container image build, Linux runtime and health check are therefore unverified.
Local Windows runtime is the verified path; Docker engine availability must be fixed
on the host before container smoke testing. No OS virtualization settings were changed.

## Tests and files

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -q
.\.venv\Scripts\python.exe -m ruff check backend scripts --config backend/pyproject.toml
cd frontend
npm test
npm run build
# Start the built app on :8000 first; installed Microsoft Edge is used:
.\node_modules\.bin\playwright.cmd test
```

Core files: `frontend/src/App.tsx`, `Report.tsx`, `styles.css`, `api.ts`, `types.ts`;
backend `api/audit.py`, `api/demo.py`, `schemas/audit.py`, `storage/audit.py`;
startup `scripts/bootstrap.py`; packaging `Dockerfile`, `compose.yaml`, `.dockerignore`.
211 backend tests passed, including 19 audit tests. React tests cover incomplete
evidence, explicit approval acknowledgement, history minimization and safe retries.
Measured browser result and screenshots: [verification report](../reports/phase5_summary.md).

Before Phase 6: open a sample, inspect mismatched fields/overlay, record a decision,
reload metadata history and verify/export chain. Phase 6 will add evaluation and
presentation/demo deliverables; no real-world accuracy is claimed here.
