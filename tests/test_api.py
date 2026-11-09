"""End-to-end tests through the HTTP API.

The models are scripted stand-ins, so the suite needs no API key and no network.
"""

import asyncio
import csv
import io
import re
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
def fake_claude(monkeypatch):
    """Pretend a key is configured and script each model's answer.

    Set ``state[model]`` to an ExtractedLabel, an Exception to raise, or a
    ("sleep", seconds, label) tuple to simulate a slow model.
    """
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


# ---------------------------------------------------------- Claude, mocked

def test_both_readers_agree_passes(fake_claude):
    fake_claude["primary-model"] = GOOD
    fake_claude["secondary-model"] = GOOD
    body = post_sample("01_old_tom_compliant.png").json()
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
    assert body["elapsed_ms"] < 2000  # we didn't wait for the slow one


def test_secondary_alone_cannot_pass_the_warning(fake_claude):
    fake_claude["primary-model"] = ClaudeExtractionError("AI service error 529")
    fake_claude["secondary-model"] = GOOD
    body = post_sample("01_old_tom_compliant.png").json()
    warning = next(f for f in body["fields"] if f["field"] == "government_warning")
    assert warning["status"] == "review" and warning["agreement"] == "single"
    assert body["overall"] == "review"


def test_unreadable_when_all_readers_fail(fake_claude):
    fake_claude["primary-model"] = ClaudeExtractionError("could not reach the AI service")
    fake_claude["secondary-model"] = ClaudeExtractionError("could not reach the AI service")
    res = post_sample("04_wrong_abv.png")
    assert res.status_code == 503
    assert "try again" in res.json()["detail"]


def test_unreadable_without_api_key(fake_claude, monkeypatch):
    monkeypatch.setattr(config, "claude_configured", lambda: False)
    assert post_sample("01_old_tom_compliant.png").status_code == 503


def test_single_reader_mode(fake_claude, monkeypatch):
    monkeypatch.setattr(config, "SECONDARY_MODEL", "")
    fake_claude["primary-model"] = GOOD
    body = post_sample("01_old_tom_compliant.png").json()
    assert body["readers"] == ["primary-model"]
    assert body["overall"] == "pass"
    assert body["extraction_note"] == ""  # single reader by choice isn't a degradation


# --------------------------------------------------------------- validation

def test_rejects_non_image(fake_claude):
    res = client.post(
        "/api/verify",
        files={"image": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
        data={"brand_name": "X"},
    )
    assert res.status_code == 400
    assert "image" in res.json()["detail"].lower()


def test_requires_some_application_data(fake_claude):
    with open(SAMPLES / "01_old_tom_compliant.png", "rb") as img:
        res = client.post("/api/verify", files={"image": ("a.png", img, "image/png")})
    assert res.status_code == 400


def test_rejects_oversized_upload(fake_claude, monkeypatch):
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


# Agents are nontechnical: nothing they see may mention how the app works.
INTERNAL_WORDS = re.compile(r"\b(AI|model|models|OCR|Claude|Opus|Haiku|Sonnet|reader|readers|API|Tesseract)\b", re.I)


def user_visible_text(body: dict) -> list[str]:
    if "detail" in body:
        return [body["detail"]]
    return [body["extraction_note"]] + [f["note"] for f in body["fields"]]


@pytest.mark.parametrize(
    "scenario",
    ["agree", "dispute", "secondary_only", "all_fail"],
)
def test_user_facing_text_never_mentions_internals(fake_claude, monkeypatch, scenario):
    typo = GOOD.model_copy(update={"government_warning": FULL_TEXT.replace("Surgeon General", "Surgeon Generel")})
    down = ClaudeExtractionError("could not reach the AI service (network blocked?)")
    fake_claude["primary-model"], fake_claude["secondary-model"] = {
        "agree": (GOOD, GOOD),
        "dispute": (typo, GOOD),
        "secondary_only": (down, GOOD),
        "all_fail": (down, down),
    }[scenario]
    for text in user_visible_text(post_sample("01_old_tom_compliant.png").json()):
        assert not INTERNAL_WORDS.search(text), text


def test_ui_source_never_mentions_internals():
    static = Path(__file__).parent.parent / "app" / "static"
    visible = re.sub(r"<[^>]+>", " ", (static / "index.html").read_text())
    strings = re.findall(r"`[^`]*`|\"[^\"]*\"", (static / "app.js").read_text())
    for text in [visible, *strings]:
        assert not re.search(r"\b(AI|OCR|Claude|Opus|Haiku|Sonnet|model)\b", text), text


def test_checker_secret_is_required_when_configured(monkeypatch):
    monkeypatch.setattr(config, "CHECKER_SECRET", "s3cret")
    assert client.get("/api/examples").status_code == 401
    assert client.get("/api/examples", headers={"X-Checker-Secret": "wrong"}).status_code == 401
    assert client.get("/api/examples", headers={"X-Checker-Secret": "s3cret"}).status_code == 200
    assert client.get("/api/health").status_code == 200
