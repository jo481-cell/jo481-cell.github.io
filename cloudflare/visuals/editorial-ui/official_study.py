"""One optional Nintendo illustration for a specific passage of Then & Now."""
import hashlib
import html
import json
import re
import shutil
from pathlib import Path

SOURCE = "https://www.nintendo.com/jp/character/zelda/history/img/branch-a/04/artwork01.jpg"
PAGE = "https://www.nintendo.com/jp/character/zelda/en/history/index.html"
URL = "/assets/editorial/reference/ocarina-1998-study.webp"
SHA = "90516f94e1c7cb841ec0e9db425909df375abad81c394700ef0c0b950d1198c3"
ORIGINAL_SHA = "2ae92433aa9f6bec08087b66b2a678a5a604e925ff092250f03b3008afbb23c5"
TEXT = {
    "en": ["Link raises his sword and shield at the left of Ganondorf’s red cape.", "In this illustration for the 1998 game, the blade draws the eye up the left edge. Ganondorf’s cape fills the opposite side. Compare that balance with the forward movement described in the study.", "Nintendo image source", "The three studies link to their source material. The Nintendo illustration in Study 02 is shown as a visual reference for the discussion of composition."],
    "fr": ["Link lève son épée et son bouclier à gauche de la cape rouge de Ganondorf.", "Sur cette illustration du jeu de 1998, la lame guide le regard vers le haut à gauche. La cape de Ganondorf occupe le côté opposé. Cet équilibre permet de comparer la scène avec le mouvement vers l’avant décrit dans l’étude.", "Image originale chez Nintendo", "Les trois études renvoient à leurs sources. L’illustration Nintendo de l’étude 02 accompagne l’analyse de la composition."],
    "es": ["Link alza la espada y el escudo a la izquierda de la capa roja de Ganondorf.", "En esta ilustración del juego de 1998, la hoja guía la mirada hacia la parte superior izquierda. La capa de Ganondorf ocupa el lado opuesto. Ese equilibrio se puede comparar con el impulso hacia delante descrito en el estudio.", "Imagen original de Nintendo", "Los tres estudios enlazan a sus fuentes. La ilustración de Nintendo del estudio 02 acompaña el análisis de la composición."],
    "ja": ["ガノンドロフの赤いマントの左で、リンクが剣と盾を構えている。", "1998年発売の作品のイラストでは、剣が視線を左上へ導き、反対側をガノンドロフのマントが占めています。この左右のバランスを、本文で取り上げた前方への動きと見比べられます。", "任天堂の原図", "三つの考察には出典へのリンクがあります。考察02では構図を読み解くために任天堂のイラストを掲載しています。"],
    "zh": ["林克在加侬多夫的红色披风左侧举起剑和盾牌。", "在这幅为1998年游戏创作的插画中，剑刃将视线引向左上方，加侬多夫的披风则占据另一侧。可以把这种平衡与正文分析的向前冲势作比较。", "任天堂原图", "三项研究均附有资料来源。研究02引用一幅任天堂插画，用于分析构图。"],
}


def inner(lang):
    alt, comment, link, _ = map(html.escape,TEXT[lang])
    return (f'<img src="{URL}" width="192" height="250" alt="{alt}" loading="lazy" decoding="async" '
            'style="width:192px;max-width:100%;height:auto;display:block"/>'
            f'<figcaption style="max-width:54ch;margin-top:.65rem"><p>{comment}</p>'
            f'© Nintendo · <a href="{SOURCE}" target="_blank" rel="noopener noreferrer">{link}</a></figcaption>')


def apply(root):
    root = Path(root).resolve()
    if not (root/"assets/editorial/sources.json").is_file() or (root/".git").exists():
        raise ValueError("Run the editorial pool replacement first on a staged export")
    reference = root / URL[1:]
    if reference.is_file():
        raise ValueError("Apply the official comparison only once to each fresh build")
    original = Path(__file__).resolve().parents[3] / "assets/official-thumbnails"
    item = next(asset for asset in json.loads((original/"sources.json").read_bytes())["assets"] if asset["slug"]=="ocarina-of-time")
    if (item["sourceAsset"],item["sourceSha256"],item["sourcePage"]) != (SOURCE,ORIGINAL_SHA,PAGE):
        raise ValueError("Nintendo source has changed")
    derivative = original/"previews/ocarina-of-time-320.webp"
    if hashlib.sha256(derivative.read_bytes()).hexdigest() != SHA:
        raise ValueError("The annotated derivative no longer matches its inspected bytes")
    chunks = set()
    for lang in TEXT:
        file = root / ("" if lang=="en" else lang) / "then-and-now/index.html"
        body = file.read_bytes().decode("utf8")
        chunks.update(re.findall(r'href="(/assets/then-and-now-[\w-]{8}\.js)"',body))
        figure = '<figure class="atlas-source-study">'+inner(lang)+'</figure>'
        body, inserted = re.subn(r'(<section\b(?=[^>]*\bid="adult-link")[^>]*>.*?)(<div class="ed-comparison__notes")',
                                 lambda m:m[1]+figure+m[2],body,count=1,flags=re.S)
        if inserted!=1:
            raise ValueError(f"Missing study 02 on {file}")
        body,note = re.subn(r'(<p class="ed-smallprint">)[^<]*(</p>)',lambda m:m[1]+html.escape(TEXT[lang][3])+m[2],body,count=1)
        if note!=1:
            raise ValueError(f"Missing reference note on {file}")
        file.write_bytes(body.encode("utf8"))
    expression = lambda d:json.dumps(d,ensure_ascii=False,separators=(",",":"))
    language = '(document.documentElement.lang.split("-")[0]||"en")'
    snippets = expression({l:inner(l) for l in TEXT})
    notes = expression({l:words[3] for l,words in TEXT.items()})
    changed = 0
    for uri in sorted(chunks):
        path = root / uri[1:]
        source = path.read_bytes().decode("utf8")
        match = re.search(r'(\w+)\(`div`,\{className:`ed-comparison__notes`,children:\[(\w+)\(`p`,\{children:(\w+)\.note',source)
        if not match:
            continue
        jsx, study = match[2],match[3]
        ref = study+'.id==="adult-link"?'+jsx+'("figure",{className:"atlas-source-study",dangerouslySetInnerHTML:{__html:('+snippets+')['+language+']}}):null,'
        source = source[:match.start()] + ref + source[match.start():]
        source,count = re.subn(r'(className:`ed-smallprint`,children:)`[^`]*`',lambda m:m[1]+'('+notes+')['+language+']',source,count=1)
        if count!=1:
            raise ValueError("Missing comparison note in "+uri)
        path.write_bytes(source.encode("utf8"))
        changed+=1
    if not changed:
        raise ValueError("Missing hydrated Then & Now module")
    reference.parent.mkdir(exist_ok=True)
    shutil.copyfile(derivative,reference)
    record = {"rightsHolder":"Nintendo","license":"All rights reserved","sourcePage":PAGE,"sourceImage":SOURCE,
              "sourceSha256":ORIGINAL_SHA,"file":URL,"sha256":SHA,"width":320,"height":416,"displayWidth":192,
              "editorialUse":"One illustration beside Study 02 of Then & Now, in five translations; critical commentary on composition."}
    (reference.parent/"source.json").write_text(json.dumps(record,ensure_ascii=False,indent=2)+"\n",encoding="utf8")
