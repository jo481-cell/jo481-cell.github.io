"""Link changed export bundles under fresh URLs after an editorial revision."""

from hashlib import sha256
from pathlib import Path
import re


TEXT_SUFFIXES = {".html", ".js", ".css", ".json", ".webmanifest", ".xml"}
FINGERPRINTED_BUNDLE = re.compile(r"[-_A-Za-z0-9]+-[A-Za-z0-9_-]{8,}\.(?:js|css)\Z")
BUNDLE_REFERENCE = re.compile(rb"(?<![.\w-])[-A-Za-z0-9_]+\.(?:js|css)(?![.\w-])")


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
