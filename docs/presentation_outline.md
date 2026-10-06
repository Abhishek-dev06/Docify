# PPT outline — 9 slides with Hinglish speaker notes

This is the requested editable **outline**, not a rendered `.pptx` deck. Use the
dashboard's teal/cream palette, short slide text, and the supplied measured charts.
Show “Synthetic prototype” wherever a result could otherwise imply real-world validation.

## 1. Sentinel: document screening assistant

Slide text: AI-Based Fake Identity & Document Screening System. Synthetic hackathon
prototype. Officer makes the final decision.

Visual: current dashboard screenshot `reports/phase5_dashboard.png` (caption it as
Phase 5 capture). Notes: “Hum evidence ko organize karte hain, authenticity certify nahi.”

## 2. The review problem

Slide text: Field alterations can disagree with MRZ. Portrait replacement can
disagree with the supplied reference. Scattered checks make review harder to explain.

Visual: fictional DOB case with conflicting fields highlighted. Notes: “Yeh use-case
assumptions hain; passenger-volume/time-saving statistics humne measure nahi kiye.”

## 3. Layer-wise architecture

Slide text: L0 quality and crop. L1 MRZ/VIZ. L2 rules, L3 forensics, L4 face in parallel.
L5 explainable points. L6 human decision and audit.

Visual: README Mermaid architecture. Notes: “Bad quality par rescan, unavailable
evidence par explicit gap. Independent Python functions aur REST routes dono hain.”

## 4. Tampering evidence

Slide text: Classical metadata/ELA/noise/copy-move evidence. Trained tiny U-Net on
procedural cards. Separate maps and documented missing detectors.

Visual: `reports/phase3_visuals/comparison.png`, caption fixed-layout synthetic.
Notes: “CNN 500 generated images par train/validation/test split ke saath trained hai.
Synthetic CNN ko risk score mein include nahi kiya. Genuine issuer stamp model absent hai.”

## 5. Explainability and officer workflow

Slide text: Raw/corrected OCR, mismatches, face cosine, points and missing evidence.
Approve / Secondary inspection / Reject with a reason. Searchable immutable events.

Visual: `reports/phase5_review.png` crop. Notes: “Genuine-looking case bhi incomplete
hai because liveness missing. Actor labels local/unverified. Images history mein nahi.”

## 6. Evaluation on synthetic data

Slide text: VIZ exact 150/156, MRZ exact 141/156. CNN fresh groups: precision 94.81%,
recall 91.25%, F1 92.99%. Classical recall 1.25% at fixed index threshold.

Visual: `reports/phase6/tamper_confusion.png`. Footnote: 100 procedural images, 20 source
groups, 80 attacks / 20 clean; same generator/layout families. Source: evaluation.md.
Notes: “TN16 FP4 FN7 TP73. Class imbalance aur negative controls context mein rakhein.
Per-attack curves aur IoU report mein hain. Held-out original test replay unchanged hai.”

## 7. Error analysis and face-test limits

Slide text: Copy-move IoU 0.179. MRZ names can gain a spurious K. Z/7 confusions remain.
Face ROC uses only two known generated identities and correlated transformations.

Visual: `reports/phase6/tamper_iou.png`; optional appendix `face_roc.png`.
Notes: “Zero observed face errors ko population FAR/FRR mat bolna. Independent captures
aur identities chahiye. Check digits names ki correctness establish nahi karte.”

## 8. Feasibility, privacy and intended impact

Slide text: CPU prototype; process-cold 12.51s, warm median 4.01s (n=6). No stored
uploaded images or embeddings. Hash-chain audit with external-checkpoint limitation.

Visual: `reports/phase6/latency.png`. Footnote: 2-thread OpenCV/Tesseract, L0-L5 only,
excludes HTTP/audit/UI. Docker config supplied, container runtime unverified.
Notes: “Consistent review aur explainable handoff intended impact hain. Real checkpoint
throughput, time savings or compliance abhi measured/certified nahi hain.”

## 9. Limitations and future scope

Slide text: Diverse authorized document evaluation. Independent face capture and
calibrated thresholds. Verified liveness and genuine stamp/chip trust validation.
Officer authentication, retention governance, protected external audit anchors.

Notes: “Working local demo delivered hai. Production readiness ke gaps openly listed
hain. Three-case walkthrough se evidence, errors aur human judgment demonstrate karenge.”

## Appendix material for questions

Keep the one-page `output/pdf/solution_overview.pdf`, raw JSON with model/protocol
hashes, per-attack IoU, illustrative ROC and `docs/demo_walkthrough.md` ready.
Do not add external impact/accuracy claims without supporting evidence.
