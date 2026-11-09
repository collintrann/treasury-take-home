"""The mandatory Government Health Warning Statement (27 CFR 16.21).

Rules enforced (27 CFR 16.22 and agent feedback):
  1. The text must match word-for-word.
  2. "GOVERNMENT WARNING:" must be in capital letters.
  3. "GOVERNMENT WARNING" must be bold.
"""

from __future__ import annotations

import difflib
import re

HEADER = "GOVERNMENT WARNING:"

BODY = (
    "(1) According to the Surgeon General, women should not drink alcoholic "
    "beverages during pregnancy because of the risk of birth defects. "
    "(2) Consumption of alcoholic beverages impairs your ability to drive a car "
    "or operate machinery, and may cause health problems."
)

FULL_TEXT = f"{HEADER} {BODY}"

# Matches the header in any casing, tolerating a missing colon / odd spacing,
# so we can *find* it first and then judge its casing separately.
_HEADER_RE = re.compile(r"government\s+warning\s*:?", re.IGNORECASE)


def _tokens(text: str) -> list[str]:
    """Split into words, normalizing typographic quotes and whitespace.

    Line breaks on a label are layout, not content, so they're ignored.
    Punctuation stays attached to words: a missing comma is a real deviation.
    """
    text = text.replace("’", "'").replace("‘", "'")
    text = text.replace("“", '"').replace("”", '"')
    return text.split()


def word_diff(expected: str, found: str) -> list[dict]:
    """Word-level diff for display: [{"op": "equal"|"missing"|"extra", "text": ...}].

    Body words are compared case-insensitively (the regulation mandates caps
    only for the header); the header's casing is checked separately.
    """
    exp, got = _tokens(expected), _tokens(found)
    matcher = difflib.SequenceMatcher(
        a=[w.lower() for w in exp], b=[w.lower() for w in got], autojunk=False
    )
    out: list[dict] = []
    for op, a1, a2, b1, b2 in matcher.get_opcodes():
        if op == "equal":
            out.append({"op": "equal", "text": " ".join(got[b1:b2])})
        else:
            if a2 > a1:
                out.append({"op": "missing", "text": " ".join(exp[a1:a2])})
            if b2 > b1:
                out.append({"op": "extra", "text": " ".join(got[b1:b2])})
    return out


def _only_near_misses(diff: list[dict]) -> bool:
    """True if every difference is a word swapped for a look-alike (e.g. 'alcahalic').

    That pattern is typical of an OCR misread rather than a reworded warning.
    """
    changes = [d for d in diff if d["op"] != "equal"]
    if not changes:
        return True
    # Pair each "missing" run with the "extra" run that replaced it.
    i = 0
    while i < len(changes):
        if i + 1 >= len(changes) or (changes[i]["op"], changes[i + 1]["op"]) != ("missing", "extra"):
            return False
        a, b = changes[i]["text"].split(), changes[i + 1]["text"].split()
        if len(a) != len(b):
            return False
        for wa, wb in zip(a, b):
            if difflib.SequenceMatcher(a=wa.lower(), b=wb.lower()).ratio() < 0.7:
                return False
        i += 2
    return True


def check_warning(
    found: str | None, header_bold: bool | None, lenient: bool = False
) -> tuple[str, str, list[dict] | None]:
    """Return (status, note, diff) for the warning statement.

    status is one of "pass" / "review" / "fail" / "missing".
    ``lenient`` is used for OCR output, where a one-letter difference is more
    likely a misread than a violation, so it goes to human review instead.
    """
    if not found or not found.strip():
        if lenient:
            return "review", "We couldn't find the government warning on the label. Please check by eye.", None
        return "missing", "No government warning was found on the label.", None

    problems: list[str] = []

    m = _HEADER_RE.search(found)
    if not m:
        problems.append("The 'GOVERNMENT WARNING:' lead-in is missing.")
        body_found = found
    else:
        header_text = " ".join(m.group(0).split())  # a line break inside the lead-in is layout
        if not header_text.startswith("GOVERNMENT WARNING"):
            problems.append(
                f"Lead-in is '{header_text.strip()}' - it must be 'GOVERNMENT WARNING:' in all capital letters."
            )
        elif not header_text.rstrip().endswith(":"):
            problems.append("Lead-in is missing the colon after 'GOVERNMENT WARNING'.")
        body_found = found[m.end():]

    diff = word_diff(BODY, body_found)
    wording_differs = any(d["op"] != "equal" for d in diff)
    if wording_differs and lenient and not problems and _only_near_misses(diff):
        return (
            "review",
            "The wording looks right, but a few words were hard to read. Please check the highlighted words.",
            diff,
        )
    if wording_differs:
        problems.append("Warning wording differs from the required text (see highlighted words).")

    if problems:
        return "fail", " ".join(problems), diff

    if header_bold is False:
        return "fail", "'GOVERNMENT WARNING' does not appear to be in bold type.", diff
    if header_bold is None:
        return (
            "review",
            "Wording and capitalization are correct. Please confirm that GOVERNMENT WARNING is in bold.",
            diff,
        )
    return "pass", "Exact match, capitalized, and bold.", diff
