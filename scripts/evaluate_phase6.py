"""Run a frozen synthetic protocol; write measured rows, counts and provenance."""

import argparse
import base64
import hashlib
import importlib.metadata
import json
import os
import platform
import time
from datetime import date, datetime, timezone
from pathlib import Path

import cv2
import numpy as np
from app.demo import SyntheticIdentity, generate_document
from app.demo_cases import PHOTO_REGION, demo_case
from app.evaluation import binary_metrics, latency_summary, mask_iou, ratio, roc_points
from app.layers.l0_capture.preprocess import decode_image
from app.layers.l3_tampering.analyzer import analyze_tampering
from app.layers.l3_tampering.learned import predict
from app.layers.l3_tampering.synthetic import ATTACKS, make_variant
from app.layers.l4_face.synthetic_identity_index import synthetic_portrait
from app.layers.l4_face.verification import verify_faces
from app.pipeline import analyze_phase1
from app.screening import screen_document
from app.settings import ROOT, load_config
from app.storage.database import seed_mock_database

PROTOCOL_PATH = ROOT / "config" / "evaluation_protocol.json"
PROTOCOL = json.loads(PROTOCOL_PATH.read_text())
FIELDS = ("name", "number", "nationality", "dob", "expiry", "gender")


def sha(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def save(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")


def provenance() -> dict:
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "protocol": PROTOCOL,
        "protocol_sha256": sha(PROTOCOL_PATH.read_bytes()),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu": platform.processor(),
        "logical_cpus": os.cpu_count(),
        "opencv_threads": cv2.getNumThreads(),
        "omp_thread_limit": os.environ.get("OMP_THREAD_LIMIT"),
        "packages": {
            p: importlib.metadata.version(p)
            for p in ("numpy", "opencv-python-headless", "torch", "Pillow")
        },
        "config_sha256": {
            p.name: sha(p.read_bytes()) for p in (ROOT / "config").glob("*.yaml")
        },
        "checkpoint": json.loads((ROOT / "models" / "tamper_unet.json").read_text()),
        "face_models": json.loads((ROOT / "models" / "manifest.json").read_text()),
    }


def system_eval() -> dict:
    cfg = PROTOCOL["system"]
    directory = ROOT / "data" / "phase6_demo"
    directory.mkdir(parents=True, exist_ok=True)
    db_url = f"sqlite:///{(directory / 'mock.db').as_posix()}"
    seed_mock_database(db_url)
    cases = {name: demo_case(name) for name in cfg["scenarios"]}
    for name, (document, live, truth) in cases.items():
        (directory / f"{name}_document.png").write_bytes(document)
        (directory / f"{name}_live.png").write_bytes(live)
        save(directory / f"{name}_truth.json", truth)
    rows = []
    order = [("genuine", "process_cold", 0)] + [
        (name, "warm", repeat + 1)
        for repeat in range(cfg["warm_repeats_per_scenario"])
        for name in cfg["scenarios"]
    ]
    for name, thermal, repeat in order:
        doc, live, _ = cases[name]
        started = time.perf_counter()
        result = screen_document(
            doc,
            date.fromisoformat(PROTOCOL["reference_date"]),
            "passport",
            live,
            PHOTO_REGION,
            db_url=db_url,
        )
        elapsed = (time.perf_counter() - started) * 1000
        row = {
            "scenario": name,
            "run_type": thermal,
            "repeat": repeat,
            "wall_ms": elapsed,
            "pipeline_ms": result.duration_ms,
            "document_sha256": result.document_hash,
            "status": result.status,
            "layer_ms": {
                layer: getattr(result, layer).duration_ms
                if getattr(result, layer)
                else None
                for layer in (
                    "capture",
                    "ocr",
                    "validation",
                    "tampering",
                    "face",
                    "liveness",
                    "risk",
                )
            },
            "parallel_ms": result.parallel_stage_ms,
            "failures": [f.model_dump() for f in result.failures],
            "score": result.risk.data.score,
            "category": result.risk.data.category,
            "missing_required": result.risk.data.missing_required_signals,
            "face_cosine": result.face.data.cosine_similarity if result.face else None,
            "face_decision": result.face.data.decision if result.face else None,
            "mismatches": result.validation.data.mismatch_count
            if result.validation
            else None,
        }
        rows.append(row)
        print(
            f"system {thermal} {name}: {elapsed:.0f}ms, score={row['score']}",
            flush=True,
        )
    return {
        "scope": cfg,
        "rows": rows,
        "cold": rows[0],
        "warm": latency_summary(
            [r["wall_ms"] for r in rows if r["run_type"] == "warm"]
        ),
        "per_scenario": {
            name: latency_summary(
                [
                    r["wall_ms"]
                    for r in rows
                    if r["scenario"] == name and r["run_type"] == "warm"
                ]
            )
            for name in cases
        },
        "limitations": (
            "Single sequential process; no HTTP/audit/UI or concurrency load. Small n."
        ),
    }


def ocr_cases():
    originals = sorted((ROOT / "data" / "synthetic").glob("*.png"))
    if len(originals) != PROTOCOL["ocr"]["original_cases"]:
        raise ValueError("Run generate_mock_documents.py; expected exactly 8 fixtures.")
    for path in originals:
        yield (
            "original_development",
            path.stem,
            path.read_bytes(),
            json.loads(path.with_suffix(".json").read_text()),
        )
    for i in range(PROTOCOL["ocr"]["new_identities"]):
        identity = SyntheticIdentity(
            surname=["EXAMPLE", "SAMPLE", "MOCK", "TEST", "DEMO", "FICTION"][i],
            given_names=["ADA", "ROBIN", "SAM", "ALEX", "KAI", "JORDAN"][i],
            number=f"Z91{i:05d}",
            dob=f"{1980 + i}-0{1 + i}-1{1 + i}",
            gender="F" if i % 2 else "M",
        )
        for condition in PROTOCOL["ocr"]["conditions"]:
            doc, truth = generate_document(
                identity, "dob_altered" if condition == "dob_altered" else "genuine"
            )
            if condition == "jpeg_q70":
                doc = cv2.imencode(
                    ".jpg", decode_image(doc), [cv2.IMWRITE_JPEG_QUALITY, 70]
                )[1].tobytes()
            yield "new_values_same_layout", f"identity_{i}_{condition}", doc, truth


def ocr_summary(rows: list[dict]) -> dict:
    output = {
        "documents": len(rows),
        "rescan_count": sum(r["status"] == "needs_rescan" for r in rows),
    }
    for channel in ("viz", "mrz"):
        output[channel] = {
            f: {
                "correct": sum(r[channel][f]["match"] for r in rows),
                "total": len(rows),
                "accuracy": ratio(sum(r[channel][f]["match"] for r in rows), len(rows)),
            }
            for f in FIELDS
        }
        correct = sum(r[channel][f]["match"] for r in rows for f in FIELDS)
        output[channel]["overall"] = {
            "correct": correct,
            "total": len(rows) * len(FIELDS),
            "accuracy": ratio(correct, len(rows) * len(FIELDS)),
        }
    valid = [r for r in rows if r["expected_valid_mrz"]]
    parsed = [r for r in valid if r["mrz_parsed"]]
    output["mrz_digits"] = {
        "valid_document_count": len(valid),
        "parsed_valid_documents": len(parsed),
        "all_checks_pass_count": sum(r["all_checks_pass"] for r in valid),
        "end_to_end_pass_rate": ratio(
            sum(r["all_checks_pass"] for r in valid), len(valid)
        ),
        "conditional_parsed_pass_rate": ratio(
            sum(r["all_checks_pass"] for r in parsed), len(parsed)
        ),
        "invalid_documents": sum(not r["expected_valid_mrz"] for r in rows),
        "invalid_flagged": sum(
            not r["expected_valid_mrz"] and r["any_check_failed"] for r in rows
        ),
    }
    return output


def ocr_eval() -> dict:
    rows = []
    for cohort, name, document, truth in ocr_cases():
        result = analyze_phase1(
            document, date.fromisoformat(PROTOCOL["reference_date"])
        )
        ocr = result.ocr.data if result.ocr else None
        mrz = ocr.mrz if ocr else None
        expected = truth["viz_fields"]
        # TD3 truth comes from generator text, never from the OCR observation.
        line = truth["mrz_lines"][1]
        mrz_expected = {**expected, "dob": line[13:19], "expiry": line[21:27]}
        row = {
            "cohort": cohort,
            "scenario": name,
            "status": result.status,
            "image_sha256": sha(document),
            "duration_ms": result.duration_ms,
            "mrz_parsed": bool(mrz),
            "expected_valid_mrz": truth["variant"] != "checksum_failed",
            "all_checks_pass": bool(
                mrz and mrz.checks and all(c.valid is True for c in mrz.checks)
            ),
            "any_check_failed": bool(mrz and any(c.valid is False for c in mrz.checks)),
            "checks": {c.field: c.valid for c in mrz.checks} if mrz else {},
        }
        for channel, observed, wanted in [
            ("viz", ocr.viz_fields if ocr else {}, expected),
            ("mrz", mrz.fields if mrz else {}, mrz_expected),
        ]:
            row[channel] = {}
            for f in FIELDS:
                value = observed[f].corrected if f in observed else None
                row[channel][f] = {
                    "expected": wanted[f],
                    "observed": value,
                    "match": value == wanted[f],
                }
        rows.append(row)
        print(
            f"ocr {name}: {result.status}, MRZ pass={row['all_checks_pass']}",
            flush=True,
        )
    return {
        "scope": (
            "8 previously developed fixtures + 18 new values/conditions, "
            "same generator/layout; TD3 image OCR only"
        ),
        "denominator": (
            "All requested fields on all documents; missing/excluded "
            "scans count as incorrect"
        ),
        "summary": ocr_summary(rows),
        "by_cohort": {
            c: ocr_summary([r for r in rows if r["cohort"] == c])
            for c in sorted({r["cohort"] for r in rows})
        },
        "rows": rows,
    }


def tamper_summary(rows: list[dict], detector: str) -> dict:
    def metrics(items):
        return binary_metrics(
            [r["attack"] != "clean" for r in items],
            [r[detector]["flagged"] for r in items],
        )

    output = {**metrics(rows), "per_attack": {}}
    for attack in ATTACKS:
        selected = [r for r in rows if r["attack"] == attack]
        comparison = [r for r in rows if r["attack"] in (attack, "clean")]
        ious = [r[detector]["iou"] for r in selected if r[detector]["iou"] is not None]
        output["per_attack"][attack] = {
            "count": len(selected),
            "flagged": sum(r[detector]["flagged"] for r in selected),
            "mean_iou": float(np.mean(ious)) if ious and attack != "clean" else None,
            "versus_shared_clean_controls": metrics(comparison)
            if attack != "clean"
            else None,
        }
    return output


def tamper_eval() -> dict:
    directory = ROOT / "data" / "tampering"
    manifest_bytes = (directory / "manifest.json").read_bytes()
    model_manifest = json.loads((ROOT / "models" / "tamper_unet.json").read_text())
    if sha(manifest_bytes) != model_manifest["dataset_manifest_sha256"]:
        raise ValueError(
            "Training dataset manifest differs from frozen checkpoint provenance."
        )
    manifest = json.loads(manifest_bytes)
    groups = {}
    for r in manifest:
        if r["group"] in groups and groups[r["group"]] != r["split"]:
            raise ValueError("Source group leakage across training splits.")
        groups[r["group"]] = r["split"]
    samples = [
        (
            "original_test_replay",
            r["group"],
            r["attack"],
            cv2.imread(str(directory / r["image"])),
            cv2.imread(str(directory / r["mask"]), cv2.IMREAD_GRAYSCALE),
        )
        for r in manifest
        if r["split"] == "test"
    ]
    cfg = PROTOCOL["tamper"]
    for seed in range(
        cfg["fresh_seed_start"], cfg["fresh_seed_start"] + cfg["fresh_source_groups"]
    ):
        group = f"procedural-card-{seed:05d}"
        if group in groups:
            raise ValueError(
                "Fresh evaluation group already occurs in training manifest."
            )
        for attack in ATTACKS:
            image, mask = make_variant(seed, attack)
            samples.append(("fresh_groups_same_generator", group, attack, image, mask))
    rows = []
    for cohort, group, attack, image, mask in samples:
        if image is None or mask is None:
            raise ValueError("Missing tamper evaluation image/mask.")
        evidence, heat = predict(image)
        if heat is None:
            raise RuntimeError(evidence.explanation)
        payload = cv2.imencode(".png", image)[1].tobytes()
        baseline = analyze_tampering(
            payload, (127 / 192, 30 / 192, 53 / 192, 88 / 192), False
        )
        baseline_heat = cv2.imdecode(
            np.frombuffer(base64.b64decode(baseline.data.heatmap_png_base64), np.uint8),
            cv2.IMREAD_GRAYSCALE,
        )
        prediction = heat >= cfg["pixel_threshold"]
        rows.append(
            {
                "cohort": cohort,
                "group": group,
                "attack": attack,
                "image_sha256": sha(payload),
                "mask_sha256": sha(mask.tobytes()),
                "cnn": {
                    "flagged": bool(
                        prediction.mean() >= cfg["image_fraction_threshold"]
                    ),
                    "iou": mask_iou(mask > 127, prediction),
                    "fraction": float(prediction.mean()),
                },
                "classical": {
                    "flagged": baseline.data.suspicion_score
                    >= cfg["baseline_image_index_threshold"],
                    "index": baseline.data.suspicion_score,
                    "iou": mask_iou(mask > 127, baseline_heat >= 128),
                },
            }
        )
        if len(rows) % 20 == 0:
            print(f"tamper {len(rows)}/{len(samples)}", flush=True)
    return {
        "thresholds": cfg,
        "model_sha256": model_manifest["sha256"],
        "limitations": (
            "Fixed layouts/attack families; new source groups "
            "only. PNG containers disable ELA/JPEG metadata. "
            "Classical threshold is exploratory, not calibrated."
        ),
        "by_cohort": {
            c: {
                d: tamper_summary([r for r in rows if r["cohort"] == c], d)
                for d in ("cnn", "classical")
            }
            for c in sorted({r["cohort"] for r in rows})
        },
        "rows": rows,
    }


def face_eval() -> dict:
    cfg = PROTOCOL["face"]
    threshold = load_config("face_thresholds.yaml")["cosine_threshold"]
    portraits = {
        k: cv2.resize(synthetic_portrait(k), (600, 600)) for k in cfg["identities"]
    }
    documents = {}
    for name, portrait in portraits.items():
        image = decode_image(generate_document()[0])
        image[245:555, 1200:1510] = cv2.resize(portrait, (310, 310))
        documents[name] = image
    rows = []
    for identity, portrait in portraits.items():
        for angle in cfg["rotations"]:
            rotated = cv2.warpAffine(
                portrait,
                cv2.getRotationMatrix2D((300, 300), angle, 1),
                (600, 600),
                borderMode=cv2.BORDER_REFLECT,
            )
            for alpha, beta in cfg["brightness"]:
                image = np.clip(rotated.astype(float) * alpha + beta, 0, 255).astype(
                    np.uint8
                )
                for claimed, doc in documents.items():
                    result = verify_faces(doc, image)
                    rows.append(
                        {
                            "reference": claimed,
                            "probe": identity,
                            "angle": angle,
                            "alpha": alpha,
                            "beta": beta,
                            "same_identity": identity == claimed,
                            "cosine": result.data.cosine_similarity,
                            "decision": result.data.decision,
                            "status": result.status,
                        }
                    )
        print(f"face {identity}: {len(rows)} cumulative pairs", flush=True)
    eligible = [r for r in rows if r["cosine"] is not None]
    truth, scores = (
        [r["same_identity"] for r in eligible],
        [r["cosine"] for r in eligible],
    )
    metrics = binary_metrics(truth, [s >= threshold for s in scores])
    return {
        "scope": (
            "Illustrative transform stress test: TWO previously "
            "seen generated identities, shared source pixels. "
            "Correlated pairs, not biometric validation."
        ),
        "threshold": threshold,
        "threshold_calibrated": False,
        "total_pairs": len(rows),
        "eligible_pairs": len(eligible),
        "undetermined_pairs": len(rows) - len(eligible),
        "metrics_on_eligible_only": metrics,
        "FAR": metrics["false_positive_rate"],
        "FRR": metrics["false_negative_rate"],
        "roc": roc_points(truth, scores),
        "rows": rows,
        "upstream_0_363_comparison": binary_metrics(
            truth, [s >= 0.363 for s in scores]
        ),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--section", choices=["all", "system", "ocr", "tamper", "face"], default="all"
    )
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "phase6")
    args = parser.parse_args()
    cv2.setNumThreads(PROTOCOL["opencv_threads"])
    os.environ["OMP_THREAD_LIMIT"] = str(PROTOCOL["tesseract_thread_limit"])
    sections = {
        "system": system_eval,
        "ocr": ocr_eval,
        "tamper": tamper_eval,
        "face": face_eval,
    }
    for name, evaluate in sections.items():
        if args.section not in ("all", name):
            continue
        started = time.perf_counter()
        result = evaluate()
        save(
            args.output / f"{name}.json",
            {
                "provenance": provenance(),
                "elapsed_s": time.perf_counter() - started,
                **result,
            },
        )
        print(f"saved {name}.json", flush=True)


if __name__ == "__main__":
    main()
