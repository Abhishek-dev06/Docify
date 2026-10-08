# Five-minute demo — Hinglish speaking script

Audience: hackathon judges. All documents/portraits fictional. Reference date stays
**2026-10-03** for repeatability; it is intentionally independent of today's date.

## Before the timer

Run `scripts/demo_phase6.py --prepare-only`, start the built app on localhost:8000,
and do one genuine sample scan to warm models. Set officer label `DEMO-PRESENTER`.
Keep `reports/phase6/evaluation.md` and the one-page PDF open. UI history does not
retain images, so load a fresh case when demonstrating the evidence panel.
If the live app is slow, use the saved measured report and explicitly call it a
recorded run. Never present saved outputs as newly computed results.

## 00:00–00:35 — problem and scope

Say: “Humne ek document review assistant banaya hai. Yeh fields, face comparison,
tamper signals aur missing evidence ko ek jagah dikhata hai. Final decision officer
ka hai. Aaj ke saare documents aur faces synthetic hain.”

Point to L0-L6 diagram. Explain L2 validation, L3 tampering and L4 face run in parallel.
No real watchlist, independent identity proof or verified liveness claim.

## 00:35–01:35 — genuine-looking mock

Select **Genuine-looking mock → Load synthetic sample → Analyze & record**.
Show MRZ/VIZ fields, raw OCR disclosure and face match. Expected observed score 3.25,
face cosine about 0.93. Highlight **Incomplete evidence**, missing liveness and 79%
coverage. Say: “Low observed points authenticity ka certificate nahi hain.”

Open **Tamper overlay**. It may highlight clean printed content: “Classical map noisy
ho sakti hai; hum ise evidence signal bolte hain.” Show reasons behind each score.

## 01:35–02:35 — replaced document photo

Click **New review**, select **Replaced document photo**, load and analyze.
The document now has synthetic B, while reference remains synthetic A. Expected
face non-match; measured score 18.25. Point to face contribution and missing liveness.

Say: “Is case mein face disagreement measured hai. Photo splice ka forensic proof
claim nahi kar raha; full-size passport layout par CNN validated nahi hai.”
Record **Secondary inspection**, note: `Synthetic demo: document portrait disagrees
with supplied reference; further evidence required.` No automatic rejection.

## 02:35–03:30 — changed date of birth

Load **Altered date of birth**. MRZ retains 1988-04-12 and printed DOB becomes
1998-04-12. Highlight the mismatched row, valid MRZ digits and cross-field reason.
Expected score 7.25; one mismatch. Say: “Valid MRZ checksum ke bawajood printed
field badal sakta hai. Isi liye MRZ aur VIZ ko compare karte hain.”

## 03:30–04:10 — decision and audit

Record a reasoned secondary-inspection decision, search `DEMO-PRESENTER` in history,
and reopen. Explain why images and identity field values are absent after reload.
Open **Audit integrity**, verify and export checkpoint.

Say: “Revised decisions naye events hain. Hash chain tampering reveal karti hai,
lekin database owner poori chain rewrite kar sakta hai. Isliye separate trusted
checkpoint chahiye. Demo officer label abhi authentication nahi hai.”

## 04:10–05:00 — measured evidence and limits

Show report: VIZ 150/156 exact fields, MRZ 141/156. Fresh procedural CNN F1 92.99%
with 4 clean false positives and 7 copy-move misses. Point to copy-move IoU 0.179
and baseline recall 1.25%. Explain the two-identity ROC is illustrative only.

Say: “Controlled warm pipeline median 4.01 seconds hai, six samples par. Browser
latency alag ho sakti hai. Next work diverse authorized data, independent captures,
verified liveness, access controls aur external audit anchoring hai.”

## If a judge asks

| Question | Honest response |
|---|---|
| 92.99% real-world accuracy? | Nahi: synthetic F1 on 100 new procedural images; same layouts/generator, with false positives/misses. |
| Which part is novel? | Prototype contribution is combined evidence review, explicit uncertainty and auditable decisions; scientific novelty has not been established. |
| Why not auto-reject? | Evidence is incomplete and detectors are uncalibrated; human review is required. |
| Can you verify a live person? | No. Current texture/blink evidence is experimental and does not certify liveness. |
| Why OpenCV face models? | CPU-capable YuNet/SFace baseline; architecture is replaceable. Current two-identity threshold is uncalibrated. |
| What about chip/stamp verification? | Chip interface and optional stamp adapter exist; trusted chip verification and genuine stamp weights/templates are unavailable. |
| Does DPDP compliance follow from no stored images? | No. Access, lawful purpose, retention and governance still require a separate assessment. |
