"""Publish the original header shield and the other site identity assets."""

from pathlib import Path
import re
import shutil


CURRENT = "/assets/identity/"
HEADER_SHIELD = "shield-96.webp"
REPLACEMENTS = {
    "aperture-mark.svg": "compass.svg",
    "atlas-shield.svg": "compass.svg",
    "favicon.svg": "compass.svg",
    "favicon.ico": "compass.ico",
    "favicon-v2.ico": "compass.ico",
    "favicon-16.png": "compass-16.png",
    "favicon-32.png": "compass-32.png",
    "favicon-48-preview.png": "compass-32.png",
    "apple-touch-icon.png": "compass-180.png",
    "icon-192.png": "compass-192.png",
    "icon-512.png": "compass-512.png",
    "icon-maskable-512.png": "compass-maskable-512.png",
    "icon-96.webp": HEADER_SHIELD,
    "mystic-shield-v2.png": "compass-512.png",
    "shield-snes.png": "compass-512.png",
}
LEGACY = re.compile(
    rb"/assets/brand/(" + b"|".join(re.escape(name.encode()) for name in REPLACEMENTS)
    + rb")(?:\?v=[A-Za-z0-9_-]+)?"
)


def apply(root: Path):
    sources = Path(__file__).with_name("identity-assets")
    target = root / "assets" / "identity"
    old = root / "assets" / "brand"
    target.mkdir(exist_ok=True)
    for name in sorted(set(REPLACEMENTS.values()) - {HEADER_SHIELD}):
        shutil.copyfile(sources / name, target / name)
    shutil.copyfile(old / "icon-96.webp", target / HEADER_SHIELD)
    # An open page from the previous release can still request the compass.
    shutil.copyfile(sources / "compass-96.webp", target / "compass-96.webp")
    for path in root.rglob("*"):
        if path.suffix in {".html", ".js", ".css", ".json", ".webmanifest", ".xml"} and path.is_file():
            original = path.read_bytes()
            updated = LEGACY.sub(
                lambda match: (CURRENT + REPLACEMENTS[match[1].decode()]).encode(), original
            )
            if updated != original:
                path.write_bytes(updated)
    for name in REPLACEMENTS:
        (old / name).unlink()
    old.rmdir()
