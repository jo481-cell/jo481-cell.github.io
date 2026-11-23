"""Publish original game-specific illustrations throughout the game catalogue."""

from hashlib import sha256
from html import escape
import json
from pathlib import Path
import re

from . import editorial


ASSETS = Path(__file__).with_name("catalogue-assets")
SITE = "https://hyruleatlas.com"
SIZE = (1200, 800)
ALTS = ASSETS / "translations.json"
ROOT_GAME_ROUTES = {"breath-of-the-wild", "tears-of-the-kingdom"}
LEGACY_COVER = r"/assets/editorial/catalogue-[1-6]\.webp\#(?P<slug>[a-z0-9-]+)"
COVER_URI = re.compile(LEGACY_COVER)
DYNAMIC_COVER = re.compile(
    r"/assets/editorial/catalogue-\$\{\(\{[^{}]+\}\)\[(?P<key>[\w$.]+)\]\}\.webp\#\$\{(?P=key)\}"
)
BUNDLED_ENTRY_COVER = re.compile(
    r'"src":"' + LEGACY_COVER + r'","width":\d+,"height":\d+,'
    r'(?:get alt\(\)\{return .*?\}|"alt":"(?:[^"\\]|\\.)*")(?=,"credit":)'
)
JSX_COVER = re.compile(
    r'(?P<property>\b(?:src|image):)(?P<quote>[`"\'])' + LEGACY_COVER + r'(?P=quote)'
    r'(?P<props>(?:,(?:width|height|loading|decoding|className):[^,{}]{1,100}){0,5}),(?P<label>alt|imageAlt):'
    r'(?P<alt_quote>[`"\'])(?P<alt>(?:(?!(?P=alt_quote))[^\\]|\\.)*)(?P=alt_quote)'
)
SRCSET_WIDTH = re.compile(r"(/assets/editorial/game-[a-z0-9-]+-[a-f0-9]{12}\.webp)\s+\d+w")
DYNAMIC_SRCSET = re.compile(
    r'(?P<property>\b(?:srcSet|imageSrcSet):)`(?P<cover>\$\{atlasCatalogueUrl\((?P<key>[\w$.]+)\)\})\s+\d+w'
    r'(?:,\s*\$\{atlasCatalogueUrl\((?P=key)\)\}\s+\d+w)*`'
)
QUICK_LINK_SIZE = re.compile(
    r'(?P<property>width|height):[\w$]+\.slug===`a-link-to-the-past`\?\d+:\d+'
)
META_START = re.compile(r'(?=[`"\']/then-and-now[`"\']:\{)')
CREDITS = {
    "en": "The 21 game illustrations depict imagined settings and objects created for Hyrule Atlas with generative AI.",
    "fr": "Les 21 illustrations du catalogue représentent des lieux et des objets imaginés pour Hyrule Atlas avec l’IA générative.",
    "es": "Las 21 ilustraciones del catálogo muestran lugares y objetos imaginados para Hyrule Atlas con IA generativa.",
    "ja": "ゲームカタログの21点のイラストは、生成AIを使ってHyrule Atlasのために考案した場所や道具を描いています。",
    "zh": "目录中的 21 张插画由生成式人工智能为 Hyrule Atlas 创作，描绘想象中的场景与物件。",
}
FEATURE_CREDIT = {
    "en": "Original map and illustration · Hyrule Atlas",
    "fr": "Carte et illustration originales · Hyrule Atlas",
    "es": "Mapa e ilustración originales · Hyrule Atlas",
    "ja": "オリジナルの地図とイラスト · Hyrule Atlas",
    "zh": "原创地图与插画 · Hyrule Atlas",
}
FEATURE_CAPTION = re.compile(r'(<figure class="alttp-featured__art"[^>]*>.*?<figcaption>)[^<]+(</figcaption>)', re.S)
FEATURE_BUNDLE_CAPTION = re.compile(
    r'(?P<lead>className:`alttp-featured__art`.{0,1400}?`figcaption`,\{children:)(?:`[^`]+`|"[^\"]+")'
)
CATALOGUE_CREDIT_SECTION = re.compile(r'(<section id="record-5">.*?</h2><p>)[^<]+(</p>)', re.S)
CATALOGUE_CREDIT_BUNDLE = re.compile(r'(heading:`Editorial catalogue`,paragraphs:\[)(?:`[^`]+`|"[^\"]+")')


def locale_value(copy):
    return (f'({editorial.compact(copy)})[document.documentElement.lang.split("-")[0]]'
            f'||{editorial.compact(copy["en"])}')


def stage_covers(root):
    editorial_root = root / "assets/editorial"
    registry_path = editorial_root / "sources.json"
    registry = json.loads(registry_path.read_bytes())
    proof = json.loads((ASSETS / "provenance.json").read_bytes())
    translations = json.loads(ALTS.read_bytes())
    games = [entry for entry in registry["assets"] if "slug" in entry]
    slugs = {entry["slug"] for entry in games}
    if len(games) != 21 or slugs != set(proof["assets"]) or slugs != set(translations):
        raise ValueError("Expected one original cover and translation record for every game")

    covers = {}
    fingerprints = set()
    for entry in games:
        slug = entry["slug"]
        record = proof["assets"][slug]
        photo = ASSETS / f"{slug}.webp"
        data = photo.read_bytes()
        digest = sha256(data).hexdigest()
        size = editorial.webp_size(photo)
        alt = {"en": record["subject"], **translations[slug]}
        if (size != SIZE or size != (record["width"], record["height"]) or digest != record["sha256"]
                or len(data) != record["bytes"] or set(alt) != set(editorial.COPY)
                or any(not text.strip() for text in alt.values())):
            raise ValueError(f"Image, provenance or localized alt text differs for {slug}")
        if digest in fingerprints:
            raise ValueError(f"The image for {slug} is already assigned to another game")
        fingerprints.add(digest)

        name = f"game-{slug}-{digest[:12]}.webp"
        (editorial_root / name).write_bytes(data)
        cover = {"src": f"/assets/editorial/{name}", "alt": alt, "width": size[0], "height": size[1],
                 "sha256": digest, "masterSha256": record["originalSha256"]}
        covers[slug] = cover
        entry.update(src=cover["src"], alt=alt["en"], width=size[0], height=size[1],
                     sha256=digest, masterSha256=record["originalSha256"])

    registry["gameIllustrations"] = {
        "credit": proof["credit"], "creation": proof["creation"], "method": proof["method"],
        "images": [{"slug": slug, **cover} for slug, cover in covers.items()],
    }
    editorial.save(registry_path, editorial.compact(registry) + "\n")
    return covers


def stage_catalogue_module(root, covers):
    visual = {slug: {"src": cover["src"], "alt": cover["alt"]} for slug, cover in covers.items()}
    script = (f"const images={editorial.compact(visual)};\n"
              "export const atlasCatalogueUrl=slug=>images[slug]?.src??'/assets/editorial/observation.webp';\n"
              "export function atlasCatalogueAlt(slug){const words=images[slug]?.alt;"
              "return words?.[document.documentElement.lang.split('-')[0]]??words?.en??'';}\n")
    name = f"catalogue-data-{sha256(script.encode('utf-8')).hexdigest()[:12]}.js"
    editorial.save(root / "assets/editorial" / name, script)
    return name


def page_identity(root, page):
    parts = page.relative_to(root).parts[:-1]
    locale = parts[0] if parts and parts[0] in editorial.COPY else "en"
    return locale, parts if locale == "en" else parts[1:]


def game_metadata_route(parts, covers):
    if len(parts) == 2 and parts[0] == "series" and parts[1] in covers:
        return parts[1]
    if len(parts) == 1 and parts[0] in ROOT_GAME_ROUTES and parts[0] in covers:
        return parts[0]
    return None


def patch_page(source, locale, route, covers):
    game = game_metadata_route(route, covers)
    images = {}
    if game and f'property="og:image" content="{SITE}/assets/original/forest-fairy.png"' in source:
        cover = covers[game]
        images = {"og:image": SITE + cover["src"], "twitter:image": SITE + cover["src"],
                  "og:image:type": "image/webp", "og:image:width": cover["width"],
                  "og:image:height": cover["height"], "og:image:alt": cover["alt"][locale],
                  "twitter:image:alt": cover["alt"][locale]}

    def update_tag(match):
        tag = match[0]
        field = editorial.attribute(tag, "property") or editorial.attribute(tag, "name")
        if tag.startswith("<meta") and field in images:
            return editorial.attr(tag, "content", images[field])
        image = COVER_URI.fullmatch(editorial.attribute(tag, "src") or "")
        if tag.startswith("<img") and image:
            cover = covers[image["slug"]]
            if editorial.attribute(tag, "alt"):
                tag = editorial.attr(tag, "alt", cover["alt"][locale])
            for size in ("width", "height"):
                if editorial.attribute(tag, size):
                    tag = editorial.attr(tag, size, cover[size])
        return COVER_URI.sub(lambda m: covers[m["slug"]]["src"], tag)

    source = editorial.IMAGE_TAG.sub(update_tag, source)
    source = COVER_URI.sub(lambda m: covers[m["slug"]]["src"], source)
    source = SRCSET_WIDTH.sub(lambda m: f"{m[1]} {SIZE[0]}w", source)
    if route == ("games",):
        source = FEATURE_CAPTION.sub(lambda m: m[1] + escape(FEATURE_CREDIT[locale]) + m[2], source)
    elif route == ("sources",):
        source, count = CATALOGUE_CREDIT_SECTION.subn(
            lambda m: m[1] + escape(CREDITS[locale]) + m[2], source,
        )
        if count != 1:
            raise ValueError(f"The catalogue credits section could not be updated for {locale}")
    return source


def patch_bundles(root, covers, module_name):
    assets = root / "assets"
    metadata = {route: slug for slug in covers for route in
                ([f"/{slug}", f"/series/{slug}"] if slug in ROOT_GAME_ROUTES else [f"/series/{slug}"])}
    for bundle in assets.glob("*.js"):
        source = bundle.read_text(encoding="utf-8")
        updated = source
        if "/assets/editorial/catalogue-" in updated:
            updated = DYNAMIC_COVER.sub(lambda m: "${atlasCatalogueUrl(" + m["key"] + ")}", updated)

            def update_entry(match):
                slug = match["slug"]
                cover = covers[slug]
                return (f'"src":{editorial.compact(cover["src"])},"width":{cover["width"]},"height":{cover["height"]},'
                        f'get alt(){{return atlasCatalogueAlt("{slug}")}}')

            def update_jsx(match):
                slug = match["slug"]
                alt = f'atlasCatalogueAlt("{slug}")' if match["alt"] else '""'
                props = re.sub(r'\b(width|height):(?:`\d+`|\d+)',
                               lambda m: f'{m[1]}:{covers[slug][m[1]]}', match["props"])
                return (f'{match["property"]}{editorial.compact(covers[slug]["src"])}'
                        f'{props},{match["label"]}:{alt}')

            updated = BUNDLED_ENTRY_COVER.sub(update_entry, updated)
            updated = JSX_COVER.sub(update_jsx, updated)
            updated = COVER_URI.sub(lambda m: covers[m["slug"]]["src"], updated)
            updated = DYNAMIC_SRCSET.sub(lambda m: f'{m["property"]}`{m["cover"]} {SIZE[0]}w`', updated)
            if bundle.name.startswith("routes-"):
                dimensions = dict(zip(("width", "height"), SIZE))
                updated = QUICK_LINK_SIZE.sub(lambda m: f'{m["property"]}:{dimensions[m["property"]]}', updated)
            if "catalogue-${(" in updated or COVER_URI.search(updated):
                raise ValueError(f"Unreplaced game cover in {bundle.name}")

        if bundle.name.startswith("series-"):
            updated = FEATURE_BUNDLE_CAPTION.sub(lambda m: m["lead"] + f"({locale_value(FEATURE_CREDIT)})", updated)
        if bundle.name.startswith("sources-"):
            updated = CATALOGUE_CREDIT_BUNDLE.sub(lambda m: m[1] + f"({locale_value(CREDITS)})", updated)
        if bundle.name.startswith("site-metadata-") and META_START.search(updated):
            entries = []
            for route, slug in metadata.items():
                if re.search(r'[`"\']' + re.escape(route) + r'[`"\']:', updated):
                    continue
                cover = covers[slug]
                markup = editorial.compact({"src": cover["src"], "width": cover["width"],
                                            "height": cover["height"], "type": "image/webp"})[:-1]
                entries.append(f'{editorial.compact(route)}:{markup},get alt(){{return atlasCatalogueAlt("{slug}")}}}},')
            updated = META_START.sub(lambda _: "".join(entries), updated, count=1)
        if updated != source:
            names = [name for name in ("atlasCatalogueUrl", "atlasCatalogueAlt") if name + "(" in updated]
            if names:
                updated = f'import {{{",".join(names)}}} from "./editorial/{module_name}";\n' + updated
            editorial.save(bundle, updated)


def apply(root):
    """Run after section covers and the existing editorial replacement pass."""
    covers = stage_covers(root)
    module_name = stage_catalogue_module(root, covers)
    for page in root.rglob("*.html"):
        source = page.read_text(encoding="utf-8")
        locale, route = page_identity(root, page)
        revised = patch_page(source, locale, route, covers)
        if revised != source:
            editorial.save(page, revised)
    patch_bundles(root, covers, module_name)
