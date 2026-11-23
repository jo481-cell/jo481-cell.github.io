"""Apply the studio presentation to the existing localized static export."""

import html
import json
from hashlib import sha256
from pathlib import Path
import re
import shutil

from .editorial import js_object_end, webp_size


HERE = Path(__file__).resolve().parent
ASSETS = HERE / "studio-assets"
LANDMARK_ASSETS = ASSETS / "landmarks"
PUBLIC = "/assets/studio/"
VALLEY = "atlas-valley"
MAP_PATH = "/series/a-link-to-the-past/#collectible-map"
MAP_LABEL = {
    "en": "Explore the atlas", "fr": "Explorer l’atlas", "es": "Explorar el atlas",
    "ja": "地図を探索", "zh": "探索地图",
}
TITLE_END = re.compile(r'(<header class="atlas-frontier-title">.*?</p>)(</header>)', re.S)
CLIENT_TITLE_END = re.compile(
    r'(?P<title>className:`atlas-frontier-title`,children:\[.*?'
    r'(?P<jsx>[\w$]+)\(`p`,\{children:`[^`]+`\}\))(?=\]\}\))', re.S
)
FIELD_CHART = re.compile(r'<figure class="field-chart"[^>]*>.*?</figure>', re.S)
COMPASS = re.compile(r'<div class="atlas-triforce-stage"[^>]*>.*?(?=<nav class="atlas-frontier-doors")', re.S)
FUNCTION_HEADER = re.compile(r'function (?P<name>[\w$]+)\([^)]*\)\{')
LANDMARK_NAMES = ("castle", "village", "lake", "compass")
STUDIO_CREDIT = re.compile(r'(<section id="record-6">.*?<h2>)([^<]+)(</h2><p>)([^<]+)(</p></section>)', re.S)


def compact(data):
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def install_landmarks(dest):
    images = {}
    for name in LANDMARK_NAMES:
        file = LANDMARK_ASSETS / f"{name}.webp"
        source = file.read_bytes()
        filename = f"{name}-{sha256(source).hexdigest()[:12]}.webp"
        width, height = webp_size(file)
        images[name] = {"src": PUBLIC + filename, "width": width, "height": height}
        (dest / filename).write_bytes(source)

    copy = json.loads((ASSETS / "home-landmarks.json").read_bytes())
    client = (ASSETS / "home-landmarks.js").read_bytes()
    client += f"\nconst images = {compact(images)};\nconst copy = {compact(copy)};\n".encode("utf-8")
    module = f"home-landmarks-{sha256(client).hexdigest()[:12]}.js"
    (dest / module).write_bytes(client)
    return images, copy, module


def image_tag(image, alt, class_name=""):
    class_attr = f' class="{class_name}"' if class_name else ""
    return (f'<img{class_attr} src="{image["src"]}" width="{image["width"]}" height="{image["height"]}" '
            f'alt="{html.escape(alt)}" loading="lazy" decoding="async"/>')


def landmark_markup(images, words, local):
    buttons = "".join(
        f'<button type="button" aria-pressed="{str(index == 0).lower()}">{html.escape(label)}</button>'
        for index, label in enumerate(words["places"])
    )
    return ('<figure class="field-chart studio-landmarks"><div class="studio-landmarks__view">'
            + image_tag(images["castle"], words["alt"][0]) + '</div>'
            '<figcaption class="studio-landmarks__controls">'
            f'<div class="field-chart__places" role="group" aria-label="{html.escape(words["choose"])}">'
            f'{buttons}</div><a class="studio-landmarks__map" href="{local}{MAP_PATH}">'
            f'{html.escape(words["map"])}</a></figcaption></figure>')


def compass_markup(images, words, local):
    return ('<div class="atlas-triforce-stage studio-compass">'
            + image_tag(images["compass"], words["compass"], "studio-compass__photo")
            + f'<a class="studio-compass__credit" href="{local}/sources/#record-6">{html.escape(words["credit"])}</a></div>')


def replace_component(source, marker, render):
    marker_index = source.index(f'className:`{marker}`')
    header = list(FUNCTION_HEADER.finditer(source, 0, marker_index))[-1]
    end = js_object_end(source, header.end() - 1)
    if not marker_index < end:
        raise ValueError(f"Could not isolate the {marker} home component")
    return source[:header.start()] + render(header["name"], source[header.end():end - 1]) + source[end:]


def render_compass(name, body):
    single = re.search(r'([\w$]+)\(`a`,\{className:`atlas-triforce-source`', body)[1]
    multiple = re.search(r'return ([\w$]+)\(`div`,\{className:`atlas-triforce-stage`', body)[1]
    return f'function {name}(){{return renderStudioCompass({single},{multiple});}}'


def render_landmarks(name, body):
    single = re.search(r'([\w$]+)\(`button`,\{type:`button`,"aria-pressed"', body)[1]
    multiple = re.search(r'return ([\w$]+)\(`figure`,\{', body)[1]
    state = re.search(r'\(0,([\w$]+)\.useState\)\(0\)', body)[1]
    return f'function {name}(){{return renderStudioLandmarks({single},{multiple},{state}.useState);}}'


def apply(root: Path):
    """Install styles and keep the atlas link identical in prerender and hydration."""
    dest = root / PUBLIC.strip("/")
    dest.mkdir()
    images, home_copy, module = install_landmarks(dest)
    stylesheet = b"\n".join(path.read_bytes() for path in (
        HERE / "studio.css", HERE / "studio-guides.css", ASSETS / "home-landmarks.css"))
    css_name = f"studio-{sha256(stylesheet).hexdigest()[:16]}.css"
    (dest / css_name).write_bytes(stylesheet)
    for path in ASSETS.glob(f"{VALLEY}-*.webp"):
        shutil.copyfile(path, dest / path.name)

    credits = {}
    for path in root.rglob("*.html"):
        source = path.read_bytes().decode("utf-8")
        prefix = path.relative_to(root).parts[0]
        lang = prefix if prefix in MAP_LABEL else "en"
        link = f'<link rel="stylesheet" href="{PUBLIC}{css_name}"/>'
        if 'id="atlas-home-title"' in source:
            local = "" if lang == "en" else "/" + lang
            button = (f'<a class="studio-atlas-link" href="{local}{MAP_PATH}">'
                      f'{html.escape(MAP_LABEL[lang])}</a>')
            source, count = TITLE_END.subn(lambda m: m[1] + button + m[2], source)
            if count != 1:
                raise ValueError(f"Expected one home title in {path}")
            source, chart_count = FIELD_CHART.subn(lambda _: landmark_markup(images, home_copy[lang], local), source)
            source, compass_count = COMPASS.subn(lambda _: compass_markup(images, home_copy[lang], local), source)
            if (chart_count, compass_count) != (1, 1):
                raise ValueError(f"Expected one landmark preview and one compass in {path}")
            link += (f'<link rel="preload" as="image" type="image/webp" media="(max-width: 760px)" '
                     f'href="{PUBLIC}{VALLEY}-960.webp"/>'
                     f'<link rel="preload" as="image" type="image/webp" media="(min-width: 761px)" '
                     f'href="{PUBLIC}{VALLEY}-1600.webp"/>')
        if path.parent.name == "sources":
            old = STUDIO_CREDIT.search(source)
            if not old:
                raise ValueError(f"Missing homepage artwork credit in {path}")
            title, description = home_copy[lang]["creditEntry"]
            credits.update({html.unescape(old[2]): title, html.unescape(old[4]): description})
            source = source[:old.start()] + old[1] + html.escape(title) + old[3] + html.escape(description) + old[5] + source[old.end():]
        if "</head>" not in source:
            raise ValueError(f"Missing head in {path}")
        path.write_bytes(source.replace("</head>", link + "</head>", 1).encode("utf-8"))

    labels = compact(MAP_LABEL)
    credit_literals = re.compile(r'(?P<q>[`"])(?P<text>' + "|".join(map(re.escape, credits)) + r')(?P=q)')
    for path in (root / "assets").glob("*.js"):
        is_credit_bundle = re.match(r'^(?:sources|en|fr|es|ja|zh)-', path.name)
        if not is_credit_bundle and not path.name.startswith("routes-"):
            continue
        source = path.read_bytes().decode("utf-8")
        if is_credit_bundle:
            updated = credit_literals.sub(lambda m: m["q"] + credits[m["text"]] + m["q"], source)
            if updated != source:
                path.write_bytes(updated.encode("utf-8"))
            continue
        if "atlas-frontier-title" not in source:
            continue

        def home_button(match):
            return (match["title"] + f',{match["jsx"]}(`a`,{{className:`studio-atlas-link`,href:`{MAP_PATH}`,'
                    f'children:({labels})[document.documentElement.lang.split("-")[0]]||"Explore the atlas"}})')

        updated, count = CLIENT_TITLE_END.subn(home_button, source)
        if count != 1:
            raise ValueError(f"Expected one home renderer in {path}")
        updated = replace_component(updated, "atlas-triforce-stage", render_compass)
        if 'className:`field-chart`' in updated:
            updated = replace_component(updated, "field-chart", render_landmarks)
        updated = (f'import {{renderStudioCompass,renderStudioLandmarks}} from "./studio/{module}";\n' + updated)
        path.write_bytes(updated.encode("utf-8"))
