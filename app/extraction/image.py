"""Image loading and normalisation shared by both readers."""

from __future__ import annotations

import io

from PIL import Image, ImageOps, UnidentifiedImageError

from .. import config


class InvalidImageError(ValueError):
    """The upload isn't an image we can read."""


def load_image(data: bytes) -> Image.Image:
    if not data:
        raise InvalidImageError("The file is empty.")
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise InvalidImageError("This file isn't a readable image. Please upload a JPG, PNG or WEBP.") from exc

    # Phone photos often carry rotation in EXIF rather than in the pixels.
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    return img


def to_upload_jpeg(img: Image.Image) -> bytes:
    """Downscale + JPEG-encode for the API: fewer bytes and tokens means lower latency."""
    img = img.copy()
    img.thumbnail((config.MAX_IMAGE_EDGE, config.MAX_IMAGE_EDGE))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=88)
    return buf.getvalue()
