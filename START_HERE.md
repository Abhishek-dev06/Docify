# Complete project bundle / Start here

All six implementation phases are included: source/tests, trained synthetic CNN,
YuNet/SFace weights and licenses, generated fictional data, evaluation plots/reports,
dashboard build, audit snapshots, Docker configuration, demo script, PDF and PPT outline.
The Windows OCR runtime is included under .tools/ocr. No model retraining is required.

Extract the cybersicurity folder to D:/Projects/cybersicurity. The ZIP is not a
standalone executable. Install Python 3.11 and Node/npm, then recreate dependencies.
The package versions at packaging time are in requirements-windows-py311.txt.
Internet is needed for package installation. This archive does not include .venv,
node_modules, downloaded package caches, git metadata, private .env files, scratch
files or the computer-wide storage audit. No original project files were deleted.

## Windows PowerShell setup (run each command only after the previous succeeds)

```powershell
Set-Location 'D:\Projects\cybersicurity'
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu -r requirements-windows-py311.txt
.\.venv\Scripts\python.exe -m pip install --no-deps -e ./backend
.\.venv\Scripts\python.exe -m pip check
.\.tools\ocr\Library\bin\tesseract.exe --version
Set-Location frontend
npm ci --cache D:\DevCaches\npm
npm run build
Set-Location ..
.\.venv\Scripts\python.exe scripts/bootstrap.py
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000 and load a synthetic sample. The OCR runtime has not been
tested after extraction at the destination. If it fails, preserve the bundle and
recreate .tools/ocr with scripts/install_ocr_windows.ps1, following README.md.
If an old .env or shell override points to C:, update it before running the new copy.

## Verification and limits

At the source workspace: 217 backend tests and 7 frontend tests passed; the native
browser workflow and audit persistence were verified in earlier phases. These are
historical test results, not new tests of this extracted archive. Package CRC/SHA-256
and the included SQLite snapshot integrity are checked when this ZIP is created.
Archive file hashes are listed in PACKAGE_MANIFEST.json; it is an integrity manifest,
not a signed authenticity guarantee.

Docker build steps ran, but image unpack failed after C: filled up. Container runtime
and container-recreation persistence remain unverified. Moving/extracting the project
alone does not move Docker's virtual disk; use Docker Desktop storage settings.
Older phase reports describe the earlier engine blocker; this note records the later
disk-full attempt. Liveness is still unverified; evaluation metrics are synthetic.

Database files are consistent SQLite backup snapshots made during packaging; database
sidecars are excluded. The synthetic demo audit history is included. Imported source
files and the original databases were not modified. Check the demo locally before
removing any source copy; the original workspace is in OneDrive.
