"""Apply the studio presentation to the existing localized static export."""

import html
import json
from hashlib import sha256
from pathlib import Path
import re
import shutil


HERE = Path(__file__).resolve().parent
ASSETS = HERE / "studio-assets"
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


def apply(root: Path):
    """Install styles and keep the atlas link identical in prerender and hydration."""
    dest = root / PUBLIC.strip("/")
    dest.mkdir()
    stylesheet = (HERE / "studio.css").read_bytes() + b"\n" + (HERE / "studio-guides.css").read_bytes()
    css_name = f"studio-{sha256(stylesheet).hexdigest()[:16]}.css"
    (dest / css_name).write_bytes(stylesheet)
    for path in ASSETS.glob(f"{VALLEY}-*.webp"):
        shutil.copyfile(path, dest / path.name)

    for path in root.rglob("*.html"):
        source = path.read_bytes().decode("utf-8")
        link = f'<link rel="stylesheet" href="{PUBLIC}{css_name}"/>'
        if 'id="atlas-home-title"' in source:
            prefix = path.relative_to(root).parts[0]
            lang = prefix if prefix in MAP_LABEL else "en"
            local = "" if lang == "en" else "/" + lang
            button = (f'<a class="studio-atlas-link" href="{local}{MAP_PATH}">'
                      f'{html.escape(MAP_LABEL[lang])}</a>')
            source, count = TITLE_END.subn(lambda m: m[1] + button + m[2], source)
            if count != 1:
                raise ValueError(f"Expected one home title in {path}")
            link += (f'<link rel="preload" as="image" type="image/webp" media="(max-width: 760px)" '
                     f'href="{PUBLIC}{VALLEY}-960.webp"/>'
                     f'<link rel="preload" as="image" type="image/webp" media="(min-width: 761px)" '
                     f'href="{PUBLIC}{VALLEY}-1600.webp"/>')
        if "</head>" not in source:
            raise ValueError(f"Missing head in {path}")
        path.write_bytes(source.replace("</head>", link + "</head>", 1).encode("utf-8"))

    labels = json.dumps(MAP_LABEL, ensure_ascii=False, separators=(",", ":"))
    for path in (root / "assets").glob("routes-*.js"):
        source = path.read_bytes().decode("utf-8")
        if "atlas-frontier-title" not in source:
            continue

        def home_button(match):
            return (match["title"] + f',{match["jsx"]}(`a`,{{className:`studio-atlas-link`,href:`{MAP_PATH}`,'
                    f'children:({labels})[document.documentElement.lang.split("-")[0]]||"Explore the atlas"}})')

        updated, count = CLIENT_TITLE_END.subn(home_button, source)
        if count != 1:
            raise ValueError(f"Expected one home renderer in {path}")
        path.write_bytes(updated.encode("utf-8"))
