"""Create a one-page PDF from measured local evaluation results."""

import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "reports" / "phase6"
OUT = ROOT / "output" / "pdf" / "solution_overview.pdf"


def main():
    ocr = json.loads((DATA / "ocr.json").read_text())
    tamper = json.loads((DATA / "tamper.json").read_text())
    system = json.loads((DATA / "system.json").read_text())
    cnn = tamper["by_cohort"]["fresh_groups_same_generator"]["cnn"]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    teal = colors.HexColor("#174d48")
    styles.add(
        ParagraphStyle(
            "BodyCustom",
            fontName="Helvetica",
            fontSize=9.6,
            leading=13.2,
            textColor=colors.HexColor("#293e42"),
            spaceAfter=7,
        )
    )
    styles.add(
        ParagraphStyle(
            "SectionCustom",
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=14,
            textColor=teal,
            spaceBefore=8,
            spaceAfter=4,
        )
    )
    styles.add(
        ParagraphStyle(
            "MetricCustom",
            fontName="Helvetica-Bold",
            fontSize=20,
            leading=25,
            textColor=teal,
            alignment=TA_CENTER,
        )
    )
    styles.add(
        ParagraphStyle(
            "SmallCustom",
            fontName="Helvetica",
            fontSize=8,
            leading=11,
            textColor=colors.HexColor("#526769"),
            alignment=TA_CENTER,
        )
    )
    story = [
        Paragraph(
            "SENTINEL",
            ParagraphStyle(
                "Brand",
                fontName="Helvetica-Bold",
                fontSize=12,
                textColor=teal,
                spaceAfter=10,
            ),
        ),
        Paragraph(
            "AI-Based Identity &amp;<br/>Document Screening",
            ParagraphStyle(
                "TitleCustom",
                fontName="Helvetica-Bold",
                fontSize=25,
                leading=29,
                textColor=teal,
                spaceAfter=8,
            ),
        ),
        Paragraph(
            "Hackathon solution overview / Synthetic demonstration",
            styles["BodyCustom"],
        ),
        Spacer(1, 7),
    ]
    values = [
        (
            f"{ocr['summary']['viz']['overall']['accuracy'] * 100:.2f}%",
            "VIZ exact field accuracy<br/>150 / 156 fields, synthetic",
        ),
        (f"{cnn['f1'] * 100:.2f}%", "Tamper CNN F1<br/>100 fresh procedural images"),
        (
            f"{system['warm']['median_ms'] / 1000:.2f} s",
            "Warm CPU median<br/>6 calls, pipeline only",
        ),
    ]
    table = Table(
        [
            [Paragraph(v, styles["MetricCustom"]) for v, _ in values],
            [Paragraph(label, styles["SmallCustom"]) for _, label in values],
        ],
        colWidths=[169] * 3,
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#eef3ef")),
                ("TOPPADDING", (0, 0), (-1, 0), 9),
                ("BOTTOMPADDING", (0, -1), (-1, -1), 10),
            ]
        )
    )
    story += [table, Spacer(1, 8)]
    sections = [
        (
            "Problem aur proposed impact",
            (
                "Document fields, face evidence aur tamper signals ko alag-alag check "
                "karna review ko slow aur inconsistent bana sakta hai. Sentinel ek "
                "officer workspace mein evidence aur reasons dikhata hai. Intended "
                "benefit: more consistent review. Real checkpoint impact abhi measure "
                "nahi hua; officer hi final decision record karta hai."
            ),
        ),
        (
            "Layer-wise implementation",
            (
                "<b>L0:</b> OpenCV crop, perspective aur quality gate. "
                "<b>L1:</b> Tesseract MRZ/VIZ, raw + corrected fields. "
                "<b>L2:</b> check digits, cross-field/date rules, fictional lookup. "
                "<b>L3:</b> classical heatmap aur separate synthetic U-Net. "
                "<b>L4:</b> YuNet/SFace comparison, inconclusive liveness evidence. "
                "<b>L5:</b> YAML-weighted points, missing evidence aur reasons. "
                "<b>L6:</b> React review, human decisions aur hash-chain audit. "
                "L2/L3/L4 parallel run hote hain."
            ),
        ),
        (
            "Engineering contribution aur feasibility",
            (
                "Prototype raw OCR corrections ko traceable rakhta hai, heatmaps ko "
                "explainable points se connect karta hai, aur unavailable evidence ko "
                "explicitly dikhata hai. Synthetic CNN risk score se excluded hai. "
                "FastAPI, React/Vite/Tailwind, SQLite/SQLAlchemy aur CPU "
                "inference local laptop par tested hain. Separate functions "
                "aur REST routes module demos allow karte hain. Docker config "
                "ready hai; engine runtime unverified hai."
            ),
        ),
        (
            "Evaluation se kya seekha",
            (
                "26 synthetic TD3 images par MRZ field accuracy 90.38%, valid-document "
                "all-check pass 22/25. Fresh CNN confusion: TN 16, FP 4, FN 7, TP 73. "
                "Copy-move IoU 0.179; classical recall 1.25% at fixed 0.55 index. "
                "Face ROC sirf two known generated identities ke 32 correlated pairs "
                "par illustrative hai. Process-cold 12.51 s; warm median "
                "above excludes "
                "HTTP, audit and UI. Browser performance varies with system load."
            ),
        ),
        (
            "Privacy aur deployment limits",
            (
                "Uploaded images, OCR identity values aur face embeddings persist nahi "
                "hote. Opt-in audit scores, hashes, officer labels aur notes "
                "store karta "
                "hai. Owner chain rewrite kar sakta hai; external checkpoint chahiye. "
                "No production auth, verified liveness, genuine issuer stamp model or "
                "chip trust validation. Synthetic-only metrics real-world accuracy ya "
                "DPDP compliance establish nahi karte."
            ),
        ),
        (
            "Next validation",
            (
                "Authorized diverse layouts/devices, independent face captures, "
                "validation-only threshold calibration, locked external testing aur "
                "retention/access controls production se pehle required hain."
            ),
        ),
    ]
    for heading, body in sections:
        story += [
            Paragraph(heading, styles["SectionCustom"]),
            Paragraph(body, styles["BodyCustom"]),
        ]

    def footer(canvas, doc):
        canvas.setStrokeColor(colors.HexColor("#d8e2dd"))
        canvas.line(44, 38, A4[0] - 44, 38)
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#526769"))
        canvas.drawString(
            44,
            26,
            "Evidence: reports/phase6/evaluation.md | Protocol: phase6-frozen-v1",
        )
        canvas.drawRightString(A4[0] - 44, 26, "03 OCT 2026 / 1")

    SimpleDocTemplate(
        str(OUT),
        pagesize=A4,
        rightMargin=44,
        leftMargin=44,
        topMargin=34,
        bottomMargin=48,
        title="Sentinel - Solution Overview",
        author="Synthetic Document Screening Project",
    ).build(story, onFirstPage=footer, onLaterPages=footer)
    from pypdf import PdfReader

    if len(PdfReader(OUT).pages) != 1:
        raise RuntimeError("Overview exceeded one page; revise layout before delivery.")
    print(OUT)


if __name__ == "__main__":
    main()
