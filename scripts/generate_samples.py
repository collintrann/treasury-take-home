"""Render synthetic test labels into samples/ plus a matching batch CSV.

Each label targets one rule from the stakeholder interviews, so the demo and
the tests cover the cases agents actually care about.

    python scripts/generate_samples.py
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "samples"

FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")
SERIF_BOLD = FONT_DIR / "DejaVuSerif-Bold.ttf"
SERIF = FONT_DIR / "DejaVuSerif.ttf"
SANS = FONT_DIR / "DejaVuSans.ttf"
SANS_BOLD = FONT_DIR / "DejaVuSans-Bold.ttf"

BODY = (
    "(1) According to the Surgeon General, women should not drink alcoholic beverages during "
    "pregnancy because of the risk of birth defects. (2) Consumption of alcoholic beverages "
    "impairs your ability to drive a car or operate machinery, and may cause health problems."
)


@dataclass
class Label:
    filename: str
    purpose: str
    # what's printed on the label
    brand: str
    class_type: str
    abv: str
    net: str
    producer: str
    country: str = ""
    warning_header: str | None = "GOVERNMENT WARNING:"
    warning_body: str = BODY
    header_bold: bool = True
    distort: bool = False
    # what the application says (defaults to the label values = compliant)
    app: dict = field(default_factory=dict)
    # correct overall verdict for a reader that sees the label perfectly
    # (used by scripts/benchmark.py to score models)
    expected: str = "pass"


LABELS = [
    Label(
        "01_old_tom_compliant.png",
        "Fully compliant - everything matches",
        "OLD TOM DISTILLERY", "Kentucky Straight Bourbon Whiskey", "45% Alc./Vol. (90 Proof)", "750 mL",
        "Bottled by Old Tom Distillery, Bardstown, KY",
    ),
    Label(
        "02_stones_throw_case.png",
        "Brand in all caps on label, title case in application (Dave's example) - should pass with a note",
        "STONE'S THROW", "Small Batch Gin", "41.5% Alc./Vol.", "1 L",
        "Distilled by Stone's Throw Spirits Co., Portland, OR",
        app={"brand_name": "Stone's Throw"},
    ),
    Label(
        "03_title_case_warning.png",
        "'Government Warning' in title case (Jenny's example) - should fail",
        "RIVERBEND", "Straight Rye Whiskey", "50% Alc./Vol. (100 Proof)", "750 mL",
        "Riverbend Distilling, Louisville, KY",
        warning_header="Government Warning:",
        expected="fail",
    ),
    Label(
        "04_wrong_abv.png",
        "Label says 40% but application says 45% - should fail",
        "COPPER HOLLOW", "Blended Whiskey", "40% Alc./Vol. (80 Proof)", "750 mL",
        "Copper Hollow Spirits, Austin, TX",
        app={"alcohol_content": "45% Alc./Vol. (90 Proof)"},
        expected="fail",
    ),
    Label(
        "05_altered_warning.png",
        "Warning wording changed ('may cause health problems' -> 'can cause problems') - should fail",
        "NORTHERN LIGHTS", "Vodka", "40% Alc./Vol.", "750 mL",
        "Northern Lights Distillery, Fargo, ND",
        warning_body=BODY.replace("may cause health problems", "can cause problems"),
        expected="fail",
    ),
    Label(
        "06_warning_not_bold.png",
        "Warning lead-in not in bold - should fail",
        "HIGH DESERT", "Blanco Tequila", "40% Alc./Vol.", "750 mL",
        "Imported by High Desert Imports, Phoenix, AZ", country="Product of Mexico",
        header_bold=False,
        app={"country_of_origin": "Mexico"},
        expected="fail",
    ),
    Label(
        "07_angled_glare.png",
        "Compliant label photographed at an angle with glare - tests robustness",
        "OLD TOM DISTILLERY", "Kentucky Straight Bourbon Whiskey", "45% Alc./Vol. (90 Proof)", "750 mL",
        "Bottled by Old Tom Distillery, Bardstown, KY",
        distort=True,
    ),
    Label(
        "08_no_warning.png",
        "No government warning at all - should fail",
        "HARBOR LIGHT", "Spiced Rum", "35% Alc./Vol. (70 Proof)", "750 mL",
        "Harbor Light Rum Co., Charleston, SC",
        warning_header=None, warning_body="",
        expected="fail",
    ),
    Label(
        "09_imported_scotch.png",
        "Import with country of origin; net contents in cl vs mL in application - should pass",
        "GLEN ARDACH", "Single Malt Scotch Whisky", "43% Alc./Vol.", "70 cl",
        "Imported by Ardach Imports LLC, New York, NY", country="Product of Scotland",
        app={"net_contents": "700 mL", "country_of_origin": "Scotland"},
    ),
    # --- Subtle warning typos. These exist to catch a reader that silently
    # "corrects" what it sees, which would turn a violation into a false PASS.
    Label(
        "10_typo_surgeon_generel.png",
        "Warning misspells 'Surgeon Generel' - should fail",
        "BLUE HERON", "Dry Gin", "42% Alc./Vol.", "750 mL",
        "Blue Heron Distillers, Seattle, WA",
        warning_body=BODY.replace("Surgeon General", "Surgeon Generel"),
        expected="fail",
    ),
    Label(
        "11_typo_alcohol_beverages.png",
        "Warning says 'alcohol beverages' instead of 'alcoholic beverages' - should fail",
        "SILVER CREEK", "Straight Bourbon Whiskey", "46% Alc./Vol. (92 Proof)", "750 mL",
        "Silver Creek Distilling Co., Frankfort, KY",
        warning_body=BODY.replace("drink alcoholic beverages", "drink alcohol beverages"),
        expected="fail",
    ),
    Label(
        "12_missing_comma.png",
        "Warning drops the comma after 'machinery' - should fail; the subtlest deviation",
        "IRON GATE", "Dark Rum", "40% Alc./Vol. (80 Proof)", "750 mL",
        "Iron Gate Rum Works, Miami, FL",
        warning_body=BODY.replace("machinery, and", "machinery and"),
        expected="fail",
    ),
]


def _font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), size)


def _center(draw: ImageDraw.ImageDraw, y: int, text: str, font, width: int, fill="#1d1d1d") -> int:
    w = draw.textlength(text, font=font)
    draw.text(((width - w) / 2, y), text, font=font, fill=fill)
    return y + font.size + int(font.size * 0.45)


def _wrap_runs(draw, runs, x0, y, max_w, line_h):
    """Draw [(text, font), ...] as one wrapped paragraph, so the bold lead-in can sit inline."""
    x = x0
    for text, font in runs:
        for word in text.split():
            w = draw.textlength(word + " ", font=font)
            if x + w > x0 + max_w and x > x0:
                x, y = x0, y + line_h
            draw.text((x, y), word, font=font, fill="#1d1d1d")
            x += w
    return y + line_h


def render(label: Label) -> Image.Image:
    W, H = 1000, 1300
    img = Image.new("RGB", (W, H), "#f4ecd8")
    d = ImageDraw.Draw(img)
    d.rectangle([24, 24, W - 24, H - 24], outline="#6b4f2a", width=6)
    d.rectangle([40, 40, W - 40, H - 40], outline="#6b4f2a", width=2)

    y = 110
    y = _center(d, y, label.brand, _font(SERIF_BOLD, 76 if len(label.brand) < 16 else 62), W)
    y += 20
    d.line([200, y, W - 200, y], fill="#6b4f2a", width=3)
    y += 40
    y = _center(d, y, label.class_type, _font(SERIF, 40), W)
    y += 60
    y = _center(d, y, label.abv, _font(SANS_BOLD, 40), W)
    y = _center(d, y, label.net, _font(SANS_BOLD, 40), W)
    y += 50
    y = _center(d, y, label.producer, _font(SANS, 26), W)
    if label.country:
        y = _center(d, y, label.country, _font(SANS, 26), W)

    if label.warning_header or label.warning_body:
        body_font = _font(SANS, 22)
        head_font = _font(SANS_BOLD if label.header_bold else SANS, 22)
        runs = []
        if label.warning_header:
            runs.append((label.warning_header, head_font))
        runs.append((label.warning_body, body_font))
        _wrap_runs(d, runs, 80, H - 300, W - 160, 32)

    if label.distort:
        img = _photo_effects(img)
    return img


def _photo_effects(img: Image.Image) -> Image.Image:
    """Fake a phone photo: rotate, add a glare hotspot, slight blur."""
    img = img.rotate(7, resample=Image.BICUBIC, expand=True, fillcolor="#5a5a5a")
    glare = Image.new("L", img.size, 0)
    gd = ImageDraw.Draw(glare)
    cx, cy, r = int(img.width * 0.68), int(img.height * 0.3), int(img.width * 0.28)
    for i in range(r, 0, -4):
        gd.ellipse([cx - i, cy - i, cx + i, cy + i], fill=int(170 * (1 - i / r) ** 0.6))
    white = Image.new("RGB", img.size, "white")
    img = Image.composite(white, img, glare)
    return img.filter(ImageFilter.GaussianBlur(1.1))


def main() -> None:
    OUT.mkdir(exist_ok=True)
    rows = []
    for label in LABELS:
        render(label).save(OUT / label.filename)
        app = {
            "brand_name": label.brand,
            "class_type": label.class_type,
            "alcohol_content": label.abv,
            "net_contents": label.net,
            "producer_name_address": label.producer,
            "country_of_origin": label.country,
        } | label.app
        rows.append(
            {"filename": label.filename, **app, "expected_result": label.expected, "what_this_tests": label.purpose}
        )
        print("wrote", label.filename)

    with open(OUT / "batch.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print("wrote batch.csv")


if __name__ == "__main__":
    main()
