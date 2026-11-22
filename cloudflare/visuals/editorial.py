"""Replace catalogue illustrations in a staged static Hyrule Atlas export."""
from __future__ import annotations

import html
import json
import re
import shutil
import struct
from hashlib import sha256
from pathlib import Path

HERE = Path(__file__).resolve().parent
UI = HERE / "editorial-ui"
COPY = json.loads((UI / "locale.json").read_text(encoding="utf-8"))
DESCRIPTIONS = json.loads((UI / "descriptions.json").read_text(encoding="utf-8"))
PREFIX = "/assets/editorial/"
CREDITS = PREFIX + "sources.json"
GAME_PAGE = "https://www.nintendo.com/us/store/products/the-legend-of-zelda-ocarina-of-time-switch-2/"
HISTORY = "https://www.nintendo.com/jp/character/zelda/en/history/index.html"
TRAILER_VIDEO = "https://www.youtube.com/watch?v=wuFfiTEr2yc"
OLD_POSTER = "/assets/official-thumbnails/nintendo-trailer-featured.jpg"
RETIRED = ("/assets/official-thumbnails/", "/assets/game-icons/", "/assets/models/triforce-bevel")
ICONS = {
    "guides": '<path d="M4 5c3-1 5-1 8 1 3-2 5-2 8-1v13c-3-1-5-1-8 1-3-2-5-2-8-1zM12 6v13"/>',
    "search": '<circle cx="10" cy="10" r="6"/><path d="m15 15 6 6"/>',
    "map": '<path d="m3 6 6-3 6 3 6-3v15l-6 3-6-3-6 3zM9 3v15m6-12v15"/>',
    "resume": '<path d="M6 3h12v18l-6-4-6 4zM9 8h6"/>',
    "music": '<path d="M4 10v4m4-7v10m4-14v18m4-14v10m4-7v4"/>',
    "compass": '<circle cx="12" cy="12" r="9.5"/><path d="m16.5 6.5-2.8 7.2-6.2 3.8 2.8-7.2zM12 2.5v2M12 19.5v2M2.5 12h2m15 0h2"/>',
}
ICON_MAP = {
    "alttp-treasure-chest": "guides", "oot-bottle": "search", "oot-dungeon-map": "map",
    "oot-heart-container": "resume", "oot-ocarina": "music", "oot3d-navi": "compass",
}
ROSE_PATH = "M150 25 167 111 244 76 190 137 265 155 177 166 190 239 151 184 106 240 121 166 34 153 109 135 58 74 135 113Z"
OLD_ROSE = "M150 20 214 131H86ZM82 138l64 111H18Zm136 0 64 111H154Z"
TRAILER = re.compile(r'<section\b[^>]*\bclass="official-trailer"[^>]*>.*?</section>', re.S)
IMAGE_TAG = re.compile(r'<(?:img|link|meta|a)\b(?:[^>"\']|"[^"]*"|\'[^\']*\')*>')
TEXT_ELEMENT = re.compile(r'<[^>]+>')
SHELF_CREDIT = {
    "en": "Illustrations by Hyrule Atlas · Credits",
    "fr": "Illustrations de Hyrule Atlas · Crédits",
    "es": "Ilustraciones de Hyrule Atlas · Créditos",
    "ja": "イラスト：Hyrule Atlas · クレジット",
    "zh": "Hyrule Atlas 插画 · 制作信息",
}
COMPARISON_LINK = {
    "en": "See Nintendo Life’s comparison ↗",
    "fr": "Voir la comparaison de Nintendo Life ↗",
    "es": "Ver la comparación de Nintendo Life ↗",
    "ja": "Nintendo Lifeの比較記事を見る ↗",
    "zh": "查看 Nintendo Life 的对比文章 ↗",
}
SOURCE_PANEL = re.compile(r'<a class="source-panel"[^>]*>[^<]*</a>')


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def save(path, text):
    path.write_bytes(text.encode("utf-8"))


def webp_size(path):
    data = path.read_bytes()
    if data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise ValueError(f"Expected WebP illustration at {path}")
    offset = 12
    while offset + 8 <= len(data):
        kind = data[offset:offset + 4]
        length = int.from_bytes(data[offset + 4:offset + 8], "little")
        pos = offset + 8
        if kind == b"VP8X":
            return tuple(1 + int.from_bytes(data[i:i + 3], "little") for i in (pos + 4, pos + 7))
        if kind == b"VP8 ":
            return tuple(i & 16383 for i in struct.unpack_from("<HH", data, pos + 6))
        if kind == b"VP8L":
            bits = int.from_bytes(data[pos + 1:pos + 5], "little")
            return 1 + (bits & 16383), 1 + ((bits >> 14) & 16383)
        offset = pos + length + (length % 2)
    raise ValueError(f"No WebP dimensions at {path}")


def attribute(tag, name):
    match = re.search(r'\s' + re.escape(name) + r'="([^"]*)"', tag, re.I)
    return html.unescape(match.group(1)) if match else ""


def attr(tag, name, value):
    escaped = html.escape(str(value), quote=True)
    return re.sub(r'(\s' + re.escape(name) + r'=)"[^"]*"', lambda m: m[1] + '"' + escaped + '"', tag, flags=re.I)


def trailer_inner(lang, width, height):
    w = COPY[lang]
    local = "/" if lang == "en" else f"/{lang}/"
    return (
        f'<a class="official-trailer-poster" href="{GAME_PAGE}" target="_blank" rel="noopener noreferrer">'
        f'<img src="{PREFIX}observation.webp" width="{width}" height="{height}" alt="{DESCRIPTIONS[lang][-1]}" loading="lazy"/></a>'
        f'<div class="official-trailer-copy"><h2>{w[8]}</h2>'
        f'<p>{w[7]} · Nintendo</p><a href="{GAME_PAGE}" target="_blank" rel="noopener noreferrer">{w[9]} ↗</a>'
        f'<a class="official-trailer-analysis" href="{local}trailer-analysis/">{w[10]} ↗</a></div>'
    )


def captured(pattern, source):
    match = re.search(pattern, source, re.S)
    return html.unescape(TEXT_ELEMENT.sub("", match[1])).strip() if match else ""


def replacement_table(root):
    """Read the localized sentences from production so all five client dictionaries match SSR."""
    table = {}
    patterns = (
        r'<section class="atlas-navi".*?<p>(.*?)</p>',
        r'<section class="atlas-navi".*?<nav aria-label="([^"]*)"',
        r'<label class="atlas-rift-control"[^>]*>\s*(?:<span>)?([^<]+)',
        r'<label class="atlas-rift-control".*?<input[^>]*aria-label="([^"]*)"',
        r'<svg class="atlas-triforce-fallback"[^>]*aria-label="([^"]*)"',
        r'<a class="atlas-triforce-source"[^>]*>(.*?)</a>',
    )
    for lang, words in COPY.items():
        base = root / ("" if lang == "en" else lang)
        page = base / "index.html"
        source = page.read_text(encoding="utf-8")
        for index, pattern in enumerate(patterns):
            old = captured(pattern, source)
            if old:
                table[old] = words[index]
        shelf_credit = captured(r'<p class="atlas-shelf-credit"><a[^>]*>(.*?)</a>',source)
        table[shelf_credit] = table[html.escape(shelf_credit)] = SHELF_CREDIT[lang]
        comparison = (base / "then-and-now/index.html").read_text(encoding="utf-8")
        link = captured(r'<a class="source-panel"[^>]*>(.*?)</a>',comparison)
        table[link] = table[html.escape(link)] = COMPARISON_LINK[lang]
        guide = root / ("" if lang == "en" else lang) / "sources/index.html"
        source = guide.read_text(encoding="utf-8")
        for old_url, i in ((RETIRED[0]+"sources.json",11),(RETIRED[1]+"sources.json",12),("/assets/models/triforce-bevel.provenance.json",4)):
            name = captured(r'<a[^>]*href="'+re.escape(old_url)+r'"[^>]*>(.*?)</a>',source)
            if name:
                table[name] = words[i]
        feature = (root / ("" if lang == "en" else lang) / "ocarina-of-time-remake/index.html").read_text(encoding="utf-8")
        panel = re.search(r'<figure class="remake-plates".*?</figure>', feature, re.S)
        if panel:
            for tag in IMAGE_TAG.findall(panel[0]):
                if tag.startswith("<img") and attribute(tag,"alt"):
                    index = 6 if attribute(tag,"src")==OLD_POSTER else 1
                    table[attribute(tag,"alt")] = DESCRIPTIONS[lang][index]
        game = (root / ("" if lang == "en" else lang) / "series/a-link-to-the-past/index.html").read_text(encoding="utf-8")
        stamp = captured(r'<a class="alttp-official-art".*?<small>(.*?)</small>',game)
        if stamp:
            table[stamp] = words[6]
        for route in ("trailer-analysis","sources"):
            doc = (root/("" if lang=="en" else lang)/route/"index.html").read_text(encoding="utf-8")
            for match in re.finditer(r'<a\b[^>]*href="'+re.escape(TRAILER_VIDEO)+r'"[^>]*>([^<>]+)</a>',doc):
                table[html.unescape(match[1])] = words[9]
    return table


def media_map(slugs, slot):
    paths = {}
    for slug in slugs:
        # Distinct fragments preserve the app's per-game lookup while sharing six downloaded images.
        url = PREFIX + f"catalogue-{slot[slug]}.webp#{slug}"
        paths[RETIRED[0]+slug+".webp"] = url
        for size in (80,128,320):
            paths[RETIRED[0]+f"previews/{slug}-{size}.webp"] = url
    for name, symbol in ICON_MAP.items():
        for variant in ("","-104","-162"):
            for ext in ("png","webp"):
                paths[RETIRED[1]+name+variant+"."+ext] = PREFIX+symbol+".svg"
    paths.update({
        OLD_POSTER: PREFIX+"observation.webp", RETIRED[0]+"nintendo-trailer.jpg": PREFIX+"observation.webp",
        RETIRED[0]+"sources.json": CREDITS, RETIRED[0]+"nintendo-trailer-featured.source.json": CREDITS,
        RETIRED[0]+"trailer-source.json": CREDITS, RETIRED[0]+"previews/provenance.json": CREDITS,
        RETIRED[1]+"sources.json": CREDITS, RETIRED[1]+"CREDITS.md": CREDITS,
        "/assets/models/triforce-bevel.provenance.json": CREDITS,
    })
    return paths


def replace_many(source, table, expression):
    return expression.sub(lambda m: table[m[0]], source)


def alternatives(table):
    return re.compile("|".join(map(re.escape, sorted(table, key=len, reverse=True))))


def resize_srcset(value, widths):
    candidates = value.split(",")
    if len(candidates) < 2:
        return value
    urls = [part.strip().split()[0] for part in candidates if part.strip()]
    if urls and len(set(urls)) == 1 and urls[0].split("#")[0] in widths:
        return urls[0] + " " + str(widths[urls[0].split("#")[0]][0]) + "w"
    return value


def js_object_end(source, start):
    """Locate the end of esbuild's object literal, including nested records and strings."""
    depth = 0
    quote = ""
    escaped = False
    for i in range(start, len(source)):
        c = source[i]
        if quote:
            if escaped:
                escaped = False
            elif c == "\\":
                escaped = True
            elif c == quote:
                quote = ""
        elif c in "`'\"":
            quote = c
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i + 1
    raise ValueError("Incomplete catalogue object in a JavaScript bundle")


def replace_objects(source, pattern, replacement):
    for match in reversed(list(re.finditer(pattern, source))):
        start = match.start()
        end = js_object_end(source, start)
        source = source[:start] + replacement + source[end:]
    return source


def clean_schema(match):
    data = json.loads(match["data"])
    if isinstance(data,dict) and data.get("@type") == "VideoObject":
        return ""
    if isinstance(data,dict) and isinstance(data.get("@graph"),list):
        data["@graph"] = [entry for entry in data["@graph"] if entry.get("@type") != "VideoObject"]
        return match["open"] + compact(data).replace("</", "<\\/") + "</script>"
    return match[0]


def localized_sections(source, lang, width, height):
    words = COPY[lang]
    section = f'<section class="official-trailer" aria-label="{words[7]}">' + trailer_inner(lang,width,height) + '</section>'
    source = TRAILER.sub(lambda _:section, source)
    if '"VideoObject"' in source:
        pattern = r'(?P<open><script\b[^>]*type="application/ld\+json"[^>]*>)(?P<data>[^<]*?"VideoObject"[^<]*)</script>'
        source = re.sub(pattern, clean_schema, source)
    # All publisher references remain available outside the on-site observation.
    def figure(match):
        fig = match[0]
        if "official-thumbnails/" not in fig:
            return fig
        fig = fig.replace(HISTORY,CREDITS)
        fig = re.sub(r'(<figcaption[^>]*>.*?<a[^>]*\shref=)"[^"]*"',r'\1"'+CREDITS+'"',fig,flags=re.S)
        fig = re.sub(r'(<span>)\d+(?:<!-- -->)? × (?:<!-- -->)?\d+(</span>)',r'\g<1>1200<!-- --> × <!-- -->800\2',fig)
        return fig.replace("© Nintendo", "Hyrule Atlas")
    source = re.sub(r'<figure\b[^>]*class="[^"]*(?:atlas-lead-art--official|remake-plates|series-hero-art)[^"]*"[^>]*>.*?</figure>',figure,source,flags=re.S)
    def local_credit(match):
        return match[0].replace("<span>"+match["attribution"]+"</span>","<span>Hyrule Atlas</span>")
    source = re.sub(r'<li><a\b[^>]*href="/assets/(?:official-thumbnails/sources\.json|game-icons/sources\.json|models/triforce-bevel\.provenance\.json)"[^>]*>[^<]*</a><span>(?P<attribution>[^<]+)</span></li>',local_credit,source)
    def edition_stamp(match):
        text = match[0].replace(HISTORY,CREDITS)
        return re.sub(r'<span>([^<]*)</span>',lambda _:f'<span>{words[6]}</span>',text)
    source = re.sub(r'<a class="alttp-official-art"[^>]*>.*?</a>',edition_stamp,source,flags=re.S)
    return source


class EditorialExport:
    def __init__(self, root, source_assets):
        self.root = root
        self.assets = root / "assets"
        self.public = self.assets / "editorial"
        self.source_assets = source_assets
        original = json.loads((self.assets/"official-thumbnails/sources.json").read_bytes())["assets"]
        # Give the six games on the home shelf six different photographs.
        shelf = ["a-link-to-the-past","ocarina-of-time","majoras-mask","breath-of-the-wild","tears-of-the-kingdom","echoes-of-wisdom"]
        slugs = shelf + [a["slug"] for a in original if a["slug"] not in shelf]
        self.slots = {slug: i % 6 + 1 for i, slug in enumerate(slugs)}
        self.paths = media_map(slugs, self.slots)
        self.paths_regex = alternatives(self.paths)
        self.words = replacement_table(root)
        self.social_alts = {}
        for lang, words in COPY.items():
            base = root / ("" if lang == "en" else lang)
            page = (base / "ocarina-of-time-switch-2/index.html").read_text(encoding="utf-8")
            for tag in IMAGE_TAG.findall(page):
                if attribute(tag,"property") == "og:image:alt":
                    self.social_alts[attribute(tag,"content")] = DESCRIPTIONS[lang][-1]
        self.words.update(self.social_alts)
        self.words.pop("", None)
        self.words_regex = alternatives(self.words)
        self.sizes = {}
        for stem in [*(f"catalogue-{i}" for i in range(1,7)), "observation"]:
            self.sizes[PREFIX+stem+".webp"] = webp_size(source_assets / (stem+".webp"))
        self.registry = {"publisher":"Hyrule Atlas", "assets":[]}
        for entry in original:
            src = self.paths[entry["src"]]
            width, height = self.sizes[src.split("#")[0]]
            self.registry["assets"].append({
                "slug":entry["slug"], "title":entry["title"], "src":src, "width":width, "height":height,
                "alt":DESCRIPTIONS["en"][self.slots[entry["slug"]]-1], "credit":"Hyrule Atlas", "sourcePage":CREDITS, "kind":"editorial",
            })
        self.poster_width, self.poster_height = self.sizes[PREFIX+"observation.webp"]
        self.trailers = {lang:trailer_inner(lang,self.poster_width,self.poster_height) for lang in COPY}

    def paths_in(self, source):
        return replace_many(source,self.paths,self.paths_regex)

    def copy_in(self, source):
        # Only an entire DOM string, JS literal, or localized dictionary value.
        # A factual paragraph mentioning Nintendo artwork keeps its original text.
        return self.words_regex.sub(lambda m:self.words[m[0]] if
            (m.start()==0 or source[m.start()-1] in "\x60\"'>") and
            (m.end()==len(source) or source[m.end()] in "\x60\"'<") else m[0],source)

    def install(self):
        self.public.mkdir(exist_ok=True)
        for url in self.sizes:
            name = url.rsplit("/",1)[-1]
            shutil.copyfile(self.source_assets/name,self.public/name)
        for name, drawing in ICONS.items():
            colour = "#e5bd72" if name == "compass" else "#ceb980"
            save(self.public/(name+".svg"),f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{colour}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">{drawing}</svg>')
        public_registry = dict(self.registry)
        public_registry["files"] = [{"src":url,"width":size[0],"height":size[1],
                               "sha256":sha256((self.public/url.rsplit('/',1)[1]).read_bytes()).hexdigest()}
                              for url,size in self.sizes.items()]
        public_registry["symbols"] = [PREFIX+name+".svg" for name in ICONS]
        provenance = self.source_assets/"provenance.json"
        if provenance.is_file():
            evidence = json.loads(provenance.read_bytes())
            public_registry["method"] = evidence["method"]
            public_registry["placement"] = evidence["placement"]
            for item in evidence["assets"]:
                recorded = next(f for f in public_registry["files"] if f["src"] == PREFIX+item["file"])
                if item["final_sha256"] != recorded["sha256"]:
                    raise ValueError("Illustration does not match its provenance: "+item["file"])
                recorded["masterSha256"] = item["source_sha256"]
        save(self.public/"sources.json",compact(public_registry)+"\n")
        shutil.copyfile(UI/"compass-scene.js",self.public/"compass-scene.js")

    def html(self, source, lang):
        words = COPY[lang]
        source = localized_sections(source,lang,self.poster_width,self.poster_height)
        if 'class="ed-comparison" id="adult-link"' in source:
            # Each study already links to the source from its discussion.
            source = SOURCE_PANEL.sub("",source)
            source = re.sub(r'<p class="ed-smallprint">[^<]*</p>',"",source)
        og_old = re.search(r'<meta[^>]*(?:property|name)="(?:og|twitter):image"[^>]*content="[^"]*/assets/official-thumbnails/[^"]+"',source)

        def update_tag(match):
            tag = match[0]
            if og_old and tag.startswith("<meta"):
                field = attribute(tag,"property") or attribute(tag,"name")
                value = {"og:image:alt":DESCRIPTIONS[lang][-1],"twitter:image:alt":DESCRIPTIONS[lang][-1],"og:image:width":self.poster_width,
                         "og:image:height":self.poster_height,"og:image:type":"image/webp"}.get(field)
                if value is not None:
                    tag = attr(tag,"content",value)
            if not any(path in tag for path in RETIRED):
                return tag
            old = attribute(tag, "src")
            if old in self.paths and old.startswith(RETIRED[0]):
                new = self.paths[old].split("#")[0]
                if new in self.sizes:
                    width,height = self.sizes[new]
                    tag = attr(attr(tag,"width",width),"height",height)
                    if attribute(tag,"alt"):
                        index = 6 if new.endswith("observation.webp") else int(new[-6])-1
                        tag = attr(tag,"alt",DESCRIPTIONS[lang][index])
            tag = self.paths_in(tag)
            for key in ("srcset","imagesrcset"):
                value = attribute(tag,key)
                if value:
                    tag = attr(tag,key,resize_srcset(value,self.sizes))
            return tag

        source = IMAGE_TAG.sub(update_tag,source)
        source = self.paths_in(source)
        source = self.copy_in(source)
        return self.common_copy(source).replace(OLD_ROSE,ROSE_PATH).replace(TRAILER_VIDEO,GAME_PAGE)

    def common_copy(self, source):
        # A comparison's observations remain the editor's text. Attribution in the
        # actual illustrations, not in historical quotations, follows their producer.
        source = source.replace(" · © Nintendo`"," · Hyrule Atlas`")
        source = source.replace(' · © Nintendo</a>', ' · Hyrule Atlas</a>')
        return source

    def javascript(self, path, source):
        if path.name.startswith("then-and-now-"):
            source = re.sub(r'\w+\(`a`,\{className:`source-panel`,href:\w+,target:`_blank`,rel:`noopener noreferrer`,children:`[^`]*`\}\),',"",source)
            source = re.sub(r'\w+\(`p`,\{className:`ed-smallprint`,children:`Artwork © Nintendo\.[^`]*`\}\),',"",source)
        if path.name.startswith("official-trailer-"):
            # Each historical Rollup chunk uses a different local alias for the JSX
            # primitive. Keep that import, and preserve the chunk's public export.
            call = re.search(r'(\w+)\([`"]img[`"],',source)
            if not call:
                raise ValueError(f"Unrecognized trailer module {path.name}")
            alias = call[1]
            imp = next((m[0] for m in re.finditer(r'import\{[^{}]+\}from"[^"]+";',source)
                        if re.search(r'(?:\{|,)(?:\w+ as )?'+alias+r'(?:,|\})',m[0])), None)
            if not imp:
                raise ValueError(f"Cannot find JSX import in {path.name}")
            labels = {l:v[7] for l,v in COPY.items()}
            return (imp+"const notes="+compact(self.trailers)+",labels="+compact(labels)+";"
                    "function feature(){const lang=location.pathname.split('/')[1];return "+alias+
                    "('section',{className:'official-trailer','aria-label':labels[lang]||labels.en,"
                    "dangerouslySetInnerHTML:{__html:notes[lang]||notes.en}})}export{feature as t};")
        registry = compact(self.registry)
        for i, description in enumerate(DESCRIPTIONS["en"][:6]):
            labels = {lang:values[i] for lang,values in DESCRIPTIONS.items()}
            registry = registry.replace('"alt":'+compact(description),'get alt(){return ('+compact(labels)+')[document.documentElement.lang.split("-")[0]]||'+compact(description)+'}')
        source = replace_objects(source,r'\{purpose:[`"]Small editorial thumbnails',registry)
        source = replace_objects(source,r'\{asset:[`"]/assets/official-thumbnails/nintendo-trailer-featured\.jpg',
                                 compact({"asset":PREFIX+"observation.webp","width":self.poster_width,
                                          "height":self.poster_height,"credit":"Hyrule Atlas","sourcePage":CREDITS}))
        # A news article may refer to a trailer. Advertise an Article and an external
        # source, never a video player that the page no longer contains.
        if "VideoObject" in source and "youtube-nocookie.com/embed" in source:
            source = replace_objects(source,r'\{"@type":[`"]VideoObject[`"]',
                                     compact({"@type":"WebPage","url":GAME_PAGE,"publisher":{"@type":"Organization","name":"Nintendo"}}))
        source = re.sub(r'(href:[`"]/assets/(?:official-thumbnails/sources\.json|game-icons/sources\.json|models/triforce-bevel\.provenance\.json)[`"],label:[`"][^`"]+[`"],note:)[`"][^`"]+[`"]',r'\1"Hyrule Atlas"',source)
        source = re.sub(r'(href:[^{}]{0,120}nintendo-trailer-featured\.source\.json[`"],target:[`"]_blank[`"],rel:[`"]noreferrer[`"],children:)[`"]© Nintendo[`"]',r'\1"Hyrule Atlas"',source)
        if "alttp-official-art" in source:
            source = re.sub(r'(className:[`"]alttp-official-art[`"],href:)[`"][^`"]+[`"]',r'\1"'+CREDITS+'"',source)
        dynamic = re.compile(r'/assets/official-thumbnails/(?:previews/)?\$\{([^{}]+)\}(?:-(?:80|128|320))?\.webp')
        slot_map = compact(self.slots)
        source = dynamic.sub(lambda m: PREFIX+"catalogue-${("+slot_map+")["+m[1]+"]}.webp#${"+m[1]+"}",source)
        source = self.paths_in(source)
        source = self.copy_in(source)
        source = source.replace(TRAILER_VIDEO,GAME_PAGE)
        source = self.common_copy(source)
        source = source.replace(OLD_ROSE,ROSE_PATH)
        # The OG provider negotiates WebP from the new asset. Keep schema and
        # both social cards consistent with the MIME type of the real response.
        source = re.sub(r'(src:[`"]'+re.escape(PREFIX+'observation.webp')+r'[`"],alt:[^}]{0,300}?type:)[`"]image/jpeg[`"]',r'\1"image/webp"',source)
        return re.sub(r'triforce-scene-[\w-]{8}\.js', "editorial/compass-scene.js", source)


def apply(root: Path, source_assets: Path | None = None):
    root = Path(root).resolve()
    if not (root/"sitemap.xml").is_file() or (root/".git").exists() or (root/"vercel.json").exists():
        raise ValueError("Expected a staged static site, not a source checkout")
    assets = root/"assets"
    if not (assets/"official-thumbnails").exists() and (assets/"editorial/sources.json").is_file():
        return
    export = EditorialExport(root,source_assets or HERE/"editorial-assets")
    export.install()
    for path in root.rglob("*.html"):
        source = path.read_bytes().decode("utf-8")
        prefix = path.relative_to(root).parts[0]
        updated = export.html(source, prefix if prefix in COPY else "en")
        if updated != source:
            save(path,updated)
    for path in assets.glob("*.js"):
        source = path.read_bytes().decode("utf-8")
        relevant = path.name.startswith("then-and-now-") or any(s in source for s in (
            *RETIRED, TRAILER_VIDEO, "VideoObject", "triforce-scene-", OLD_ROSE, "Navi lights the way", "atlas-shelf-credit"))
        if not relevant and not re.fullmatch(r'(?:en|fr|es|ja|zh)-[\w-]{8}\.js',path.name):
            continue
        updated = export.javascript(path,source)
        if updated != source:
            save(path,updated)
    social = assets/"social/sources.json"
    document = json.loads(social.read_bytes())
    document["assets"] = [item for item in document["assets"] if not item["src"].startswith(RETIRED[0])]
    document["assets"].append({"src":PREFIX+"observation.webp","kind":"Editorial illustration by Hyrule Atlas","source":CREDITS,"width":export.poster_width,"height":export.poster_height})
    save(social,json.dumps(document,ensure_ascii=False,indent=2)+"\n")
    # All file removals are confined to the staged output. The source manifests
    # and original bytes stay available in the pre-migration checkout.
    for name in ("official-thumbnails","game-icons"):
        shutil.rmtree(assets/name)
    for path in [*(assets/"models").glob("triforce-bevel.*"), *assets.glob("triforce-scene-*.js")]:
        path.unlink()
