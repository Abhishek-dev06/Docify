# Phase 3 verification

- Implemented L3 classical evidence + heatmap, independent trained tiny U-Net,
  typed REST endpoint, standalone functions, synthetic training and data tooling.
- CPU training: 12 epochs, 633.53 seconds, PyTorch 2.14.1+cpu, seed 310.
- 500 procedural images / 100 source-card groups; train 375, validation 90, test 35.
- Best validation checkpoint: epoch 11 (BCE 0.223854). Held-out test used once.
- Synthetic precision 0.9600, recall 0.8571, F1 0.9057. TN=6, FP=1, FN=4, TP=24.
- Copy-move is weakest: 3/7 detected, mean IoU 0.2401. Photo IoU 0.7275,
  text IoU 0.5029, stamp-edit IoU 0.6261. These are fixed-layout synthetic results.
- Classical noise initially overreacted to printed text. Flat-region estimation
  now masks sharp edges; rerun artifacts replace the earlier saturated maps.
- Current five-image smoke baseline indices: clean .166, text .168, copy .177,
  photo .166, stamp .167. This baseline does not reliably separate these attacks.
- Warm full L3 smoke latency 94–106 ms at 192x192; first call 5306 ms including
  PyTorch import/model startup. Not a latency benchmark for full-size scans.
- 138 tests passed with no skips; Ruff clean, pip dependency check clean.
  One existing Starlette/httpx deprecation warning remains.
- Real checkpoint inference, optional-model failures, normalized geometry,
  EXIF rotation, invalid inputs, dataset checksums and split leakage tested.
- MIDV-DM public license download verified: 592 bytes,
  MD5 `7ee73f11b0afb81289a98a00d841a54e`, SHA-256
  `41ddf51a61bc5573d142d778f18457eb2ec46d2f9ad4fb4c44191dba57b57550`.
- Public image archives not downloaded/trained. Generic explicit-manifest importer
  provided; dataset-specific author annotations require curated mapping.
- YOLO stamp adapter decoding/NMS tested; no stamp-trained weights supplied or
  real YOLO inference verified. No verified issuer templates. Default unavailable.
- Uploaded API images/EXIF are not persisted; saved verification artifacts are
  clearly synthetic. No real-world accuracy or authenticity claim.
- Full L2/L3/L4 parallel orchestration and L5 integration belong to Phase 4.

See `phase3_training.json`, `phase3_smoke.json` and `phase3_visuals/comparison.png`.
