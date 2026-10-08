# Phase 3 — L3 tampering

L3 ab standalone Python function aur `POST /api/v1/tampering/analyze` se run hota
hai. Baseline explainable signals deta hai; separately trained small U-Net spatial
activation map deta hai. `tamper_probability` intentionally `null` hai: available
scores calibrated fraud probabilities nahi hain. Officer decision Phase 5 mein aayega.

## Implemented files

- `backend/app/layers/l3_tampering/classical.py`: EXIF, DCT compression-history
  proxy, ELA, flat-region noise, photo-region comparison, copy-move, font geometry.
- `stamps.py`: color candidates, fictional DEMO template matching, checksum-verified
  one-class YOLOv8 ONNX adapter.
- `network.py`, `learned.py`: 2-level small U-Net, actual PyTorch CPU inference,
  strict state-dict loading, checkpoint SHA-256 verification.
- `analyzer.py`: module orchestration, normalized regions, classical overlay and
  separate CNN heatmap. Original image bytes are used, not L0's re-encoded PNG.
- `backend/app/schemas/tampering.py`, `backend/app/api/tampering.py`: typed contract.
- `synthetic.py`, `scripts/generate_tamper_dataset.py`, `train_tamper_model.py`:
  reproducible generation, source-group splits, training and held-out evaluation.
- `scripts/download_datasets.py`, `prepare_tamper_dataset.py`: bounded downloads
  and explicit image/mask manifest preprocessing.
- `scripts/demo_phase3.py`, `verify_phase3.py`: CLI and synthetic visual smoke test.
- `backend/tests/test_tampering.py`, `test_tamper_data.py`: contract, coordinates,
  null/missing evidence, checksum errors and data-leakage checks.

## Install/run — project root, PowerShell

CPU PyTorch install is approximately 124 MB on this Windows environment, plus
dependencies. Existing `.venv` already has it installed.

```powershell
.\.venv\Scripts\python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m pip install -e "./backend[dev,face,tampering]"
.\.venv\Scripts\python.exe scripts/generate_tamper_dataset.py --bases 100
.\.venv\Scripts\python.exe scripts/train_tamper_model.py --epochs 12
.\.venv\Scripts\python.exe scripts/verify_phase3.py
.\.venv\Scripts\python.exe -m pytest backend/tests -q
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Installed checkpoint: `models/tamper_unet.pt`; digest/provenance:
`models/tamper_unet.json`. Model binaries aur generated datasets Git-ignored hain;
fresh checkout par generation/training rerun karein. This run took **633.5 seconds**
for 12 epochs on CPU; API warm inference training se much faster hai.

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/v1/tampering/analyze -F "document=@data/tampering/00008_photo_replacement.png" -F "photo_region=[0.661458,0.15625,0.276042,0.458333]"
.\.venv\Scripts\python.exe scripts/demo_phase3.py data/tampering/00008_photo_replacement.png --photo-region '[0.661458,0.15625,0.276042,0.458333]' --output reports/local_demo
```

CLI `--output` explicitly image/overlay export karta hai. API processing image ya
EXIF disk par persist nahi karti. Response contains PNG base64; downstream apps
should avoid logging the response images.

Standalone usage:

```python
from pathlib import Path
from app.layers.l3_tampering.analyzer import analyze_tampering

result = analyze_tampering(
    Path("data/tampering/00008_photo_replacement.png").read_bytes(),
    photo_region=(127/192, 30/192, 53/192, 88/192),
)
print(result.data.tamper_probability)  # None; intentionally uncalibrated
for detector in result.data.detectors:
    print(detector.name, detector.status, detector.score)
```

## Contract and image coordinates

Multipart fields: `document` required; `photo_region` optional JSON `[x,y,w,h]`;
`include_cnn` optional `true`/`false`. Unknown fields and invalid regions return
422. File limit 10 MiB, L3 image limit 4 MP, minimum size 32×32. Visual processing
resizes to max dimension 960; original-resolution ELA happens before resizing.
Output coordinates refer to **EXIF-oriented original**, normalized to `[0,1]`.
Regions are axis-aligned bounding boxes, not precise segmentation ground truth.

`data.detectors[]` returns `name`, `status`, nullable `score`, `method`,
`explanation`, `regions`, `metrics`. `status: ok` means processing succeeded.
`suspicion_score` is maximum available classical index; it is **not an approval
or rejection threshold**. Global metadata/DCT signals have no spatial localization.
Classical heatmap is the maximum of localized signals; CNN heatmap is separate.
An empty/small heatmap cannot prove authenticity.

## Actual synthetic CNN results

100 source cards × (clean + 4 attacks) = 500 images. SHA-256 group split produces
375 train / 90 validation / 35 test images; all variants of a card stay together.
Best checkpoint selected by validation BCE loss (epoch 11), not test results.
Test thresholds fixed before evaluation: pixel activation ≥0.5, image flag if
≥2% of pixels pass it. `cnn.score` is top-1% activation mean, **not** this image
decision; use the explicitly named `synthetic_flag`/`predicted_fraction` metrics.

| Held-out synthetic measure | Result |
|---|---:|
| Precision | 0.9600 |
| Recall | 0.8571 |
| F1 | 0.9057 |
| TN / FP / FN / TP | 6 / 1 / 4 / 24 |
| Clean false positives | 1 / 7 |

| Attack | Flagged / count | Mean localization IoU |
|---|---:|---:|
| Copy-move | 3 / 7 | 0.2401 |
| Photo replacement | 7 / 7 | 0.7275 |
| Stamp edit | 7 / 7 | 0.6261 |
| Text replacement | 7 / 7 | 0.5029 |

**Scope:** fixed-layout, procedural cartoon portraits, same attack generator and
layout across splits. Only seven source cards in test. The network can learn
layout/edit artifacts; these numbers are not real-document performance or a
public-dataset benchmark. Copy-move remains weak. The masks label edited regions,
not every JPEG pixel changed by later recompression. Do not tune thresholds on
this test set for a future reported benchmark.

Raw run: `reports/phase3_training.json`; actual inference smoke:
`reports/phase3_smoke.json`; visually checked comparison:
`reports/phase3_visuals/comparison.png` (input / ground truth / classical / CNN).

## Detector limits and honest gaps

- Metadata: editing tags and reversed dates are weak signals; missing EXIF gives
  unknown. Raw EXIF values are not returned. A forged tag can evade these checks.
- Double-JPEG: DCT histogram periodicity **proxy**, not a validated double-JPEG
  classifier. Only JPEG sources are assessed; resizing/rotation/graphics confound it.
- ELA: fixed-quality recompression residual. PNG/WebP compression history is
  unavailable, and legitimate text/photos can have high ELA residuals.
- Noise: sharp-edge mask removes much printed-text energy; regions with poor
  flat-pixel support are excluded. Printing/scanning and content still confound it.
- Photo: caller supplies the full portrait region. Its noise/recompression
  statistics are compared to a nearby ring. This is not automatic photo detection
  or proof of replacement; face bounding box and portrait region differ.
- Copy-move uses ORB displacement consensus, not a learned forgery model. Small
  edited text, featureless pasted regions and rescaled copies may be missed.
- Font check uses row/component heights. Mixed scripts/headings create false positives.
- Stamp: **no stamp-trained YOLO weights or verified issuer templates bundled**.
  Default YOLO status stays `unavailable`; fictional template similarity stays
  separate from authenticity score. Optional model must be a one-class YOLOv8
  640px ONNX export, raw `[1,5,N]`, `nms=False`, `dynamic=False`. Configure
  `STAMP_YOLO_PATH` and `STAMP_YOLO_SHA256`. Adapter decoding/NMS is tested; real
  YOLO stamp inference is not verified in this phase. COCO weights are unsuitable.
- CNN model trained in this phase is experimental synthetic-only, not calibrated.
  No issuer-authenticity certification, automatic border decision or real-person data.

## Public datasets and preparation

Large archives were **not** downloaded or used for training. Downloader tested
with the 592-byte MIDV-DM license; publisher MD5 verified and SHA-256 recorded.
Default download cap 256 MiB stops multi-GB files before transfer. It never extracts
archives or executes dataset content.

```powershell
.\.venv\Scripts\python.exe scripts/download_datasets.py midv2020
.\.venv\Scripts\python.exe scripts/download_datasets.py midvdm
.\.venv\Scripts\python.exe scripts/download_datasets.py idnet
.\.venv\Scripts\python.exe scripts/download_datasets.py doctamper
```

- [MIDV-2020 author host](https://l3i-share.univ-lr.fr/MIDV2020/midv2020.html): access
  form/license acceptance for hosted 124 GB collection. Base OCR dataset does not
  supply forged-region labels automatically.
- [MIDV-DM pinned Zenodo record](https://zenodo.org/records/18861850): 94.6 GB archive,
  `images/<attack>/<document-type>/...`, corresponding `masks` and `annotations`.
  License CC BY-SA 2.5; preserve MIDV-2020 and Generated Photos attribution. Group
  original/manipulated/donor-linked images together using author annotations.
- [IDNet pinned part 3](https://zenodo.org/records/13852734): provided sample download
  catalog covers ESP/FIN archives. Whole collection roughly 400 GB. Requires
  explicit image/mask mapping; do not infer ground truth from filename alone.
- [DocTamper author repository](https://github.com/qcf-568/DocTamper): authorization
  application and research/noncommercial conditions; use author's download/export
  instructions for authorized LMDB images and masks. No access bypass scripted.

After authorized extraction/export, create a JSON list with explicit mappings:

```json
[
  {"image":"images/edited/demo1.png", "mask":"masks/edited/demo1.png",
   "group":"dataset:source-and-donor-connected-group-001", "attack":"text_replacement",
   "source":"midvdm", "split":"train"},
  {"image":"images/clean/demo2.png", "mask":null, "verified_clean":true,
   "group":"dataset:document-002", "attack":"clean", "source":"midv2020", "split":"val"}
]
```

```powershell
.\.venv\Scripts\python.exe scripts/prepare_tamper_dataset.py --source datasets/raw/authorized --manifest datasets/raw/authorized/pairs.json --output datasets/processed/experiment
```

This is a shared manifest preprocessor, **not an unverified automatic converter
for every dataset release**. It validates relative paths, mask/image dimensions,
explicit clean labels, duplicate decoded pixels and source-group split leakage;
resizes masks with nearest-neighbor and preserves source digest. EXIF-oriented
inputs must have image and mask normalized together beforehand. Choose a fresh
output directory on a failed import; no usable manifest is written on failure.
Use dataset-defined official splits when available; donor-linked groups need
curation before import. The shipped training recipe and checkpoint are scoped to
`procedural-synthetic-v1`; public-dataset adaptation/evaluation remains future work.

## Before Phase 4

Run tests, inspect clean and altered heatmaps side by side, and verify missing-model
and PNG compression signals remain null/unavailable. Risk integration must keep
missing evidence distinct from low risk, and keep synthetic CNN evidence marked
experimental. L2/L3/L4 parallel orchestration and L5 weighted risk are next phase.

Sources: [PyTorch CPU installation](https://pytorch.org/get-started/locally/),
[Ultralytics ONNX export](https://docs.ultralytics.com/modes/export/).
