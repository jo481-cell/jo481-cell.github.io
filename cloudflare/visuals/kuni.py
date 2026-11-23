"""Publish Kuni in the atlas, guide, and adventure journal."""

import html
from hashlib import sha256
import json
from pathlib import Path
import re


ART = Path(__file__).with_name("map-assets")
ROUTE = Path("series/a-link-to-the-past/index.html")
MAP_LANDING_PAGES = (Path("map/instagram/index.html"), Path("map/tiktok/index.html"))
PUBLIC = "/assets/atlas-charts/"
LEGACY_URL = r"/assets/original/fairy-guide(?:\.png|-240\.webp)"
HTML_IMAGE = re.compile(r'<img\b(?=[^>]*\bsrc="' + LEGACY_URL + r'")[^>]*>')
CLIENT_IMAGE = re.compile(r"src:`" + LEGACY_URL + r"`[^{}]*?(?=\})")
LABELS = {
    "en": (
        ("Living atlas & fairy guide", "Living atlas and Kuni"),
        ("Your fairy guide", "Kuni, your fairy guide"),
        ("YOUR FAIRY GUIDE", "Kuni"),
    ),
    "fr": (
        ("Atlas vivant & fée-guide", "Atlas vivant et Kuni"),
        ("Votre fée-guide", "Kuni, votre fée-guide"),
        ("VOTRE FÉE-GUIDE", "Kuni"),
    ),
    "es": (
        ("Atlas vivo y hada guía", "Atlas vivo y Kuni"),
        ("Tu hada guía", "Kuni, tu hada guía"),
        ("TU HADA GUÍA", "Kuni"),
    ),
    "ja": (
        ("動くアトラスと妖精ガイド", "動くアトラスとKuni"),
        ("あなたの妖精ガイド", "妖精ガイドのKuni"),
        ("あなたの妖精ガイド", "Kuni"),
    ),
    "zh": (
        ("灵动地图与精灵向导", "灵动地图与 Kuni"),
        ("你的精灵向导", "你的精灵向导 Kuni"),
        ("你的精灵向导", "Kuni"),
    ),
}


def _replace(source, old, new, path):
    if old not in source:
        raise ValueError(f"Expected Kuni placeholder {old!r} in {path}")
    return source.replace(old, new)


def _update_html(path, language, url, width, height):
    source = path.read_text(encoding="utf-8")

    def image(match):
        tag = re.sub(LEGACY_URL, url, match[0])
        tag = re.sub(r'\bwidth="\d+"', f'width="{width}"', tag)
        return re.sub(r'\bheight="\d+"', f'height="{height}"', tag)

    source, count = HTML_IMAGE.subn(image, source)
    if count != 3:
        raise ValueError(f"Expected three fairy images in {path}, found {count}")
    formats = ('{}</label>', 'aria-label="{}"', '<p class="alttp-kicker">{}</p>')
    for pair, markup in zip(LABELS[language], formats):
        old, new = (markup.format(html.escape(text, quote=False)) for text in pair)
        source = _replace(source, old, new, path)
    path.write_bytes(source.encode("utf-8"))


def _update_client(path, source, url, width, height):
    def image(match):
        props = re.sub(LEGACY_URL, url, match[0])
        props = re.sub(r"\bwidth:\d+", f"width:{width}", props)
        return re.sub(r"\bheight:\d+", f"height:{height}", props)

    source, count = CLIENT_IMAGE.subn(image, source)
    if count != 3:
        raise ValueError(f"Expected three fairy images in {path}, found {count}")
    for old, new in LABELS["fr"]:
        source = _replace(source, f"`{old}`", f"`{new}`", path)
    path.write_bytes(source.encode("utf-8"))


def _update_messages(assets):
    for language, labels in LABELS.items():
        count = 0
        for path in assets.glob(f"{language}-*.js"):
            source = path.read_text(encoding="utf-8")
            if f'"{LABELS["fr"][0][0]}":' not in source:
                continue
            for (old_key, new_key), (old_text, new_text) in zip(LABELS["fr"], labels):
                source = _replace(source, f'"{old_key}":`{old_text}`', f'"{new_key}":`{new_text}`', path)
            path.write_bytes(source.encode("utf-8"))
            count += 1
        if count == 0:
            raise ValueError(f"No {language} messages found for Kuni")


def apply(root: Path):
    record = json.loads((ART / "kuni-provenance.json").read_text(encoding="utf-8"))
    portrait = (ART / "kuni.webp").read_bytes()
    digest = sha256(portrait).hexdigest()
    if digest != record["derivative"]["sha256"]:
        raise ValueError("Kuni portrait differs from its provenance record")
    url = PUBLIC + f"kuni-{digest[:16]}.webp"
    target = root / PUBLIC.strip("/")
    target.mkdir(parents=True, exist_ok=True)
    (root / url.lstrip("/")).write_bytes(portrait)
    record["derivative"]["url"] = url
    (target / "kuni-provenance.json").write_bytes(
        (json.dumps(record, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    )
    width, height = record["derivative"]["dimensions"]
    for language in LABELS:
        base = root if language == "en" else root / language
        _update_html(base / ROUTE, language, url, width, height)
    for route in MAP_LANDING_PAGES:
        _update_html(root / route, "en", url, width, height)
    assets = root / "assets"
    count = 0
    for pattern in ("alttp-*.js", "series*.js"):
        for path in assets.glob(pattern):
            source = path.read_text(encoding="utf-8")
            if not re.search(LEGACY_URL, source):
                continue
            _update_client(path, source, url, width, height)
            count += 1
    if count == 0:
        raise ValueError("No atlas client files found for Kuni")
    _update_messages(assets)
