"""HTTP layer: thin routes that validate input and delegate to extraction + matching."""

from __future__ import annotations

import asyncio
import csv
import io
import logging
import secrets
import time
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .extraction import ClaudeExtractionError, InvalidImageError, extract
from .consensus import verify_extraction
from .models import ApplicationData, VerificationResult

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("label-check")

STATIC_DIR = Path(__file__).parent / "static"
SAMPLES_DIR = Path(__file__).parent.parent / "samples"
APP_FIELDS = list(ApplicationData.model_fields)

app = FastAPI(title="Label Check", docs_url="/api/docs", redoc_url=None)

# Caps simultaneous extractions so a 300-label batch can't exhaust API rate
# limits or the box's CPU. Extra requests wait their turn.
_slots = asyncio.Semaphore(config.MAX_CONCURRENCY)


@app.middleware("http")
async def require_checker_secret(request: Request, call_next):
    path = request.url.path
    if config.CHECKER_SECRET and path.startswith("/api/") and path != "/api/health":
        given = request.headers.get("X-Checker-Secret", "")
        if not secrets.compare_digest(given, config.CHECKER_SECRET):
            return JSONResponse({"detail": "Not allowed."}, status_code=401)
    return await call_next(request)


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "configured": config.claude_configured(),
        "models": [m for m, _ in config.reader_models()],
    }


@app.post("/api/verify", response_model=VerificationResult)
async def verify_label(
    image: UploadFile = File(...),
    brand_name: str = Form(""),
    class_type: str = Form(""),
    alcohol_content: str = Form(""),
    net_contents: str = Form(""),
    producer_name_address: str = Form(""),
    country_of_origin: str = Form(""),
) -> VerificationResult:
    started = time.perf_counter()
    data = await image.read(config.MAX_UPLOAD_BYTES + 1)
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"Image is too large (limit {config.MAX_UPLOAD_BYTES // (1024 * 1024)} MB).")

    application = ApplicationData(
        brand_name=brand_name,
        class_type=class_type,
        alcohol_content=alcohol_content,
        net_contents=net_contents,
        producer_name_address=producer_name_address,
        country_of_origin=country_of_origin,
    )
    if not any(application.model_dump().values()):
        raise HTTPException(400, "Enter at least one application field to compare against.")

    try:
        async with _slots:
            result = await extract(data)
    except InvalidImageError as exc:
        raise HTTPException(400, str(exc)) from exc
    except ClaudeExtractionError as exc:
        log.error("could not read %s: %s", image.filename, exc)
        raise HTTPException(503, "We couldn't read this label right now. Please try again in a minute.") from exc

    overall, fields = verify_extraction(application, result)
    elapsed = int((time.perf_counter() - started) * 1000)
    readers = [r.model for r in result.readings]
    disputed = [f.field for f in fields if f.agreement == "disputed"]
    log.info(
        "verified %s via %s in %d ms -> %s%s",
        image.filename, ",".join(readers), elapsed, overall.value, f" (disputed: {','.join(disputed)})" if disputed else "",
    )
    return VerificationResult(
        overall=overall,
        fields=fields,
        readers=readers,
        extraction_note=result.note,
        elapsed_ms=elapsed,
        filename=image.filename,
    )


def _header_key(name: str) -> str:
    return "_".join(name.strip().lower().replace("/", " ").split())


# Friendly CSV header spellings -> internal field names.
_HEADER_ALIASES = {
    "file": "filename",
    "image": "filename",
    "brand": "brand_name",
    "class": "class_type",
    "abv": "alcohol_content",
    "alcohol": "alcohol_content",
    "net": "net_contents",
    "volume": "net_contents",
    "producer": "producer_name_address",
    "bottler": "producer_name_address",
    "country": "country_of_origin",
}


@app.post("/api/parse-manifest")
async def parse_manifest(manifest: UploadFile = File(...)) -> dict:
    """Parse the batch CSV (one row per label) into application records.

    Parsed server-side because Python's csv module copes with quoted commas
    in addresses, BOMs from Excel, etc. - fiddly to get right in browser JS.
    """
    raw = await manifest.read(2 * 1024 * 1024)
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(400, "The CSV file is empty.")
    keys = {h: _HEADER_ALIASES.get(_header_key(h), _header_key(h)) for h in reader.fieldnames}
    if "filename" not in keys.values():
        raise HTTPException(400, "The CSV needs a 'filename' column naming each label image.")

    rows, errors = [], []
    for line_no, raw_row in enumerate(reader, start=2):
        row = {keys[k]: (v or "").strip() for k, v in raw_row.items() if k in keys}
        if not row.get("filename"):
            if any(row.values()):
                errors.append(f"Row {line_no}: missing filename.")
            continue
        rows.append(
            {
                "filename": row["filename"],
                "application": {f: row.get(f, "") for f in APP_FIELDS},
            }
        )
    if not rows:
        raise HTTPException(400, "No label rows found in the CSV.")
    return {"rows": rows, "errors": errors}


@app.get("/api/examples")
def examples() -> list[dict]:
    """The bundled sample labels, so evaluators can try the app in one click."""
    path = SAMPLES_DIR / "batch.csv"
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return [
            {
                "filename": row["filename"],
                "what_this_tests": row.get("what_this_tests", ""),
                "application": {k: row.get(k, "") for k in APP_FIELDS},
            }
            for row in csv.DictReader(f)
        ]


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
if SAMPLES_DIR.exists():
    app.mount("/samples", StaticFiles(directory=SAMPLES_DIR), name="samples")
