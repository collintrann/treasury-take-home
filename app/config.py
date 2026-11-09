"""Runtime configuration, all from environment variables (12-factor style)."""

from __future__ import annotations

import os


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


# "auto"   - use Claude when a key is configured, otherwise / on failure use OCR
# "claude" - Claude only (errors surface to the user)
# "ocr"    - offline OCR only (for locked-down networks)
EXTRACTION_MODE = os.environ.get("EXTRACTION_MODE", "auto").lower()

MODEL = os.environ.get("LABEL_MODEL", "claude-opus-5-5")
EFFORT = os.environ.get("CLAUDE_EFFORT", "low")  # low effort = less thinking = lower latency

# Hard ceiling on the Claude call. The stakeholder bar is ~5 s end-to-end; if
# the API is slower than this we abandon it and fall back to OCR rather than
# leave an agent staring at a spinner.
CLAUDE_TIMEOUT_SECONDS = _float("CLAUDE_TIMEOUT_SECONDS", 8.0)

# Images are downscaled to this many pixels on the long edge before upload.
# Claude's vision encoder doesn't benefit from more, and smaller = faster.
MAX_IMAGE_EDGE = int(_float("MAX_IMAGE_EDGE", 1568))

MAX_UPLOAD_BYTES = int(_float("MAX_UPLOAD_MB", 15) * 1024 * 1024)

# How many labels the server will send to Claude/OCR at the same time.
MAX_CONCURRENCY = int(_float("MAX_CONCURRENCY", 8))


def claude_configured() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))
