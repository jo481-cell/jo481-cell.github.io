"""Replace the ALttP raster maps in a built Pages export with original editorial diagrams."""
import html
import json
from pathlib import Path
import re
from string import ascii_uppercase
from functools import lru_cache


ART = Path(__file__).with_name("map-assets")
OLD = "/assets/alttp/"
NEW = "/assets/atlas-charts/"
NOTES = NEW + "provenance.json"
LEGACY_SOURCE = "https://ian-albert.com/games/legend_of_zelda_a_link_to_the_past_maps/"
FLOOR = re.compile(r"dungeon-([A-Z]\d?)-(B\d+|\d+F)\.png$")
EMBEDDED = re.compile(r"\{source:`" + re.escape(LEGACY_SOURCE) +
                      r"`,credit:`[^`]*`,permission:`[^`]*`,assets:\[.*?\](?:,previewDerivatives:\[.*?\])?\}")
FORMATS = {".html", ".css", ".js", ".json", ".xml", ".txt", ".webmanifest", ".md"}
WORLD_FILES = {"light_world-1.png":"light.svg","dark_world.png":"dark.svg",
               "light-field-2048.webp":"places.svg","light-field-960.webp":"places.svg"}
for world in ("light","dark"):
    for size in ("1024","4096","preview"):
        WORLD_FILES[f"{world}-world-{size}.webp"] = world+".svg"


def _render(name, **values):
    svg = (ART / (name+".template.svg")).read_text(encoding="utf8")
    return re.sub(r"\{\{(\w+)\}\}", lambda m:str(values[m[1]]), svg)


def _world(world, places=False):
    if world == "light":
        colors = dict(paper="#e9e3d2",fine="#c9c9b4",line="#99ab99",ink="#526d61")
    else:
        colors = dict(paper="#24343e",fine="#364951",line="#596e73",ink="#b2c2b7")
    coords=[]
    for col in range(10):
        for row in range(10):
            coords.append(f'<text x="{col*100+10}" y="{row*100+22}">{ascii_uppercase[col]}{row+1}</text>')
    pins=[]
    if places:
        # These three guide anchors are the same existing fractional coordinates used by FieldChart.
        # The background contains no game terrain. Giving the three destinations distinct marks
        # keeps the camera controls meaningful even in the standalone home illustration.
        for x,y,label,shape in [(500,455,"A",'<circle r="9"/>'),(160,470,"B",'<path d="M0-10 10 0 0 10-10 0Z"/>'),(795,845,"C",'<rect x="-8" y="-8" width="16" height="16"/>')]:
            pins.append(f'<g transform="translate({x} {y})"><circle fill="#f5ecce" stroke="#32655a" stroke-width="2" r="28"/>'
                        f'<circle fill="none" stroke="#708b72" r="39" stroke-dasharray="3 5"/><g fill="#295b50">{shape}</g>'
                        f'<text x="41" y="5" font-family="system-ui,sans-serif" font-weight="650" font-size="22" fill="#26584c">{label}</text></g>')
    return _render("world",**colors,title=("Light" if world=="light" else "Dark")+" World · Hyrule Atlas",coordinates="\n".join(coords),focus="\n".join(pins))


def _height(floor):
    return -int(floor[1:]) if floor.startswith("B") else int(floor[:-1])


def _floor_svg(name, floors, selected):
    levels = sorted(floors, key=_height,reverse=True)
    row_height = min(62,336/len(levels))
    top = 240 - (len(levels)-1)*row_height/2
    stack = []
    for i,level in enumerate(levels):
        y=round(top+i*row_height,1)
        active=level==selected
        if active:
            stack.append(f'<rect x="52" y="{y-row_height*.42:g}" width="344" height="{row_height*.84:g}" rx="5" fill="#25483f"/>')
        color = "#efd393" if active else "#abc0ae"
        stack.append(f'<path d="M94 {y}H275" stroke="{color}" stroke-width="{4 if active else 1.5}"/>'
                     f'<circle cx="94" cy="{y}" r="{7 if active else 4}" fill="{color}"/>'
                     f'<text x="297" y="{y+9:g}" font-size="29" fill="{color}">{level}</text>')
    return _render("floor",title=f"{name} · {selected}",selected=selected,position=levels.index(selected)+1,total=len(levels),stack="\n".join(stack))


def _image_files(manifest):
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
    result={"light.svg":_world("light"),"dark.svg":_world("dark"),"places.svg":_world("light", True)}
    for code,levels in groups.items():
        for floor in levels:
            result[f"dungeon-{code}-{floor}.svg"] = _floor_svg(code,levels,floor)
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
    diagrams=_image_files(legacy)
    existing={p.name for p in old.iterdir() if p.is_file()}
    supported=set(WORLD_FILES)|{"light-field-water.webp","sources.json","light-field-source.json"}|{n.replace(".svg",".png") for n in diagrams if n.startswith("dungeon-")}
    if existing-supported or any(p.is_dir() or p.is_symlink() for p in old.iterdir()):
        raise ValueError("Review new ALttP files before publishing: "+str(sorted(existing-supported)))
    if out.exists() or old.is_symlink() or out.is_symlink():
        raise ValueError("Unexpected chart destination or symlink")
    out.mkdir()
    rows=[]
    for name,svg in diagrams.items():
        (out/name).write_text(svg,encoding="utf8")
        w,h=(800,480) if name.startswith("dungeon-") else (1000,1000)
        rows.append({"file":name,"url":NEW+name,"width":w,"height":h})
    doc={"source":NOTES,"credit":"Hyrule Atlas","permission":"Original editorial coordinate grids and dungeon floor indexes by Hyrule Atlas.",
         "method":{"en":"Two indexed coordinate grids for the guide markers, three home landmarks and a floor selector. Level bands record the dungeon floor sequence. The diagrams use only guide facts and contain no game pixels.",
                   "fr":"Deux grilles de coordonnées accueillent les repères du guide. Trois lieux sont mis en avant sur l’accueil. Les bandes indiquent les étages de chaque donjon. Les schémas utilisent les données du guide.",
                   "es":"Dos cuadrículas de coordenadas muestran los lugares de la guía. La portada destaca tres puntos. Las bandas indican las plantas de cada mazmorra.",
                   "ja":"2つの座標グリッドに攻略地点を表示します。トップページでは3地点を紹介します。帯は各ダンジョンの階層を示します。",
                   "zh":"两个坐标网格显示攻略中的地点。首页突出三个地点。横条表示各迷宫的楼层。"},
         "assets":rows}
    (out/"provenance.json").write_text(json.dumps(doc,indent=2,ensure_ascii=False)+"\n",encoding="utf8")
    # Keep the original manifest's presentation order: it also supplies the default selected
    # floor for the one tower whose published range starts above 1F.
    lookup={r["file"]:r for r in rows}
    floor_rows=[lookup[r["file"][:-4]+".svg"] for r in legacy["assets"] if FLOOR.fullmatch(r["file"])]
    bundle=json.dumps({"source":NOTES,"credit":"Hyrule Atlas","permission":doc["permission"],"assets":floor_rows,"previewDerivatives":[]},
                      separators=(",",":"),ensure_ascii=False)
    mapping=_messages()
    mapping.update(WORLD_FILES)
    mapping.update({"-world-1024.webp":".svg","-world-4096.webp":".svg",
                    OLD+"sources.json":NOTES, OLD+"light-field-source.json":NOTES,
                    LEGACY_SOURCE:NOTES, OLD:NEW, "A Link to the Past · © Nintendo · Ian Albert":"Hyrule Atlas",
                    "-1F.png":"-1F.svg", "light-field-water.webp":"places.svg"})
    for n in floor_rows:
        mapping[n["file"][:-4]+".png"]=n["file"]
    keys=sorted(mapping,key=len,reverse=True)
    clean_floor_ext=re.compile(r'(replace\(`dungeon-\$\{\w+\}-`,``\)\.replace\(\x60)\.png(\x60)')
    size=re.compile(r'<img\b(?=[^>]*?/assets/atlas-charts/dungeon-)[^>]*>')
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
        if p.suffix==".js":
            s=clean_floor_ext.sub(r'\1.svg\2',s)
            s=re.sub(r"Le Miroir compare la géographie ; les repères restent ceux du \$\{[^}]+\}\.",
                     "Le Miroir superpose les grilles des deux mondes.",s)
        relevant=tuple(k for k in keys if k in s)
        if relevant:
            s=_pattern(relevant).sub(lambda m:mapping[m[0]],s)
        if NEW in s:
            s=re.sub(r"(/assets/atlas-charts/(?:light|dark|\$\{\w+\})\.svg) 1024w, \1 4096w",r"\1",s)
        if p.suffix==".html":
            s=size.sub(lambda m:re.sub(r'\b(width|height)="\d+"',lambda a:'width="800"' if a[1]=='width' else 'height="480"',m[0]),s)
        revised=s.encode("utf8")
        if content!=revised:
            p.write_bytes(revised)
    for p in old.iterdir():
        p.unlink()
    old.rmdir()
