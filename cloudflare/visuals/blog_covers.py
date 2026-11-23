"""Install original illustrations on the blog's cards, articles and share previews."""

from hashlib import sha256
from pathlib import Path
import html
import json
import re

from . import editorial


INPUT = Path(__file__).with_name("blog-assets")
SITE = "https://hyruleatlas.com"
CREDIT_URL = "/sources/#record-5"
SIZE = (1440, 960)
POSTS = {
    "why-ocarina-of-time-music-stays-with-us": ("music", {
        "en": "A handmade terracotta ocarina resting on sheet music in warm window light.",
        "fr": "Un ocarina artisanal en terre cuite repose sur une partition éclairée par la fenêtre.",
        "es": "Una ocarina artesanal de terracota sobre una partitura, iluminada por la cálida luz de la ventana.",
        "ja": "窓から差し込む暖かな光の中、楽譜の上に置かれた手作りの素焼きのオカリナ。",
        "zh": "温暖的窗光下，一支手工陶笛放在乐谱上。",
    }),
    "how-to-read-an-ocarina-of-time-reveal": ("reveal", {
        "en": "A brass loupe over a landscape study of a stone arch and a forest path.",
        "fr": "Une loupe en laiton posée sur une étude peinte d’une arche de pierre et d’un sentier forestier.",
        "es": "Una lupa de latón sobre un estudio pintado de un arco de piedra y un sendero en el bosque.",
        "ja": "石のアーチと森の小道を描いた習作の上に置かれた真鍮のルーペ。",
        "zh": "一枚黄铜放大镜放在描绘石拱与林间小径的风景习作上。",
    }),
    "the-lost-art-of-zelda-secrets": ("secrets", {
        "en": "A narrow wooden door ajar in an ivy-covered stone wall, with warm light spilling out.",
        "fr": "Une porte de bois entrouverte dans un mur de pierre couvert de lierre laisse filtrer une lumière dorée.",
        "es": "Una puerta de madera entreabierta en un muro de piedra cubierto de hiedra deja escapar una luz dorada.",
        "ja": "ツタに覆われた石壁の小さな木の扉が半開きになり、暖かな光が漏れている。",
        "zh": "爬满常春藤的石墙上，一扇半开的木门透出暖光。",
    }),
}
CREDIT = {
    "en": "Original illustration · Hyrule Atlas",
    "fr": "Illustration originale · Hyrule Atlas",
    "es": "Ilustración original · Hyrule Atlas",
    "ja": "オリジナルイラスト · Hyrule Atlas",
    "zh": "原创插画 · Hyrule Atlas",
}
CREDIT_NOTE = {
    "en": "The blog’s ocarina, painted landscape study and hidden door are original illustrations created for Hyrule Atlas with OpenAI ImageGen.",
    "fr": "L’ocarina, l’étude de paysage et la porte cachée qui illustrent le blog ont été créés pour Hyrule Atlas avec OpenAI ImageGen.",
    "es": "La ocarina, el estudio de paisaje y la puerta oculta del blog son ilustraciones originales creadas para Hyrule Atlas con OpenAI ImageGen.",
    "ja": "ブログのオカリナ、風景の習作、隠し扉は、OpenAI ImageGenでHyrule Atlasのために制作したオリジナルイラストです。",
    "zh": "博客里的陶笛、风景习作和隐藏木门是使用 OpenAI ImageGen 为 Hyrule Atlas 创作的原创插画。",
}

CARD = re.compile(r'(?P<link><a class="ed-blog-card__image"[^>]*>)</a>')
HERO = re.compile(r'<figure class="atlas-lead-art atlas-lead-art--official"[^>]*>.*?</figure>', re.S)
CREDIT_SECTION = re.compile(r'(<section id="record-5">.*?)(</section>)', re.S)
STRUC_DATA = re.compile(r'(<script type="application/ld\+json">)(?P<data>[^<]+)(</script>)')
POST = re.compile(
    r'(?P<lead>\{slug:[`"](?P<slug>' + "|".join(map(re.escape, POSTS))
    + r')[`"],[^{}]{0,1000}?)image:[`"][^`"]+[`"]\s*,imageAlt:[`"][^`"]*[`"](?=,imageCaption:)'
)
CARD_SIZE = re.compile(r'(alt:[\w$]+\.imageAlt,loading:`lazy`,width:)`1920`,height:`1080`')
HERO_LOOKUP = re.compile(
    r';return (?P<selection>[^;\n{}]{0,250}?(?P<route>[\w$]+)===`/blog/'
    r'why-ocarina-of-time-music-stays-with-us`[^;\n{}]+)(?=\})'
)
METADATA_MAP = re.compile(r'(?=[`"\']/then-and-now[`"\']:\{)')
CREDIT_PARAGRAPHS = re.compile(r'(?P<paragraphs>heading:`Editorial catalogue`,paragraphs:\[[^{}\[\]]+)(?=\]\})')


def localized(copy):
    return (f'({editorial.compact(copy)})[document.documentElement.lang.split("-")[0]]'
            f'||{editorial.compact(copy["en"])}')


def install(root):
    covers = {}
    evidence = json.loads((INPUT / "provenance.json").read_bytes())
    public = root / "assets/editorial"
    for slug, (name, alt) in POSTS.items():
        file = INPUT / f"{name}.webp"
        data = file.read_bytes()
        digest = sha256(data).hexdigest()
        width, height = editorial.webp_size(file)
        recorded = evidence["assets"][name]
        if ((width, height) != SIZE or digest != recorded["sha256"]
                or (width, height, len(data)) != (recorded["width"], recorded["height"], recorded["bytes"])):
            raise ValueError(f"Illustration dimensions or provenance mismatch in {file}")
        downloadable = f"blog-{name}-{digest[:12]}.webp"
        (public / downloadable).write_bytes(data)
        covers[slug] = {
            "src": f"/assets/editorial/{downloadable}", "width": width, "height": height, "alt": alt,
            "sha256": digest, "masterSha256": recorded["originalSha256"],
        }

    registry_file = public / "sources.json"
    registry = json.loads(registry_file.read_bytes())
    registry["blogIllustrations"] = {
        "credit": evidence["credit"], "creation": evidence["creation"], "method": evidence["method"],
        "images": [{"page": f"/blog/{slug}/", **cover} for slug, cover in covers.items()],
    }
    editorial.save(registry_file, editorial.compact(registry) + "\n")
    return covers


def update_post_data(source, covers, lang=None):
    def update(match):
        cover = covers[match["slug"]]
        alt = (f'imageAlt:{editorial.compact(cover["alt"][lang])}' if lang else
               f'get imageAlt(){{return {localized(cover["alt"])}}}')
        return f'{match["lead"]}image:{editorial.compact(cover["src"])},{alt}'

    return POST.subn(update, source)


def image(cover, lang, loading):
    return (f'<img src="{cover["src"]}" width="{cover["width"]}" height="{cover["height"]}" '
            f'alt="{html.escape(cover["alt"][lang])}" {loading}/>')


def article(page, cover, covers, lang, local):
    source = page.read_text(encoding="utf-8")
    old = HERO.search(source)
    if not old:
        raise ValueError(f"Missing article hero on {page}")
    former_src = editorial.attribute(re.search(r'<img\b[^>]+>', old[0])[0], "src")
    new = ('<figure class="atlas-lead-art atlas-lead-art--official" data-plate="artwork">'
           + image(cover, lang, 'fetchPriority="high"')
           + f'<figcaption><a href="{local}{CREDIT_URL}" target="_blank" rel="noopener noreferrer">'
           f'{html.escape(CREDIT[lang])}</a></figcaption></figure>')
    fields = {
        "og:image": SITE + cover["src"], "twitter:image": SITE + cover["src"],
        "og:image:type": "image/webp", "og:image:width": cover["width"], "og:image:height": cover["height"],
        "og:image:alt": cover["alt"][lang], "twitter:image:alt": cover["alt"][lang],
    }

    def update_tag(match):
        tag = match[0]
        field = editorial.attribute(tag, "property") or editorial.attribute(tag, "name")
        if tag.startswith("<meta") and field in fields:
            return editorial.attr(tag, "content", fields.pop(field))
        if (tag.startswith("<link") and editorial.attribute(tag, "as") == "image"
                and editorial.attribute(tag, "href") == former_src):
            return editorial.attr(tag, "href", cover["src"])
        return tag

    def schema_image(match):
        data = json.loads(match["data"])
        if not isinstance(data, dict) or data.get("@type") != "BlogPosting":
            return match[0]
        data["image"] = SITE + cover["src"]
        return match[1] + editorial.compact(data).replace("</", "<\\/") + match[3]

    source = source[:old.start()] + new + source[old.end():]
    source = editorial.IMAGE_TAG.sub(update_tag, source)
    source = STRUC_DATA.sub(schema_image, source)
    source, loaders = update_post_data(source, covers, lang)
    if fields or loaders != 1:
        raise ValueError(f"Missing share fields or inline loader on {page}")
    editorial.save(page, source)


def blog_index(page, covers, lang):
    def card_image(match):
        slug = editorial.attribute(match["link"], "href").rstrip("/").rsplit("/", 1)[-1]
        return match["link"] + image(covers[slug], lang, 'loading="lazy"') + "</a>"

    source, count = CARD.subn(card_image, page.read_text(encoding="utf-8"))
    if count != len(covers):
        raise ValueError(f"Expected one image per blog card on {page}")
    editorial.save(page, source)


def image_map(covers, *, hero):
    entries = []
    for slug, cover in covers.items():
        properties = {
            "src": cover["src"], "width": cover["width"], "height": cover["height"],
        }
        if hero:
            properties.update(kind="artwork", source=CREDIT_URL)
        else:
            properties["type"] = "image/webp"
        value = (editorial.compact(properties)[:-1] + f',get alt(){{return {localized(cover["alt"])}}}')
        if hero:
            value += f',get credit(){{return {localized(CREDIT)}}}'
        entries.append(f'"/blog/{slug}":' + value + "}")
    return ",".join(entries)


def patch_bundles(root, covers):
    assets = root / "assets"
    for path in assets.glob("blog-data-*.js"):
        revised, count = update_post_data(path.read_text(encoding="utf-8"), covers)
        if count != len(covers):
            raise ValueError(f"Unexpected blog data layout in {path}")
        editorial.save(path, revised)

    width, height = SIZE
    for path in assets.glob("blog.index-*.js"):
        source = path.read_text(encoding="utf-8")
        if "ed-blog-card__image" in source:
            source, count = CARD_SIZE.subn(lambda m: f'{m[1]}`{width}`,height:`{height}`', source)
            if count != 1:
                raise ValueError(f"Unexpected blog card layout in {path}")
            editorial.save(path, source)

    heroes = image_map(covers, hero=True)
    for path in assets.glob("archive-shell-*.js"):
        source = path.read_text(encoding="utf-8")
        if "why-ocarina-of-time-music-stays-with-us" not in source:
            continue
        source, count = HERO_LOOKUP.subn(
            lambda match: f';return ({{{heroes}}})[{match["route"]}]??({match["selection"]})', source,
        )
        if count != 1:
            raise ValueError(f"Unexpected article cover selection in {path}")
        editorial.save(path, source)

    metadata = image_map(covers, hero=False)
    for path in assets.glob("site-metadata-*.js"):
        source = path.read_text(encoding="utf-8")
        if METADATA_MAP.search(source):
            editorial.save(path, METADATA_MAP.sub(lambda _: metadata + ",", source, count=1))

    for path in assets.glob("sources-*.js"):
        source = path.read_text(encoding="utf-8")
        revised = CREDIT_PARAGRAPHS.sub(lambda m: f'{m[0]},({localized(CREDIT_NOTE)})', source)
        if revised != source:
            editorial.save(path, revised)


def apply(root: Path):
    covers = install(root)
    for lang in CREDIT:
        local = "" if lang == "en" else f"/{lang}"
        base = root / local.lstrip("/")
        blog_index(base / "blog/index.html", covers, lang)
        for slug, cover in covers.items():
            article(base / "blog" / slug / "index.html", cover, covers, lang, local)

        credits = base / "sources/index.html"
        source, count = CREDIT_SECTION.subn(
            lambda m: m[1] + f'<p>{html.escape(CREDIT_NOTE[lang])}</p>' + m[2],
            credits.read_text(encoding="utf-8"),
        )
        if count != 1:
            raise ValueError(f"Missing illustration credit section in {credits}")
        editorial.save(credits, source)

    patch_bundles(root, covers)
