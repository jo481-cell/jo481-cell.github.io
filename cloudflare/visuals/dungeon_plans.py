"""Draw editorial circulation plans from documented SNES room and passage facts."""

from html import escape
import json
import math
import re
from unicodedata import east_asian_width
from urllib.parse import urlsplit


LANGUAGES = ("en", "fr", "es", "ja", "zh")
STOP_TYPES = ("entry", "room", "chest", "key", "boss", "exit", "switch", "junction")
PASSAGE_TYPES = ("door", "stairs", "drop", "warp", "sequence")
WORDS = {
    "en": ("Room connections", "Rooms and passages", "Direct passage", "Walkthrough order", "Floor changes", "Sources", "Door", "Stairs", "Drop", "Warp", "Guide order", "Original schematic · SNES"),
    "fr": ("Salles et passages", "Détails des salles et passages", "Passage direct", "Ordre de la soluce", "Changements d’étage", "Sources", "Porte", "Escalier", "Chute", "Téléportation", "Ordre de la soluce", "Schéma original · Super NES"),
    "es": ("Salas y conexiones", "Detalles de salas y pasos", "Paso directo", "Orden de la guía", "Cambios de planta", "Fuentes", "Puerta", "Escalera", "Caída", "Teletransporte", "Orden de la guía", "Esquema original · Super NES"),
    "ja": ("部屋と通路", "部屋と通路の詳細", "直接つながる通路", "攻略順", "階層の移動", "出典", "扉", "階段", "落下", "ワープ", "攻略順", "オリジナル略図 · SFC"),
    "zh": ("房间与通道", "房间和通道详情", "直接通道", "攻略顺序", "楼层转换", "来源", "门", "楼梯", "下落", "传送", "攻略顺序", "原创示意图 · SFC"),
}
DIRECTIONS = {
    "north": ("north", "nord", "norte", "北", "北"), "south": ("south", "sud", "sur", "南", "南"),
    "east": ("east", "est", "este", "東", "东"), "west": ("west", "ouest", "oeste", "西", "西"),
    "northeast": ("northeast", "nord-est", "noreste", "北東", "东北"), "northwest": ("northwest", "nord-ouest", "noroeste", "北西", "西北"),
    "southeast": ("southeast", "sud-est", "sureste", "南東", "东南"), "southwest": ("southwest", "sud-ouest", "suroeste", "南西", "西南"),
}
SYMBOLS = {"entry": "→", "room": "·", "chest": "◇", "key": "⌑", "boss": "✦", "exit": "↗", "switch": "□", "junction": "○"}
IDENTIFIER = re.compile(r"[a-z0-9][a-z0-9-]*\Z")


def load(art, floors, routes):
    sources, dungeons = {}, {}
    for path in sorted(art.glob("dungeon-facts*.json")):
        factbook = json.loads(path.read_text(encoding="utf-8"))
        if factbook["edition"].lower() != "snes":
            raise ValueError(f"Expected the SNES edition in {path.name}")
        for key, source in factbook["sources"].items():
            url = urlsplit(source["url"])
            if url.scheme != "https" or not url.hostname or url.username or url.password or not source["title"]:
                raise ValueError(f"Invalid plan source {key}")
            if key in sources and sources[key] != source:
                raise ValueError(f"Conflicting plan source {key}")
            sources[key] = source
        for code, dungeon in factbook["dungeons"].items():
            if code not in floors or dungeon["chapter"] != routes[code][0]:
                raise ValueError(f"Unknown dungeon: {code}")
            plan = dungeons.setdefault(code, {})
            for floor, facts in dungeon["floors"].items():
                if floor not in floors[code] or floor in plan:
                    raise ValueError(f"Unexpected or duplicate floor {code}/{floor}")
                validate_floor(code, floor, facts, floors[code], sources)
                plan[floor] = facts
    return sources, dungeons


def validate_floor(code, floor, facts, floors, sources):
    stops = facts["stops"]
    ids = {stop["id"] for stop in stops}
    if not 1 <= len(stops) <= 16 or len(ids) != len(stops) or not facts["sources"]:
        raise ValueError(f"Expected documented, unique stops for {code}/{floor}")
    if not set(facts["sources"]).issubset(sources):
        raise ValueError(f"Unknown source for {code}/{floor}")
    for stop in stops:
        if (not IDENTIFIER.fullmatch(stop["id"]) or stop["kind"] not in STOP_TYPES
                or any(not isinstance(stop["labels"].get(lang), str) or not stop["labels"][lang].strip()
                       for lang in LANGUAGES)):
            raise ValueError(f"Invalid stop {code}/{floor}/{stop['id']}")
    for link in facts["links"]:
        other = link.get("otherFloor")
        target = link.get("to")
        if (link["from"] not in ids or link["kind"] not in PASSAGE_TYPES
                or (other is None and (target not in ids or target == link["from"]))
                or (other is not None and (other not in floors or other == floor))
                or (link.get("direction") and link["direction"] not in DIRECTIONS)):
            raise ValueError(f"Invalid passage for {code}/{floor}: {link}")


def _units(value):
    return sum(2 if east_asian_width(char) in "WF" else 1 for char in value)


def _lines(value, limit):
    if _units(value) <= limit:
        return [value]
    breaks = [i for i in range(1, len(value)) if value[i].isspace() or east_asian_width(value[i-1]) in "WF"]
    cut = min(breaks or range(1, len(value)), key=lambda i: abs(_units(value[:i]) - _units(value[i:])))
    return [value[:cut].strip(), value[cut:].strip()]


def _edge(start, end, width, height):
    dx, dy = end[0] - start[0], end[1] - start[1]
    clip = min(width / 2 / abs(dx) if dx else math.inf, height / 2 / abs(dy) if dy else math.inf)
    return (start[0] + dx * clip, start[1] + dy * clip,
            end[0] - dx * clip, end[1] - dy * clip)


def _positions(stops):
    count = len(stops)
    columns = min(count, 2 if count <= 6 else 3 if count <= 12 else 4)
    rows = math.ceil(count / columns)
    cell_width = 736 / columns
    cell_height = 326 / rows
    width, height = min(286, cell_width - 38), min(73, cell_height - 23)
    points = {}
    for index, stop in enumerate(stops):
        row, column = divmod(index, columns)
        length = min(columns, count - row * columns)
        if row % 2:
            column = length - 1 - column
        x = 400 + (column - (length - 1) / 2) * cell_width
        y = 231 + (row - (rows - 1) / 2) * cell_height
        points[stop["id"]] = (x, y)
    return points, width, height


def drawing(title, floor, language, facts):
    heading, _, connected, order, *_ = WORDS[language]
    stops, links = facts["stops"], facts["links"]
    points, width, height = _positions(stops)
    arrows, bearings, cards = [], [], []
    for link in links:
        if link.get("otherFloor") is not None:
            continue
        x1, y1, x2, y2 = _edge(points[link["from"]], points[link["to"]], width, height)
        planned = link["kind"] == "sequence"
        dash = ' stroke-dasharray="4 5"' if planned else ""
        color = "#879d88" if planned else "#daca9a"
        arrows.append(f'<path d="M{x1:.1f} {y1:.1f}L{x2:.1f} {y2:.1f}" stroke="{color}"{dash} marker-end="url(#arrow)"/>')
        direction = link.get("direction")
        if direction:
            label = DIRECTIONS[direction][LANGUAGES.index(language)]
            x, y = (x1 + x2) / 2, (y1 + y2) / 2
            half = 5 + _units(label) * 3.6
            bearings.append(f'<rect x="{x-half:.1f}" y="{y-10:.1f}" width="{half*2:.1f}" height="20" rx="3" fill="#182a23"/>'
                            f'<text x="{x:.1f}" y="{y+4:.1f}" text-anchor="middle" font-size="13" fill="#f1d5a1">{escape(label)}</text>')
    for stop in stops:
        x, y = points[stop["id"]]
        label = stop["labels"][language]
        floors = sorted({link["otherFloor"] for link in links if link["from"] == stop["id"] and link.get("otherFloor")})
        fill = "#49362c" if stop["kind"] == "boss" else "#374d3f"
        lines = _lines(label, int((width - 26) / 10))
        level = ' · '.join(floors)
        left = x - width / 2
        text_x = left + 30
        cards.append(f'<g><title>{escape(label)}</title><rect x="{left:.1f}" y="{y-height/2:.1f}" width="{width:.1f}" height="{height:.1f}" rx="5" fill="{fill}" stroke="#9ba480"/>')
        cards.append(f'<text x="{left+10:.1f}" y="{y+5:.1f}" fill="#e9c989" font-size="17">{SYMBOLS[stop["kind"]]}</text>')
        for index, line in enumerate(lines):
            baseline = y + (13 if not level else 5) + (index - len(lines) + 1) * 19
            sizing = f' textLength="{width-40:.1f}" lengthAdjust="spacingAndGlyphs"' if _units(line) * 9 > width - 40 else ""
            cards.append(f'<text x="{text_x:.1f}" y="{baseline:.1f}"{sizing}>{escape(line)}</text>')
        if level:
            cards.append(f'<text x="{text_x:.1f}" y="{y+21:.1f}" fill="#e9c989" font-size="13">↕ {escape(level)}</text>')
        cards.append('</g>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 480" width="800" height="480" xml:lang="{language}">'
            f'<title>{escape(title)} · {floor} · {escape(heading)}</title>'
            f'<desc>{escape("; ".join(stop["labels"][language] for stop in stops))}</desc>'
            '<defs><pattern id="paper" width="26" height="26" patternUnits="userSpaceOnUse"><path d="M26 0H0V26" fill="none" stroke="#899574" stroke-opacity=".13"/></pattern>'
            '<marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto" markerUnits="userSpaceOnUse"><path d="M1 1l6 3-6 3" fill="none" stroke="#dac79a" stroke-width="1.3"/></marker></defs>'
            '<rect width="800" height="480" fill="#182a23"/><rect x="16" y="16" width="768" height="448" fill="url(#paper)" stroke="#52694e"/>'
            '<path d="M30 70H770M30 415H770" stroke="#52694e"/>'
            '<g font-family="system-ui,sans-serif" fill="#f2ecd9" font-size="17" font-weight="600">'
            f'<text x="37" y="50" font-size="26" fill="#e9c989">{floor}</text><text x="111" y="49" font-size="22">{escape(heading)}</text>'
            f'<g fill="none" stroke-width="2">{"".join(arrows)}</g>{"".join(cards)}{"".join(bearings)}'
            '<path d="M42 442H88" stroke="#daca9a" stroke-width="2" marker-end="url(#arrow)"/>'
            f'<text x="103" y="449" fill="#cbd6c1">{escape(connected)}</text>'
            '<path d="M414 442H460" stroke="#879d88" stroke-width="2" stroke-dasharray="4 5" marker-end="url(#arrow)"/>'
            f'<text x="475" y="449" fill="#cbd6c1">{escape(order)}</text></g></svg>')


def details(facts, sources, language, page, step_ids):
    _, title, _, _, _, credits, *words = WORDS[language]
    labels = {stop["id"]: escape(stop["labels"][language]) for stop in facts["stops"]}
    stops = []
    for stop in facts["stops"]:
        label = labels[stop["id"]]
        if stop.get("step"):
            step = stop["step"]
            if step not in step_ids:
                raise ValueError(f"Unknown guide step in {page}: {step}")
            label = f'<a href="{page}#step-{step}">{label}</a>'
        stops.append(f'<li>{label}</li>')
    links = []
    for link in facts["links"]:
        target = escape(link["otherFloor"]) if link.get("otherFloor") else labels[link["to"]]
        relation = words[PASSAGE_TYPES.index(link["kind"])]
        if link.get("direction"):
            relation += " · " + DIRECTIONS[link["direction"]][LANGUAGES.index(language)]
        links.append(f'<li>{labels[link["from"]]} <span>→ {escape(relation)} →</span> {target}</li>')
    entries = [sources[key] for key in facts["sources"]]
    refs = ' · '.join(f'<a href="{escape(entry["url"], quote=True)}">{escape(entry["title"])}</a>' for entry in entries)
    return (f'<details class="atlas-plan-notes"><summary>{escape(title)}</summary>'
            f'<ul class="atlas-plan-stops">{"".join(stops)}</ul>'
            + (f'<ul class="atlas-plan-passages">{"".join(links)}</ul>' if links else "")
            + f'<p class="atlas-plan-references">{escape(credits)} · {refs}</p></details>')
