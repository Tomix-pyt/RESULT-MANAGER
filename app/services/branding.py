"""Logo and principal's signature printed on results. Defaults ship with the app (taken from your template);
the operator can replace them in Settings. Overrides live in instance/branding/ (never in the database)."""
import os
from flask import current_app
from PIL import Image

NAMES = ("logo", "signature")
_DEFAULTS = os.path.join(os.path.dirname(os.path.dirname(__file__)), "branding")


def _override_dir() -> str:
    d = os.path.join(current_app.instance_path, "branding")
    os.makedirs(d, exist_ok=True)
    return d


def path_for(name: str) -> str | None:
    if name not in NAMES:
        return None
    custom = os.path.join(_override_dir(), name + ".png")
    if os.path.exists(custom):
        return custom
    default = os.path.join(_DEFAULTS, name + ".png")
    return default if os.path.exists(default) else None


def save_upload(name: str, file_storage, max_px: int = 700) -> None:
    if name not in NAMES:
        raise ValueError("unknown branding image")
    try:
        im = Image.open(file_storage.stream)
        im.load()
    except Exception:
        from app.errors import ValidationError
        raise ValidationError("That file is not a usable image (use PNG or JPG).")
    im = im.convert("RGB")
    im.thumbnail((max_px, max_px))
    im.save(os.path.join(_override_dir(), name + ".png"), optimize=True)


def reset(name: str) -> None:
    custom = os.path.join(_override_dir(), name + ".png")
    if name in NAMES and os.path.exists(custom):
        os.remove(custom)
