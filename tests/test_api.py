"""End-to-end tests through the HTTP API.

The OCR tests run real Tesseract on the bundled sample labels. The Claude
reader is mocked, so the suite needs no API key and no network.
"""

import asyncio
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
    """Pretend a key is configured and script each model's answer.

    Set ``state[model]`` to an ExtractedLabel, an Exception to raise, or a
    ("sleep", seconds, label) tuple to simulate a slow model.
    """
    monkeypatch.setattr(config, "EXTRACTION_MODE", "auto")
    monkeypatch.setattr(config, "claude_configured", lambda: True)
    monkeypatch.setattr(config, "PRIMARY_MODEL", "primary-model")
    monkeypatch.setattr(config, "SECONDARY_MODEL", "secondary-model")
    state = {}

    async def fake(jpeg: bytes, model: str, usage=None):
        assert jpeg[:2] == b"\xff\xd8", "should upload a JPEG"
        result = state[model]
        if isinstance(result, tuple):
            _, seconds, result = result
            await asyncio.sleep(seconds)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(extraction, "extract_with_claude", fake)
    return state


GOOD = ExtractedLabel(
    brand_name="OLD TOM DISTILLERY",
    class_type="Kentucky Straight Bourbon Whiskey",
    alcohol_content="45% Alc./Vol. (90 Proof)",
    net_contents="750 mL",
    producer_name_address="Bottled by Old Tom Distillery, Bardstown, KY",
    government_warning=FULL_TEXT,
    warning_header_bold=True,
)


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

def test_both_readers_agree_passes(fake_claude):
    fake_claude["primary-model"] = GOOD
    fake_claude["secondary-model"] = GOOD
    body = post_sample("01_old_tom_compliant.png").json()
    assert body["extraction_method"] == "claude"
    assert body["readers"] == ["primary-model", "secondary-model"]
    assert body["overall"] == "pass"
    assert {f["agreement"] for f in body["fields"]} == {"agreed"}


def test_silent_correction_is_caught_by_disagreement(fake_claude):
    # The label has a typo. The primary reads it faithfully; the secondary
    # "fixes" it. Neither model alone is trusted with a PASS here.
    typo = FULL_TEXT.replace("Surgeon General", "Surgeon Generel")
    fake_claude["primary-model"] = GOOD.model_copy(update={"government_warning": typo})
    fake_claude["secondary-model"] = GOOD
    body = post_sample("01_old_tom_compliant.png").json()  # application data matches GOOD
    warning = next(f for f in body["fields"] if f["field"] == "government_warning")
    assert warning["status"] == "review"
    assert warning["agreement"] == "disputed"
    assert [r["status"] for r in warning["readings"]] == ["fail", "pass"]
    assert {"op": "missing", "text": "General,"} in warning["diff"]  # points the agent at the word
    assert body["overall"] == "review"


def test_slow_secondary_is_dropped_at_deadline(fake_claude, monkeypatch):
    monkeypatch.setattr(config, "READ_DEADLINE_SECONDS", 0.3)
    fake_claude["primary-model"] = GOOD
    fake_claude["secondary-model"] = ("sleep", 5, GOOD)
    res = post_sample("01_old_tom_compliant.png")
    body = res.json()
    assert body["readers"] == ["primary-model"]
    assert body["overall"] == "pass"  # the strong reader alone is trusted
    assert "not double-checked" in body["extraction_note"]
    assert body["elapsed_ms"] < 2000  # we didn't wait for the slow one


def test_secondary_alone_cannot_pass_the_warning(fake_claude):
    fake_claude["primary-model"] = ClaudeExtractionError("AI service error 529")
    fake_claude["secondary-model"] = GOOD
    body = post_sample("01_old_tom_compliant.png").json()
    warning = next(f for f in body["fields"] if f["field"] == "government_warning")
    assert warning["status"] == "review" and warning["agreement"] == "single"
    assert body["overall"] == "review"


def test_falls_back_to_ocr_when_all_readers_fail(fake_claude):
    fake_claude["primary-model"] = ClaudeExtractionError("could not reach the AI service (network blocked?)")
    fake_claude["secondary-model"] = ClaudeExtractionError("could not reach the AI service (network blocked?)")
    body = post_sample("04_wrong_abv.png").json()
    assert body["extraction_method"] == "ocr"
    assert "network blocked" in body["extraction_note"]
    assert body["overall"] == "fail"


def test_single_reader_mode(fake_claude, monkeypatch):
    monkeypatch.setattr(config, "SECONDARY_MODEL", "")
    fake_claude["primary-model"] = GOOD
    body = post_sample("01_old_tom_compliant.png").json()
    assert body["readers"] == ["primary-model"]
    assert body["overall"] == "pass"
    assert body["extraction_note"] == ""  # single reader by choice isn't a degradation


def test_claude_only_mode_surfaces_error(fake_claude, monkeypatch):
    monkeypatch.setattr(config, "EXTRACTION_MODE", "claude")
    fake_claude["primary-model"] = ClaudeExtractionError("AI reader timed out")
    fake_claude["secondary-model"] = ClaudeExtractionError("AI reader timed out")
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
    assert len(client.get("/api/examples").json()) == 12
    assert client.get("/").status_code == 200
    assert client.get("/samples/01_old_tom_compliant.png").status_code == 200
    assert client.get("/api/health").json()["status"] == "ok"
