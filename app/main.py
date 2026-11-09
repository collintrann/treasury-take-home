"""HTTP layer: thin routes that validate input and delegate to extraction + matching."""

from __future__ import annotations

import asyncio
import logging
import secrets
import time
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .extraction import ClaudeExtractionError, InvalidImageError, extract
from .consensus import verify_extraction
from .models import ApplicationData, VerificationResult

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("label-check")

SAMPLES_DIR = Path(__file__).parent.parent / "samples"

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


if SAMPLES_DIR.exists():
    app.mount("/samples", StaticFiles(directory=SAMPLES_DIR), name="samples")
