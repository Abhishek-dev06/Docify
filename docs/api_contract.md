# Phase 1 API contract

L4 endpoints Phase 2 mein added hain: [face API contract](phase2.md#api-and-standalone-functions).
Existing Phase 1 routes aur payload contracts retained hain.
Integrated Phase 4 routes: [risk and pipeline contract](phase4.md#endpoints-and-standalone-use).

- `GET /api/v1/risk/policy`: validated weights, thresholds and policy hash.
- `POST /api/v1/risk/score`: caller-supplied `RiskInput` → `LayerResult[RiskData]`.
- `POST /api/v1/screening/analyze`: document + optional live/frames → server-derived
  L0/L1/L2/L3/L4 evidence, L5 score, coverage, missing signals and stage failures.
  Required `reference_date`; incomplete evidence may yield a null category/score.

Base: `/api/v1`. Machine-readable exact schemas: `/openapi.json`.
Swagger `/docs` mein synthetic upload aur JSON calls directly try kar sakte hain.

| Endpoint | Request | Response |
|---|---|---|
| `GET /health` | None | Phase, executable availability, privacy flags |
| `POST /capture/preprocess` | Multipart `document`, optional `document_type` | `LayerResult[CaptureData]` |
| `POST /ocr/extract` | Same multipart | `LayerResult[OCRData]` |
| `POST /ocr/parse-mrz` | JSON `{"lines": ["...", "..."]}` | `MRZData` |
| `POST /validation/check` | `ValidationRequest` JSON | `LayerResult[ValidationData]` |
| `POST /phase1/analyze` | Multipart plus required `reference_date=YYYY-MM-DD` | `Phase1Result` |

Document type: `passport | visa | id | license | permit | unknown`.
Uploads: one JPEG/PNG/WEBP, max 10 MiB, max 20 megapixels. Request overhead bounded
to another 64 KiB. Excess size gets 413 (stream overrun may return 400);
unsupported request content type gets 415; invalid image/schema gets 422.

```json
{
  "status": "ok",
  "data": {},
  "findings": [
    {
      "code": "FIELD_MISMATCH",
      "severity": "medium",
      "explanation": "MRZ and printed dob disagree.",
      "field": "dob",
      "region": null
    }
  ],
  "duration_ms": 12.5
}
```

Yeh response-shape example hai; timings measured claim nahi hain.
Statuses: `ok`, `needs_rescan`, `insufficient_evidence`, `unavailable`.
`ok` execution status hai; risk/approval category nahi.

Field schema:

```json
{
  "raw": "BBO4I2",
  "corrected": "880412",
  "confidence": null,
  "source": "mrz",
  "corrections": ["Position-constrained OCR correction: BBO4I2 -> 880412"]
}
```

MRZ output mein `format`, `raw_lines`, `corrected_lines`, `fields`, `checks`,
`corrections`, `limitations` milte hain. Har check mein `input`, `observed`,
`expected`, `valid` hota hai. `valid: null` means unsupported/unavailable.
Checks corrected text par calculate hote hain; corrections alag visible hain.

Validation request:

```json
{
  "document_type": "passport",
  "reference_date": "2026-10-03",
  "mrz": null,
  "viz_fields": {}
}
```

Real demo mein OCR response ka `data.mrz` aur `data.viz_fields` yahan pass karein.
Server supplied checksum booleans ko trust nahi karta; raw MRZ dobara parse hoti hai.
Missing comparison `consistent: null` hoti hai; zero mismatches se complete evidence
infer nahi karna chahiye. Database not seeded ho to blacklist value `null` hogi.

Capture response `image_base64` PNG hai, data-URI prefix ke bina. `transform` 3x3
homography EXIF-oriented input coordinates se corrected image coordinates tak hai.
Pipeline mein bad quality milne par `ocr` aur `validation` null rahenge.

```json
{
  "error": {
    "code": "INVALID_INPUT",
    "message": "Invalid or unsafe image payload.",
    "request_id": "server-generated-id"
  }
}
```

Phase 1 endpoints stateless hain. Phase 5 separate opt-in audit endpoints provide
karte hain. No authentication yet; local synthetic demo only.
# Phase 3 addition

`POST /api/v1/tampering/analyze`: multipart `document`, optional normalized
JSON-string `photo_region=[x,y,w,h]`, optional `include_cnn=true|false`.
Returns `LayerResult[TamperingData]`: `suspicion_score`, null `tamper_probability`,
`score_calibrated=false`, per-detector availability/score/explanation/regions,
classical `heatmap_png_base64`/`overlay_png_base64`, optional separate
`cnn_heatmap_png_base64`, output dimensions and coordinate frame. Original bytes
preserve metadata/JPEG history; do not submit a re-encoded L0 image for this endpoint.
All scores are experimental evidence indices. See [Phase 3](phase3.md) for limits.

# Phase 5 audited workflow

`POST /api/v1/scans/analyze` accepts the same multipart inputs as the Phase 4
`/screening/analyze`: document, reference_date, optional document_type, live OR
frames, photo_region and timestamps_ms. Required headers: `X-Officer-ID` local
label (3–64 letters/digits/_/-) and UUID `Idempotency-Key`. Response:
`{analysis: ScreeningResult | null, scan_event: AuditEvent, replayed: boolean}`.
Same-key replay returns the stored event without retained images or OCR values.

`GET /api/v1/scans?q=&decision=&limit=20&offset=0` returns
`{items: [{scan, latest_decision, latest_event_hash}], total, limit, offset}`.
Decision filter: `pending`, `approve`, `secondary_inspection`, `reject`.
Search covers scan UUID/hash and scan/latest-decision actor labels.
`GET /api/v1/scans/{scan_id}` returns all events plus latest event hash.

`POST /api/v1/scans/{scan_id}/decisions` requires `X-Officer-ID` and JSON:
`{decision, note, expected_event_hash, request_id, acknowledge_incomplete}`.
Note is 8–500 characters; request_id is a UUID reused on an identical retry;
expected_event_hash must equal the scan's most recent event hash. Incomplete
approval needs acknowledgement. Conflicting/stale requests return 409.

AuditEvent contains seq, event_id, request_id, scan_id, kind, timestamp, actor,
document_hash, previous_hash, event_hash and payload. Scan payload is an explicit
metadata allowlist (scores/provenance/availability/mismatch field names/face cosine),
not raw OCR or document images. Decision payload includes decision/note/acknowledgement
and superseded event hash. Labels are explicitly not authenticated identities.

`GET /api/v1/audit/verify` returns validity and, if valid, event_count/head_seq/head_hash.
Optional `anchor_seq` and `anchor_hash` must be supplied together to check an exported
trusted checkpoint. Invalid chain blocks subsequent history and writes.
Storage unavailable returns 503, unknown scan 404, malformed inputs 422.

Synthetic PNG fixtures: `GET /api/v1/demo/fixtures/{scenario}/{kind}` with scenario
`genuine|dob_altered|wrong_face|blacklisted|blurred`, kind `document|live`.
Run commands, trust limits and Docker notes: [Phase 5](phase5.md).
