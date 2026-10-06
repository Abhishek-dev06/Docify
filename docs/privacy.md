# Privacy design — Phases 1–5

Yeh local synthetic demo hai. Real passport/live-face data ingest na karein.

- **Minimization:** uploads aur corrected images memory mein process hoti hain;
  multipart spool threshold request cap se bada hai. OCR image stdin se transfer hoti hai.
- **Purpose:** fictional documents ke quality, OCR aur rules demonstrate karna.
- **Persistence (transient APIs):** server images/raw OCR store nahi karta. Explicit generator
  synthetic fixtures banata hai; CLI `--output` explicitly JSON report save karta hai.
- **Mock database:** only issuer+number digest, fictional blacklist flag aur count.
  Plain SHA-256 anonymity guarantee nahi deta; predictable IDs brute-force ho sakte hain.
- **Logging/cache:** request bodies log nahi karte; responses `Cache-Control: no-store`
  use karte hain. Host OS swap, crash dumps aur operator screenshots app ke control se bahar hain.
- **DPDP-style considerations:** purpose limitation, data minimization, notice,
  appropriate access control, limited retention aur deletion process production design
  ke inputs honge. Yeh DPDP Act compliance assessment ya legal advice nahi hai.
- **Face embeddings:** one-to-one verification mein transient arrays hain, JSON
  response/database/log mein return ya persist nahi hoti. FAISS demo sirf bundled
  generated portraits se per-request memory index banata hai; external enrollment
  accept nahi hota. Synthetic sample IDs ke alawa image-gallery search unavailable hai.
- **Access:** officer labels unverified hain; authentication aur production retention
  lifecycle implemented nahi hain. Phase 5 append-only behavior verified hai. Optional chip verifier
  abhi interface-only hai; trust-chain verification implemented nahi hai.

Default service localhost par bind karein. Network deployment, real border decisions,
identity registration aur production data retention Phase 1 ki capability nahi hai.

# Phase 3 image forensics

L3 API uses bounded in-memory uploads and returns heatmaps without persisting
documents, EXIF values or CNN input. Only boolean metadata findings are returned.
Explicit CLI `--output` exports images; generated training fixtures and verification
artifacts are procedural synthetic cards. Public datasets require authorized access
and their own attribution/retention terms. Do not log base64 response images.

# Phase 4 integrated scoring

Phase 4 integration also keeps uploaded document/live/frame images in memory and
does not enroll faces. Its portrait exclusion is an in-memory OCR working copy;
original pixels remain available only for the current request's L3/L4 work.
`demo_phase4.py --output` explicitly exports JSON without images but with extracted
fields, so use synthetic data. Risk responses carry policy provenance and
experimental/unknown flags. This transient endpoint adds no scan-history persistence.

# Phase 5 opt-in audit

Dashboard explicitly calls `/api/v1/scans/analyze`, which records a metadata allowlist:
UTC timestamp, original-document SHA-256, risk points/reasons/policy provenance,
layer availability, mismatch field names, face similarity, duration and unverified
officer label. Decisions add choice, acknowledgement and an officer-written note.
Images, extracted names/numbers/DOB, raw OCR, EXIF values and face embeddings are
excluded. Notes are plain text: UI asks officers not to include personal identifiers;
automatic personal-data redaction is not implemented.

SQLite data persists in `data/audit.db`; Compose uses a persistent named volume.
There is no automatic retention expiry or deletion API. Application decisions are
appended rather than overwritten. Audit hashes are linkage identifiers, not anonymity
guarantees. Synthetic browser QA entries remain in the demonstration history.

Requests to older standalone/transient endpoints are not automatically audited.
History reload shows retained metadata only, so uploaded evidence cannot be replayed.
Response retry with the same idempotency key returns the stored metadata, not images.
The local HTTP app has no authentication, authorization or encrypted audit storage.
Keep it bound to localhost. Production access, retention and deletion governance
require separate design; this phase makes no legal compliance claim.
