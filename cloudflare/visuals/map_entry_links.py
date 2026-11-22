"""Connect the social landing pages' journal to the ALttP progress export."""

from pathlib import Path
import re


GUIDE_COMPLETION = "/series/a-link-to-the-past/#completion"
ENTRY_PAGES = ("map/instagram/index.html", "map/tiktok/index.html")
JOURNAL_DECLARATION = re.compile(
    r"function (?P<name>[$\w]+)\(\{progress:[$\w]+,ready:[$\w]+,"
    r"openChapter:[$\w]+,locate:[$\w]+(?=\}\)\{)"
)
MAP_ENTRY_ARGUMENT = re.compile(r"function [$\w]+\(\{mapEntry:([$\w]+)=!1\}=\{\}\)")
HASH_LINK = "href:`#completion`"
JOURNAL_LINK = HASH_LINK + ",children:`Emporter ma progression ↗`"


def apply(root: Path):
    """Keep the exported HTML and client-side journal anchor in agreement."""
    for entry in ENTRY_PAGES:
        page = root / entry
        html = page.read_bytes()
        old = b'<a href="#completion">Take my progress with me'
        if html.count(old) != 1:
            raise ValueError(f"Expected a single journal link in {entry}")
        new = old.replace(b"#completion", GUIDE_COMPLETION.encode("ascii"))
        page.write_bytes(html.replace(old, new))

    patched = 0
    for path in (root / "assets").glob("alttp-*.js"):
        source = path.read_bytes().decode("utf-8")
        map_entry = MAP_ENTRY_ARGUMENT.search(source)
        if not map_entry:
            continue
        journal = JOURNAL_DECLARATION.search(source)
        if not journal or source.count(JOURNAL_LINK) != 1:
            raise ValueError(f"Expected the ALttP map-entry journal in {path.name}")

        journal_call = re.compile(
            r"\(" + re.escape(journal["name"]) + r",\{progress:[$\w]+,ready:[$\w]+,"
            r"openChapter:[$\w]+=>[$\w]+\([$\w]+,!0\),locate:[$\w]+(?=\}\))"
        )
        source, count = journal_call.subn(
            lambda match: (
                f'{match[0]},progressHref:{map_entry[1]}?"{GUIDE_COMPLETION}":undefined'
            ),
            source,
        )
        if count != 1:
            raise ValueError(f"Expected one ALttP journal call in {path.name}")
        source = JOURNAL_DECLARATION.sub(
            lambda match: f'{match[0]},progressHref="#completion"', source, count=1
        )
        source = source.replace(JOURNAL_LINK, JOURNAL_LINK.replace(HASH_LINK, "href:progressHref", 1))
        path.write_bytes(source.encode("utf-8"))
        patched += 1
    if not patched:
        raise ValueError("No ALttP map-entry journal bundles were patched")
