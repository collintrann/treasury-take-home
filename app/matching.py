"""Deterministic comparison rules: application value vs. what's on the label.

Design notes
------------
* Every comparison returns one of PASS / REVIEW / FAIL / MISSING / SKIPPED and
  a plain-English note. REVIEW exists because, as Dave put it, "you need
  judgment" - we surface near-misses rather than silently pass or reject them.
* Text fields: an exact match passes. A match that differs only in
  case/punctuation/spacing ("STONE'S THROW" vs "Stone's Throw") also passes,
  with a note. A close-but-different value (one typo) goes to REVIEW. Anything
  else fails.
* Numeric fields (ABV, net contents) are compared as *numbers*, so
  "45% Alc./Vol." == "45 % ALC/VOL" and "75 cl" == "750 mL".
"""

from __future__ import annotations

import difflib
import re
import unicodedata

from .models import ApplicationData, ExtractedLabel, FieldResult, Status, VerificationResult
from .warning import FULL_TEXT, check_warning

# Ratio above which two non-identical strings are "probably the same thing"
# (one or two characters off - typical of a typo or a misread).
REVIEW_SIMILARITY = 0.85

FIELD_LABELS = {
    "brand_name": "Brand name",
    "class_type": "Class / type",
    "alcohol_content": "Alcohol content",
    "net_contents": "Net contents",
    "producer_name_address": "Bottler / producer",
    "country_of_origin": "Country of origin",
    "government_warning": "Government warning",
}


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
_ROLE = r"(?:distilled|bottled|produced|brewed|blended|made|imported|vinted|cellared|packed)"
_LABEL_PHRASING = {
    "country_of_origin": re.compile(r"^(?:product of|produce of|made in|imported from) "),
    "producer_name_address": re.compile(rf"^{_ROLE}(?: and {_ROLE})* (?:by|for) "),
}


def _strip_phrasing(key: str, normalized: str) -> str:
    pattern = _LABEL_PHRASING.get(key)
    return pattern.sub("", normalized) if pattern else normalized


def compare_text(key: str, expected: str, found: str | None) -> FieldResult:
    label = FIELD_LABELS[key]
    base = dict(field=key, label=label, expected=expected or None, found=found)

    if not normalize(expected):
        return FieldResult(**base, status=Status.SKIPPED, note="Not provided in the application.")
    if not found or not found.strip():
        return FieldResult(**base, status=Status.MISSING, note=f"{label} was not found on the label.")

    if " ".join(expected.split()) == " ".join(found.split()):
        return FieldResult(**base, status=Status.PASS, note="Exact match.")

    n_exp, n_found = normalize(expected), normalize(found)
    if n_exp == n_found:
        return FieldResult(
            **base, status=Status.PASS, note="Matches (differs only in capitalization or punctuation)."
        )

    if _strip_phrasing(key, n_exp) == _strip_phrasing(key, n_found):
        return FieldResult(**base, status=Status.PASS, note="Matches (with standard label wording around it).")

    ratio = similarity(expected, found)
    if ratio >= REVIEW_SIMILARITY:
        return FieldResult(
            **base,
            status=Status.REVIEW,
            note=f"Very close but not identical ({ratio:.0%} similar) - please check by eye.",
        )
    if re.search(rf"\b{re.escape(n_found)}\b", n_exp):
        return FieldResult(
            **base, status=Status.REVIEW, note="Label shows only part of the application value - please check."
        )
    if re.search(rf"\b{re.escape(n_exp)}\b", n_found):
        return FieldResult(
            **base, status=Status.REVIEW, note="Label has extra words around the application value - please check."
        )
    return FieldResult(**base, status=Status.FAIL, note="Does not match the application.")


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


def compare_alcohol(expected: str, found: str | None) -> FieldResult:
    key = "alcohol_content"
    base = dict(field=key, label=FIELD_LABELS[key], expected=expected or None, found=found)
    if not expected.strip():
        return FieldResult(**base, status=Status.SKIPPED, note="Not provided in the application.")
    if not found or not found.strip():
        return FieldResult(**base, status=Status.MISSING, note="No alcohol content statement found on the label.")

    exp_abv, exp_proof = parse_abv(expected)
    got_abv, got_proof = parse_abv(found)
    # Proof is defined as 2x ABV in the US; derive whichever side is missing.
    exp_abv = exp_abv if exp_abv is not None else (exp_proof / 2 if exp_proof is not None else None)
    got_abv_eff = got_abv if got_abv is not None else (got_proof / 2 if got_proof is not None else None)

    if exp_abv is None or got_abv_eff is None:
        return compare_text(key, expected, found)  # can't parse numbers; fall back

    if abs(exp_abv - got_abv_eff) > 0.001:
        return FieldResult(
            **base,
            status=Status.FAIL,
            note=f"Application says {exp_abv:g}% ABV but the label says {got_abv_eff:g}%.",
        )
    if got_abv is not None and got_proof is not None and abs(got_proof - 2 * got_abv) > 0.001:
        return FieldResult(
            **base,
            status=Status.FAIL,
            note=f"Label is inconsistent: {got_abv:g}% ABV should be {2 * got_abv:g} proof, not {got_proof:g}.",
        )
    return FieldResult(**base, status=Status.PASS, note=f"{exp_abv:g}% ABV matches.")


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


def compare_volume(expected: str, found: str | None) -> FieldResult:
    key = "net_contents"
    base = dict(field=key, label=FIELD_LABELS[key], expected=expected or None, found=found)
    if not expected.strip():
        return FieldResult(**base, status=Status.SKIPPED, note="Not provided in the application.")
    if not found or not found.strip():
        return FieldResult(**base, status=Status.MISSING, note="No net contents statement found on the label.")

    exp_ml, got_ml = parse_volume_ml(expected), parse_volume_ml(found)
    if exp_ml is None or got_ml is None:
        return compare_text(key, expected, found)

    if abs(exp_ml - got_ml) <= max(exp_ml, got_ml) * 0.005:  # 0.5% tolerance for unit rounding
        same_text = normalize(expected).replace(" ", "") == normalize(found).replace(" ", "")
        note = "Matches." if same_text else f"Same volume ({exp_ml:g} mL) written differently."
        return FieldResult(**base, status=Status.PASS, note=note)
    return FieldResult(
        **base, status=Status.FAIL, note=f"Application says {exp_ml:g} mL but the label says {got_ml:g} mL."
    )


# ------------------------------------------------------------------------ overall


def overall_status(results: list[FieldResult]) -> Status:
    statuses = {r.status for r in results}
    if statuses & {Status.FAIL, Status.MISSING}:
        return Status.FAIL
    if Status.REVIEW in statuses:
        return Status.REVIEW
    return Status.PASS


def verify(app: ApplicationData, label: ExtractedLabel) -> tuple[Status, list[FieldResult]]:
    """Compare every field and roll up an overall verdict."""
    results = [
        compare_text("brand_name", app.brand_name, label.brand_name),
        compare_text("class_type", app.class_type, label.class_type),
        compare_alcohol(app.alcohol_content, label.alcohol_content),
        compare_volume(app.net_contents, label.net_contents),
        compare_text("producer_name_address", app.producer_name_address, label.producer_name_address),
        compare_text("country_of_origin", app.country_of_origin, label.country_of_origin),
    ]
    w_status, w_note, w_diff = check_warning(label.government_warning, label.warning_header_bold)
    results.append(
        FieldResult(
            field="government_warning",
            label=FIELD_LABELS["government_warning"],
            expected=FULL_TEXT,
            found=label.government_warning,
            status=Status(w_status),
            note=w_note,
            diff=w_diff,
        )
    )

    return overall_status(results), results


__all__ = ["verify", "VerificationResult"]
