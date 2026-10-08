# Online deployment: Vercel frontend + Docker backend

## Current failure

`https://docify-beryl.vercel.app/api/v1/health` responds, but reports
`ocr_available: false`. The deployed serverless filesystem is read-only except for a
temporary directory, while the audit database originally targeted the repository's
`data/` directory. Synthetic fixture generation also assumed an operating-system font.
Those two paths caused HTTP 500 responses. A serverless deployment also cannot provide
durable SQLite history, and it does not contain the Tesseract system binary.

The code now uses a writable temporary database on Vercel, falls back to Pillow's
bundled font, reports deployment capabilities in `/api/v1/health`, supports a separate
browser API origin and includes model weights in standalone Docker images. This makes
the Vercel backend usable as a degraded preview: OCR remains unavailable and history
can reset at any cold start.

For the complete demo, keep Vercel for the React UI and deploy the supplied Dockerfile
to a container host. The Docker image installs Tesseract and serves the FastAPI API.

## Step 1: deploy the backend on Render

1. Push the fixed repository to GitHub.
2. In Render, choose **New > Blueprint**, connect `Abhishek-dev06/Docify`, and apply
   `render.yaml`.
3. Wait for the service health check to pass. Open:

   `https://YOUR-SERVICE.onrender.com/api/v1/health`

4. Confirm `status` is `ok` and `ocr_available` is `true`. The initial Blueprint uses
   `WITH_TORCH=0`, so the trained CNN is deliberately unavailable; classical tamper,
   OCR and other available layers still run. Change it to `1` only on a host with
   enough build storage and memory for CPU PyTorch.
5. The initial filesystem is ephemeral and health truthfully reports
   `audit_persistent: false`. For durable review history, attach a persistent disk at
   `/app/data`, then set `AUDIT_PERSISTENT=true` and redeploy. Do not call temporary
   serverless SQLite history permanent evidence.

## Step 2: connect the Vercel frontend

1. In the Vercel project, set **Root Directory** to `frontend`.
2. Add this Production/Preview environment variable:

   `VITE_API_BASE_URL=https://YOUR-SERVICE.onrender.com`

3. Redeploy. Vite reads `VITE_` variables at build time, so changing the variable
   without redeploying does not update the JavaScript bundle.
4. Open the browser Network tab. `/api/v1/health`, fixture and scan requests must go to
   the backend host, not `docify-beryl.vercel.app/api/...`.

The backend already permits `https://docify-beryl.vercel.app` through
`CORS_ALLOWED_ORIGINS`. If the Vercel domain changes, update that Render environment
variable to the exact HTTPS origin and redeploy the backend. Do not use `*` for this
review application.

## Step 3: acceptance check

1. Load **Genuine-looking mock**. Both fictional images must appear.
2. Analyze it. The response must show OCR evidence rather than a request-failed banner.
3. Record **Secondary inspection**, open Review history, and verify Audit integrity.
4. Restart/redeploy the backend and check history again. This must pass only after a
   persistent disk is attached.
5. Upload only fictional/authorized test documents. Real ID images are sensitive;
   the prototype has no production authentication or verified liveness.

## Local fallback

The complete system can be demonstrated locally without cloud setup:

```powershell
.\.venv\Scripts\python.exe scripts/bootstrap.py
Set-Location frontend
npm ci
npm run build
Set-Location ..
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`. This path uses the bundled Windows OCR runtime and the
project-local databases.
