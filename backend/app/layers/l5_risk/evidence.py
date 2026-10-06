"""Translate layer evidence without double-counting correlated sub-detectors."""

from app.schemas.common import LayerResult
from app.schemas.documents import ValidationData
from app.schemas.faces import LivenessData, SyntheticIdentityData, VerificationData
from app.schemas.risk import RiskInput, RiskSignal
from app.schemas.tampering import TamperingData

DATE_FLAGS = {
    "DOCUMENT_EXPIRED",
    "DOB_IMPLAUSIBLE",
    "EXPIRY_IMPLAUSIBLE",
    "ISSUE_EXPIRY_ORDER",
    "FUTURE_ISSUE",
    "ISSUE_BEFORE_BIRTH",
    "VISA_WINDOW_INVALID",
    "VISA_NOT_YET_VALID",
    "VISA_ENTRY_WINDOW_EXPIRED",
    "VISA_STAY_INVALID",
    "INVALID_MRZ_DATE",
}
DATE_UNKNOWN = {"DATE_UNREADABLE", "DOB_CENTURY_AMBIGUOUS", "EXPIRY_CENTURY_INFERRED"}
FORMAT_FLAGS = {"COUNTRY_CODE_UNKNOWN", "NUMBER_FORMAT", "COUNTRY_NUMBER_FORMAT"}


def risk_inputs(
    validation: LayerResult[ValidationData] | None = None,
    tampering: LayerResult[TamperingData] | None = None,
    face: LayerResult[VerificationData] | None = None,
    liveness: LayerResult[LivenessData] | None = None,
    duplicate: LayerResult[SyntheticIdentityData] | None = None,
) -> RiskInput:
    signals = {}

    def add(name, value, complete, explanation, source, experimental=False):
        signals[name] = RiskSignal(
            value=value,
            complete=complete,
            explanation=explanation,
            source=source,
            experimental=experimental,
        )

    if validation and validation.status not in {"unavailable", "needs_rescan"}:
        data = validation.data
        codes = {f.code for f in validation.findings}
        known_checks = [c.valid for c in data.checks if c.valid is not None]
        add(
            "mrz",
            float(False in known_checks) if known_checks else None,
            bool(data.checks)
            and len(known_checks) == len(data.checks)
            and "MRZ_VARIANT_UNSUPPORTED" not in codes,
            "Failed MRZ checks add one capped signal; OCR errors can cause failure.",
            "L2",
        )
        known_cross = [
            c.consistent for c in data.cross_checks if c.consistent is not None
        ]
        mismatches = sum(v is False for v in known_cross)
        add(
            "cross_fields",
            min(mismatches / 2, 1) if known_cross else None,
            {c.field for c in data.cross_checks if c.consistent is not None}
            >= {"name", "number", "dob", "expiry"},
            f"{mismatches} observed MRZ/VIZ mismatches; capped at two.",
            "L2",
        )
        dates_complete = all(
            data.resolved_dates.get(k) for k in ("dob", "expiry")
        ) and not codes.intersection(DATE_UNKNOWN)
        date_flags = sorted(codes.intersection(DATE_FLAGS))
        add(
            "dates",
            1.0 if date_flags else 0.0 if dates_complete else None,
            bool(dates_complete),
            "Date rules: "
            + (
                ", ".join(date_flags)
                or "no violation observed; unresolved dates remain unknown."
            ),
            "L2",
        )
        add(
            "blacklist",
            float(data.blacklist_hit)
            if data.database_available and data.blacklist_hit is not None
            else None,
            data.database_available and data.blacklist_hit is not None,
            "Fictional local blacklist lookup; not an official watchlist.",
            "L2 mock SQLite",
            True,
        )
        format_flags = sorted(codes.intersection(FORMAT_FLAGS))
        format_complete = bool(known_checks) and "MRZ_VARIANT_UNSUPPORTED" not in codes
        add(
            "format",
            float(bool(format_flags)) if format_complete or format_flags else None,
            format_complete,
            "Demo country/number rules: "
            + (", ".join(format_flags) or "no violation observed."),
            "L2 demo policy",
            True,
        )
    if tampering and tampering.status == "ok":
        # CNN is deliberately excluded: the fixed-layout model is synthetic-only.
        spatial_names = {
            "ela",
            "noise_splicing",
            "photo_replacement",
            "copy_move",
            "font_inconsistency",
        }
        available = {
            e.name: e
            for e in tampering.data.detectors
            if e.status == "ok" and e.score is not None
        }
        spatial = [e.score for n, e in available.items() if n in spatial_names]
        core = spatial_names - {"ela"}  # ELA does not apply to lossless sources.
        add(
            "tampering",
            max(spatial) if spatial else None,
            core <= available.keys(),
            "Maximum classical spatial index; correlated detectors are not summed. "
            "Synthetic CNN and stamp-template similarity are excluded.",
            "L3 classical",
            True,
        )
        meta = [
            available[n].score for n in ("metadata", "double_jpeg") if n in available
        ]
        add(
            "metadata",
            max(meta) if meta else None,
            {"metadata", "double_jpeg"} <= available.keys(),
            "Maximum EXIF/compression proxy; editing alone does not prove fraud.",
            "L3 metadata",
            True,
        )
    if face and face.status == "ok" and face.data.cosine_similarity is not None:
        data = face.data
        usable = data.document_face_count == data.live_face_count == 1
        add(
            "face",
            float(data.cosine_similarity < data.threshold) if usable else None,
            usable,
            f"Cosine {data.cosine_similarity:.4f}, threshold {data.threshold:.4f}; "
            "one-to-one comparison is not identity or liveness certification.",
            "L4 SFace",
            not data.threshold_calibrated,
        )
    if liveness and liveness.status != "unavailable":
        # An inconclusive texture result is never a verified low-spoof result.
        spoof = liveness.data.spoof_indicator_score
        add(
            "liveness",
            spoof if spoof is not None and spoof > 0 else None,
            False,
            "Untrained spoof indicator only; liveness remains unverified.",
            "L4 heuristics",
            True,
        )
    if duplicate and duplicate.status == "ok":
        hit = duplicate.data.duplicate_identity_hit
        add(
            "duplicate_identity",
            float(hit) if hit is not None else None,
            hit is not None,
            "Bundled synthetic-identity demonstration only; not a passenger gallery.",
            "L4 synthetic FAISS",
            True,
        )
    return RiskInput(signals=signals)
