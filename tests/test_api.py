"""End-to-end tests through the HTTP API.

The OCR tests run real Tesseract on the bundled sample labels. The Claude
reader is mocked, so the suite needs no API key and no network.
"""

import csv
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import config
from app import extraction
from app.extraction.claude_reader import ClaudeExtractionError
from app.main import app
from app.models import ExtractedLabel
from app.warning import FULL_TEXT

SAMPLES = Path(__file__).parent.parent / "samples"
client = TestClient(app)


def sample_rows() -> dict[str, dict]:
    with open(SAMPLES / "batch.csv", newline="") as f:
        return {r["filename"]: r for r in csv.DictReader(f)}


def post_sample(filename: str, **overrides):
    row = sample_rows()[filename] | overrides
    fields = {k: row.get(k, "") for k in config_fields()}
    with open(SAMPLES / filename, "rb") as img:
        return client.post("/api/verify", files={"image": (filename, img, "image/png")}, data=fields)


def config_fields():
    return ["brand_name", "class_type", "alcohol_content", "net_contents", "producer_name_address", "country_of_origin"]


@pytest.fixture
def ocr_only(monkeypatch):
    monkeypatch.setattr(config, "EXTRACTION_MODE", "ocr")


@pytest.fixture
def fake_claude(monkeypatch):
    """Pretend a key is configured and make the Claude call return ``label``."""
    monkeypatch.setattr(config, "EXTRACTION_MODE", "auto")
    monkeypatch.setattr(config, "claude_configured", lambda: True)
    state = {}

    async def fake(jpeg: bytes):
        assert jpeg[:2] == b"\xff\xd8", "should upload a JPEG"
        if isinstance(state.get("result"), Exception):
            raise state["result"]
        return state["result"]

    monkeypatch.setattr(extraction, "extract_with_claude", fake)
    return state


# ----------------------------------------------------------------- OCR, real

@pytest.mark.parametrize(
    "filename, expected",
    [
        ("01_old_tom_compliant.png", "review"),  # OCR can't confirm bold -> review
        ("03_title_case_warning.png", "fail"),
        ("04_wrong_abv.png", "fail"),
        ("05_altered_warning.png", "fail"),
        ("07_angled_glare.png", "review"),  # deskew makes this readable
        ("09_imported_scotch.png", "review"),
    ],
)
def test_ocr_on_samples(ocr_only, filename, expected):
    res = post_sample(filename)
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["extraction_method"] == "ocr"
    assert body["overall"] == expected
    assert body["elapsed_ms"] < 5000  # the stakeholder's latency bar


def test_ocr_compliant_label_only_flags_boldness(ocr_only):
    fields = post_sample("01_old_tom_compliant.png").json()["fields"]
    not_passing = {f["field"] for f in fields if f["status"] not in ("pass", "skipped")}
    assert not_passing == {"government_warning"}


# ---------------------------------------------------------- Claude, mocked

def test_claude_result_is_used(fake_claude):
    fake_claude["result"] = ExtractedLabel(
        brand_name="OLD TOM DISTILLERY",
        class_type="Kentucky Straight Bourbon Whiskey",
        alcohol_content="45% Alc./Vol. (90 Proof)",
        net_contents="750 mL",
        producer_name_address="Bottled by Old Tom Distillery, Bardstown, KY",
        government_warning=FULL_TEXT,
        warning_header_bold=True,
    )
    body = post_sample("01_old_tom_compliant.png").json()
    assert body["extraction_method"] == "claude"
    assert body["overall"] == "pass"


def test_falls_back_to_ocr_when_claude_fails(fake_claude):
    fake_claude["result"] = ClaudeExtractionError("could not reach the AI service (network blocked?)")
    body = post_sample("04_wrong_abv.png").json()
    assert body["extraction_method"] == "ocr"
    assert "network blocked" in body["extraction_note"]
    assert body["overall"] == "fail"


def test_claude_only_mode_surfaces_error(fake_claude, monkeypatch):
    monkeypatch.setattr(config, "EXTRACTION_MODE", "claude")
    fake_claude["result"] = ClaudeExtractionError("AI reader timed out")
    res = post_sample("01_old_tom_compliant.png")
    assert res.status_code == 502
    assert "timed out" in res.json()["detail"]


# --------------------------------------------------------------- validation

def test_rejects_non_image(ocr_only):
    res = client.post(
        "/api/verify",
        files={"image": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
        data={"brand_name": "X"},
    )
    assert res.status_code == 400
    assert "image" in res.json()["detail"].lower()


def test_requires_some_application_data(ocr_only):
    with open(SAMPLES / "01_old_tom_compliant.png", "rb") as img:
        res = client.post("/api/verify", files={"image": ("a.png", img, "image/png")})
    assert res.status_code == 400


def test_rejects_oversized_upload(ocr_only, monkeypatch):
    monkeypatch.setattr(config, "MAX_UPLOAD_BYTES", 10)
    with open(SAMPLES / "01_old_tom_compliant.png", "rb") as img:
        res = client.post("/api/verify", files={"image": ("a.png", img, "image/png")}, data={"brand_name": "X"})
    assert res.status_code == 413


# -------------------------------------------------------------------- batch

def test_parse_manifest_handles_quoted_commas_and_aliases():
    csv_text = 'File,Brand,ABV,Producer\nlabel1.jpg,Acme,40%,"Acme Co., Austin, TX"\n,,,\n'
    res = client.post("/api/parse-manifest", files={"manifest": ("m.csv", csv_text.encode("utf-8-sig"), "text/csv")})
    assert res.status_code == 200, res.text
    rows = res.json()["rows"]
    assert rows == [
        {
            "filename": "label1.jpg",
            "application": {
                "brand_name": "Acme",
                "class_type": "",
                "alcohol_content": "40%",
                "net_contents": "",
                "producer_name_address": "Acme Co., Austin, TX",
                "country_of_origin": "",
            },
        }
    ]


def test_parse_manifest_requires_filename_column():
    res = client.post("/api/parse-manifest", files={"manifest": ("m.csv", b"brand\nAcme\n", "text/csv")})
    assert res.status_code == 400


def test_examples_and_static():
    assert len(client.get("/api/examples").json()) == 9
    assert client.get("/").status_code == 200
    assert client.get("/samples/01_old_tom_compliant.png").status_code == 200
    assert client.get("/api/health").json()["status"] == "ok"
