"""Bounded classical image-forensics signals; none certifies authenticity."""

from datetime import datetime
from io import BytesIO

import cv2
import numpy as np
from PIL import Image

from app.schemas.tampering import DetectorEvidence


def regions_from_map(heat: np.ndarray, threshold: float = 0.55) -> list[tuple]:
    binary = (heat >= threshold).astype(np.uint8)
    count, _, stats, _ = cv2.connectedComponentsWithStats(binary, 8)
    h, w = heat.shape
    boxes = []
    for x, y, bw, bh, area in stats[1:count]:
        if area >= max(12, h * w * 0.001):
            boxes.append((int(area), (x / w, y / h, bw / w, bh / h)))
    return [tuple(float(v) for v in box) for _, box in sorted(boxes, reverse=True)[:12]]


def signal(
    name: str,
    heat: np.ndarray,
    method: str,
    explanation: str,
    metrics: dict | None = None,
) -> DetectorEvidence:
    # Fixed top-one-percent mean retains small regions without per-image max scaling.
    values = heat.ravel()
    k = max(1, int(len(values) * 0.01))
    score = float(np.mean(np.partition(values, len(values) - k)[-k:]))
    return DetectorEvidence(
        name=name,
        score=score,
        method=method,
        explanation=explanation,
        regions=regions_from_map(heat),
        metrics=metrics or {},
    )


def metadata(payload: bytes) -> DetectorEvidence:
    with Image.open(BytesIO(payload)) as image:
        exif = image.getexif()
        software = str(exif.get(305, "")).lower()
        dates = [exif.get(306), exif.get(36867), exif.get(36868)]
        if 34665 in exif:
            nested = exif.get_ifd(34665)
            dates[1:] = [nested.get(36867), nested.get(36868)]
        editing = any(
            word in software
            for word in ("photoshop", "gimp", "affinity", "paint", "lightroom")
        )
        parsed = []
        for value in dates:
            try:
                parsed.append(datetime.strptime(str(value), "%Y:%m:%d %H:%M:%S"))
            except ValueError:
                parsed.append(None)
        inconsistent = bool(parsed[0] and parsed[1] and parsed[0] < parsed[1])
        present = bool(exif)
        return DetectorEvidence(
            name="metadata",
            status="ok" if present else "insufficient_evidence",
            score=min(1, 0.35 * editing + 0.65 * inconsistent) if present else None,
            method="EXIF software/timestamp rules",
            explanation=(
                "Editing software tag or reversed capture/edit dates are "
                "review signals; metadata can be removed or forged. "
                "No metadata never means authentic."
            ),
            metrics={
                "exif_present": present,
                "editing_software_tag": editing,
                "reversed_timestamps": inconsistent,
                "format": image.format or "unknown",
            },
        )


def compression(image: np.ndarray, is_jpeg: bool) -> DetectorEvidence:
    if not is_jpeg:
        return DetectorEvidence(
            name="double_jpeg",
            status="unavailable",
            method="DCT histogram periodicity proxy",
            explanation="Only applicable to a JPEG source; no compression verdict.",
        )
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float32) - 128
    h, w = gray.shape
    if min(h, w) < 64:
        return DetectorEvidence(
            name="double_jpeg",
            status="insufficient_evidence",
            method="DCT histogram periodicity proxy",
            explanation="Too few blocks.",
        )
    coefficients = []
    # Bounded subsampling: at most roughly 4096 blocks, on the original JPEG grid.
    stride = max(1, int(np.ceil(np.sqrt((h // 8) * (w // 8) / 4096))))
    for y in range(0, h - 7, 8 * stride):
        for x in range(0, w - 7, 8 * stride):
            block = cv2.dct(gray[y : y + 8, x : x + 8])
            coefficients.append([block[0, 1], block[1, 0], block[1, 1]])
    periodicities = []
    for series in np.asarray(coefficients).T:
        hist, _ = np.histogram(series, bins=np.arange(-64.5, 65.5))
        residual = hist.astype(float) - np.convolve(hist, np.ones(9) / 9, "same")
        power = np.abs(np.fft.rfft(residual))[2:]
        periodicities.append(float(power.max() / (power.sum() + 1e-8)))
    index = float(np.clip((np.mean(periodicities) - 0.04) * 4, 0, 1))
    return DetectorEvidence(
        name="double_jpeg",
        score=index,
        method="DCT histogram spectral concentration proxy",
        explanation="Periodic DCT histograms can indicate quantization history; "
        "single compression, graphics and resizing also cause peaks. "
        "This heuristic does not establish double compression.",
        metrics={
            "blocks": len(coefficients),
            "spectral_concentration": float(np.mean(periodicities)),
        },
    )


def ela(
    image: np.ndarray, is_jpeg: bool, quality: int = 90
) -> tuple[DetectorEvidence, np.ndarray]:
    if not is_jpeg:
        return DetectorEvidence(
            name="ela",
            status="unavailable",
            method="JPEG recompression residual",
            explanation="Lossless source: prior JPEG history cannot be assessed.",
        ), np.zeros(image.shape[:2], np.float32)
    _, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, quality])
    restored = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
    residual = np.mean(cv2.absdiff(image, restored).astype(np.float32), axis=2)
    energy = cv2.GaussianBlur(residual, (15, 15), 0)
    heat = np.clip((energy - 2) / 12, 0, 1)
    return signal(
        "ela",
        heat,
        "JPEG recompression at fixed quality",
        "Strong recompression residuals localize inconsistent edges/color; "
        "normal text and high-detail photos can also respond.",
        {"quality": quality, "mean_absolute_error": float(residual.mean())},
    ), heat


def residual_energy(image: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float32)
    residual = gray - cv2.GaussianBlur(gray, (5, 5), 1)
    return np.sqrt(cv2.GaussianBlur(residual**2, (25, 25), 0) + 1e-6)


def noise(image: np.ndarray) -> tuple[DetectorEvidence, np.ndarray]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY).astype(np.float32)
    residual = gray - cv2.GaussianBlur(gray, (5, 5), 1)
    dx = cv2.Sobel(gray, cv2.CV_32F, 1, 0)
    dy = cv2.Sobel(gray, cv2.CV_32F, 0, 1)
    edges = (np.hypot(dx, dy) > 25).astype(np.uint8)
    flat = 1 - cv2.dilate(edges, np.ones((5, 5), np.uint8)).astype(np.float32)
    support = cv2.GaussianBlur(flat, (25, 25), 0)
    variance = cv2.GaussianBlur(residual**2 * flat, (25, 25), 0)
    energy = np.sqrt(variance / np.maximum(support, 0.01))
    reference = cv2.GaussianBlur(energy, (0, 0), 35)
    heat = np.clip((np.abs(energy - reference) - 0.5) / 3, 0, 1)
    heat[support < 0.3] = 0
    if float(np.mean(support >= 0.3)) < 0.05:
        return DetectorEvidence(
            name="noise_splicing",
            status="insufficient_evidence",
            method="Flat-region residual comparison",
            explanation="Too little flat-region support to estimate noise.",
        ), heat
    return signal(
        "noise_splicing",
        heat,
        "Flat-region high-pass energy inconsistency with text-edge suppression",
        "Abrupt noise/texture changes are splice candidates; printed security "
        "patterns and natural image content are confounders; low-support areas "
        "are excluded from this map.",
        {
            "flat_pixel_fraction": float(flat.mean()),
            "supported_fraction": float(np.mean(support >= 0.3)),
        },
    ), heat


def validate_region(region: tuple | list) -> tuple[float, float, float, float]:
    if not isinstance(region, (tuple, list)) or len(region) != 4:
        raise ValueError("photo_region must be normalized [x,y,width,height].")
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in region):
        raise ValueError("photo_region must contain four finite numbers.")
    vals = np.asarray(region, dtype=float)
    x, y, w, h = vals
    if (
        not np.isfinite(vals).all()
        or min(x, y) < 0
        or min(w, h) <= 0
        or x + w > 1
        or y + h > 1
    ):
        raise ValueError("photo_region must lie within the image.")
    return tuple(float(v) for v in vals)


def photo(
    image: np.ndarray, region: tuple | None
) -> tuple[DetectorEvidence, np.ndarray]:
    heat = np.zeros(image.shape[:2], np.float32)
    if region is None:
        return DetectorEvidence(
            name="photo_replacement",
            status="unavailable",
            method="Photo versus surrounding noise/compression statistics",
            explanation="Supply photo_region in normalized original coordinates; "
            "the face box is not the full portrait region.",
        ), heat
    x, y, w, h = validate_region(region)
    ih, iw = image.shape[:2]
    x1, y1 = int(x * iw), int(y * ih)
    x2, y2 = min(iw, int((x + w) * iw)), min(ih, int((y + h) * ih))
    if min(x2 - x1, y2 - y1) < 16:
        raise ValueError("photo_region must be at least 16 pixels on each side.")
    ring = np.zeros((ih, iw), np.uint8)
    margin = max(8, int(min(x2 - x1, y2 - y1) * 0.2))
    ring[
        max(0, y1 - margin) : min(ih, y2 + margin),
        max(0, x1 - margin) : min(iw, x2 + margin),
    ] = 1
    ring[y1:y2, x1:x2] = 0
    if not ring.any():
        return DetectorEvidence(
            name="photo_replacement",
            status="insufficient_evidence",
            method="Portrait/ring statistics",
            explanation="No surrounding region.",
        ), heat
    energy = residual_energy(image)
    _, enc = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 90])
    restored = cv2.imdecode(enc, cv2.IMREAD_COLOR)
    error = np.mean(cv2.absdiff(image, restored), axis=2)
    inside = float(np.median(energy[y1:y2, x1:x2]))
    outside = float(np.median(energy[ring > 0]))
    inside_ela = float(np.mean(error[y1:y2, x1:x2]))
    outside_ela = float(np.mean(error[ring > 0]))
    contrast = abs(np.log((inside + 1) / (outside + 1)))
    compression_contrast = abs(np.log((inside_ela + 1) / (outside_ela + 1)))
    score = float(np.clip((max(contrast, compression_contrast) - 0.7) / 2, 0, 1))
    heat[y1:y2, x1:x2] = score
    return signal(
        "photo_replacement",
        heat,
        "Portrait/ring residual comparison",
        "Photo and surrounding print have different texture/compression residuals. "
        "Content naturally differs, so this cannot establish photo replacement.",
        {
            "photo_noise": inside,
            "ring_noise": outside,
            "photo_recompression_error": inside_ela,
            "ring_recompression_error": outside_ela,
        },
    ), heat


def copy_move(image: np.ndarray) -> tuple[DetectorEvidence, np.ndarray]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    points, descriptors = cv2.ORB_create(nfeatures=500).detectAndCompute(gray, None)
    heat = np.zeros(gray.shape, np.float32)
    groups: dict[tuple, list] = {}
    if descriptors is not None and len(points) >= 5:
        matches = cv2.BFMatcher(cv2.NORM_HAMMING).knnMatch(
            descriptors, descriptors, k=5
        )
        for candidates in matches:
            for match in candidates:
                if match.queryIdx >= match.trainIdx or match.distance > 24:
                    continue
                a = np.array(points[match.queryIdx].pt)
                b = np.array(points[match.trainIdx].pt)
                delta = b - a
                if np.linalg.norm(delta) < 30:
                    continue
                key = tuple(np.round(delta / 12).astype(int))
                groups.setdefault(key, []).append((a, b))
    accepted = 0
    for pairs in groups.values():
        if len(pairs) < 4:
            continue
        accepted += len(pairs)
        for a, b in pairs:
            for point in (a, b):
                cv2.circle(heat, tuple(point.astype(int)), 14, 0.65, -1)
    return signal(
        "copy_move",
        heat,
        "ORB self-matches with displacement consensus",
        "Repeated local features share a displacement; repeated legitimate text "
        "and document patterns can produce the same signal.",
        {"consensus_pairs": accepted},
    ), heat


def font_consistency(image: np.ndarray) -> tuple[DetectorEvidence, np.ndarray]:
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
    _, _, stats, centroids = cv2.connectedComponentsWithStats(binary, 8)
    heat = np.zeros(gray.shape, np.float32)
    chars = [
        (box, center)
        for box, center in zip(stats[1:], centroids[1:], strict=True)
        if 4 <= box[3] <= 36 and 2 <= box[2] <= 30 and box[4] >= 6
    ]
    outliers = 0
    for box, center in chars[:1500]:
        neighbors = [
            b[3]
            for b, c in chars[:1500]
            if abs(c[1] - center[1]) < 5 and abs(c[0] - center[0]) < 120
        ]
        if len(neighbors) < 6:
            continue
        typical = float(np.median(neighbors))
        deviation = abs(float(box[3]) - typical) / max(typical, 1)
        if deviation > 0.6:
            x, y, w, h, _ = box
            heat[y : y + h, x : x + w] = min(1, deviation)
            outliers += 1
    return signal(
        "font_inconsistency",
        heat,
        "Same-row component-height outliers",
        "Character-height outliers can suggest inconsistent fonts. Headings, "
        "mixed scripts, punctuation and layout changes are common false positives.",
        {"outlier_components": outliers},
    ), heat
