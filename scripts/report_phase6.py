"""Render measured evaluation JSON as shareable figures and a concise report."""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports" / "phase6"
TEAL, ORANGE = "#246659", "#bf672a"
plt.rcParams.update(
    {"font.size": 11, "axes.spines.top": False, "axes.spines.right": False}
)


def pct(value):
    return "undefined" if value is None else f"{value * 100:.2f}%"


def save(fig, name):
    fig.savefig(OUT / f"{name}.png", dpi=170, bbox_inches="tight")
    fig.savefig(OUT / f"{name}.svg", bbox_inches="tight")
    plt.close(fig)


def main():
    reports = {
        n: json.loads((OUT / f"{n}.json").read_text())
        for n in ("ocr", "tamper", "face", "system")
    }
    hashes = {r["provenance"]["protocol_sha256"] for r in reports.values()}
    if len(hashes) != 1:
        raise ValueError("Evaluation sections use different protocols.")
    ocr, tamper, face, system = (
        reports[n] for n in ("ocr", "tamper", "face", "system")
    )
    fresh = tamper["by_cohort"]["fresh_groups_same_generator"]
    fig, axes = plt.subplots(1, 2, figsize=(10, 4.6), layout="constrained")
    for ax, detector in zip(axes, ("cnn", "classical"), strict=True):
        m = fresh[detector]["confusion_matrix"]
        a = np.array([[m["tn"], m["fp"]], [m["fn"], m["tp"]]])
        ax.imshow(a, cmap="BuGn", vmin=0, vmax=80)
        for (i, j), count in np.ndenumerate(a):
            ax.text(
                j,
                i,
                str(count),
                ha="center",
                va="center",
                fontsize=22,
                color="white" if count > 40 else "#122f31",
            )
        ax.set(
            xticks=[0, 1],
            yticks=[0, 1],
            xticklabels=["Clean", "Tampered"],
            yticklabels=["Clean", "Tampered"],
            xlabel="Predicted",
            ylabel="Ground truth",
            title="Frozen U-Net" if detector == "cnn" else "Classical index >= 0.55",
        )
    fig.suptitle(
        (
            "Fresh procedural groups: 100 images / 20 groups\nSame "
            "generator and layouts as development; synthetic "
            "only"
        ),
        fontsize=13,
    )
    save(fig, "tamper_confusion")
    attacks = [a for a in fresh["cnn"]["per_attack"] if a != "clean"]
    fig, ax = plt.subplots(figsize=(9, 4.5), layout="constrained")
    x = np.arange(len(attacks))
    for offset, detector, color in [(-0.18, "cnn", TEAL), (0.18, "classical", ORANGE)]:
        values = [fresh[detector]["per_attack"][a]["mean_iou"] for a in attacks]
        bars = ax.bar(x + offset, values, width=0.36, label=detector, color=color)
        ax.bar_label(bars, fmt="%.3f", padding=3)
    ax.set(
        xticks=x,
        xticklabels=[a.replace("_", " ") for a in attacks],
        ylim=(0, 1),
        ylabel="Mean localization IoU",
        title="Localization on 20 synthetic examples per attack",
    )
    ax.legend()
    save(fig, "tamper_iou")
    fig, ax = plt.subplots(figsize=(6.8, 5.4), layout="constrained")
    points = face["roc"]
    ax.plot(
        [p["fpr"] for p in points],
        [p["tpr"] for p in points],
        color=TEAL,
        marker="o",
        label="Observed transformed pairs",
    )
    ax.plot([0, 1], [0, 1], "--", color="gray", linewidth=1)
    ax.scatter(
        [face["FAR"]],
        [1 - face["FRR"]],
        color=ORANGE,
        s=75,
        zorder=3,
        label=f"Configured threshold {face['threshold']}",
    )
    ax.set(
        xlim=(-0.03, 1.03),
        ylim=(-0.03, 1.03),
        xlabel="False accept rate (eligible pairs)",
        ylabel="True accept rate (eligible pairs)",
        title=(
            f"Illustrative face ROC: {face['eligible_pairs']} "
            f"correlated pairs\nOnly TWO generated identities, "
            f"already used for tuning"
        ),
    )
    ax.legend(loc="lower right", fontsize=9)
    save(fig, "face_roc")
    fig, ax = plt.subplots(figsize=(9, 4.5), layout="constrained")
    rows = system["rows"]
    times = [r["wall_ms"] / 1000 for r in rows]
    bars = ax.bar(range(len(rows)), times, color=[ORANGE] + [TEAL] * (len(rows) - 1))
    ax.bar_label(bars, fmt="%.2f", padding=3)
    ax.set(
        xticks=range(len(rows)),
        xticklabels=["cold\ngenuine"]
        + [
            f"{r['scenario'].replace('_', ' ')}\nrepeat {r['repeat']}" for r in rows[1:]
        ],
        ylabel="Wall time (seconds)",
        ylim=(0, max(times) * 1.22),
        title=(
            "Sequential L0-L5 CPU timing, 1600 x 1000 document\nOpenCV "
            "/ Tesseract limit: 2 threads; excludes HTTP, audit "
            "and UI"
        ),
    )
    ax.tick_params(axis="x", labelsize=9)
    save(fig, "latency")
    fields = [f for f in ocr["summary"]["viz"] if f != "overall"]
    fig, ax = plt.subplots(figsize=(8.8, 4.5), layout="constrained")
    x = np.arange(len(fields))
    for offset, channel, color in [(-0.18, "viz", TEAL), (0.18, "mrz", ORANGE)]:
        bars = ax.bar(
            x + offset,
            [ocr["summary"][channel][f]["accuracy"] * 100 for f in fields],
            width=0.36,
            label=channel.upper(),
            color=color,
        )
        ax.bar_label(bars, fmt="%.1f", padding=3, fontsize=9)
    ax.set(
        xticks=x,
        xticklabels=fields,
        ylim=(0, 112),
        ylabel="Exact field accuracy (%)",
        title=(
            "26 synthetic TD3 document images\nMissing fields "
            "and quality-gated scans count as incorrect"
        ),
    )
    ax.legend(loc="lower right")
    save(fig, "ocr_fields")
    lines = [
        "# Phase 6 measured evaluation",
        "",
        (
            "Synthetic development evidence only. No real-document "
            "or biometric accuracy claim."
        ),
        "",
        "## Protocol and sample boundaries",
        "",
        (
            "- OCR: 8 existing fixtures + 18 new values/conditions, "
            "same TD3 layout. TD1/TD2 parser tests are separate "
            "from image OCR metrics."
        ),
        (
            "- Tampering: frozen checkpoint, 35 original held-out "
            "images replayed for reproducibility; 100 fresh "
            "images from 20 new source groups. Same generator/layouts/attack "
            "families."
        ),
        (
            "- Face: 32 correlated transformed pairs from two "
            "generated identities already used for threshold "
            "selection. No independent biometric test cohort."
        ),
        (
            "- Latency: one process-cold call + six sequential "
            "warm calls. Timing excludes fixture generation, "
            "HTTP, audit and UI. Two threads configured for "
            "OpenCV and Tesseract."
        ),
        "",
        "## OCR",
        "",
        "| Channel | Exact correct / fields | Accuracy |",
        "|---|---:|---:|",
    ]
    for ch in ("viz", "mrz"):
        s = ocr["summary"][ch]["overall"]
        lines.append(
            f"| {ch.upper()} | {s['correct']} / {s['total']} | {pct(s['accuracy'])} |"
        )
    checks = ocr["summary"]["mrz_digits"]
    lines += [
        "",
        (
            f"Valid-MRZ documents: {checks['all_checks_pass_count']}/"
            f"{checks['valid_document_count']} "
            f"all-check pass ({pct(checks['end_to_end_pass_rate'])}); "
            f"parsed-only rate {pct(checks['conditional_parsed_pass_rate'])} "
            f"on {checks['parsed_valid_documents']} documents."
        ),
        (
            f"Deliberately invalid MRZ: {checks['invalid_flagged']}/"
            f"{checks['invalid_documents']} "
            f"flagged. Quality rescan count: {ocr['summary']['rescan_count']}."
        ),
        "",
        "![OCR field accuracy](ocr_fields.png)",
        "",
        "## Tampering",
        "",
        ("| Cohort / detector | Precision | Recall | F1 | TN / FP / FN / TP |"),
        "|---|---:|---:|---:|---|",
    ]
    for cohort, detectors in tamper["by_cohort"].items():
        for detector, m in detectors.items():
            cm = m["confusion_matrix"]
            lines.append(
                f"| {cohort} / {detector} | {pct(m['precision'])} "
                f"| {pct(m['recall'])} | {pct(m['f1'])} | {cm['tn']} "
                f"/ {cm['fp']} / {cm['fn']} / {cm['tp']} |"
            )
    lines += [
        "",
        (
            "| Fresh attack | CNN flagged / 20 | CNN precision* "
            "| CNN recall | CNN F1* | CNN IoU | Classical IoU "
            "|"
        ),
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for a in attacks:
        c, b = fresh["cnn"]["per_attack"][a], fresh["classical"]["per_attack"][a]
        m = c["versus_shared_clean_controls"]
        lines.append(
            f"| {a} | {c['flagged']} / {c['count']} | {pct(m['precision'])} "
            f"| {pct(m['recall'])} | {pct(m['f1'])} | {c['mean_iou']:.3f} "
            f"| {b['mean_iou']:.3f} |"
        )
    lines += [
        "",
        (
            "*Per-attack precision/F1 compare each attack against "
            "the SAME 20 clean controls. Do not sum these overlapping "
            "cohorts. Image CNN flag = >=2% pixels at activation "
            ">=0.5; baseline flag = classical index >=0.55. "
            "Localization uses CNN activation >=0.5 and baseline "
            "uint8 map >=128. Clean-clean IoU is undefined."
        ),
        "",
        "![Confusion matrices](tamper_confusion.png)",
        "",
        "![Localization IoU](tamper_iou.png)",
        "",
        "## Face",
        "",
        (
            f"Configured threshold: {face['threshold']}; eligible "
            f"{face['eligible_pairs']}/{face['total_pairs']}, "
            f"undetermined {face['undetermined_pairs']}. Illustrative "
            f"FAR={pct(face['FAR'])}, FRR={pct(face['FRR'])} "
            f"on eligible pairs only."
        ),
        (
            "These values cannot establish a deployment threshold "
            "or FAR/FRR guarantee. Positive pairs share pixels "
            "and negative identities are already known. No "
            "population confidence interval is justified."
        ),
        "",
        "![Illustrative face ROC](face_roc.png)",
        "",
        "## System latency",
        "",
        (
            f"Process-cold: {system['cold']['wall_ms'] / 1000:.2f}s. "
            f"Warm median: {system['warm']['median_ms'] / 1000:.2f}s; "
            f"descriptive p95: {system['warm']['p95_ms'] / 1000:.2f}s "
            f"(n={system['warm']['n']}, linear interpolation)."
        ),
        (
            "Phase 5 browser measurements (92-124s cold, 22.50s "
            "warm) remain valid observations under different "
            "load/configuration. This controlled profile does "
            "not prove browser or checkpoint throughput."
        ),
        "",
        "![Latency](latency.png)",
        "",
        "## OCR errors (exact rows preserved in ocr.json)",
        "",
    ]
    for row in ocr["rows"]:
        failures = [
            f"{channel}.{field}: {v['observed']!r} vs {v['expected']!r}"
            for channel in ("viz", "mrz")
            for field, v in row[channel].items()
            if not v["match"]
        ]
        if failures:
            lines.append(
                f"- {row['scenario']} ({row['status']}): " + "; ".join(failures)
            )
    lines += [
        "",
        "## Interpretation and next engineering work",
        "",
        (
            "- A clean synthetic card can trigger classical "
            "signals because printed features and compression "
            "are not specific to tampering. PNG evaluation "
            "inputs lack ELA/JPEG-history evidence. Missing "
            "baseline detections are reported, not retuned "
            "away."
        ),
        (
            "- Copy-move localization and misses should be "
            "judged per attack. Fixed procedural patterns are "
            "easier than unseen document layouts. The CNN remains "
            "excluded from risk scoring."
        ),
        (
            "- MRZ check-digit pass measures consistency, not "
            "authentic issuance. DOB alteration can preserve "
            "a valid MRZ while disagreeing with VIZ."
        ),
        (
            "- Photo-replacement demo tests disagreement with "
            "the supplied reference face; forensic localization "
            "may be inconclusive. It does not prove a detected "
            "splice."
        ),
        (
            "- Next validation needs authorized data across "
            "devices/layouts, independent face identities/captures, "
            "threshold calibration on validation only, and "
            "a locked external test set."
        ),
        (
            "- Production gaps: verified liveness, genuine "
            "stamp models/templates, chip trust validation, "
            "officer authentication, external audit anchoring, "
            "retention governance and container runtime validation."
        ),
        "",
        "## Reproduction",
        "",
        "```powershell",
        ".\\.venv\\Scripts\\python.exe scripts/evaluate_phase6.py",
        ".\\.venv\\Scripts\\python.exe scripts/report_phase6.py",
        "```",
        "",
        (
            "Raw section JSON includes sample rows, config/model/protocol "
            "hashes, environment versions and timestamps. Re-running "
            "overwrites reports, never trains or tunes models. "
            "Keep prior output directories when comparing runs."
        ),
    ]
    (OUT / "evaluation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Report and five PNG/SVG figures: {OUT}")


if __name__ == "__main__":
    main()
