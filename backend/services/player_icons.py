"""Player icon codec and shared cross-process mutation lock.

No application/DB imports: also used by offline migration and unit tests.
"""
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
import os
import threading
import warnings

from PIL import Image, UnidentifiedImageError

QUALITY = 80
MAX_BYTES = 10 * 1024 * 1024
MAX_DIMENSION = 10_000
MAX_PIXELS = 25_000_000
IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp"}
_LOCK = threading.RLock()


class InvalidIcon(ValueError):
    pass


class IconTooLarge(InvalidIcon):
    pass


def decode_icon(data):
    if len(data) > MAX_BYTES:
        raise IconTooLarge("Image exceeds 10 MB")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                if image.format not in {"PNG", "JPEG", "WEBP"}:
                    raise InvalidIcon("Unsupported image format")
                w, h = image.size
                if w > MAX_DIMENSION or h > MAX_DIMENSION or w * h > MAX_PIXELS:
                    raise IconTooLarge("Decoded image dimensions exceed the allowed limit")
                if getattr(image, "n_frames", 1) != 1:
                    raise InvalidIcon("Animated images are not supported")
                image.verify()
            with Image.open(BytesIO(data)) as image:
                image.load()
                return image.convert("RGBA")
    except IconTooLarge:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError,
            Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise InvalidIcon("File is not a valid image") from exc


def encode_webp(data):
    source = decode_icon(data)
    stream = BytesIO()
    # Alpha is lossless by default. exact retains hidden RGB in transparent pixels.
    source.save(stream, "WEBP", quality=QUALITY, method=4, exact=True,
                alpha_quality=100, icc_profile=source.info.get("icc_profile", b""))
    encoded = stream.getvalue()
    result = decode_icon(encoded)
    if result.size != source.size or result.getchannel("A").tobytes() != source.getchannel("A").tobytes():
        raise InvalidIcon("WebP validation failed")
    return encoded


def write_webp(path, data):
    encoded = encode_webp(data)
    with Path(path).open("wb") as output:
        output.write(encoded)
        output.flush()
        os.fsync(output.fileno())


@contextmanager
def icon_mutation_lock(root):
    """All API and migration mutations must acquire this before DB row locks.

    The lock file is persistent; never unlink it while a service is running.
    Reads/dry-runs deliberately do not create or acquire this lock.
    """
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    with _LOCK, (root / ".player-icon.lock").open("a+b") as stream:
        if os.name == "nt":
            import msvcrt
            stream.seek(0, 2)
            if stream.tell() == 0:
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(stream, fcntl.LOCK_UN)
