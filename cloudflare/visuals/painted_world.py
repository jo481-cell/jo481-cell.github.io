"""Fit the approved painted relief to the existing square map layers."""

from hashlib import sha256
import html
import json
from pathlib import Path
import re


ART = Path(__file__).with_name("map-assets") / "painted"
PUBLIC = "/assets/atlas-charts/painted/"
LABELS = {
    "en": ("Map layers", "Schematic view", "Names and grid", "Painted relief is illustrative. Follow the markers for locations.",
           "The Mirror overlays both maps. Markers show the entrances in the active world."),
    "fr": ("Calques de la carte", "Vue schématique", "Noms et grille", "Le relief peint est illustratif. Suivez les repères pour trouver les lieux.",
           "Le Miroir superpose les deux cartes. Les repères indiquent les accès du monde actif."),
    "es": ("Capas del mapa", "Vista esquemática", "Nombres y cuadrícula", "El relieve pintado es ilustrativo. Sigue los marcadores para encontrar los lugares.",
           "El Espejo superpone los dos mapas. Los marcadores indican los accesos del mundo activo."),
    "ja": ("地図レイヤー", "模式図", "地名とグリッド", "地形はイメージです。場所はマーカーで確認してください。",
           "鏡は2つの地図を重ねます。マーカーは選択中の世界の入口を示します。"),
    "zh": ("地图图层", "示意图", "地名和网格", "绘制的地形仅作示意。实际地点请查看标记。",
           "镜子会叠加两张地图。标记指示当前世界的入口。"),
}
LAYER_HTML = re.compile(r'<img class="alttp-world-image(?P<mirror> alttp-mirror-image)?"[^>]*>')
LAYER_JS = re.compile(r'(?P<jsx>\w+)\(`img`,(?=\{className:`alttp-world-image(?: alttp-mirror-image)?`,)')
CONTROLS_JS = re.compile(r'(?P<jsxs>\w+)\(`div`,\{className:`alttp-map-controls`')
OPTIONS_HTML = '<div class="atlas-atmosphere">'
OPTIONS_JS = re.compile(r'(?P<tag>\w+\(`div`,\{className:`atlas-atmosphere`)')


def publish(root):
    manifest = json.loads((ART / "provenance.json").read_text(encoding="utf8"))
    destination = root / PUBLIC.strip("/")
    destination.mkdir(parents=True)
    for world in ("light", "dark"):
        row = manifest["worlds"][world]
        data = (ART / row["file"]).read_bytes()
        digest = sha256(data).hexdigest()
        if digest != row["sha256"] or row["file"] != f"{world}-{digest[:16]}.webp":
            raise ValueError(f"Unexpected painted relief fingerprint for {world}")
        (destination / row["file"]).write_bytes(data)
        row["url"] = PUBLIC + row["file"]
    return manifest


def _src(worlds, world):
    return worlds[world]["url"]


def update_html(source, language, worlds):
    heading, schematic, names, note, _ = map(html.escape, LABELS[language])

    def layer(match):
        original = match[0]
        src = re.search(r'\bsrc="([^"]+)"', original)[1]
        world = Path(src).stem
        style = ""
        classes = "atlas-world-layer"
        if match["mirror"]:
            style = " " + re.search(r'\bstyle="[^"]+"', original)[0]
            original = original.replace(style, "", 1).replace(" alttp-mirror-image", "", 1)
            classes += " alttp-mirror-image"
        return (f'<span class="{classes}"{style}>{original}'
                f'<img class="atlas-painted-relief" src="{_src(worlds, world)}" alt="" aria-hidden="true" '
                f'width="1024" height="1024" loading="lazy" draggable="false"/>'
                f'<img class="atlas-painted-labels" src="{src[:-4]}-labels.svg" alt="" aria-hidden="true" '
                f'width="1000" height="1000" loading="lazy" draggable="false"/></span>')

    source, count = LAYER_HTML.subn(layer, source)
    if not count:
        return source
    options = (f'<fieldset class="atlas-world-options"><legend>{heading}</legend>'
               f'<label><input class="atlas-schematic-toggle" type="checkbox"/>{schematic}</label>'
               f'<label class="atlas-map-names"><input class="atlas-labels-toggle" type="checkbox" checked=""/>{names}</label>'
               '</fieldset>')
    if source.count(OPTIONS_HTML) != 1:
        raise ValueError("Expected one place to insert the map layer controls")
    return source.replace(OPTIONS_HTML, options + OPTIONS_HTML, 1).replace(
        '<p class="alttp-map-caption">', f'<p class="alttp-map-caption"><span>{note} </span>', 1)


def update_js(source, worlds):
    control = CONTROLS_JS.search(source)
    if not control:
        return source
    jsxs = control["jsxs"]
    single = LAYER_JS.search(source)["jsx"]
    source, count = LAYER_JS.subn(lambda m: f'atlasWorldLayer({m["jsx"]},{jsxs},', source)
    if count != 2:
        raise ValueError(f"Expected the main and Mirror world layers, found {count}")
    source, count = OPTIONS_JS.subn(lambda m: f'atlasWorldOptions({single},{jsxs}),{m["tag"]}', source)
    if count != 1:
        raise ValueError("Expected one map settings group in the shared renderer")
    caption = re.compile(r'(className:`alttp-map-caption`,children:\[)')
    source, count = caption.subn(lambda m: m[0] + f'{single}("span",{{children:atlasWorldWords()[3]+" "}}),', source)
    if count != 1:
        raise ValueError("Expected one map caption in the shared renderer")
    mirror_caption = re.compile(r'`Le Miroir compare la géographie ; les repères restent ceux du \$\{[^}]+\}\. `')
    source, count = mirror_caption.subn('atlasWorldWords()[4]+" "', source)
    if count != 1:
        raise ValueError("Expected one Mirror caption in the shared renderer")

    images = json.dumps({world: _src(worlds, world) for world in worlds}, separators=(",", ":"))
    copy = json.dumps(LABELS, ensure_ascii=False, separators=(",", ":"))
    return f"const atlasWorldImages={images},atlasWorldCopy={copy};\n" + r'''
function atlasWorldWords() {
  return atlasWorldCopy[document.documentElement.lang.split('-')[0]] ?? atlasWorldCopy.en;
}
function atlasWorldLayer(jsx, jsxs, props) {
  const { style, src, ...image } = props;
  const world = src.endsWith('/light.svg') ? 'light' : 'dark';
  const decoration = { alt: '', 'aria-hidden': 'true', loading: 'lazy', draggable: false };
  return jsxs('span', {
    className: style ? 'atlas-world-layer alttp-mirror-image' : 'atlas-world-layer', style,
    children: [
      jsx('img', { ...image, src, className: 'alttp-world-image' }),
      jsx('img', { ...decoration, className: 'atlas-painted-relief', src: atlasWorldImages[world], width: 1024, height: 1024 }),
      jsx('img', { ...decoration, className: 'atlas-painted-labels', src: src.slice(0, -4) + '-labels.svg', width: 1000, height: 1000 }),
    ],
  });
}
function atlasWorldOptions(jsx, jsxs) {
  const [heading, schematic, names] = atlasWorldWords();
  return jsxs('fieldset', { className: 'atlas-world-options', children: [
    jsx('legend', { children: heading }),
    jsxs('label', { children: [jsx('input', { className: 'atlas-schematic-toggle', type: 'checkbox' }), schematic] }),
    jsxs('label', { className: 'atlas-map-names', children: [jsx('input', { className: 'atlas-labels-toggle', type: 'checkbox', defaultChecked: true }), names] }),
  ] });
}
''' + source
