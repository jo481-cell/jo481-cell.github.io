"""Publish the original shield for the masthead and browser favicons."""

from pathlib import Path
import re
import shutil


CURRENT = "/assets/identity/"
SHIELD_FILES = {
    "shield.ico": "favicon-v2.ico",
    "shield-16.png": "favicon-16.png",
    "shield-32.png": "favicon-32.png",
    "shield-48.png": "favicon-48-preview.png",
    "shield-180.png": "apple-touch-icon.png",
    "shield-192.png": "icon-192.png",
    "shield-96.webp": "icon-96.webp",
}
REPLACEMENTS = {
    "aperture-mark.svg": "compass.svg",
    "atlas-shield.svg": "compass.svg",
    "favicon.svg": "compass.svg",
    "favicon.ico": "shield.ico",
    "favicon-v2.ico": "shield.ico",
    "favicon-16.png": "shield-16.png",
    "favicon-32.png": "shield-32.png",
    "favicon-48-preview.png": "shield-48.png",
    "apple-touch-icon.png": "shield-180.png",
    "icon-192.png": "compass-192.png",
    "icon-512.png": "compass-512.png",
    "icon-maskable-512.png": "compass-maskable-512.png",
    "icon-96.webp": "shield-96.webp",
    "mystic-shield-v2.png": "compass-512.png",
    "shield-snes.png": "compass-512.png",
}
LEGACY = re.compile(
    rb"/assets/brand/(" + b"|".join(re.escape(name.encode()) for name in REPLACEMENTS)
    + rb")(?:\?v=[A-Za-z0-9_-]+)?"
)
SMALL_ICON = (CURRENT + "shield-32.png").encode()
SEARCH_ICON = (CURRENT + "shield-192.png").encode()


def apply(root: Path):
    sources = Path(__file__).with_name("identity-assets")
    target = root / "assets" / "identity"
    old = root / "assets" / "brand"
    target.mkdir(exist_ok=True)
    # Keep compass files available to browsers holding documents from earlier releases.
    for source in sources.glob("compass.*"):
        shutil.copyfile(source, target / source.name)
    for source in sources.glob("compass-*"):
        shutil.copyfile(source, target / source.name)
    for name, previous in SHIELD_FILES.items():
        shutil.copyfile(old / previous, target / name)
    shutil.copyfile(target / "shield.ico", root / "favicon.ico")
    for path in root.rglob("*"):
        if path.suffix in {".html", ".js", ".css", ".json", ".webmanifest", ".xml"} and path.is_file():
            original = path.read_bytes()
            updated = LEGACY.sub(
                lambda match: (CURRENT + REPLACEMENTS[match[1].decode()]).encode(), original
            )
            # Keep the small browser variants and set the default to a larger PNG for Google.
            if path.suffix == ".html":
                link = b'<link rel="icon" href="' + SMALL_ICON + b'"/>'
                updated = updated.replace(link, link.replace(SMALL_ICON, SEARCH_ICON))
            elif path.suffix == ".js":
                default = b'favicon_url:`' + SMALL_ICON + b'`'
                updated = updated.replace(default, default.replace(SMALL_ICON, SEARCH_ICON))
            if updated != original:
                path.write_bytes(updated)
    for name in REPLACEMENTS:
        (old / name).unlink()
    old.rmdir()
