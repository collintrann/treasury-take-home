"""Fallback reader: local Tesseract OCR. No network, so it works behind any firewall.

Raw OCR gives one blob of text with no idea which line is the "brand" and
which is the "class/type". So this reader is *application-guided*: for the
free-text fields it searches the OCR text for the stretch of words that best
resembles what the application says, and hands that to the normal matcher.
Numeric fields and the warning have recognizable shapes and are found by pattern.

Limitations, also surfaced in the UI:
* It can't tell bold from regular type, so the warning's bold check always
  comes back as REVIEW.
* It's much weaker than Claude on angled, curved or glary photos.
"""

from __future__ import annotations

import difflib
import os
import re

import pytesseract
from PIL import Image, ImageFilter, ImageOps

from ..matching import _ABV_RE, _ABV_STATEMENT_RE, _PROOF_RE, _VOL_RE, normalize
from ..models import ApplicationData, ExtractedLabel

# Tesseract parallelises each call with OpenMP, one thread per core. With several
# labels OCR'd at once that oversubscribes the CPU badly (we measured >60x
# slowdowns). One thread per process, with parallelism across processes instead.
os.environ.setdefault("OMP_THREAD_LIMIT", "1")

# A window has to be at least this similar to the application value to count
# as "found". It's deliberately loose: the matcher makes the real call and
# will return REVIEW/FAIL for a weak match.
_MIN_WINDOW_SIMILARITY = 0.6

_WARNING_RE = re.compile(r"g\s*o\s*v\s*e\s*r\s*n\s*m\s*e\s*n\s*t\s+w\s*a\s*r\s*n\s*i\s*n\s*g", re.IGNORECASE)
_WARNING_END_RE = re.compile(r"health\s+problems\.?", re.IGNORECASE)


# Pixels darker than this count as "ink" when estimating skew. Fixed rather
# than adaptive: simple, and right for the common dark-text-on-light label.
_INK_THRESHOLD = 80


def _row_contrast(binary: Image.Image, angle: float) -> float:
    """Variance of per-row ink density after rotating by ``angle``.

    When text lines are horizontal, rows alternate between "all ink" and
    "no ink", so the variance peaks. This is the classic projection-profile
    deskew, done with Pillow alone: resizing to 1px wide averages each row.
    """
    rotated = binary.rotate(angle, resample=Image.BILINEAR)
    rows = list(rotated.resize((1, rotated.height), Image.BOX).get_flattened_data())
    mean = sum(rows) / len(rows)
    return sum((r - mean) ** 2 for r in rows)


def estimate_skew(img: Image.Image, max_angle: int = 15) -> float:
    """Return the rotation (degrees) that best levels the text lines."""
    small = ImageOps.grayscale(img)
    small.thumbnail((800, 800))
    binary = small.point(lambda p: 255 if p < _INK_THRESHOLD else 0)
    coarse = max(range(-max_angle, max_angle + 1), key=lambda a: _row_contrast(binary, a))
    fine = [coarse + d / 4 for d in range(-3, 4)]
    return max(fine, key=lambda a: _row_contrast(binary, a))


def _preprocess(img: Image.Image) -> Image.Image:
    angle = estimate_skew(img)
    if abs(angle) >= 1:
        img = img.rotate(angle, resample=Image.BICUBIC, expand=True, fillcolor="white")
    gray = ImageOps.grayscale(img)
    # Tesseract does best with text around 30px tall; upscale small images.
    if max(gray.size) < 2000:
        scale = 2000 / max(gray.size)
        gray = gray.resize((int(gray.width * scale), int(gray.height * scale)), Image.LANCZOS)
    gray = ImageOps.autocontrast(gray, cutoff=1)
    return gray.filter(ImageFilter.SHARPEN)


def run_ocr(img: Image.Image) -> tuple[str, float]:
    """Return (text, mean word confidence 0-100)."""
    # psm 11 = "sparse text": labels are scattered blocks, not a page of prose.
    data = pytesseract.image_to_data(_preprocess(img), config="--psm 11", output_type=pytesseract.Output.DICT)
    lines: dict[tuple, list[str]] = {}
    confidences = []
    for i, word in enumerate(data["text"]):
        if not word.strip():
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        lines.setdefault(key, []).append(word)
        if float(data["conf"][i]) >= 0:
            confidences.append(float(data["conf"][i]))
    text = "\n".join(" ".join(words) for _, words in sorted(lines.items()))
    return text, (sum(confidences) / len(confidences) if confidences else 0.0)


def find_best_window(expected: str, text: str) -> str | None:
    """Return the run of OCR words most similar to ``expected``, or None."""
    target = normalize(expected)
    if not target:
        return None
    words = text.split()
    n = len(target.split())
    best, best_ratio = None, 0.0
    for size in {max(1, n - 1), n, n + 1}:
        for i in range(0, max(1, len(words) - size + 1)):
            candidate = " ".join(words[i : i + size])
            ratio = difflib.SequenceMatcher(a=target, b=normalize(candidate), autojunk=False).ratio()
            if ratio > best_ratio:
                best, best_ratio = candidate, ratio
    return best if best_ratio >= _MIN_WINDOW_SIMILARITY else None


def _find_line(pattern: re.Pattern, text: str) -> str | None:
    for line in text.splitlines():
        if pattern.search(line):
            return line.strip()
    return None


def _find_warning(text: str) -> str | None:
    flat = " ".join(text.split())
    start = _WARNING_RE.search(flat)
    if not start:
        return None
    end = _WARNING_END_RE.search(flat, start.end())
    stop = end.end() if end else min(len(flat), start.start() + 400)
    return flat[start.start() : stop]


def parse_ocr_text(text: str, app: ApplicationData) -> ExtractedLabel:
    alcohol = _find_line(_ABV_STATEMENT_RE, text) or _find_line(_ABV_RE, text) or _find_line(_PROOF_RE, text)
    volume = _VOL_RE.search(text)
    return ExtractedLabel(
        brand_name=find_best_window(app.brand_name, text),
        class_type=find_best_window(app.class_type, text),
        alcohol_content=alcohol,
        net_contents=volume.group(0) if volume else None,
        producer_name_address=find_best_window(app.producer_name_address, text),
        country_of_origin=find_best_window(app.country_of_origin, text),
        government_warning=_find_warning(text),
        warning_header_bold=None,  # OCR can't see font weight
        image_issues=None,
    )


# Below this mean word confidence, tell the agent the read is shaky.
LOW_CONFIDENCE = 75


def extract_with_ocr(img: Image.Image, app: ApplicationData) -> tuple[ExtractedLabel, float]:
    text, confidence = run_ocr(img)
    label = parse_ocr_text(text, app)
    if confidence < LOW_CONFIDENCE:
        label.image_issues = "This photo is hard to read. A clearer photo may be needed."
    return label, confidence
