# Phase 2 — L4 face verification and liveness evidence

**Implemented:** YuNet detection → five-landmark alignment → SFace embedding →
cosine comparison. Inference CPU par OpenCV DNN se hoti hai. Ek document portrait
aur ek supplied live/reference image ka one-to-one comparison hai; match identity
authenticity ya live camera capture prove nahi karta.

## Model choice

YuNet 2023mar + SFace 2021dec existing OpenCV environment mein run hote hain.
Is baseline ke liye extra InsightFace/ONNX Runtime/native build dependencies nahi
chahiye. InsightFace adapter future mein same `FaceEngine` interface implement kar
sakta hai. PyTorch abhi face inference ke liye required nahi; trained tampering
model Phase 3 ka scope hai.

[OpenCV tutorial](https://docs.opencv.org/4.x/d0/dd4/tutorial_dnn_face.html) mein
YuNet/SFace APIs aur LFW cosine reference `0.363` documented hai. Humne is reference
ko initially try kiya: generated different-face pair ka cosine ~0.456 tha, jisse
false match hua. Default **0.60** ab synthetic development policy hai. Yeh threshold
isi small demo ko dekhkar choose hua hai, held-out calibration nahi. Real deployment
ke liye representative consented validation set aur FAR/FRR analysis required hain.

`threshold_calibrated=false` har response mein rahega. Request threshold explicitly
override ho sakta hai; response `threshold_source=request_override` dikhaega.
Threshold badalne se model accuracy prove nahi hoti.

[InsightFace license terms](https://github.com/deepinsight/insightface/blob/master/server/LICENSING.md)
pretrained packages ke non-commercial research scope ko explain karte hain. Chosen
OpenCV Zoo model licenses local `models/yunet-LICENSE.txt` aur `models/sface-LICENSE.txt`
mein retained hain. Model manifest expected byte sizes aur SHA-256 digests pin karta
hai. Download mismatch par existing file overwrite nahi hoti; loader tampered file
ko inference ke pehle reject karta hai.

## Install and run

Project root, existing Phase 1 virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -e "./backend[dev,face]"
.\.venv\Scripts\python.exe scripts/download_face_models.py
.\.venv\Scripts\python.exe scripts/generate_face_fixtures.py
.\.venv\Scripts\python.exe scripts/demo_phase2.py data/synthetic_faces/a_document.png data/synthetic_faces/a_live.png
.\.venv\Scripts\python.exe scripts/verify_phase2.py
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Model download ~39 MB hai. `FACE_MODEL_DIR` se model folder override kar sakte hain.
FAISS optional extra unavailable ho to verification still works; synthetic-index
endpoint explicit `unavailable` return karta hai. Actual model tests installed
weights ke saath run karein; missing models par tests marked skip honge.

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -q
.\.venv\Scripts\python.exe -m ruff check backend scripts --config backend/pyproject.toml
```

## API and standalone functions

| Endpoint | Input | Python function |
|---|---|---|
| `GET /api/v1/faces/status` | None | `get_engine()` integrity/load check |
| `POST /api/v1/faces/detect` | Multipart `image` | `detect_faces(image)` |
| `POST /api/v1/faces/verify` | Multipart `document`, `live`, optional `threshold` | `verify_faces(document, live, threshold)` |
| `POST /api/v1/faces/liveness` | Repeated multipart `frames`, JSON-string `timestamps_ms` for sequences | `evaluate_liveness(images, timestamps_ms)` |
| `POST /api/v1/demo/identities/check` | Synthetic identity claim JSON | `check_synthetic_identity(request)` |

All functions `app.layers.l4_face` modules mein hain. Image arrays uint8 OpenCV BGR
format mein honi chahiye. Exact JSON schemas `/openapi.json` mein generated hain.

```powershell
curl.exe -X POST http://127.0.0.1:8000/api/v1/faces/verify -F "document=@data/synthetic_faces/a_document.png" -F "live=@data/synthetic_faces/a_live.png"
curl.exe -X POST http://127.0.0.1:8000/api/v1/faces/liveness -F "frames=@data/synthetic_faces/a_live.png"
```

Verification response mein face counts, normalized boxes/landmarks, quality reasons,
cosine similarity, threshold, match boolean aur model digest milte hain. Embeddings
JSON response mein nahi milti. `match=null` means evidence/model unavailable;
`match=false` means valid comparison threshold se neeche tha. `status=ok` execution
status hai. Liveness independent evidence hai; `liveness_verified` default false hai.

No-face, multiple-face, clipped face, blur ya poor illumination par comparison
abstain karta hai. Ghost portraits/multiple printed faces bhi multiple-face finding
de sakte hain; module silently first/largest face choose nahi karta. Thresholds
`config/face_thresholds.yaml` mein configurable hain.

## Liveness baseline ka actual meaning

- Texture contrast aur frequency-domain periodicity possible flat/printed/display
  artifacts flag karte hain. `spoof_indicator_score` arbitrary heuristic index hai,
  probability nahi. Lighting, compression aur natural texture false alarms de sakte hain.
- Five or more frames mein Haar eye detection ka open/open/zero/open/open pattern
  blink candidate ban sakta hai. Missing eye detection actual eyelid closure prove
  nahi karta. Face similarity continuity, quality aur timing checks apply hote hain.
- Identical repeated frames temporal evidence provide nahi karti aur flag hoti hain.
- Uploaded sequences trusted camera capture nahi hain; replay mein blink ho sakta hai.
  Isliye `liveness_score=null`, `review_required=true`, verdict `inconclusive` ya
  `suspicious` hota hai. Koi `live/pass` output implemented nahi hai.

Sequence maximum 12 frames, 12 megapixels total, timestamps strictly increasing within
0–20000 ms. Maximum gap 500 ms; candidate closure 60–500 ms. JSON timestamps example:
`[0,100,200,300,400]`. Multipart total 20 MiB plus bounded form overhead, per-image
10 MiB. Frames memory mein process hoti hain; image/temp file persistence nahi.

## Synthetic FAISS identity demo

Index sirf bundled generated portraits `synthetic_a` and `synthetic_b` se runtime
mein build hota hai. API external embeddings, uploaded enrollment ya arbitrary
gallery IDs accept nahi karti. Canonical fictional claims:

| Sample | Name | Document |
|---|---|---|
| synthetic_a | SYNTHETIC ALPHA | DEMO-A001 |
| synthetic_b | SYNTHETIC BETA | DEMO-B001 |

```json
{
  "sample_id": "synthetic_a",
  "claimed_name": "SYNTHETIC ALIAS",
  "document_number": "DEMO-A002"
}
```

Is request mein fixture embedding same hai, claim different; duplicate-rule flag
expected hai. FAISS normalized vectors par inner-product search karta hai. Index
memory-only hai aur request ke baad retain nahi hota. Yeh alias-rule demonstration
hai, independently observed repeated traveler detection ya biometric benchmark nahi.

## What is verified before Phase 3

Actual model inference on generated portraits, same-source transformed positive pair,
different synthetic face, no-face/multiple-face/blur abstention, repeated frames,
synthetic alias rules, checksum failure, concurrent model calls, request limits and
memory-only uploads test hote hain. Blink state machine ke tests synthetic observations
use karte hain; real blink or spoof-detection accuracy measure nahi karte.

Positive image pair same generated source se derived hai; isliye easy smoke case hai.
FAR/FRR/ROC numbers report nahi hote. `reports/phase2_smoke.json` original 0.363-threshold
false match bhi preserve karta hai. Phase 1 endpoints retained hain; full concurrent
L2/L3/L4 orchestration L3/L5 integration ke baad complete hogi.

Optional e-Passport support abhi `chip_interface.py` mein typed interface only hai.
SOD signature/trust-chain verification aur DG1/DG2 hash checking implemented nahi;
no chip-authentication success response ya NFC hardware support claim hai.
