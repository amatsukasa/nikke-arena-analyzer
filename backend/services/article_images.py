"""Store immutable article WebP files alongside the existing uploads volume."""

import os
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4

from PIL import Image, ImageOps

from services.player_icons import decode_icon


ARTICLE_IMAGE_ROOT = Path("uploads") / "article_images"
MAX_EDGE = 2400


def image_path(image_id: UUID) -> Path:
    return ARTICLE_IMAGE_ROOT / f"{image_id}.webp"


def store_article_image(data: bytes) -> UUID:
    image = ImageOps.exif_transpose(decode_icon(data))
    image.thumbnail((MAX_EDGE, MAX_EDGE), Image.Resampling.LANCZOS)
    if image.getchannel("A").getextrema() == (255, 255):
        image = image.convert("RGB")
    encoded = BytesIO()
    image.save(encoded, "WEBP", lossless=True, method=4)
    # Prefer lossless text and UI edges when the screenshot compresses well.
    if encoded.tell() > 1400 * 1024:
        encoded = BytesIO()
        image.save(encoded, "WEBP", quality=93, method=5, alpha_quality=100)
    image_id = uuid4()
    path = image_path(image_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    try:
        with temporary.open("xb") as output:
            output.write(encoded.getbuffer())
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return image_id
