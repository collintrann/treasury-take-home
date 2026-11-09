"""Build the review queue in samples/queue/: label images plus applications.json.

The queue mixes two kinds of application.

* Generated: one drawn label per case. Each case knows exactly what it
  printed, so it also records the correct overall result
  (``expected_overall``) for the tests and the benchmark.
* Real: a random draw of approved applications from the TTB test set in
  samples/ttb/ (see scripts/build_ttb_testset.py), with all their label
  images. Their right answer isn't known in advance, so ``expected_overall``
  is None.

    python scripts/generate_samples.py
"""

from __future__ import annotations

import datetime as dt
import json
import random
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.models import MAX_LABEL_IMAGES, Application, Overall, ProductType, QueueEntry  # noqa: E402
from app.queue import MANIFEST, QUEUE_DIR  # noqa: E402
from app.warning import BODY, HEADER  # noqa: E402

# DejaVu on Linux, Supplemental fonts on macOS. Images differ slightly between them.
_FONT_CANDIDATES = {
    "serif_bold": ["/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf", "/System/Library/Fonts/Supplemental/Georgia Bold.ttf"],
    "serif": ["/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf", "/System/Library/Fonts/Supplemental/Georgia.ttf"],
    "sans": ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf"],
    "sans_bold": ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf"],
}


def _find_font(kind: str) -> Path:
    for candidate in _FONT_CANDIDATES[kind]:
        if Path(candidate).exists():
            return Path(candidate)
    raise SystemExit(f"No {kind} font found. Install DejaVu fonts (apt-get install fonts-dejavu-core).")


SERIF_BOLD, SERIF, SANS, SANS_BOLD = (_find_font(k) for k in ("serif_bold", "serif", "sans", "sans_bold"))

Photo = Literal["flat", "angled_glare", "angled_glare_left", "blurry"]


@dataclass
class Printed:
    """What is printed on the label. An empty ``abv`` means no alcohol statement."""

    brand: str
    class_type: str
    abv: str
    net: str
    producer: str
    country: str = ""
    warning_header: str | None = HEADER
    warning_body: str = BODY
    header_bold: bool = True
    photo: Photo = "flat"

    @property
    def has_warning(self) -> bool:
        return bool(self.warning_header or self.warning_body)


@dataclass
class Case:
    id: str
    submitted_at: str
    applicant: str
    product_type: ProductType
    scenario: str
    expected_overall: Overall
    printed: Printed
    application: dict = field(default_factory=dict)  # where the application differs from the default

    def entry(self) -> QueueEntry:
        return QueueEntry(
            id=self.id,
            submitted_at=dt.date.fromisoformat(self.submitted_at),
            applicant=self.applicant,
            product_type=self.product_type,
            images=[f"{self.id}.png"],
            application=default_application(self.printed).model_copy(update=self.application),
            expected_overall=self.expected_overall,
            scenario=self.scenario,
        )


_PRODUCER_ROLE = re.compile(r"^(?:\w+ )*?(?:and \w+ )?by ", re.IGNORECASE)


def default_application(p: Printed) -> Application:
    """What a matching application says: the label's values, without label wording like 'Bottled by'."""
    return Application(
        brand_name=p.brand,
        class_type=p.class_type,
        alcohol_content=p.abv,
        net_contents=p.net,
        producer_name_address=_PRODUCER_ROLE.sub("", p.producer),
        country_of_origin=p.country.removeprefix("Product of "),
    )


S, W, B = "distilled_spirits", "wine", "malt_beverage"

CASES = [
    Case("COLA-26-0001", "2026-10-02", "Old Tom Distillery LLC", S, "Clean bourbon label.", "pass",
         Printed("OLD TOM DISTILLERY", "Kentucky Straight Bourbon Whiskey", "45% Alc./Vol. (90 Proof)", "750 mL",
                 "Bottled by Old Tom Distillery, Bardstown, KY")),
    Case("COLA-26-0002", "2026-10-05", "Marrow Creek Vineyards", W, "Clean wine over 14%, so the alcohol statement is required and present.", "pass",
         Printed("MARROW CREEK", "Cabernet Sauvignon", "Alc. 14.5% by Vol.", "750 mL",
                 "Produced and bottled by Marrow Creek Vineyards, Paso Robles, CA")),
    Case("COLA-26-0003", "2026-10-06", "Switchback Hollow Brewing Co.", B, "Clean beer can in US units (12 FL OZ).", "pass",
         Printed("SWITCHBACK HOLLOW", "India Pale Ale", "6.8% ALC/VOL", "12 FL OZ",
                 "Brewed and canned by Switchback Hollow Brewing Co., Asheville, NC")),
    Case("COLA-26-0004", "2026-10-08", "Stone's Throw Spirits Co.", S, "Brand in capitals on the label, title case in the application.", "pass",
         Printed("STONE'S THROW", "Small Batch Gin", "41.5% Alc./Vol. (83 Proof)", "1 L",
                 "Distilled by Stone's Throw Spirits Co., Portland, OR"),
         {"brand_name": "Stone's Throw"}),
    Case("COLA-26-0005", "2026-10-09", "Copper Hollow Spirits", S, "Wrong alcohol content: label 40%, application 45%.", "fail",
         Printed("COPPER HOLLOW", "Blended Whiskey", "40% Alc./Vol. (80 Proof)", "750 mL",
                 "Bottled by Copper Hollow Spirits, Austin, TX"),
         {"alcohol_content": "45% Alc./Vol. (90 Proof)"}),
    Case("COLA-26-0006", "2026-10-12", "Larkspur Bend Cellars", W, "Wine at 11.5% with no alcohol statement on the label, which is allowed.", "pass",
         Printed("LARKSPUR BEND", "Dry Riesling", "", "750 mL",
                 "Vinted and bottled by Larkspur Bend Cellars, Hood River, OR"),
         {"alcohol_content": "11.5% Alc./Vol."}),
    Case("COLA-26-0007", "2026-10-13", "Ferrous Ox Brewing", B, "Beer with no alcohol statement on the label, which is allowed.", "pass",
         Printed("FERROUS OX", "Lager", "", "16 FL. OZ.", "Brewed by Ferrous Ox Brewing, Duluth, MN"),
         {"alcohol_content": "4.2% Alc./Vol."}),
    Case("COLA-26-0008", "2026-10-14", "Ardach Imports LLC", S, "Imported Scotch with country of origin; 70 cl on the label, 700 mL in the application.", "pass",
         Printed("GLEN ARDACH", "Single Malt Scotch Whisky", "43% Alc./Vol.", "70 cl",
                 "Imported by Ardach Imports LLC, New York, NY", country="Product of Scotland"),
         {"net_contents": "700 mL"}),
    Case("COLA-26-0009", "2026-10-15", "Calloway Flats Winery", W, "Wrong net contents: label 375 mL, application 750 mL.", "fail",
         Printed("CALLOWAY FLATS", "Merlot", "13.5% Alc./Vol.", "375 mL",
                 "Produced and bottled by Calloway Flats Winery, Lodi, CA"),
         {"net_contents": "750 mL"}),
    Case("COLA-26-0010", "2026-10-16", "Riverbend Distilling", S, "Warning lead-in in title case ('Government Warning:').", "fail",
         Printed("RIVERBEND", "Straight Rye Whiskey", "50% Alc./Vol. (100 Proof)", "750 mL",
                 "Distilled and bottled by Riverbend Distilling, Louisville, KY", warning_header="Government Warning:")),
    Case("COLA-26-0011", "2026-10-19", "Tidewater Gull Brewing", B, "Warning lead-in not in bold.", "needs_review",
         Printed("TIDEWATER GULL", "American Pale Ale", "5.4% ALC/VOL", "12 FL OZ",
                 "Brewed by Tidewater Gull Brewing, Wilmington, NC", header_bold=False)),
    Case("COLA-26-0012", "2026-10-20", "Ocaso Selections", W, "Imported Spanish wine with country of origin.", "pass",
         Printed("OCASO", "Rioja", "13.5% Alc./Vol.", "750 mL",
                 "Imported by Ocaso Selections, Miami, FL", country="Product of Spain")),
    Case("COLA-26-0013", "2026-10-21", "Northern Lights Distillery", S, "Clean label photographed at an angle with glare.", "pass",
         Printed("NORTHERN LIGHTS", "Vodka", "40% Alc./Vol. (80 Proof)", "750 mL",
                 "Distilled by Northern Lights Distillery, Fargo, ND", photo="angled_glare")),
    Case("COLA-26-0014", "2026-10-22", "Saltmarsh Estate Winery", W, "Warning wording changed ('can cause problems').", "fail",
         Printed("SALTMARSH ESTATE", "Sauvignon Blanc", "12.5% Alc./Vol.", "750 mL",
                 "Produced and bottled by Saltmarsh Estate Winery, Cutchogue, NY",
                 warning_body=BODY.replace("may cause health problems", "can cause problems"))),
    Case("COLA-26-0015", "2026-10-23", "Prairie Kiln Brewing", B, "Warning lead-in without the colon.", "fail",
         Printed("PRAIRIE KILN", "Hefeweizen", "5.1% ALC/VOL", "12 FL OZ",
                 "Brewed by Prairie Kiln Brewing, Wichita, KS", warning_header="GOVERNMENT WARNING")),
    Case("COLA-26-0016", "2026-10-26", "Salt Harbor Rum Co.", S, "Brand on the label differs from the application, and the application's brand appears nowhere on the label.", "fail",
         Printed("SALT HARBOR", "Spiced Rum", "35% Alc./Vol. (70 Proof)", "750 mL",
                 "Bottled by Salt Harbor Rum Co., Charleston, SC"),
         {"brand_name": "Harbor Light"}),
    Case("COLA-26-0017", "2026-10-27", "Quillmont Vineyards", W, "750 mL on the label, 0.75 L in the application.", "pass",
         Printed("QUILLMONT", "Chardonnay", "13.9% Alc./Vol.", "750 mL",
                 "Produced and bottled by Quillmont Vineyards, Sonoma, CA"),
         {"net_contents": "0.75 L"}),
    Case("COLA-26-0018", "2026-10-28", "Carra Beverage Imports", B, "Imported Irish stout; 1 PINT on the label, 16 fl oz in the application.", "pass",
         Printed("LOUGH CARRA", "Irish Stout", "4.3% ALC/VOL", "1 PINT",
                 "Imported by Carra Beverage Imports, Boston, MA", country="Product of Ireland"),
         {"net_contents": "16 fl oz"}),
    Case("COLA-26-0019", "2026-10-29", "Iron Gate Rum Works", S, "Warning drops the comma after 'machinery'.", "fail",
         Printed("IRON GATE", "Dark Rum", "40% Alc./Vol. (80 Proof)", "750 mL",
                 "Bottled by Iron Gate Rum Works, Miami, FL",
                 warning_body=BODY.replace("machinery, and", "machinery and"))),
    Case("COLA-26-0020", "2026-10-30", "Thistledown Winery", W, "No warning on this panel (it may be on the back label).", "needs_review",
         Printed("THISTLEDOWN", "Pinot Gris", "13% Alc./Vol.", "750 mL",
                 "Produced and bottled by Thistledown Winery, Dundee, OR", warning_header=None, warning_body="")),
    Case("COLA-26-0021", "2026-11-02", "Ashgrove Distilling Co.", S, "Application gives 90 proof, label gives 45%.", "pass",
         Printed("ASHGROVE", "Straight Bourbon Whiskey", "45% Alc./Vol.", "750 mL",
                 "Distilled and bottled by Ashgrove Distilling Co., Frankfort, KY"),
         {"alcohol_content": "90 Proof"}),
    Case("COLA-26-0022", "2026-11-03", "Bramblecask Brewing", B, "Blurry, low-contrast photo that can't be read reliably.", "needs_review",
         Printed("BRAMBLECASK", "Porter", "5.8% ALC/VOL", "12 FL OZ",
                 "Brewed by Bramblecask Brewing, Burlington, VT", photo="blurry")),
    Case("COLA-26-0023", "2026-11-04", "Cindervale Cellars", W, "Clean wine label photographed at an angle with glare.", "pass",
         Printed("CINDERVALE", "Pinot Noir", "13.5% Alc./Vol.", "750 mL",
                 "Vinted and bottled by Cindervale Cellars, Carlton, OR", photo="angled_glare_left")),
    Case("COLA-26-0024", "2026-11-05", "High Desert Imports", S, "Imported tequila with country of origin.", "pass",
         Printed("HIGH DESERT", "Blanco Tequila", "40% Alc./Vol. (80 Proof)", "750 mL",
                 "Imported by High Desert Imports, Phoenix, AZ", country="Product of Mexico")),
    Case("COLA-26-0025", "2026-11-06", "Granite Fold Brewing", B, "Warning misspells 'Surgeon Generel'.", "fail",
         Printed("GRANITE FOLD", "Amber Ale", "5.5% ALC/VOL", "12 FL OZ",
                 "Brewed by Granite Fold Brewing, Bend, OR",
                 warning_body=BODY.replace("Surgeon General", "Surgeon Generel"))),
]


@dataclass(frozen=True)
class Style:
    background: str
    ink: str
    accent: str
    brand_font: Path
    class_font: Path


STYLES = {
    S: Style("#f4ecd8", "#1d1d1d", "#6b4f2a", SERIF_BOLD, SERIF),
    W: Style("#fbf8f1", "#2a1a1f", "#7a1f33", SERIF_BOLD, SERIF),
    B: Style("#1f3b33", "#f3efe2", "#e0b54a", SANS_BOLD, SANS_BOLD),
}


def _font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), size)


def _center(draw: ImageDraw.ImageDraw, y: int, text: str, font, width: int, fill: str) -> int:
    w = draw.textlength(text, font=font)
    draw.text(((width - w) / 2, y), text, font=font, fill=fill)
    return y + font.size + int(font.size * 0.45)


def _wrap_runs(draw, runs, x0, y, max_w, line_h, fill):
    """Draw [(text, font), ...] as one wrapped paragraph, so the bold lead-in can sit inline."""
    x = x0
    for text, font in runs:
        for word in text.split():
            w = draw.textlength(word + " ", font=font)
            if x + w > x0 + max_w and x > x0:
                x, y = x0, y + line_h
            draw.text((x, y), word, font=font, fill=fill)
            x += w
    return y + line_h


def render(case: Case) -> Image.Image:
    p, style = case.printed, STYLES[case.product_type]
    width, height = 1000, 1300
    img = Image.new("RGB", (width, height), style.background)
    d = ImageDraw.Draw(img)
    d.rectangle([24, 24, width - 24, height - 24], outline=style.accent, width=6)
    d.rectangle([40, 40, width - 40, height - 40], outline=style.accent, width=2)

    y = 110
    y = _center(d, y, p.brand, _font(style.brand_font, 76 if len(p.brand) < 14 else 60), width, style.ink)
    y += 20
    d.line([200, y, width - 200, y], fill=style.accent, width=3)
    y += 40
    y = _center(d, y, p.class_type, _font(style.class_font, 40), width, style.ink)
    y += 60
    for line in (p.abv, p.net):
        if line:
            y = _center(d, y, line, _font(SANS_BOLD, 40), width, style.ink)
    y += 50
    y = _center(d, y, p.producer, _font(SANS, 25), width, style.ink)
    if p.country:
        y = _center(d, y, p.country, _font(SANS, 25), width, style.ink)

    if p.has_warning:
        body_font = _font(SANS, 22)
        head_font = _font(SANS_BOLD if p.header_bold else SANS, 22)
        runs = [(p.warning_header, head_font)] if p.warning_header else []
        runs.append((p.warning_body, body_font))
        _wrap_runs(d, runs, 80, height - 300, width - 160, 32, style.ink)

    return PHOTO_EFFECTS[p.photo](img)


def _angled_glare(img: Image.Image, angle: float, glare_x: float) -> Image.Image:
    """Fake a phone photo: rotate, add a glare hotspot, slight blur."""
    img = img.rotate(angle, resample=Image.BICUBIC, expand=True, fillcolor="#5a5a5a")
    glare = Image.new("L", img.size, 0)
    gd = ImageDraw.Draw(glare)
    cx, cy, r = int(img.width * glare_x), int(img.height * 0.3), int(img.width * 0.28)
    for i in range(r, 0, -4):
        gd.ellipse([cx - i, cy - i, cx + i, cy + i], fill=int(170 * (1 - i / r) ** 0.6))
    img = Image.composite(Image.new("RGB", img.size, "white"), img, glare)
    return img.filter(ImageFilter.GaussianBlur(1.1))


def _blurry(img: Image.Image) -> Image.Image:
    """Out of focus, dim and washed out: too poor to read the small print with confidence."""
    small = img.resize((img.width // 3, img.height // 3), Image.BILINEAR).filter(ImageFilter.GaussianBlur(2.2))
    img = small.resize(img.size, Image.BILINEAR)
    img = ImageEnhance.Contrast(img).enhance(0.35)
    return ImageEnhance.Brightness(img).enhance(0.75)


PHOTO_EFFECTS = {
    "flat": lambda img: img,
    "angled_glare": lambda img: _angled_glare(img, 7, 0.68),
    "angled_glare_left": lambda img: _angled_glare(img, -5, 0.32),
    "blurry": _blurry,
}


# ------------------------------------------------------------ real applications

TTB_DIR = ROOT / "samples" / "ttb"
TTB_PRODUCT_TYPES: dict[str, ProductType] = {"distilled spirits": S, "wine": W, "malt beverage": B}
REGISTRY_URL = "https://ttbonline.gov/colasonline/viewColaDetails.do?action=publicDisplaySearchBasic&ttbid={}"
REAL_SCENARIO = "Real application from TTB's Public COLA Registry"
REAL_PER_TYPE = 6
# Fixed so the draw is reproducible. The picks are random, not chosen by hand.
REAL_SEED = 20261110


def ttb_records() -> list[dict]:
    return json.loads((TTB_DIR / "manifest.json").read_text(encoding="utf-8"))


def real_entry(record: dict) -> QueueEntry:
    """A queue entry for one registry record.

    TTB's application record gives the brand, the applicant and whether the
    product is imported, but not the class/type statement, alcohol content,
    net contents or bottler, so those stay blank and are not evaluated.
    """
    month, day, year = (int(part) for part in record["approval_date"].split("/"))
    imported = record["source_of_product"] == "Imported"
    return QueueEntry(
        id=record["ttb_id"],
        submitted_at=dt.date(year, month, day),
        applicant=record["applicant_name_address"].split(",")[0].strip(),
        product_type=TTB_PRODUCT_TYPES[record["product_type"]],
        images=[image["file"] for image in record["images"]][:MAX_LABEL_IMAGES],
        registry_url=REGISTRY_URL.format(record["ttb_id"]),
        application=Application(
            brand_name=record["brand_name"],
            country_of_origin=record["origin_code"].title() if imported else "",
        ),
        expected_overall=None,
        scenario=REAL_SCENARIO,
    )


def real_picks() -> list[dict]:
    """REAL_PER_TYPE random records per beverage type."""
    rng = random.Random(REAL_SEED)
    records = sorted(ttb_records(), key=lambda r: r["ttb_id"])
    return [
        pick
        for kind in TTB_PRODUCT_TYPES
        for pick in rng.sample([r for r in records if r["product_type"] == kind], REAL_PER_TYPE)
    ]


def queue_entries() -> list[QueueEntry]:
    return [c.entry() for c in CASES] + [real_entry(r) for r in real_picks()]


def main() -> None:
    QUEUE_DIR.mkdir(parents=True, exist_ok=True)
    for case in CASES:
        render(case).save(QUEUE_DIR / f"{case.id}.png", optimize=True)
        print("wrote", case.id)
    real = [real_entry(r) for r in real_picks()]
    wanted = {name for entry in real for name in entry.images}
    for stale in QUEUE_DIR.glob("*.jpg"):
        if stale.name not in wanted:
            stale.unlink()
    for entry in real:
        for name in entry.images:
            shutil.copyfile(TTB_DIR / "images" / name, QUEUE_DIR / name)
        print("copied", entry.id, f"({len(entry.images)} images)")
    manifest = [e.model_dump(mode="json") for e in queue_entries()]
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("wrote", MANIFEST.relative_to(ROOT))


if __name__ == "__main__":
    main()
