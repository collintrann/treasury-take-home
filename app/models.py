"""Data shapes shared across the app. The API models here are the contract the web page mirrors.

Reading and judging stay separate. ``ExtractedLabel`` is what a reader saw on
the label. ``Finding`` and ``CheckResult`` are what the rules in
``matching.py``, ``warning.py`` and ``consensus.py`` decided from it.
"""

from __future__ import annotations

import datetime as dt
from typing import Literal, Optional

from pydantic import BaseModel, Field

ProductType = Literal["distilled_spirits", "wine", "malt_beverage"]
Status = Literal["pass", "fail", "needs_review", "not_evaluated"]
Overall = Literal["pass", "fail", "needs_review"]

# Real applications split the label across front, back and neck panels.
MAX_LABEL_IMAGES = 6


class Application(BaseModel):
    """What the application says. Blank means the applicant didn't give it."""

    brand_name: str = ""
    class_type: str = ""
    alcohol_content: str = ""
    net_contents: str = ""
    producer_name_address: str = ""
    country_of_origin: str = ""  # blank for domestic products


class DiffOp(BaseModel):
    op: Literal["equal", "missing", "extra"]
    text: str


class Finding(BaseModel):
    key: str
    group: Literal["application", "warning"]
    label: str
    status: Status
    expected: Optional[str] = None
    observed: Optional[str] = None  # as printed, original casing and punctuation kept
    explanation: str
    diff: Optional[list[DiffOp]] = None  # warning wording only


class CheckResult(BaseModel):
    overall: Overall
    image_assessable: bool
    image_note: str  # ready to show; says to request a clearer image when not assessable
    findings: list[Finding]
    elapsed_ms: int


class QueueItem(BaseModel):
    id: str
    submitted_at: dt.date
    applicant: str
    product_type: ProductType
    brand_name: str
    images: list[str]  # URL paths, e.g. /samples/queue/COLA-26-0001.png, front panel first
    registry_url: Optional[str] = None  # the record in TTB's Public COLA Registry, for real applications


class QueueDetail(BaseModel):
    id: str
    submitted_at: dt.date
    applicant: str
    product_type: ProductType
    images: list[str]
    registry_url: Optional[str] = None
    application: Application


class QueueEntry(BaseModel):
    """One row of samples/queue/applications.json. The last two fields are test truth, never served."""

    id: str
    submitted_at: dt.date
    applicant: str
    product_type: ProductType
    images: list[str] = Field(min_length=1, max_length=MAX_LABEL_IMAGES)  # file names inside samples/queue/
    registry_url: Optional[str] = None
    application: Application
    expected_overall: Optional[Overall]  # None for real applications, whose right answer isn't known
    scenario: str


class ExtractedLabel(BaseModel):
    """What one reader saw on the label.

    This class is also the JSON schema the reader must answer in, so the
    descriptions below are part of the prompt.
    """

    brand_name: Optional[str] = Field(None, description="Brand name exactly as printed, preserving capitalization.")
    class_type: Optional[str] = Field(
        None, description="Class/type designation, e.g. 'Kentucky Straight Bourbon Whiskey' or 'India Pale Ale'."
    )
    alcohol_content: Optional[str] = Field(
        None, description="Alcohol content statement exactly as printed, e.g. '45% Alc./Vol. (90 Proof)'."
    )
    net_contents: Optional[str] = Field(None, description="Net contents exactly as printed, e.g. '750 mL'.")
    producer_name_address: Optional[str] = Field(
        None, description="Bottler/producer/importer name and address as printed, including 'Bottled by' or similar."
    )
    country_of_origin: Optional[str] = Field(
        None, description="Country of origin statement if present, e.g. 'Product of Scotland'."
    )
    other_names: Optional[list[str]] = Field(
        None,
        description="Every other prominent name on the label besides brand_name, exactly as printed: product or "
        "fanciful names, and brewery, winery, distillery or company names. Labels often lead with one of these.",
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
        description="True if the 'GOVERNMENT WARNING:' lead-in is visibly bolder than the rest of the warning; "
        "false if not; null if you cannot tell.",
    )
    warning_body_bold: Optional[bool] = Field(
        None,
        description="True if the rest of the warning, after the lead-in, is set in bold type; "
        "false if it is regular weight; null if you cannot tell.",
    )
    warning_continuous_paragraph: Optional[bool] = Field(
        None,
        description="True if the warning is one continuous paragraph (line wrapping is fine), not split "
        "into separate paragraphs, bullets or pieces; false if it is split; null if you cannot tell.",
    )
    warning_separate_from_other_text: Optional[bool] = Field(
        None,
        description="True if the warning stands apart from the other label text and graphics; false if it "
        "runs into or is crowded by them; null if you cannot tell.",
    )
    warning_legible: Optional[bool] = Field(
        None,
        description="True if the warning is clearly legible with good contrast against its background; "
        "false if it is faint, low-contrast or hard to read; null if you cannot tell.",
    )
    image_readable: bool = Field(
        description="True if the images are clear enough to read all of the label's text with confidence. "
        "False if blur, glare, darkness, low resolution or cropping leave any of the text uncertain."
    )
    image_issues: Optional[str] = Field(
        None,
        description="One short plain sentence for a reviewer about anything in the images that made reading "
        "hard (glare, angle, blur), or null.",
    )
