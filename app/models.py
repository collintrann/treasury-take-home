"""Data shapes shared across the app.

Three layers, kept deliberately separate:

* ``ApplicationData``  - what the applicant *claims* (typed in, or a CSV row).
* ``ExtractedLabel``   - what we *read* off the label image (Claude or OCR).
* ``VerificationResult`` - the field-by-field *comparison* of the two.

Keeping "reading" and "judging" apart means the matching rules are plain,
deterministic, unit-tested Python - the AI model never decides pass/fail.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ApplicationData(BaseModel):
    """Values from the COLA application that the label must match."""

    brand_name: str = ""
    class_type: str = ""
    alcohol_content: str = ""
    net_contents: str = ""
    producer_name_address: str = ""
    country_of_origin: str = ""  # only required for imports


class ExtractedLabel(BaseModel):
    """Fields transcribed from the label image.

    This class doubles as the JSON schema Claude is constrained to, so the
    descriptions below are effectively part of the prompt.
    """

    brand_name: Optional[str] = Field(
        None, description="Brand name exactly as printed, preserving capitalization."
    )
    class_type: Optional[str] = Field(
        None, description="Class/type designation, e.g. 'Kentucky Straight Bourbon Whiskey'."
    )
    alcohol_content: Optional[str] = Field(
        None, description="Alcohol content statement exactly as printed, e.g. '45% Alc./Vol. (90 Proof)'."
    )
    net_contents: Optional[str] = Field(None, description="Net contents exactly as printed, e.g. '750 mL'.")
    producer_name_address: Optional[str] = Field(
        None, description="Bottler/producer/importer name and address as printed."
    )
    country_of_origin: Optional[str] = Field(
        None, description="Country of origin statement if present, e.g. 'Product of Scotland'."
    )
    government_warning: Optional[str] = Field(
        None,
        description=(
            "The full government health warning, transcribed character-for-character "
            "including the exact capitalization of the 'GOVERNMENT WARNING:' lead-in. "
            "Do NOT correct typos or normalize case."
        ),
    )
    warning_header_bold: Optional[bool] = Field(
        None,
        description=(
            "True if the words 'GOVERNMENT WARNING' are visibly bold/heavier than the "
            "rest of the warning text; false if not; null if you cannot tell."
        ),
    )
    image_issues: Optional[str] = Field(
        None,
        description="Short note on anything that made reading hard (glare, angle, blur), or null.",
    )


class Status(str, Enum):
    PASS = "pass"  # matches
    REVIEW = "review"  # probably fine but a human should glance (e.g. case-only difference)
    FAIL = "fail"  # clear mismatch
    MISSING = "missing"  # required but not found on the label
    SKIPPED = "skipped"  # not provided in the application, nothing to compare


class FieldResult(BaseModel):
    field: str  # machine key, e.g. "brand_name"
    label: str  # human name, e.g. "Brand name"
    expected: Optional[str] = None
    found: Optional[str] = None
    status: Status
    note: str = ""  # plain-English explanation for the agent
    diff: Optional[list[dict]] = None  # word diff, only for the warning
    # Two-reader consensus (AI path only):
    #   "agreed"   - both readers reached the same verdict
    #   "disputed" - one reader passed it and the other didn't -> forced to REVIEW
    #   "single"   - only one reader answered; not double-checked
    agreement: Optional[str] = None


class VerificationResult(BaseModel):
    overall: Status
    fields: list[FieldResult]
    extraction_method: str  # "claude" or "ocr"
    readers: list[str] = []  # models that answered in time (AI path)
    extraction_note: str = ""  # e.g. why we fell back to OCR
    elapsed_ms: int
    filename: Optional[str] = None
