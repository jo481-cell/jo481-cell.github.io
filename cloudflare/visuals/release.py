"""Version changed bundles and retain the assets needed by open tabs."""

from hashlib import sha256
import json
from pathlib import Path
import re


TEXT_SUFFIXES = {".html", ".js", ".css", ".json", ".webmanifest", ".xml"}
BUNDLE_STEM = r"[-_A-Za-z0-9]+(?:\.[-_A-Za-z0-9]+)*"
FINGERPRINTED_BUNDLE = re.compile(rf"{BUNDLE_STEM}-[A-Za-z0-9_-]{{8,}}\.(?:js|css)\Z")
BUNDLE_REFERENCE = re.compile(rf"(?<![.\w-]){BUNDLE_STEM}\.(?:js|css)(?![.\w-])".encode("ascii"))
EDITION_URL = re.compile(rf"/assets/{BUNDLE_STEM}-edition-[0-9a-f]{{16}}\.(?:js|css)")
STUDIO_STYLE = re.compile(r"studio-([0-9a-f]{16})\.css")
STUDIO_LANDMARK = re.compile(r"(?:home-landmarks-([0-9a-f]{12})\.js|(?:castle|village|lake|compass)-([0-9a-f]{12})\.webp)")
COMPANION_ASSET = re.compile(r"kuni-([0-9a-f]{16})\.webp")
FONT_LICENSE_MODULE = re.compile(r"font-licenses-[0-9a-f]{16}\.js")
BLOG_COVER = re.compile(r"blog-(?:music|reveal|secrets)-[0-9a-f]{12}\.webp")
SECTION_ART = re.compile(r"section-[a-z0-9-]+-([0-9a-f]{12})\.(?:webp|js|css)")
GAME_ART = re.compile(r"(?:game-[a-z0-9-]+|catalogue-data)-([0-9a-f]{12})\.(?:webp|js)")
CHART_URL = re.compile(
    r"/assets/atlas-charts/(?:(?:terrain|plans(?:-v\d+)?|schematics)/(?:en|fr|es|ja|zh)/"
    r"(?:light(?:-labels)?|dark(?:-labels)?|places|dungeon-[A-Z]\d?-(?:B\d+|\d+F))\.svg|"
    r"painted/(?:light|dark)-[0-9a-f]{16}\.webp)"
)
CHART_CREDIT = "Original editorial maps and walkthrough diagrams by Hyrule Atlas."
MAX_ASSET_SIZE = 25 * 1024 * 1024


def digests(root: Path):
    return {path.relative_to(root).as_posix(): sha256(path.read_bytes()).digest()
            for path in root.rglob("*") if path.is_file()}


def rekey_bundles(root: Path, before):
    bundles = {path.name: path for path in (root / "assets").iterdir()
               if path.is_file() and FINGERPRINTED_BUNDLE.fullmatch(path.name)}
    after = digests(root)
    changed = {name for name, path in bundles.items()
               if after[f"assets/{name}"] != before.get(f"assets/{name}")}
    if not changed:
        return {}

    filenames = {name.encode() for name in bundles}
    documents = {}
    parents = {}
    for path in root.rglob("*"):
        if path.is_file() and path.suffix in TEXT_SUFFIXES:
            doc = path.read_bytes()
            uses = {match[0].decode("ascii") for match in BUNDLE_REFERENCE.finditer(doc)
                    if match[0] in filenames}
            if uses:
                documents[path] = (doc, uses)
            if path.parent == root / "assets" and path.name in bundles:
                for name in uses:
                    parents.setdefault(name, set()).add(path.name)

    pending = list(changed)
    while pending:
        for parent in parents.get(pending.pop(), ()):
            if parent not in changed:
                changed.add(parent)
                pending.append(parent)

    release = sha256()
    for path, digest in sorted(after.items()):
        release.update(path.encode("utf-8") + b"\0" + digest)
    salt = release.digest()
    rekeyed = {}
    for name in sorted(changed):
        stem, extension = name.rsplit(".", 1)
        prefix = stem[:-9] if len(stem) > 9 and stem[-9] == "-" else stem
        key = sha256(name.encode() + salt).hexdigest()[:16]
        rekeyed[name] = f"{prefix}-edition-{key}.{extension}"
    if len(set(rekeyed.values())) != len(rekeyed) or set(rekeyed.values()) & bundles.keys():
        raise ValueError("Visual release bundle filenames collide")

    replacements = {old.encode(): new.encode() for old, new in rekeyed.items()}
    for path, (doc, uses) in documents.items():
        if uses & rekeyed.keys():
            path.write_bytes(BUNDLE_REFERENCE.sub(lambda match: replacements.get(match[0], match[0]), doc))
    for old, new in rekeyed.items():
        bundles[old].rename(root / "assets" / new)
    return rekeyed


def _require_ordinary_path(path: Path):
    for part in (*reversed(path.parents), path):
        if part.is_symlink() or part.is_junction():
            raise ValueError(f"Previous Pages assets require ordinary paths: {part}")


def _read_asset(path: Path):
    _require_ordinary_path(path)
    if not path.is_file() or path.stat().st_size > MAX_ASSET_SIZE:
        raise ValueError(f"Invalid previous Pages asset: {path}")
    return path.read_bytes()


def retain_previous_assets(root: Path, previous: Path, *, retain_dotted=False) -> tuple[str, ...]:
    """Copy the public edition graph and original chart files from a trusted Pages build."""
    root, previous = root.absolute(), previous.absolute()
    _require_ordinary_path(previous)
    assets = previous / "assets"
    _require_ordinary_path(assets)
    if not assets.is_dir() or not (previous / "_routes.json").is_file():
        raise ValueError(f"Expected a previous Pages distribution: {previous}")

    redirects = _read_asset(previous / "_redirects").decode("utf-8")
    paths = set()
    for line in redirects.splitlines():
        fields = line.split()
        if len(fields) == 3 and fields[2] == "302" and EDITION_URL.fullmatch(fields[1]):
            paths.add(fields[1][1:])
    if not paths:
        raise ValueError(f"Previous Pages distribution is missing edition redirects: {previous}")
    for path in assets.iterdir():
        if "." not in path.stem:
            continue
        url = f"/assets/{path.name}"
        # A retained raw alias takes the place of a redirect, so that rule
        # cannot identify the dotted edition when we build the next release.
        if EDITION_URL.fullmatch(url) or (retain_dotted and FINGERPRINTED_BUNDLE.fullmatch(path.name)):
            paths.add(url[1:])

    studio = assets / "studio"
    _require_ordinary_path(studio)
    for path in studio.glob("*"):
        if STUDIO_STYLE.fullmatch(path.name) or STUDIO_LANDMARK.fullmatch(path.name):
            paths.add(path.relative_to(previous).as_posix())

    fonts = assets / "fonts"
    _require_ordinary_path(fonts)
    for path in fonts.glob("font-licenses-*.js"):
        if FONT_LICENSE_MODULE.fullmatch(path.name):
            paths.add(path.relative_to(previous).as_posix())

    editorial = assets / "editorial"
    _require_ordinary_path(editorial)
    for path in editorial.iterdir():
        if any(pattern.fullmatch(path.name) for pattern in (BLOG_COVER, SECTION_ART, GAME_ART)):
            paths.add(path.relative_to(previous).as_posix())

    provenance = json.loads(_read_asset(previous / "assets/atlas-charts/provenance.json"))
    if provenance["credit"] != "Hyrule Atlas" or provenance["permission"] != CHART_CREDIT:
        raise ValueError(f"Expected original Hyrule Atlas charts in {previous}")
    for chart in provenance["assets"]:
        if CHART_URL.fullmatch(chart["url"]):
            paths.add(chart["url"][1:])
    for chart in provenance.get("painted_relief", {}).get("worlds", {}).values():
        if CHART_URL.fullmatch(chart["url"]):
            paths.add(chart["url"][1:])

    for path in (previous / "assets/atlas-charts").glob("kuni-*.webp"):
        if COMPANION_ASSET.fullmatch(path.name):
            paths.add(path.relative_to(previous).as_posix())

    copied = []
    for relative in sorted(paths):
        data = _read_asset(previous / relative)
        digest = sha256(data).hexdigest()
        name = Path(relative).name
        fingerprint = next((match for pattern in (STUDIO_STYLE, STUDIO_LANDMARK, COMPANION_ASSET, SECTION_ART, GAME_ART)
                            if (match := pattern.fullmatch(name))), None)
        if fingerprint and not digest.startswith(next(group for group in fingerprint.groups() if group)):
            raise ValueError(f"Previous Pages asset fingerprint differs: {relative}")
        dest = root / relative
        _require_ordinary_path(dest)
        if dest.exists():
            if sha256(_read_asset(dest)).hexdigest() != digest:
                raise ValueError(f"Previous Pages asset conflicts with the new build: {relative}")
            continue
        dest.parent.mkdir(exist_ok=True, parents=True)
        dest.write_bytes(data)
        copied.append(relative)
    return tuple(copied)
