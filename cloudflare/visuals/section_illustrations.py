"""Apply original section covers to the prerendered HTML and the hydrated site."""

from hashlib import sha256
from html import escape
import json
from pathlib import Path
import re

from . import editorial
from .blog_covers import CREDIT, localized
from .section_illustration_copy import CREDIT_NOTE, DESCRIPTIONS, LANGUAGES


HERE = Path(__file__).parent
INPUT = HERE / "section-assets"
ART_DIR = "/assets/editorial/"
SOURCE = "/sources/#record-3"
HOST = "https://hyruleatlas.com"
MAP_ENTRIES = ("/map/instagram/", "/map/tiktok/")
REMAKE = "ocarina-of-time-remake"
CLASSIC = "zelda-64"
COMPACT = {"ocarina", "search"}
DIRECTORY = {"guides": "games", "remake": REMAKE, "discover": "blog", "community": "forum"}
SIZE = (1440, 960)

LEAD = re.compile(r'<header class="atlas-lead [^"]+"[^>]*>.*?</header>', re.S)
LEAD_FIGURE = re.compile(r'<figure class="atlas-lead-art [^"]+"[^>]*>.*?</figure>', re.S)
MAP_HEADER = '<header class="alttp-map-entry-intro">'
HTML_IMAGE = re.compile(r"<img\b[^>]*>")
JS_LOOKUP = re.compile(
    r'(function \w+\(\w+,\w+,\w+\)\{let (?P<path>\w+)=\w+\(\w+\)\.replace\(/\\/\$/,``\),'
    r'\w+=\w+\.assets\.find\(\w+=>\w+\.src===\w+\);return )'
)
JS_META = re.compile(r'(function \w+\(\w+\)\{let (?P<path>\w+)=\w+\(new URL\(\w+,\w+\)\.pathname\)\.replace\(/\\/\+\$/,``\)\|\|`/`;return )')
JS_REMAKE_LINK = re.compile(r'(href:)\w+\?\w+\.sourcePage:`[^`]+`')
JS_MAP_HEADER = re.compile(r'(?P<multi>\w+)\(`header`,\{className:`alttp-map-entry-intro`,children:\[(?P<one>\w+)\(`p`,')
JS_SOURCE_CREDIT = re.compile(r'heading:`(?:Original section illustrations|Original illustrations of the sections)`,paragraphs:\[[^\[\]{}]+(?=\]\})')
HTML_SOURCE_CREDIT = re.compile(r'(<section id="record-3">.*?)(</section>)', re.S)
JSON_LD = re.compile(r'(<script type="application/ld\+json">)([^<]+)(</script>)')


def source_url(lang):
    return ("" if lang == "en" else f"/{lang}") + SOURCE


def cover_pages(slug):
    if slug == "map":
        return MAP_ENTRIES
    if slug == CLASSIC:
        return (f"/{CLASSIC}/", f"/{REMAKE}/")
    return (f"/{slug}/",)


def publish_images(root):
    pending = json.loads((INPUT / "provenance.json").read_bytes())
    records = pending["assets"]
    if set(records) != set(DESCRIPTIONS):
        raise ValueError(f"Section artwork inventory differs: missing {sorted(set(DESCRIPTIONS) - set(records))}, extra {sorted(set(records) - set(DESCRIPTIONS))}")
    covers = {}
    used = set()
    for slug, text in DESCRIPTIONS.items():
        record = records[slug]
        source = INPUT / f"{slug}.webp"
        body = source.read_bytes()
        digest = sha256(body).hexdigest()
        width, height = editorial.webp_size(source)
        if (source.name != record["file"] or (width, height) != SIZE or
                (width, height, len(body), digest) != (record["width"], record["height"], record["bytes"], record["sha256"])):
            raise ValueError(f"Image metadata and file differ for {slug}")
        if digest in used or not re.fullmatch(r"[0-9a-f]{64}", record["originalSha256"]):
            raise ValueError(f"Duplicate image or invalid original fingerprint for {slug}")
        used.add(digest)
        pages = cover_pages(slug)
        url = f"{ART_DIR}section-{slug}-{digest[:12]}.webp"
        (root / url.lstrip("/")).write_bytes(body)
        covers[slug] = {
            "slug": slug, "page": pages[0], "pages": pages, "src": url, "alt": dict(zip(LANGUAGES, text, strict=True)),
            "width": width, "height": height, "sha256": digest, "masterSha256": record["originalSha256"],
        }
    registry = root / editorial.CREDITS.lstrip("/")
    entries = json.loads(registry.read_bytes())
    entries["sectionIllustrations"] = {
        "credit": pending["credit"], "creation": pending["creation"], "method": pending["method"],
        "images": list(covers.values()), "directory": DIRECTORY,
    }
    editorial.save(registry, editorial.compact(entries) + "\n")
    return covers


def fingerprinted(output, stem, ext, data):
    name = f"{stem}-{sha256(data).hexdigest()[:12]}.{ext}"
    (output / name).write_bytes(data)
    return name


def prepare_public_files(root, covers):
    assets = root / ART_DIR.strip("/")
    routes = {cover["page"].rstrip("/"): slug for slug, cover in covers.items()}
    routes[MAP_ENTRIES[1].rstrip("/")] = "map"
    public_covers = {slug: {key: row[key] for key in ("src", "alt", "width", "height")} for slug, row in covers.items()}
    data = (
        f"const covers={editorial.compact(public_covers)};\n"
        f"const routes={editorial.compact(routes)};\n"
        f"const directory={editorial.compact(DIRECTORY)};\n"
        f"const languages={editorial.compact(LANGUAGES)};\n"
        f"const credit={editorial.compact(CREDIT)};\n"
        + (HERE / "section-illustrations.js").read_text(encoding="utf-8")
    ).encode("utf-8")
    filename = fingerprinted(assets, "section-art-data", "js", data)
    stylesheet = fingerprinted(assets, "section-art", "css", (HERE / "section-illustrations.css").read_bytes())
    return filename, stylesheet


def figure(cover, lang, *, map_entry=False):
    css = "atlas-section-art" if map_entry else "atlas-lead-art atlas-section-art"
    priority = 'decoding="async"' if map_entry else 'fetchPriority="high"'
    return (
        f'<figure class="{css}" data-plate="artwork" data-section-art="{cover["slug"]}">'
        f'<img src="{cover["src"]}" width="{cover["width"]}" height="{cover["height"]}" '
        f'alt="{escape(cover["alt"][lang], quote=True)}" {priority}/>'
        f'<figcaption><a href="{source_url(lang)}" target="_blank" rel="noopener noreferrer">'
        f'{escape(CREDIT[lang])}</a></figcaption></figure>'
    )


def remake_figure(header, covers, lang):
    originals = {}
    for slot, slug in (("old", CLASSIC), ("new", REMAKE)):
        cover = covers[slug]
        def image(match):
            tag = match[0]
            originals[editorial.attribute(tag, "src")] = cover["src"]
            for key, value in (("src", cover["src"]), ("width", cover["width"]), ("height", cover["height"]), ("alt", cover["alt"][lang])):
                tag = editorial.attr(tag, key, value)
            return tag.replace("<img ", f'<img data-section-art="{slug}" ', 1)

        header, count = re.subn(r'<img class="remake-plates__' + slot + r'"[^>]*>', image, header)
        if count != 1:
            raise ValueError(f"Missing {slot} remake plate in {lang}")
    source = re.compile(r'<a href="(?:/\w+)?/sources/#record-5"([^>]*)>[^<]*</a>')
    header, count = source.subn(lambda match: f'<a href="{source_url(lang)}"{match[1]}>{escape(CREDIT[lang])}</a>', header)
    if count != 1:
        raise ValueError(f"Missing remake plate credit in {lang}")
    return header, originals


def share_markup(source, cover, lang, preloads):
    url = HOST + cover["src"]
    alt = cover["alt"][lang]
    fields = {
        "og:image": url, "twitter:image": url, "og:image:width": cover["width"], "og:image:height": cover["height"],
        "og:image:type": "image/webp", "og:image:alt": alt, "twitter:image:alt": alt,
    }

    def tag(match):
        old = match[0]
        field = editorial.attribute(old, "name") or editorial.attribute(old, "property")
        if old.startswith("<meta") and field in fields:
            return editorial.attr(old, "content", fields.pop(field))
        href = editorial.attribute(old, "href")
        if old.startswith("<link") and editorial.attribute(old, "as") == "image" and href in preloads:
            return editorial.attr(old, "href", preloads.pop(href))
        return old

    def schema(match):
        data = json.loads(match[2])
        if not isinstance(data, dict):
            return match[0]
        for page in data.get("@graph", [data]):
            if page.get("@type") in {"Article", "WebPage", "CollectionPage"} and "image" in page:
                page["image"] = url
        return match[1] + editorial.compact(data).replace("</", "<\\/") + match[3]

    head, rest = source.split("</head>", 1)
    head = editorial.IMAGE_TAG.sub(tag, head)
    if fields:
        raise ValueError(f"Incomplete share metadata for {lang} {cover['page']}: {', '.join(fields)}")
    if cover["slug"] == "ocarina" or cover["slug"] == "search":
        head += f'<link rel="preload" as="image" href="{cover["src"]}" fetchPriority="high"/>'
    return JSON_LD.sub(schema, head + "</head>" + rest)


def patch_page(path, covers, slug, lang):
    source = path.read_text(encoding="utf-8")
    cover = covers[slug]
    if slug == "map":
        if source.count(MAP_HEADER) != 1:
            raise ValueError(f"Expected one social-map heading in {path}")
        markup = source.replace(MAP_HEADER, MAP_HEADER + figure(cover, lang, map_entry=True), 1)
        return share_markup(markup, cover, lang, {})

    header = LEAD.search(source)
    if not header:
        raise ValueError(f"Missing section heading in {path}")
    if slug == REMAKE:
        replacement, preloads = remake_figure(header[0], covers, lang)
    elif slug in COMPACT:
        replacement = header[0].removesuffix("</header>") + figure(cover, lang) + "</header>"
        preloads = {}
    else:
        former = LEAD_FIGURE.search(header[0])
        if not former:
            raise ValueError(f"Missing editorial hero in {path}")
        just_image = HTML_IMAGE.search(former[0])
        preloads = {editorial.attribute(just_image[0], "src"): cover["src"]} if just_image else {}
        replacement = header[0][:former.start()] + figure(cover, lang) + header[0][former.end():]
    source = source[:header.start()] + replacement + source[header.end():]
    return share_markup(source, cover, lang, preloads)


def section_header_bundle(text, path):
    def lookup(match):
        return match[0] + f'sectionCover({match["path"]})??'

    text, count = JS_LOOKUP.subn(lookup, text)
    if count != 1:
        raise ValueError(f"Could not find section art lookup in {path}")
    substitutions = {
        'l=!o&&!a?Q(s,c.id,r):void 0': 'l=!a?Q(s,c.id,r):void 0',
        '!o&&(a??(l&&': '(!o||l?.slug)&&(a??(l&&',
        'className:`atlas-lead-art atlas-lead-art--official`,"data-plate":l.kind':
            'className:l.slug?`atlas-lead-art atlas-section-art`:`atlas-lead-art atlas-lead-art--official`,"data-plate":l.kind,"data-section-art":l.slug',
        'alt:r===l.src?i??``:``': 'alt:l.slug?l.alt:r===l.src?i??``:``',
        'let t=Z(e.id);return': 'let t=sectionDirectoryCover(e.id)??Z(e.id);return',
    }
    for old, new in substitutions.items():
        if text.count(old) != 1:
            raise ValueError(f"Could not find a unique heading renderer in {path}: {old}")
        text = text.replace(old, new, 1)
    return text


def remake_bundle(text, path):
    for slot, slug in (("old", CLASSIC), ("new", REMAKE)):
        marker = 'className:`remake-plates__' + slot + '`'
        asset = f'sectionCover(`/{slug}`)'

        def image(match):
            tag = match[0]
            for key in ("src", "alt", "width", "height"):
                tag, count = re.subn(r'\b' + key + r':(?:`[^`]*`|[^,}]+)', f'{key}:{asset}.{key}', tag)
                if count != 1:
                    raise ValueError(f"Could not find {slot} {key} in {path}")
            return tag.replace(marker, marker + f',"data-section-art":`{slug}`', 1)

        text, count = re.subn(re.escape(marker) + r'[^}]*', image, text)
        if count != 1:
            raise ValueError(f"Could not find the remake {slot} plate in {path}")
    text, count = JS_REMAKE_LINK.subn(r'\1sectionCover(`/ocarina-of-time-remake`).source', text)
    if count != 1:
        raise ValueError(f"Could not find the remake credit link in {path}")
    return text


def map_header_bundle(text, path):
    def header(match):
        one, multi = match["one"], match["multi"]
        fragment = (
            f'((cover)=>{multi}(`figure`,{{className:`atlas-section-art`,"data-plate":`artwork`,"data-section-art":`map`,children:['
            f'{one}(`img`,{{src:cover.src,width:cover.width,height:cover.height,alt:cover.alt,decoding:`async`}}),'
            f'{one}(`figcaption`,{{children:{one}(`a`,{{href:cover.source,target:`_blank`,rel:`noopener noreferrer`,children:cover.credit}})}})'
            f']}}))(sectionCover(`/map/instagram`,`en`)),'
        )
        return match[0].replace("children:[", "children:[" + fragment, 1)

    text, count = JS_MAP_HEADER.subn(header, text)
    if count != 1:
        raise ValueError(f"Could not find reusable social-map header in {path}")
    return text


def patch_script(path, filename):
    name = path.name
    text = path.read_text(encoding="utf-8")
    imports = "sectionCover"
    if name.startswith("archive-shell-") and 'className:`atlas-lead-art atlas-lead-art--official`' in text:
        text = section_header_bundle(text, path)
        imports += ",sectionDirectoryCover"
    elif name.startswith("site-metadata-") and JS_META.search(text):
        text = JS_META.sub(lambda match: match[0] + f'sectionCover({match["path"]})??', text, count=1)
    elif name.startswith("ocarina-of-time-remake-") and 'className:`remake-plates__old`' in text:
        text = remake_bundle(text, path)
    elif name.startswith("alttp-") and 'className:`alttp-map-entry-intro`' in text:
        text = map_header_bundle(text, path)
    elif name.startswith("sources-") and JS_SOURCE_CREDIT.search(text):
        text = JS_SOURCE_CREDIT.sub(lambda match: f'{match[0]},({localized(CREDIT_NOTE)})', text, count=1)
        editorial.save(path, text)
        return "sources"
    else:
        return None
    editorial.save(path, f'import {{{imports}}} from "./editorial/{filename}";\n' + text)
    return name.split("-")[0]


def apply(root: Path):
    covers = publish_images(root)
    filename, stylesheet = prepare_public_files(root, covers)
    stylesheet_tag = f'<link rel="stylesheet" href="{ART_DIR}{stylesheet}"/>'
    for lang in LANGUAGES:
        localized_root = root if lang == "en" else root / lang
        for slug in covers.keys() - {"map"}:
            page = localized_root / slug / "index.html"
            markup = patch_page(page, covers, slug, lang)
            if slug == "sources":
                markup, count = HTML_SOURCE_CREDIT.subn(lambda match: match[1] + f'<p>{escape(CREDIT_NOTE[lang])}</p>' + match[2], markup)
                if count != 1:
                    raise ValueError(f"Missing the section artwork credits in {page}")
            editorial.save(page, markup)
    for route in MAP_ENTRIES:
        page = root / route.strip("/") / "index.html"
        editorial.save(page, patch_page(page, covers, "map", "en"))

    for page in root.rglob("index.html"):
        text = page.read_text(encoding="utf-8")
        if text.count("</head>") != 1:
            raise ValueError(f"Missing unique document head in {page}")
        editorial.save(page, text.replace("</head>", stylesheet_tag + "</head>", 1))

    prefixes = ("archive-shell-", "site-metadata-", "ocarina-of-time-remake-", "alttp-", "sources-")
    patched = {patch_script(path, filename) for path in (root / "assets").glob("*.js") if path.name.startswith(prefixes)}
    if not {"archive", "site", "ocarina", "alttp", "sources"}.issubset(patched):
        raise ValueError(f"An illustration client renderer was not found: {patched}")
