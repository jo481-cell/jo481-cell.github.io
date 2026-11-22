"""Keep the shared link preview and the corresponding media credit in sync."""

import json
from hashlib import sha256
from pathlib import Path
import re
import shutil

from . import editorial


OLD = "/assets/social/then-and-now-editorial.png"
NEW = "/assets/social/then-and-now-notes.jpg"
PAGE = "/then-and-now/"
WIDTH, HEIGHT = 1280, 720
ALT = {
    "en": "A brass magnifier over open notebook pages on an editorial desk.",
    "fr": "Une loupe en laiton posée sur un carnet ouvert, sur un bureau de rédaction.",
    "es": "Una lupa de latón sobre un cuaderno abierto en una mesa de redacción.",
    "ja": "編集机の上で開いたノートに置かれた真鍮の拡大鏡。",
    "zh": "编辑桌上，一把黄铜放大镜放在摊开的笔记本上。",
}


def apply(root: Path):
    target = root / NEW.lstrip("/")
    shutil.copyfile(editorial.HERE / "editorial-assets" / target.name, target)
    for lang, alt in ALT.items():
        base = root if lang == "en" else root / lang
        path = base / PAGE.strip("/") / "index.html"
        source = path.read_text(encoding="utf-8")
        fields = {
            "og:image:width": WIDTH, "og:image:height": HEIGHT,
            "og:image:type": "image/jpeg", "og:image:alt": alt, "twitter:image:alt": alt,
        }

        def update_tag(match):
            tag = match[0]
            value = fields.get(editorial.attribute(tag, "property") or editorial.attribute(tag, "name"))
            return editorial.attr(tag, "content", value) if value is not None else tag

        if source.count(OLD) != 2:
            raise ValueError(f"Expected two share image URLs in {path}")
        editorial.save(path, re.sub(r"<meta\b[^>]+>", update_tag, source.replace(OLD, NEW)))

    bundle_entry = re.compile(r'\{src:[`"]' + re.escape(OLD) + r'[`"],alt:[^}]+\}')
    descriptions = editorial.compact(ALT)
    fallback = editorial.compact(ALT["en"])
    payload = (f'{{src:"{NEW}",get alt(){{return ({descriptions})'
               f'[document.documentElement.lang.split("-")[0]]||{fallback}}},'
               f'width:{WIDTH},height:{HEIGHT},type:"image/jpeg"}}')
    for path in (root / "assets").glob("site-metadata-*.js"):
        source = path.read_text(encoding="utf-8")
        if OLD not in source:
            continue
        updated, count = bundle_entry.subn(lambda _: payload, source)
        if count != 1 or OLD in updated:
            raise ValueError(f"Unrecognized share metadata in {path}")
        editorial.save(path, updated)

    manifest = target.with_name("sources.json")
    registry = json.loads(manifest.read_bytes())
    registry["assets"] = [asset for asset in registry["assets"] if asset["src"] != OLD]
    registry["assets"].append({
        "src": NEW, "page": PAGE, "kind": "Editorial illustration by Hyrule Atlas",
        "source": "/assets/editorial/observation.webp", "provenance": editorial.CREDITS,
        "processing": "JPEG conversion of the existing original illustration, without cropping.",
        "width": WIDTH, "height": HEIGHT, "type": "image/jpeg",
        "sha256": sha256(target.read_bytes()).hexdigest(),
    })
    registry["scope"] = "Illustrations by Hyrule Atlas. Sharing metadata is localized by page."
    editorial.save(manifest, json.dumps(registry, ensure_ascii=False, indent=2) + "\n")
    (root / OLD.lstrip("/")).unlink()
