"""The Government Health Warning Statement (27 CFR 16.21 and 16.22).

Wording and the capitalized "GOVERNMENT WARNING:" lead-in are checked from the
text, so a difference there fails. Typography (bold, paragraph, separation,
legibility) is a visual judgment from the photo, so it can pass or go to
needs_review but never fail. Type size can't be measured from a photo.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

from .models import DiffOp, ExtractedLabel, Finding, Status

HEADER = "GOVERNMENT WARNING:"

BODY = (
    "(1) According to the Surgeon General, women should not drink alcoholic "
    "beverages during pregnancy because of the risk of birth defects. "
    "(2) Consumption of alcoholic beverages impairs your ability to drive a car "
    "or operate machinery, and may cause health problems."
)

FULL_TEXT = f"{HEADER} {BODY}"

# Finds the lead-in in any casing, with or without the colon, so its casing
# can be judged separately from the wording.
_HEADER_RE = re.compile(r"government\s+warning\s*:?", re.IGNORECASE)

NO_WARNING = "No warning was found in this image to check."


def _tokens(text: str) -> list[str]:
    """Words with typographic quotes unified. Line breaks are layout; punctuation stays on its word."""
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return text.split()


def word_diff(expected: str, found: str) -> list[DiffOp]:
    """Word-level diff for display. Body words compare case-insensitively; only the lead-in must be capitals."""
    exp, got = _tokens(expected), _tokens(found)
    matcher = difflib.SequenceMatcher(a=[w.lower() for w in exp], b=[w.lower() for w in got], autojunk=False)
    out: list[DiffOp] = []
    for op, a1, a2, b1, b2 in matcher.get_opcodes():
        if op == "equal":
            out.append(DiffOp(op="equal", text=" ".join(got[b1:b2])))
            continue
        if a2 > a1:
            out.append(DiffOp(op="missing", text=" ".join(exp[a1:a2])))
        if b2 > b1:
            out.append(DiffOp(op="extra", text=" ".join(got[b1:b2])))
    return out


@dataclass(frozen=True)
class VisualCheck:
    key: str
    label: str
    attribute: str  # the ExtractedLabel field holding the reader's judgment
    compliant: bool  # the value of that field that means "looks right"
    looks_right: str
    looks_wrong: str
    unsure: str


VISUAL_CHECKS = [
    VisualCheck(
        "warning_header_bold", "GOVERNMENT WARNING: in bold", "warning_header_bold", True,
        "GOVERNMENT WARNING: appears in bold.",
        "GOVERNMENT WARNING: may not be in bold. Please check the label.",
        "We couldn't tell whether GOVERNMENT WARNING: is in bold. Please check the label.",
    ),
    VisualCheck(
        "warning_body_not_bold", "Rest of the warning not bold", "warning_body_bold", False,
        "The rest of the warning is in regular type.",
        "The rest of the warning may be in bold. Only GOVERNMENT WARNING: should be. Please check the label.",
        "We couldn't tell whether the rest of the warning is in regular type. Please check the label.",
    ),
    VisualCheck(
        "warning_paragraph", "One continuous paragraph", "warning_continuous_paragraph", True,
        "The warning is one continuous paragraph.",
        "The warning may be split into pieces. It should be one continuous paragraph. Please check the label.",
        "We couldn't tell whether the warning is one continuous paragraph. Please check the label.",
    ),
    VisualCheck(
        "warning_separate", "Separate from other text", "warning_separate_from_other_text", True,
        "The warning stands apart from the other text.",
        "The warning may run into other text or graphics. Please check the label.",
        "We couldn't tell whether the warning stands apart from other text. Please check the label.",
    ),
    VisualCheck(
        "warning_legible", "Clear and easy to read", "warning_legible", True,
        "The warning is clear and easy to read.",
        "The warning may be faint or hard to read. Please check the label.",
        "We couldn't tell whether the warning is easy to read. Please check the label.",
    ),
]

def _finding(key: str, label: str, status: Status, explanation: str, **extra) -> Finding:
    return Finding(key=key, group="warning", label=label, status=status, explanation=explanation, **extra)


def _wording(found: str, header: re.Match | None) -> Finding:
    body = found[header.end():] if header else found
    diff = word_diff(BODY, body)
    if any(d.op != "equal" for d in diff):
        status, explanation = "fail", "The wording differs from the required text. See the highlighted words."
    else:
        status, explanation = "pass", "Matches the required wording word for word."
    return _finding(
        "warning_wording", "Warning wording", status, explanation, expected=BODY, observed=body.strip(), diff=diff
    )


def _header_caps(header: re.Match | None) -> Finding:
    key, label = "warning_header_caps", "GOVERNMENT WARNING: in capitals"
    if header is None:
        return _finding(key, label, "fail", "The warning doesn't start with GOVERNMENT WARNING:.", expected=HEADER)
    observed = " ".join(header.group(0).split())  # a line break inside the lead-in is layout
    if not observed.startswith("GOVERNMENT WARNING"):
        status, explanation = "fail", "It must be GOVERNMENT WARNING: in all capital letters."
    elif not observed.endswith(":"):
        status, explanation = "fail", "The colon after GOVERNMENT WARNING is missing."
    else:
        status, explanation = "pass", "In capital letters, with the colon."
    return _finding(key, label, status, explanation, expected=HEADER, observed=observed)


def _visual(check: VisualCheck, label: ExtractedLabel) -> Finding:
    seen = getattr(label, check.attribute)
    if seen is None:
        status, explanation = "needs_review", check.unsure
    elif seen == check.compliant:
        status, explanation = "pass", check.looks_right
    else:
        status, explanation = "needs_review", check.looks_wrong
    return _finding(check.key, check.label, status, explanation)


def warning_findings(label: ExtractedLabel) -> list[Finding]:
    """The warning findings, always in the same order."""
    type_size = _finding(
        "warning_type_size", "Type size and letters per inch", "not_evaluated",
        "Can't be measured reliably from a photo.",
    )
    found = (label.government_warning or "").strip()
    if not found:
        present = _finding(
            "warning_present", "Warning present", "needs_review",
            "The warning wasn't found in this image. It may be on another part of the label.",
        )
        rest = [
            _finding("warning_wording", "Warning wording", "not_evaluated", NO_WARNING, expected=BODY),
            _finding("warning_header_caps", "GOVERNMENT WARNING: in capitals", "not_evaluated", NO_WARNING),
            *(_finding(c.key, c.label, "not_evaluated", NO_WARNING) for c in VISUAL_CHECKS),
        ]
        return [present, *rest, type_size]

    header = _HEADER_RE.search(found)
    return [
        _finding("warning_present", "Warning present", "pass", "The warning is on the label."),
        _wording(found, header),
        _header_caps(header),
        *(_visual(c, label) for c in VISUAL_CHECKS),
        type_size,
    ]
