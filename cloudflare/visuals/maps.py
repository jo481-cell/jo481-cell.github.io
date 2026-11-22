"""Replace the ALttP raster maps in a built Pages export with original editorial diagrams."""
import html
import json
from pathlib import Path
import re
from string import ascii_uppercase
from functools import lru_cache
from unicodedata import east_asian_width


ART = Path(__file__).with_name("map-assets")
OLD = "/assets/alttp/"
NEW = "/assets/atlas-charts/"
SCHEMATICS = NEW + "schematics/"
NOTES = NEW + "provenance.json"
LEGACY_SOURCE = "https://ian-albert.com/games/legend_of_zelda_a_link_to_the_past_maps/"
FLOOR = re.compile(r"dungeon-([A-Z]\d?)-(B\d+|\d+F)\.png$")
EMBEDDED = re.compile(r"\{source:`" + re.escape(LEGACY_SOURCE) +
                      r"`,credit:`[^`]*`,permission:`[^`]*`,assets:\[.*?\](?:,previewDerivatives:\[.*?\])?\}")
FORMATS = {".html", ".css", ".js", ".json", ".xml", ".txt", ".webmanifest", ".md"}
LANGUAGES = ("en", "fr", "es", "ja", "zh")
GUIDE_ROOT = Path("series/a-link-to-the-past")
WORLD_COLORS = {
    "light": dict(paper="#ece6d0", ink="#273e35", grid="#76877b",
        landline="#6a7a5e", green="#b7c8a3", wood="#6f9b78", sand="#e9c78d",
        stone="#c8bca5", peak="#dccfb9", water="#a6c7cb", waterline="#59838a",
        building="#dccda4", buildingline="#665c46"),
    "dark": dict(paper="#26343e", ink="#f4e7c8", grid="#899599",
        landline="#9a927c", green="#536c5a", wood="#2e504a", sand="#94775d",
        stone="#65596a", peak="#958091", water="#42616b", waterline="#8ca5aa",
        building="#b49074", buildingline="#eed4a6"),
}
WORLD_DESCRIPTION = {
    "en": ("Light World", "Dark World", "Editorial map showing regions and approximate positions."),
    "fr": ("Monde de la Lumière", "Monde des Ténèbres", "Carte schématique des régions et de leurs positions approximatives."),
    "es": ("Mundo de la Luz", "Mundo de las Tinieblas", "Mapa esquemático de las regiones y sus posiciones aproximadas."),
    "ja": ("光の世界", "闇の世界", "地域のおおよその位置を示す略図。"),
    "zh": ("光明世界", "黑暗世界", "显示各区域大致位置的示意图。"),
}
FLOOR_HEADINGS = {
    "en": ("Floors", "Walkthrough highlights"),
    "fr": ("Étages", "Étapes clés de la soluce"),
    "es": ("Plantas", "Pasos clave de la guía"),
    "ja": ("階層", "攻略の要点"),
    "zh": ("楼层", "攻略要点"),
}
WORLD_FILES = {"light_world-1.png":"light.svg","dark_world.png":"dark.svg",
               "light-field-2048.webp":"places.svg","light-field-960.webp":"places.svg"}
for world in ("light","dark"):
    for size in ("1024","4096","preview"):
        WORLD_FILES[f"{world}-world-{size}.webp"] = world+".svg"


def _render(name, **values):
    svg = (ART / (name+".template.svg")).read_text(encoding="utf8")
    return re.sub(r"\{\{(\w+)\}\}", lambda m:str(values[m[1]]), svg)


def _world(world, language, regions, places=False):
    coords = [
        f'<text x="{col * 100 + 22}" y="{row * 100 + 32}">{ascii_uppercase[col]}{row + 1}</text>'
        for col in range(10) for row in range(10)
    ]
    terrain = []
    labels = []
    for kind, x, y, label_x, label_y, translations in regions:
        terrain.append(f'<use href="#{kind}" x="{x}" y="{y}"/>')
        label = translations[LANGUAGES.index(language)]
        extent = min(label_x - 20, 980 - label_x) * 2
        if _measure(label) * 15 > extent:
            extent = f' textLength="{extent}" lengthAdjust="spacingAndGlyphs"'
        else:
            extent = ""
        labels.append(f'<text class="landmark" x="{label_x}" y="{label_y}"{extent}>{html.escape(label)}</text>')
    pins = []
    if places:
        # These three guide anchors are the same existing fractional coordinates used by FieldChart.
        for x,y,label,shape in [(500,455,"A",'<circle r="9"/>'),(160,470,"B",'<path d="M0-10 10 0 0 10-10 0Z"/>'),(795,845,"C",'<rect x="-8" y="-8" width="16" height="16"/>')]:
            pins.append(f'<g transform="translate({x} {y})"><circle fill="#f5ecce" stroke="#32655a" stroke-width="2" r="28"/>'
                        f'<circle fill="none" stroke="#708b72" r="39" stroke-dasharray="3 5"/><g fill="#295b50">{shape}</g>'
                        f'<text x="41" y="5" font-family="system-ui,sans-serif" font-weight="650" font-size="22" fill="#26584c">{label}</text></g>')
    light, dark, description = WORLD_DESCRIPTION[language]
    return _render("world", **WORLD_COLORS[world], language=language,
                   title=f"{light if world == 'light' else dark} · Hyrule Atlas",
                   description=description, coordinates="".join(coords),
                   terrain="".join(terrain), labels="".join(labels), focus="".join(pins))


def _height(floor):
    return -int(floor[1:]) if floor.startswith("B") else int(floor[:-1])


def _measure(text):
    return sum(2 if east_asian_width(ch) in "WF" else 1 for ch in text)


def _wrap(text, limit=31):
    if _measure(text) <= limit:
        return [text]
    breaks = [i for i in range(1, len(text))
              if text[i] == " " or east_asian_width(text[i - 1]) in "WF"]
    cut = min(breaks or range(1, len(text)), key=lambda i: abs(_measure(text[:i]) - _measure(text[i:])))
    return [text[:cut].rstrip(), text[cut:].lstrip()]


def _floor_svg(title, floors, selected, language, steps):
    levels = sorted(floors, key=_height, reverse=True)
    row_height = min(54, 352 / len(levels))
    top = 253 - (len(levels) - 1) * row_height / 2
    stack = []
    for index, level in enumerate(levels):
        y = round(top + index * row_height, 1)
        active = level == selected
        if active:
            stack.append(f'<rect x="24" y="{y - 20:g}" width="112" height="40" rx="5" fill="#edcf8b"/>')
        color = "#172f2b" if active else "#c5d6c4"
        stack.append(f'<text x="80" y="{y + 10:g}" fill="{color}">{level}</text>')
    route = []
    for index, (number, label) in enumerate(steps):
        y = 112 + index * 98
        lines = _wrap(label)
        route.append(f'<circle cx="223" cy="{y}" r="28" fill="#284a42" stroke="#b3c9b3" stroke-width="2"/>'
                     f'<text x="223" y="{y + 10}" text-anchor="middle" fill="#edcf8b">{number}</text>')
        for line, text in enumerate(lines):
            baseline = y + 10 + 33 * (line - (len(lines) - 1) / 2)
            length = ' textLength="478" lengthAdjust="spacingAndGlyphs"' if _measure(text) > 31 else ""
            route.append(f'<text x="274" y="{baseline:g}"{length}>{html.escape(text)}</text>')
    levels_label, route_label = FLOOR_HEADINGS[language]
    return _render("floor", title=f"{html.escape(title)} · {selected}", language=language,
                   description=f"{levels_label}: {selected}. {route_label}: "
                               + " → ".join(f"{number}. {html.escape(label)}" for number, label in steps),
                   level_title=levels_label, route_title=route_label,
                   stack="".join(stack), route="".join(route))


def _chapter(root, language, slug, references):
    base = root if language == "en" else root / language
    chapter = (base / GUIDE_ROOT / slug / "index.html").read_text(encoding="utf8")
    title = re.search(r'<h1 id="atlas-page-title">(.*?)</h1>', chapter, re.S)[1]
    steps = dict(re.findall(r'<h2><label for="check-([^"]+)">(.*?)</label></h2>', chapter, re.S))
    highlights = []
    for reference in references:
        text = html.unescape(re.sub(r"<[^>]+>", "", steps[reference]))
        number, label = text.split(".", 1)
        highlights.append((int(number), label.strip()))
    return html.unescape(title), sorted(highlights)


def _image_files(root, manifest):
    groups={}
    for record in manifest["assets"]:
        name = record["file"]
        m=FLOOR.fullmatch(name)
        if m:
            groups.setdefault(m[1], []).append(m[2])
        elif name not in WORLD_FILES:
            raise ValueError("Unrecognized ALttP map record: "+name)
    if not groups:
        raise ValueError("The export contains no dungeon floor records")
    landmarks = json.loads((ART / "landmarks.json").read_text(encoding="utf8"))
    routes = json.loads((ART / "routes.json").read_text(encoding="utf8"))
    if set(routes) != set(groups):
        raise ValueError("Each dungeon needs a walkthrough diagram")
    result = {}
    for language in LANGUAGES:
        result[f"{language}/light.svg"] = _world("light", language, landmarks["light"])
        result[f"{language}/dark.svg"] = _world("dark", language, landmarks["dark"])
        result[f"{language}/places.svg"] = _world("light", language, landmarks["light"], places=True)
        for code, levels in groups.items():
            title, steps = _chapter(root, language, *routes[code])
            for floor in levels:
                result[f"{language}/dungeon-{code}-{floor}.svg"] = _floor_svg(title, levels, floor, language, steps)
    return result


def _messages():
    texts=json.loads((ART/"messages.json").read_text(encoding="utf8"))
    # Static HTML attributes and rendered React text may both use entity escapes.
    for old,new in list(texts.items()):
        for quote in (False,True):
            texts[html.escape(old,quote=quote)] = html.escape(new,quote=quote)
    return texts


@lru_cache(maxsize=256)
def _pattern(keys):
    return re.compile("|".join(map(re.escape,keys)))


def apply(root: Path):
    root=Path(root).resolve()
    old=root/"assets/alttp"
    out=root/"assets/atlas-charts"
    if (root/".git").exists() or not (root/"index.html").is_file() or not (root/"assets").is_dir():
        raise ValueError("Expected a built export directory, got "+str(root))
    if (root/"assets").is_symlink() or old.is_symlink() or out.is_symlink():
        raise ValueError("Chart transformation requires ordinary export directories")
    if not old.exists():
        if (out/"provenance.json").is_file():
            return
        raise ValueError("Missing ALttP map manifest")
    legacy=json.loads((old/"sources.json").read_text(encoding="utf8"))
    diagrams=_image_files(root, legacy)
    existing={p.name for p in old.iterdir() if p.is_file()}
    supported=set(WORLD_FILES)|{"light-field-water.webp","sources.json","light-field-source.json"}|{
        Path(n).name.replace(".svg",".png") for n in diagrams if Path(n).name.startswith("dungeon-")
    }
    if existing-supported or any(p.is_dir() or p.is_symlink() for p in old.iterdir()):
        raise ValueError("Review new ALttP files before publishing: "+str(sorted(existing-supported)))
    if out.exists() or old.is_symlink() or out.is_symlink():
        raise ValueError("Unexpected chart destination or symlink")
    rows=[]
    for relative,svg in diagrams.items():
        language,name = relative.split("/")
        path=out/"schematics"/relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(svg,encoding="utf8")
        w,h=(800,480) if name.startswith("dungeon-") else (1000,1000)
        rows.append({"file":name,"locale":language,"url":SCHEMATICS+relative,"width":w,"height":h})
    doc={"source":NOTES,"credit":"Hyrule Atlas","permission":"Original editorial maps and walkthrough diagrams by Hyrule Atlas.",
         "method":{"en":"Regions and terrain symbols show approximate positions. The guide pins retain their earlier positions, originally placed over Ian Albert’s assembly. Dungeon diagrams highlight the selected floor and four numbered steps from the chapter. The floor index and steps are independent.",
                   "fr":"Les régions et les symboles indiquent des positions approximatives. Les repères reprennent les coordonnées initialement placées sur l’assemblage d’Ian Albert. Chaque schéma de donjon associe un index d’étages et quatre étapes numérotées de la soluce. Les étapes couvrent le donjon dans son ensemble.",
                   "es":"Las regiones y los símbolos indican posiciones aproximadas. Los marcadores conservan las coordenadas asignadas originalmente sobre el montaje de Ian Albert. El índice de plantas acompaña cuatro pasos numerados del recorrido de la mazmorra.",
                   "ja":"地域と地形記号はおおよその位置を示します。地点には、イアン・アルバートの地図に付けた既存の座標を使用しています。階層一覧と、攻略記事から選んだ4つの手順を表示します。",
                   "zh":"区域和地形符号只表示大致位置。标记沿用最初在 Ian Albert 拼接地图上设定的坐标。迷宫示意图同时显示楼层索引和对应攻略章节的四个关键步骤。"},
         "assets":rows}
    (out/"provenance.json").write_text(json.dumps(doc,indent=2,ensure_ascii=False)+"\n",encoding="utf8")
    # Keep the original manifest's presentation order: it also supplies the default selected
    # floor for the one tower whose published range starts above 1F.
    lookup={r["file"]:r for r in rows if r["locale"] == "en"}
    floor_rows=[lookup[r["file"][:-4]+".svg"] for r in legacy["assets"] if FLOOR.fullmatch(r["file"])]
    bundle=json.dumps({"source":NOTES,"credit":"Hyrule Atlas","permission":doc["permission"],"assets":floor_rows,"previewDerivatives":[]},
                      separators=(",",":"),ensure_ascii=False)
    mapping=_messages()
    mapping.update(WORLD_FILES)
    mapping.update({"-world-1024.webp":".svg","-world-4096.webp":".svg",
                    OLD+"sources.json":NOTES, OLD+"light-field-source.json":NOTES,
                    LEGACY_SOURCE:NOTES, OLD:SCHEMATICS, "A Link to the Past · © Nintendo · Ian Albert":"Hyrule Atlas",
                    "-1F.png":"-1F.svg", "light-field-water.webp":"places.svg"})
    for n in floor_rows:
        mapping[n["file"][:-4]+".png"]=n["file"]
    keys=sorted(mapping,key=len,reverse=True)
    clean_floor_ext=re.compile(r'(replace\(`dungeon-\$\{\w+\}-`,``\)\.replace\(\x60)\.png(\x60)')
    size=re.compile(r'<img\b(?=[^>]*?/assets/atlas-charts/schematics/[a-z]{2}/dungeon-)[^>]*>')
    charts_pattern=re.compile(re.escape(SCHEMATICS)+r"(?![a-z]{2}/|\$\{document\.)")
    srcset_pattern=re.compile(r"("+re.escape(SCHEMATICS)+r"(?:light|dark|\$\{\w+\})\.svg) 1024w, \1 4096w")
    for p in sorted(root.rglob("*")):
        if p.is_symlink():
            raise ValueError("Unexpected symlink in the built export: "+str(p))
        if not p.is_file() or p.suffix.lower() not in FORMATS or old in p.parents or out in p.parents:
            continue
        content=p.read_bytes()
        s=content.decode("utf8")
        if p.suffix==".js" and LEGACY_SOURCE in s:
            s=EMBEDDED.sub(lambda _m:bundle,s)
        if p.suffix==".css" and "light-field-water.webp" in s:
            s=re.sub(r'background\s*:\s*url\(["\']?/assets/alttp/light-field-water\.webp["\']?\)\s*center/100%\s+100%',"background:none",s)
        if p.suffix==".css" and ".alttp-floor.is-large" in s:
            s+=("\n.alttp-floor:not(.is-large) img{width:min(100%,940px);height:auto;margin-inline:auto;image-rendering:auto}"
                ".alttp-floor.is-large img{width:max(125%,1000px);max-width:none;height:auto;image-rendering:auto}\n")
        if p.suffix == ".css":
            s = s.replace(".alttp-search-page .atlas-shell .alttp-plans[open]>p{display:none}", "")
        if p.suffix==".js":
            s=clean_floor_ext.sub(r'\1.svg\2',s)
            s=re.sub(r"Le Miroir compare la géographie ; les repères restent ceux du \$\{[^}]+\}\.",
                     "Le Miroir superpose les deux cartes. Les repères indiquent les accès du monde actif.",s)
        relevant=tuple(k for k in keys if k in s)
        if relevant:
            s=_pattern(relevant).sub(lambda m:mapping[m[0]],s)
        if SCHEMATICS in s:
            s=srcset_pattern.sub(r"\1",s)
            if p.suffix == ".js":
                # Vite's shared chunks use template literals for these public asset URLs.
                # Keep the localized prerender and the hydrated page on the same asset.
                s=s.replace("`"+SCHEMATICS, "`"+SCHEMATICS+"${document.documentElement.lang.split('-')[0]}/")
            locale = p.relative_to(root).parts[0] if p.suffix == ".html" else "en"
            s=charts_pattern.sub(SCHEMATICS+(locale if locale in LANGUAGES else "en")+"/",s)
        if p.suffix==".html":
            s=size.sub(lambda m:re.sub(r'\b(width|height)="\d+"',lambda a:'width="800"' if a[1]=='width' else 'height="480"',m[0]),s)
        revised=s.encode("utf8")
        if content!=revised:
            p.write_bytes(revised)
    for p in old.iterdir():
        p.unlink()
    old.rmdir()
