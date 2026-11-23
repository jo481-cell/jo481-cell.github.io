"""Replace the ALttP raster maps in a built Pages export with original editorial diagrams."""
import html
import json
from pathlib import Path
import re
from string import ascii_uppercase
from functools import lru_cache
from unicodedata import east_asian_width

from . import dungeon_plans, painted_world

ART = Path(__file__).with_name("map-assets")
OLD = "/assets/alttp/"
NEW = "/assets/atlas-charts/"
SCHEMATIC_DIR = "plans-v2"
SCHEMATICS = NEW + SCHEMATIC_DIR + "/"
NOTES = NEW + "provenance.json"
LEGACY_SOURCE = "https://ian-albert.com/games/legend_of_zelda_a_link_to_the_past_maps/"
FLOOR = re.compile(r"dungeon-([A-Z]\d?)-(B\d+|\d+F)\.png$")
EMBEDDED = re.compile(r"\{source:`" + re.escape(LEGACY_SOURCE) +
                      r"`,credit:`[^`]*`,permission:`[^`]*`,assets:\[.*?\](?:,previewDerivatives:\[.*?\])?\}")
FORMATS = {".html", ".css", ".js", ".json", ".xml", ".txt", ".webmanifest", ".md"}
FLOOR_HTML = re.compile(r'(<div\b[^>]*\bclass="alttp-floor[^"]*"[^>]*>)(<img\b[^>]*>)(</div>)')
FLOOR_JS = re.compile(
    r'(?P<region>\w+)\(`div`,\{(?P<props>className:`alttp-floor [^,]+,tabIndex:0,role:`region`,"aria-label":`[^`]+`,children:)'
    r'(?P<jsx>\w+)\(`img`,\{(?P<image>.*?)\}\)\}\)(?=,\w+\(`small`)'
)
LANGUAGES = ("en", "fr", "es", "ja", "zh")
GUIDE_ROOT = Path("series/a-link-to-the-past")
WORLD_COLORS = {
    "light": dict(paper="#e8dec3", ink="#253c32", grid="#697960", shade="#cbb998",
        landline="#6e7860", green="#b4c29c", wood="#72926c", woodshade="#597758", sand="#d5b383",
        stone="#c7b494", peak="#bcab91", water="#9fb8ad", waterline="#547c75",
        building="#e6cf9f", buildingline="#67563d"),
    "dark": dict(paper="#233732", ink="#f1e1bd", grid="#899583", shade="#38463f",
        landline="#83917d", green="#496253", wood="#678171", woodshade="#354f48", sand="#6c674b",
        stone="#635e53", peak="#726b58", water="#3d5e61", waterline="#8fa6a0",
        building="#a78e61", buildingline="#e3cda0"),
}
WORLD_DESCRIPTION = {
    "en": ("Light World", "Dark World", "Original illustrated terrain and documented guide locations."),
    "fr": ("Monde de la Lumière", "Monde des Ténèbres", "Relief illustré original et emplacements documentés par les guides."),
    "es": ("Mundo de la Luz", "Mundo de las Tinieblas", "Relieve ilustrado original y lugares documentados en las guías."),
    "ja": ("光の世界", "闇の世界", "独自に描いた地形と、攻略ガイドに記載された地点。"),
    "zh": ("光明世界", "黑暗世界", "原创地形插画与攻略中已记录的地点。"),
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


def _world(world, language, regions, sites, places=False, overlay=False):
    coords = []
    for index, letter in enumerate(ascii_uppercase[:10]):
        offset = index * 100 + 50
        coords.append(f'<text x="{offset}" y="12" text-anchor="middle">{letter}</text>'
                      f'<text x="8" y="{offset + 3}" text-anchor="middle">{index + 1}</text>')
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
    site_labels = []
    if not places:
        for point_id, x, y, label_x, label_y, anchor, translations in sites:
            label = translations[LANGUAGES.index(language)]
            tail_x = label_x + (5 if anchor == "end" else -5)
            extent = label_x - 23 if anchor == "end" else 977 - label_x
            fit = f' textLength="{extent}" lengthAdjust="spacingAndGlyphs"' if _measure(label) * 10 > extent else ""
            site_labels.append(f'<g data-guide-location="{point_id}">'
                               f'<path d="M{x} {y}L{tail_x} {label_y - 6}" class="site-leader"/>'
                               f'<circle cx="{x}" cy="{y}" r="2.5" class="site-origin"/>'
                               f'<text x="{label_x}" y="{label_y}" text-anchor="{anchor}"{fit}>'
                               f'{html.escape(label)}</text></g>')
    pins = []
    if places:
        # These three guide anchors are the same existing fractional coordinates used by FieldChart.
        for x,y,label,shape in [(500,455,"A",'<circle r="9"/>'),(160,470,"B",'<path d="M0-10 10 0 0 10-10 0Z"/>'),(795,845,"C",'<rect x="-8" y="-8" width="16" height="16"/>')]:
            pins.append(f'<g transform="translate({x} {y})"><circle fill="#f5ecce" stroke="#32655a" stroke-width="2" r="28"/>'
                        f'<circle fill="none" stroke="#708b72" r="39" stroke-dasharray="3 5"/><g fill="#295b50">{shape}</g>'
                        f'<text x="41" y="5" font-family="system-ui,sans-serif" font-weight="650" font-size="22" fill="#26584c">{label}</text></g>')
    light, dark, description = WORLD_DESCRIPTION[language]
    title = f"{light if world == 'light' else dark} · Hyrule Atlas"
    if overlay:
        return _render("world-overlay", language=language, title=title,
                       coordinates="".join(coords), labels="".join(labels), site_labels="".join(site_labels))
    return _render("world", **WORLD_COLORS[world], language=language,
                   title=title,
                   description=description, coordinates="".join(coords),
                   terrain="".join(terrain), labels="".join(labels),
                   site_labels="".join(site_labels), focus="".join(pins))


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
        route.append(f'<path d="M200 {y + 44}H767" stroke="#5e6b55" stroke-opacity=".55"/>'
                     f'<circle cx="223" cy="{y}" r="24" fill="#314839" stroke="#b6a070" stroke-width="1.5"/>'
                     f'<text x="223" y="{y + 9}" text-anchor="middle" fill="#ead3a0">{number}</text>'
                     f'<path d="M735 {y}h23m-8-8 8 8-8 8" fill="none" stroke="#dbc28b" stroke-width="2.6"/>')
        for line, text in enumerate(lines):
            baseline = y + 10 + 33 * (line - (len(lines) - 1) / 2)
            length = ' textLength="435" lengthAdjust="spacingAndGlyphs"' if _measure(text) > 29 else ""
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
        highlights.append((int(number), label.strip(), reference))
    return html.unescape(title), sorted(highlights), steps.keys()


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
    sites = json.loads((ART / "world-sites.json").read_text(encoding="utf8"))
    routes = json.loads((ART / "routes.json").read_text(encoding="utf8"))
    if set(routes) != set(groups):
        raise ValueError("Each dungeon needs a walkthrough diagram")
    plan_sources, plans = dungeon_plans.load(ART, groups, routes)
    result = {}
    walkthroughs = {}
    for language in LANGUAGES:
        prefix = "" if language == "en" else f"/{language}"
        walkthroughs[language] = {
            "label": FLOOR_HEADINGS[language][1], "dungeons": {}
        }
        result[f"{language}/light.svg"] = _world("light", language, landmarks["light"], sites["light"])
        result[f"{language}/dark.svg"] = _world("dark", language, landmarks["dark"], sites["dark"])
        for world in ("light", "dark"):
            result[f"{language}/{world}-labels.svg"] = _world(world, language, landmarks[world], sites[world], overlay=True)
        result[f"{language}/places.svg"] = _world("light", language, landmarks["light"], sites["light"], places=True)
        for code, levels in groups.items():
            slug, references = routes[code]
            title, steps, step_ids = _chapter(root, language, slug, references)
            overview = f"{prefix}/{GUIDE_ROOT.as_posix()}/{slug}/"
            walkthrough = {"steps": [
                (f"{number}. {label}", f"{overview}#step-{reference}") for number, label, reference in steps
            ], "plans": {}}
            walkthroughs[language]["dungeons"][code] = walkthrough
            for floor in levels:
                filename = f"dungeon-{code}-{floor}.svg"
                facts = plans.get(code, {}).get(floor)
                if facts is not None:
                    result[f"{language}/{filename}"] = dungeon_plans.drawing(title, floor, language, facts)
                    walkthrough["plans"][filename] = {
                        "__html": dungeon_plans.details(facts, plan_sources, language, overview, step_ids)
                    }
                else:
                    result[f"{language}/{filename}"] = _floor_svg(
                        title, levels, floor, language, [(number, label) for number, label, _ in steps]
                    )
    return result, walkthroughs, plan_sources, plans


def _floor_html(source, language, walkthroughs):
    routes = walkthroughs[language]

    def with_links(match):
        opening, image, closing = match.groups()
        filename, code = re.search(r"(dungeon-([A-Z]\d?)-(?:B\d+|\d+F)\.svg)", image).group(1, 2)
        guide = routes["dungeons"][code]
        plan = guide["plans"].get(filename)
        if plan is not None:
            return (f'<div class="atlas-floor-layout">{opening}<div class="atlas-floor-board">{image}</div>{closing}'
                    f'<div class="atlas-plan-detail">{plan["__html"]}</div></div>')
        links = "".join(
            f'<a href="{href}" aria-label="{html.escape(label, quote=True)}"></a>'
            for label, href in guide["steps"]
        )
        heading = html.escape(routes["label"], quote=True)
        return (f'{opening}<div class="atlas-floor-board">{image}'
                f'<nav class="atlas-step-links" aria-label="{heading}">{links}</nav></div>{closing}')

    return FLOOR_HTML.sub(with_links, source)


def _floor_js(source, route_data):
    def with_links(match):
        props = match["props"]
        region = match["region"]
        call = match["jsx"]
        image = match["image"]
        code = re.search(r"dungeon-\$\{(\w+)\}-", image)[1]
        filename = re.search(r"src:`/assets/alttp/\$\{(\w+)\}`", image)[1]
        return ("(()=>{const locale=atlasDungeonRoutes[document.documentElement.lang.split('-')[0]]"
                f"??atlasDungeonRoutes.en;const guide=locale.dungeons[{code}],plan=guide.plans[{filename}];"
                f"const board={region}(`div`,{{{props}{call}(`div`,{{className:`atlas-floor-board`,children:[{call}(`img`,{{{image}}}),"
                f"!plan&&{call}(`nav`,{{className:`atlas-step-links`,\"aria-label\":locale.label,"
                f"children:guide.steps.map(([label,href])=>"
                f"{call}(`a`,{{href,\"aria-label\":label}},href))}})]}})}});"
                f"return plan?{call}(`div`,{{className:`atlas-floor-layout`,children:[board,"
                f"{call}(`div`,{{className:`atlas-plan-detail`,dangerouslySetInnerHTML:plan}},{filename})]}}):board;"
                "})()")

    source, replaced = FLOOR_JS.subn(with_links, source)
    if replaced != 1:
        raise ValueError(f"Expected one dungeon renderer in a shared chunk, found {replaced}")
    return "const atlasDungeonRoutes=" + route_data + ";\n" + source


def _messages():
    texts=json.loads((ART/"messages.json").read_text(encoding="utf8"))
    texts.update(json.loads((ART/"floor-copy.json").read_text(encoding="utf8")))
    texts.update({
        "% 轻": "% 光明世界",
        "Antecedentes del Mundo Oscuro": "Fondo del Mundo Oscuro",
        "Desliza para moverte; acérquese para leer los detalles.": "Desliza para moverte y amplía el mapa para ver los detalles.",
        "ズームマップ": "地図を拡大",
        "缩放地图": "放大地图",
        "适合整个地图": "显示完整地图",
    })
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
    diagrams,walkthroughs,plan_sources,plans=_image_files(root, legacy)
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
        path=out/SCHEMATIC_DIR/relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(svg,encoding="utf8")
        w,h=(800,480) if name.startswith("dungeon-") else (1000,1000)
        rows.append({"file":name,"locale":language,"url":SCHEMATICS+relative,"width":w,"height":h})
    painted = painted_world.publish(root)
    doc={"source":NOTES,"credit":"Hyrule Atlas","permission":"Original editorial maps and walkthrough diagrams by Hyrule Atlas.",
         "method":{"en":"Terrain is illustrative. Guide pins retain the locations recorded over Ian Albert’s map. Dungeon plans use documented SNES rooms, items and passages without distances. Solid lines show direct passages and dotted lines show guide order. Floors without enough facts retain the walkthrough highlights.",
                   "fr":"Le relief est illustratif. Les repères gardent les positions relevées sur l’assemblage d’Ian Albert. Les schémas de donjon indiquent des salles, objets et passages documentés pour la Super NES, sans échelle. Les traits pleins montrent les passages directs et les pointillés l’ordre de la soluce. Les étages insuffisamment documentés gardent le récapitulatif de la soluce.",
                   "es":"El relieve es ilustrativo. Los marcadores conservan las posiciones registradas sobre el mapa de Ian Albert. Los esquemas sin escala muestran salas, objetos y pasos de Super NES documentados. Las líneas continuas indican pasos directos y las punteadas, el orden de la guía.",
                   "ja":"地形はイメージです。地点にはイアン・アルバートの地図に付けた既存の座標を使用しています。SFC版の部屋・アイテム・通路の確認済み情報を縮尺なしで示します。実線は直接の通路、点線は攻略順です。",
                   "zh":"地形为示意。标记沿用在 Ian Albert 地图上设定的位置。迷宫示意图标明有出处的 SFC 版房间、道具和通道，不按比例绘制。实线为直接通道，虚线为攻略顺序。"},
         "historical_reference":LEGACY_SOURCE,
         "companion": {"name":"Kuni", "provenance":NEW+"kuni-provenance.json"},
         "dungeon_plans": {"edition":"SNES", "scale":"schematic",
                           "sources":plan_sources, "dungeons":plans}, "painted_relief":painted, "assets":rows}
    (out/"provenance.json").write_text(json.dumps(doc,indent=2,ensure_ascii=False)+"\n",encoding="utf8")
    # Keep the original manifest's presentation order: it also supplies the default selected
    # floor for the one tower whose published range starts above 1F.
    lookup={r["file"]:r for r in rows if r["locale"] == "en"}
    floor_rows=[lookup[r["file"][:-4]+".svg"] for r in legacy["assets"] if FLOOR.fullmatch(r["file"])]
    bundle=json.dumps({"source":NOTES,"credit":"Hyrule Atlas","permission":doc["permission"],"assets":floor_rows,"previewDerivatives":[]},
                      separators=(",",":"),ensure_ascii=False)
    route_data=json.dumps(walkthroughs,separators=(",",":"),ensure_ascii=False)
    styles=(ART/"map-interface.css").read_text(encoding="utf8")
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
    size=re.compile(r'<img\b(?=[^>]*?'+re.escape(SCHEMATICS)+r'[a-z]{2}/dungeon-)[^>]*>')
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
            s += "\n" + styles
        if p.suffix == ".css":
            s = s.replace(".alttp-search-page .atlas-shell .alttp-plans[open]>p{display:none}", "")
        if p.suffix==".js":
            if 'className:`alttp-floor ' in s:
                s = _floor_js(s, route_data)
            if 'className:`atlas-living-map__world atlas-living-map__world--light`' in s:
                s = painted_world.update_preview_js(s, painted["worlds"], p)
            s=clean_floor_ext.sub(r'\1.svg\2',s)
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
            locale = p.relative_to(root).parts[0]
            language = locale if locale in LANGUAGES else "en"
            s = _floor_html(s, language, walkthroughs)
            if 'class="atlas-living-map__surface"' in s:
                s = painted_world.update_preview_html(s, language, painted["worlds"])
            if 'class="alttp-world-image' in s:
                s = painted_world.update_html(s, language, painted["worlds"])
        elif p.suffix == ".js" and 'className:`alttp-world-image' in s:
            s = painted_world.update_js(s, painted["worlds"])
        revised=s.encode("utf8")
        if content!=revised:
            p.write_bytes(revised)
    for p in old.iterdir():
        p.unlink()
    old.rmdir()
