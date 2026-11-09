"""Primary reader: Claude vision with a JSON-schema-constrained response.

Claude is only asked to *transcribe*. It never decides pass/fail; that's
``matching.py``'s job. That split keeps verdicts explainable and testable, and
it means a prompt change can't quietly change compliance policy.
"""

from __future__ import annotations

import base64

import anthropic

from .. import config
from ..models import ExtractedLabel

SYSTEM_PROMPT = """\
You transcribe alcohol beverage labels for U.S. TTB compliance review.

Transcribe what is printed. Do not fix, normalize or complete anything:
- Keep the label's capitalization, punctuation and spelling, typos included. \
A reviewer compares your transcription to the required text, so a "corrected" \
transcription hides the very errors they are looking for.
- If a field is not visible in this image, return null. Do not guess it from \
context. It may be on another panel of the label.
- The photo may be angled, curved around a bottle, glary or low-contrast. Read \
through that where you can, and say what got in the way in image_issues, \
written for a reviewer and describing only the photo.
- Set image_readable to false when you can't read the text with confidence. \
Uncertain is not the same as absent: don't return a confident transcription \
of text you can't make out.
- For the government warning, transcribe the whole statement, from its lead-in \
("GOVERNMENT WARNING:" or however it is actually written) to the end. Judge \
its typography separately: lead-in bold, rest not bold, one continuous \
paragraph, set apart from other text, and legible. Answer null for any of \
these you can't judge from the photo."""


class ClaudeExtractionError(RuntimeError):
    pass


_client: anthropic.AsyncAnthropic | None = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        # One retry covers a fast transient error (429/5xx); the caller's deadline
        # still bounds the total wait, so a retry can never blow the budget.
        _client = anthropic.AsyncAnthropic(timeout=config.READ_DEADLINE_SECONDS, max_retries=1)
    return _client


async def extract_with_claude(jpeg: bytes, model: str, usage: dict | None = None) -> ExtractedLabel:
    """Transcribe a label with ``model``. If ``usage`` is given, token counts are written into it."""
    try:
        response = await _get_client().messages.parse(
            model=model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            output_config={"effort": config.EFFORT},
            output_format=ExtractedLabel,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": base64.standard_b64encode(jpeg).decode("ascii"),
                            },
                        },
                        {"type": "text", "text": "Transcribe this label's fields."},
                    ],
                }
            ],
        )
    except anthropic.APITimeoutError as exc:
        raise ClaudeExtractionError("AI reader timed out") from exc
    except anthropic.AuthenticationError as exc:
        raise ClaudeExtractionError("AI reader API key was rejected") from exc
    except anthropic.RateLimitError as exc:
        raise ClaudeExtractionError("AI reader is rate-limited") from exc
    except anthropic.APIConnectionError as exc:
        # This is what a firewall block looks like from here.
        raise ClaudeExtractionError("could not reach the AI service (network blocked?)") from exc
    except anthropic.APIStatusError as exc:
        raise ClaudeExtractionError(f"AI service error {exc.status_code}") from exc

    if usage is not None:
        usage["input_tokens"] = response.usage.input_tokens
        usage["output_tokens"] = response.usage.output_tokens
    if response.stop_reason == "refusal":
        raise ClaudeExtractionError("AI reader declined this image")
    if response.stop_reason == "max_tokens" or response.parsed_output is None:
        raise ClaudeExtractionError("AI reader returned an incomplete answer")
    return response.parsed_output
