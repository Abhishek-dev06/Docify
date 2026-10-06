# Install an isolated Tesseract runtime without changing the system PATH.
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$toolRoot = Join-Path $projectRoot '.tools'
New-Item -ItemType Directory -Path $toolRoot -Force | Out-Null
$mamba = Join-Path $toolRoot 'micromamba.exe'
if (-not (Test-Path -LiteralPath $mamba)) {
    Invoke-WebRequest -Uri 'https://github.com/mamba-org/micromamba-releases/releases/latest/download/micromamba-win-64' -OutFile $mamba
}
& $mamba create --yes --no-rc --root-prefix (Join-Path $toolRoot 'mamba') --prefix (Join-Path $toolRoot 'ocr') --override-channels --channel conda-forge 'tesseract>=5.5,<6'
if ($LASTEXITCODE -ne 0) { throw 'Tesseract environment installation failed.' }
& (Join-Path $toolRoot 'ocr\Library\bin\tesseract.exe') --version
if ($LASTEXITCODE -ne 0) { throw 'Tesseract runtime verification failed.' }
