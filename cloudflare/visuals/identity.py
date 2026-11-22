"""Publish the site's independently drawn compass mark and its size variants."""

from pathlib import Path
import re
import shutil


CURRENT = "/assets/identity/"
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
    "icon-96.webp": "compass-96.webp",
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
    target.mkdir(exist_ok=True)
    for name in sorted(set(REPLACEMENTS.values())):
        shutil.copyfile(sources / name, target / name)
    for path in root.rglob("*"):
        if path.suffix in {".html", ".js", ".css", ".json", ".webmanifest", ".xml"} and path.is_file():
            original = path.read_bytes()
            updated = LEGACY.sub(
                lambda match: (CURRENT + REPLACEMENTS[match[1].decode()]).encode(), original
            )
            if updated != original:
                path.write_bytes(updated)
    old = root / "assets" / "brand"
    for name in REPLACEMENTS:
        (old / name).unlink()
    old.rmdir()
