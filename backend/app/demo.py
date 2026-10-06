"""Clearly marked fictional documents; never a real passport template."""

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from app.layers.l1_ocr.mrz import check_digit


@dataclass(frozen=True)
class SyntheticIdentity:
    surname: str = "EXAMPLE"
    given_names: str = "ALEX"
    number: str = "Z9000000"
    country: str = "UTO"
    dob: str = "1988-04-12"
    expiry: str = "2031-10-03"
    issue: str = "2021-10-04"
    gender: str = "X"


def build_mrz(identity: SyntheticIdentity, fmt: str = "TD3") -> list[str]:
    number = identity.number.ljust(9, "<")
    if len(number) != 9:
        raise ValueError(
            "Synthetic MRZ generator supports numbers up to nine characters."
        )
    dob = date.fromisoformat(identity.dob).strftime("%y%m%d")
    expiry = date.fromisoformat(identity.expiry).strftime("%y%m%d")
    name = (
        identity.surname.replace(" ", "<")
        + "<<"
        + identity.given_names.replace(" ", "<")
    )
    country = identity.country
    if len(country) != 3 or identity.gender not in {"M", "F", "X", "<"}:
        raise ValueError("Invalid synthetic country or sex marker.")
    sex = identity.gender if identity.gender in {"M", "F"} else "<"
    if fmt == "TD1":
        a = "I<" + country + number + check_digit(number) + "<" * 15
        b = (
            dob
            + check_digit(dob)
            + sex
            + expiry
            + check_digit(expiry)
            + country
            + "<" * 11
        )
        b += check_digit(a[5:30] + b[:7] + b[8:15] + b[18:29])
        return [a, b, name[:30].ljust(30, "<")]
    if fmt not in {"TD2", "TD3"}:
        raise ValueError("Unsupported MRZ format.")
    width = 44 if fmt == "TD3" else 36
    a = (
        ("P<" if fmt == "TD3" else "I<")
        + country
        + name[: width - 5].ljust(width - 5, "<")
    )
    b = (
        number
        + check_digit(number)
        + country
        + dob
        + check_digit(dob)
        + sex
        + expiry
        + check_digit(expiry)
    )
    b += "<" * (14 if fmt == "TD3" else 7)
    if fmt == "TD3":
        b += check_digit(b[28:42])
    b += check_digit(b[:10] + b[13:20] + b[21:])
    return [a, b]


def _font(size: int, mono: bool = False) -> ImageFont.FreeTypeFont:
    candidates = (
        []
        if mono
        else [
            r"C:\Windows\Fonts\arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
    )
    for path in candidates + [
        r"C:\Windows\Fonts\cour.ttf",
        r"C:\Windows\Fonts\consola.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/System/Library/Fonts/Menlo.ttc",
    ]:
        if Path(path).is_file():
            return ImageFont.truetype(path, size)
    raise RuntimeError("Install a monospace font: Consolas or DejaVu Sans Mono.")


def generate_document(
    identity: SyntheticIdentity | None = None,
    variant: str = "genuine",
) -> tuple[bytes, dict]:
    identity = identity or SyntheticIdentity()
    if variant not in {
        "genuine",
        "dob_altered",
        "checksum_failed",
        "blurred",
        "perspective",
    }:
        raise ValueError("Unsupported synthetic variant.")
    lines = build_mrz(identity)
    if variant == "checksum_failed":
        lines[1] = lines[1][:-1] + str((int(lines[1][-1]) + 1) % 10)
    visible_dob = "1998-04-12" if variant == "dob_altered" else identity.dob
    fields = {
        "name": f"{identity.surname} {identity.given_names}",
        "number": identity.number,
        "nationality": identity.country,
        "dob": visible_dob,
        "expiry": identity.expiry,
        "issue": identity.issue,
        "gender": identity.gender,
    }
    image = Image.new("RGB", (1600, 1000), (238, 241, 239))
    draw = ImageDraw.Draw(image)
    draw.rectangle((12, 12, 1587, 987), outline=(30, 60, 80), width=3)
    draw.text(
        (70, 45),
        "SYNTHETIC PASSPORT - NOT VALID FOR TRAVEL",
        fill=(22, 45, 60),
        font=_font(43),
    )
    draw.text(
        (70, 115),
        "FICTIONAL UTOPIA / HACKATHON TEST DOCUMENT",
        fill=(40, 60, 70),
        font=_font(30),
    )
    labels = [
        ("NAME", fields["name"]),
        ("PASSPORT NO", fields["number"]),
        ("NATIONALITY", fields["nationality"]),
        ("DOB", fields["dob"]),
        ("EXPIRY", fields["expiry"]),
        ("ISSUE DATE", fields["issue"]),
        ("SEX", fields["gender"]),
    ]
    for index, (label, value) in enumerate(labels):
        draw.text(
            (75, 205 + index * 72),
            f"{label}: {value}",
            fill=(20, 25, 30),
            font=_font(38),
        )
    # Geometric avatar: no real person's likeness is used.
    draw.rectangle(
        (1200, 210, 1510, 670), fill=(213, 222, 225), outline=(60, 80, 90), width=3
    )
    draw.ellipse((1280, 260, 1430, 425), fill=(104, 139, 158))
    draw.rounded_rectangle((1235, 445, 1475, 620), radius=55, fill=(104, 139, 158))
    draw.text((1208, 680), "TEST AVATAR", fill=(30, 50, 60), font=_font(28))
    draw.text(
        (75, 755), "SPECIMEN / GENERATED DATA ONLY", fill=(45, 65, 75), font=_font(28)
    )
    for index, line in enumerate(lines):
        draw.text(
            (65, 825 + index * 65), line, fill=(10, 15, 20), font=_font(51, mono=True)
        )
    array = cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2BGR)
    if variant == "blurred":
        array = cv2.GaussianBlur(array, (45, 45), 12)
    if variant == "perspective":
        source = np.float32([[0, 0], [1599, 0], [1599, 999], [0, 999]])
        target = np.float32([[120, 110], [1640, 65], [1710, 1110], [80, 1140]])
        transform = cv2.getPerspectiveTransform(source, target)
        array = cv2.warpPerspective(
            array, transform, (1800, 1250), borderValue=(40, 45, 50)
        )
    success, encoded = cv2.imencode(".png", array)
    if not success:
        raise RuntimeError("Synthetic image encoding failed.")
    return encoded.tobytes(), {
        "synthetic": True,
        "variant": variant,
        "reference_date": "2026-10-03",
        "mrz_lines": lines,
        "viz_fields": fields,
        "expected": {
            "dob_mismatch": variant == "dob_altered",
            "checksum_failure": variant == "checksum_failed",
            "needs_rescan": variant == "blurred",
        },
    }
