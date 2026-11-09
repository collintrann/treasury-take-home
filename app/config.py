"""Runtime configuration, all from environment variables (12-factor style).

See docs/DESIGN.md for why each default was chosen.
"""

from __future__ import annotations

import os


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


# Two independent readers ("double-keying"). The primary is the most accurate
# model; the secondary is a different, faster model whose job is to catch the
# primary's silent mistakes (and vice versa). Different models matter: the same
# model twice tends to make the same mistake twice. Set SECONDARY_MODEL="" to
# run a single reader.
PRIMARY_MODEL = os.environ.get("PRIMARY_MODEL") or "claude-opus-5-5"
SECONDARY_MODEL = os.environ.get("SECONDARY_MODEL", "claude-haiku-5-5").strip()

EFFORT = os.environ.get("CLAUDE_EFFORT", "low")  # low effort = less thinking = lower latency

# Guard against a hung call. The readers run in parallel and usually finish
# well inside the ~5 s target; whatever hasn't answered by now is abandoned.
READ_DEADLINE_SECONDS = _float("READ_DEADLINE_SECONDS", 15)

# Images are downscaled to this many pixels on the long edge before upload.
# Claude's vision encoder doesn't benefit from more, and smaller = faster.
MAX_IMAGE_EDGE = int(_float("MAX_IMAGE_EDGE", 1568))

MAX_UPLOAD_BYTES = int(_float("MAX_UPLOAD_MB", 15) * 1024 * 1024)

# How many labels the server checks at the same time.
MAX_CONCURRENCY = int(_float("MAX_CONCURRENCY", 8))

# When set, every /api route except health requires this value in the
# X-Checker-Secret header, so only our front end can spend API credits.
CHECKER_SECRET = os.environ.get("CHECKER_SECRET", "")


def reader_models() -> list[tuple[str, str]]:
    """[(model, role)] for the AI readers, primary first."""
    readers = [(PRIMARY_MODEL, "primary")]
    if SECONDARY_MODEL and SECONDARY_MODEL != PRIMARY_MODEL:
        readers.append((SECONDARY_MODEL, "secondary"))
    return readers


def claude_configured() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))
