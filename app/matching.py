"""Rules that compare each application field with what the label shows.

* Text fields pass when identical, or the same apart from capitalization and
  punctuation ("STONE'S THROW" matches "Stone's Throw"). Near-misses and extra
  or missing words go to needs_review. A clearly different value fails.
* Alcohol content and net contents are compared as numbers, so "90 Proof"
  equals 45% and 0.75 L equals 750 mL.
* Which fields apply depends on the product type (``_not_evaluated_reason``).
  A field missing from the photo is needs_review, never fail: it may be on
  another panel of the label.
"""

from __future__ import annotations

import difflib
import re
import unicodedata

from .models import Application, ExtractedLabel, Finding, ProductType, Status

# Ratio above which two non-identical strings are "probably the same thing"
# (one or two characters off, typical of a typo or a misread).
REVIEW_SIMILARITY = 0.85

FIELD_LABELS = {
    "brand_name": "Brand name",
    "class_type": "Class / type",
    "alcohol_content": "Alcohol content",
    "net_contents": "Net contents",
    "producer_name_address": "Bottler / producer",
    "country_of_origin": "Country of origin",
}

# Wine at or under this strength may leave alcohol content off the label.
WINE_ABV_OPTIONAL_UP_TO = 14.0


# --------------------------------------------------------------------------- text


def normalize(text: str) -> str:
    """Lowercase, unify quotes/dashes, drop punctuation, collapse whitespace."""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("’", "'").replace("‘", "'").replace("&", " and ")
    text = text.lower()
    text = re.sub(r"[^\w\s]", " ", text)  # punctuation -> space
    return " ".join(text.split())


def similarity(a: str, b: str) -> float:
    return difflib.SequenceMatcher(a=normalize(a), b=normalize(b), autojunk=False).ratio()


# Standard label phrasing that wraps a value. Stripped from both sides before
# comparing, so "Product of Scotland" matches "Scotland" but "Product of New
# Mexico" does not match "Mexico".
_ROLE = r"(?:distilled|bottled|produced|brewed|blended|made|imported|vinted|cellared|packed|canned)"
_LABEL_PHRASING = {
    "country_of_origin": re.compile(r"^(?:product of|produce of|made in|imported from) "),
    "producer_name_address": re.compile(rf"^{_ROLE}(?: and {_ROLE})* (?:by|for) "),
}


def _strip_phrasing(key: str, normalized: str) -> str:
    pattern = _LABEL_PHRASING.get(key)
    return pattern.sub("", normalized) if pattern else normalized


def compare_text(key: str, expected: str, found: str) -> tuple[Status, str]:
    """Compare one text field. Both values are present."""
    if " ".join(expected.split()) == " ".join(found.split()):
        return "pass", "Exact match."

    n_exp, n_found = normalize(expected), normalize(found)
    if n_exp == n_found:
        return "pass", "Matches (differs only in capitalization or punctuation)."
    if _strip_phrasing(key, n_exp) == _strip_phrasing(key, n_found):
        return "pass", "Matches (with standard label wording around it)."

    ratio = similarity(expected, found)
    if ratio >= REVIEW_SIMILARITY:
        return "needs_review", f"Very close but not identical ({ratio:.0%} similar). Please check by eye."
    if re.search(rf"\b{re.escape(n_found)}\b", n_exp):
        return "needs_review", "The label shows only part of the application value. Please check."
    if re.search(rf"\b{re.escape(n_exp)}\b", n_found):
        return "needs_review", "The label has extra words around the application value. Please check."
    return "fail", "Does not match the application."


# ------------------------------------------------------------------------ alcohol

_ABV_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*%")
# A percentage tied to alcohol wording, so "100% Blue Agave" isn't read as the ABV.
_ABV_STATEMENT_RE = re.compile(
    r"(?:alc(?:ohol)?\.?|abv)[^%\d]{0,15}(\d+(?:[.,]\d+)?)\s*%|(\d+(?:[.,]\d+)?)\s*%\s*(?:alc|abv|alcohol|by vol|vol)",
    re.IGNORECASE,
)
_PROOF_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:°\s*)?proof", re.IGNORECASE)


def _num(s: str) -> float:
    """Parse "1,000" as one thousand and "12,5" (European decimal) as twelve and a half."""
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?", s):
        return float(s.replace(",", ""))
    return float(s.replace(",", "."))


def parse_abv(text: str) -> tuple[float | None, float | None]:
    """Return (abv_percent, proof) found in a statement; either may be None."""
    statement = _ABV_STATEMENT_RE.search(text)
    if statement:
        abv_text = statement.group(1) or statement.group(2)
    else:
        bare = _ABV_RE.search(text)
        abv_text = bare.group(1) if bare else None
    proof = _PROOF_RE.search(text)
    return (_num(abv_text) if abv_text else None, _num(proof.group(1)) if proof else None)


def abv_percent(text: str) -> float | None:
    """The alcohol content as a percentage, from either % or proof (US proof is 2x ABV)."""
    abv, proof = parse_abv(text)
    if abv is not None:
        return abv
    return proof / 2 if proof is not None else None


def compare_alcohol(expected: str, found: str) -> tuple[Status, str]:
    exp_abv, got_abv = abv_percent(expected), abv_percent(found)
    if exp_abv is None or got_abv is None:
        return compare_text("alcohol_content", expected, found)
    if abs(exp_abv - got_abv) > 0.001:
        return "fail", f"The application says {exp_abv:g}% but the label says {got_abv:g}%."

    label_abv, label_proof = parse_abv(found)
    if label_abv is not None and label_proof is not None and abs(label_proof - 2 * label_abv) > 0.001:
        return "fail", (
            f"The label contradicts itself: {label_abv:g}% should be {2 * label_abv:g} proof, not {label_proof:g}."
        )
    return "pass", f"{exp_abv:g}% matches."


# --------------------------------------------------------------------- net volume

# Conversion factors to millilitres.
_UNITS = {
    "ml": 1.0,
    "milliliter": 1.0,
    "millilitre": 1.0,
    "cl": 10.0,
    "centiliter": 10.0,
    "centilitre": 10.0,
    "l": 1000.0,
    "liter": 1000.0,
    "litre": 1000.0,
    "fl oz": 29.5735,
    "fl. oz": 29.5735,
    "fluid ounce": 29.5735,
    "oz": 29.5735,
    "pint": 473.176,
    "pt": 473.176,
    "quart": 946.353,
    "qt": 946.353,
    "gallon": 3785.41,
    "gal": 3785.41,
}
_VOL_RE = re.compile(
    r"(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:[.,]\d+)?)\s*(" + "|".join(sorted((re.escape(u) for u in _UNITS), key=len, reverse=True)) + r")s?\b",
    re.IGNORECASE,
)


def parse_volume_ml(text: str) -> float | None:
    m = _VOL_RE.search(text)
    if not m:
        return None
    return _num(m.group(1)) * _UNITS[m.group(2).lower()]


def compare_volume(expected: str, found: str) -> tuple[Status, str]:
    exp_ml, got_ml = parse_volume_ml(expected), parse_volume_ml(found)
    if exp_ml is None or got_ml is None:
        return compare_text("net_contents", expected, found)
    if abs(exp_ml - got_ml) <= max(exp_ml, got_ml) * 0.005:  # 0.5% tolerance for unit rounding
        same_text = normalize(expected).replace(" ", "") == normalize(found).replace(" ", "")
        return "pass", "Matches." if same_text else f"Same amount ({exp_ml:g} mL) written differently."
    return "fail", f"The application says {exp_ml:g} mL but the label says {got_ml:g} mL."


# -------------------------------------------------------------- applicability


def _not_evaluated_reason(key: str, product_type: ProductType, expected: str, found: str | None) -> str | None:
    """Why this field isn't checked for this product, or None when it is."""
    if not normalize(expected):
        return (
            "No country of origin in the application. It is needed only for imports."
            if key == "country_of_origin"
            else "Not provided in the application."
        )
    if key == "alcohol_content" and not found:
        if product_type == "malt_beverage":
            return "Not required for malt beverages."
        abv = abv_percent(expected)
        if product_type == "wine" and abv is not None and abv <= WINE_ABV_OPTIONAL_UP_TO:
            return "Not required for wine at 14% or less."
    return None


def _compare(key: str, expected: str, found: str) -> tuple[Status, str]:
    if key == "alcohol_content":
        return compare_alcohol(expected, found)
    if key == "net_contents":
        return compare_volume(expected, found)
    return compare_text(key, expected, found)


def application_findings(product_type: ProductType, app: Application, label: ExtractedLabel) -> list[Finding]:
    """One finding per application field, in the order of ``Application``."""
    findings = []
    for key, name in FIELD_LABELS.items():
        expected = getattr(app, key).strip()
        found = (getattr(label, key) or "").strip() or None
        reason = _not_evaluated_reason(key, product_type, expected, found)
        if reason:
            status, explanation = "not_evaluated", reason
        elif found is None:
            status, explanation = "needs_review", "Not found in this image. It may be on another part of the label."
        else:
            status, explanation = _compare(key, expected, found)
        findings.append(
            Finding(
                key=key,
                group="application",
                label=name,
                status=status,
                expected=expected or None,
                observed=found,
                explanation=explanation,
            )
        )
    return findings
