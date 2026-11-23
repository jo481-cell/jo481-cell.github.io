"""Prepare the Cloudflare Pages static directory from a Hyrule Atlas production checkout."""
import argparse
import itertools
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlsplit
from xml.etree.ElementTree import fromstring
from visuals import credit_links, editorial, identity, kuni, map_entry_links, maps, release, share_images, studio


HERE = Path(__file__).resolve().parent
PAGES = HERE / "pages"
PUBLIC_ROOT_FILES = {"404.html", "feed.xml", "robots.txt", "site.webmanifest", "sitemap.xml"}
ASSET_CACHE = re.compile(r"[a-zA-Z0-9_-]+-[a-zA-Z0-9_-]{8,}\.(?:js|css)")
ROUTE_RETRY = re.compile(rb"onClick:\(\)=>\{\w+\.invalidate\(\),\w+\(\)\}(?=,type:`button`,children:`Try again`)")
ADSENSE_PUBLISHER_ID = re.compile(r"ca-pub-[0-9]{16}")
ADSENSE_META_NAME = b"google-adsense-account"
PRIVATE_ROOTS = {"api", "cloudflare", "functions", "node_modules", "workflows", "test", "tests"}
ASSET_TYPES = {
    ".avif", ".bin", ".css", ".gif", ".glb", ".gltf", ".ico", ".jpeg", ".jpg", ".js",
    ".json", ".m4a", ".md", ".mp3", ".mp4", ".ogg", ".otf", ".pdf", ".png", ".svg",
    ".ttf", ".txt", ".wasm", ".wav", ".webm", ".webp", ".woff", ".woff2",
}


def default_source():
    # Support both the migration branch and an independent checkout staged
    # next to a standalone migration toolkit.
    for candidate in (HERE.parent, HERE.parent / "production"):
        if (candidate / "vercel.json").is_file() and (candidate / "sitemap.xml").is_file():
            return candidate
    raise ValueError("Specify the path to the published Hyrule Atlas Git checkout")


def public_routes(sitemap):
    paths = {"index.html", "community-admin/index.html", "map/instagram/index.html", "map/tiktok/index.html"}
    for prefix in ("", "fr/", "es/", "ja/", "zh/"):
        for route in ("forum", "fan-art", "search"):
            paths.add(f"{prefix}{route}/index.html")
    for location in fromstring(sitemap).findall("{*}url/{*}loc"):
        url = urlsplit(location.text)
        path = url.path.strip("/")
        parts = path.split("/") if path else []
        if (url.scheme, url.netloc) != ("https", "hyruleatlas.com") or url.query or url.fragment or any(
            part in PRIVATE_ROOTS or part.startswith(".") or not part for part in parts
        ):
            raise ValueError(f"Unexpected sitemap location: {location.text}")
        paths.add(f"{path}/index.html" if path else "index.html")
    return paths


def expand_redirects(config):
    rules = {}
    token = re.compile(r":(\w+)\(([a-z0-9|-]+)\)")
    for row in config["redirects"]:
        source, target = row["source"], row["destination"]
        variables = token.findall(source)
        if ":" in token.sub("", source) or not variables:
            raise ValueError(f"Unsupported redirect source: {source}")
        for group in itertools.product(*(values.split("|") for _, values in variables)):
            pairs = dict(zip((name for name, _ in variables), group))
            src = token.sub(lambda match: pairs[match[1]], source)
            dst = re.sub(r":(\w+)", lambda match: pairs[match[1]], target)
            value = f"{dst} {308 if row['permanent'] else 307}"
            if src in rules and rules[src] != value:
                raise ValueError(f"Conflicting redirect: {src}")
            rules[src] = value
    return rules


def immutable_patterns(assets):
    # Pages supports one splat per header rule. Split a filename family where an
    # unhashed, dotted or nested resource would otherwise get immutable caching.
    rules = []
    for ext in (".js", ".css"):
        wanted = {name for name in assets if name.endswith(ext) and ASSET_CACHE.fullmatch(name)}
        others = {name for name in assets if name.endswith(ext) and name not in wanted}

        def cover(prefix, names):
            if not any(other.startswith(prefix) for other in others):
                rules.append(prefix + "*" + ext)
                return
            for char in sorted({name[len(prefix)] for name in names}):
                extended = prefix + char
                cover(extended, [name for name in names if name.startswith(extended)])

        for prefix in sorted({name.split("-", 1)[0] + "-" for name in wanted}):
            cover(prefix, [name for name in wanted if name.startswith(prefix)])
    return rules


def make_headers(config, assets):
    security, cache, robots = config["headers"]
    common = security["headers"]
    cache_hdr = cache["headers"][0]
    robots_hdr = robots["headers"][0]
    assert cache_hdr["key"] == "Cache-Control" and robots_hdr["key"] == "X-Robots-Tag"
    # Local HTTP, stable Pages aliases and branch deployments are inert. Only
    # the canonical production hostname enables telemetry and external embeds.
    production_policy = next(e["value"] for e in common if e["key"] == "Content-Security-Policy")
    production_policy = production_policy.replace(" https://www.youtube.com", "").replace(
        "https://www.youtube-nocookie.com ", ""
    )
    policy = ("default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
              "img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; frame-src 'none'; "
              "frame-ancestors 'self'; base-uri 'self'; form-action 'self'")
    shared = [f"  {e['key']}: {e['value']}" for e in common if e["key"] != "Content-Security-Policy"]
    blocks = ["/*\n" + "\n".join([*shared, f"  Content-Security-Policy: {policy}", f"  X-Robots-Tag: {robots_hdr['value']}"]),
              "https://hyruleatlas.com/*\n  ! X-Robots-Tag\n  ! Content-Security-Policy\n"
              f"  Content-Security-Policy: {production_policy}"]
    for pattern in immutable_patterns(assets):
        blocks.append(f"/assets/{pattern}\n  {cache_hdr['key']}: {cache_hdr['value']}")
    if len(blocks) > 100:
        raise ValueError("Cloudflare Pages accepts at most 100 _headers rules")
    return "\n\n".join(blocks) + "\n", common


def with_adsense_verification(data, publisher_id):
    if publisher_id is None:
        return data
    if ADSENSE_META_NAME in data.lower() or data.count(b"</head>") != 1:
        raise ValueError("Expected one <head> without an AdSense verification tag in index.html")
    tag = f'<meta name="google-adsense-account" content="{publisher_id}">'.encode("ascii")
    return data.replace(b"</head>", tag + b"</head>", 1)


def fix_route_retry(root):
    """Retry in a new document so failed imports are no longer cached in memory."""
    count = 0
    for bundle in (root / "assets").glob("index-*.js"):
        updated, replacements = ROUTE_RETRY.subn(b"onClick:()=>window.location.reload()", bundle.read_bytes())
        if replacements:
            bundle.write_bytes(updated)
            count += replacements
    if not count:
        raise ValueError("Could not find the archive route error retry handler")


def build(source, adsense_publisher_id=None, adsense_ads_txt=False, retain_from=()):
    if adsense_publisher_id is not None and (
        not ADSENSE_PUBLISHER_ID.fullmatch(adsense_publisher_id)
        or adsense_publisher_id == "ca-pub-0000000000000000"
    ):
        raise ValueError("Use the AdSense publisher ID in the form ca-pub- followed by 16 digits")
    if adsense_ads_txt and not adsense_publisher_id:
        raise ValueError("An AdSense publisher ID is required to generate ads.txt")
    git = ["git", "-C", str(source)]
    commit = subprocess.check_output([*git, "rev-parse", "HEAD"]).decode().strip()
    config = json.loads(subprocess.check_output([*git, "show", f"{commit}:vercel.json"]))
    pages = public_routes(subprocess.check_output([*git, "show", f"{commit}:sitemap.xml"]))
    entries = subprocess.check_output([*git, "ls-tree", "-rz", commit]).split(b"\0")
    public = {}
    for entry in filter(None, entries):
        meta, raw_path = entry.split(b"\t", 1)
        mode, kind, oid = meta.split()
        path = raw_path.decode()
        if path.startswith("assets/"):
            if any(s.startswith(".") or s in PRIVATE_ROOTS for s in path.split("/")) or Path(path).suffix.lower() not in ASSET_TYPES:
                raise ValueError(f"Unrecognized asset type: {path}. Review it before including it.")
        elif path not in PUBLIC_ROOT_FILES and path not in pages:
            # A newly exported non-indexable route needs an explicit entry;
            # never publish migration fixtures, configuration or arbitrary HTML.
            root = path.split("/", 1)[0]
            if path.endswith("/index.html") and root not in PRIVATE_ROOTS and not root.startswith("."):
                raise ValueError(f"Unlisted HTML page: {path}. Verify the export or explicitly allow the public route.")
            continue
        if kind != b"blob" or mode not in (b"100644", b"100755") or any(component in ("", ".", "..") for component in path.split("/")):
            raise ValueError(f"Invalid public Git entry: {path}")
        public[path] = oid
    missing = (PUBLIC_ROOT_FILES | pages) - public.keys()
    if missing:
        raise ValueError(f"Public files missing from the Git tree: {sorted(missing)}")
    redirects = expand_redirects(config)
    dist = PAGES / "dist"
    tmp = Path(tempfile.mkdtemp(prefix=".build-", dir=PAGES))
    try:
        # Read actual Git blobs: on Windows core.autocrlf can silently rewrite
        # JavaScript/HTML when copying from a checkout, breaking integrity hashes.
        with subprocess.Popen([*git, "cat-file", "--batch"], stdin=subprocess.PIPE, stdout=subprocess.PIPE) as blobs:
            try:
                for path, oid in public.items():
                    blobs.stdin.write(oid + b"\n")
                    blobs.stdin.flush()
                    key, kind, raw_size = blobs.stdout.readline().split()
                    size = int(raw_size)
                    if key != oid or kind != b"blob" or size > 25 * 1024 * 1024:
                        raise ValueError(f"Invalid Pages asset: {path}")
                    data = blobs.stdout.read(size)
                    if len(data) != size or blobs.stdout.read(1) != b"\n":
                        raise ValueError(f"Incomplete Git blob: {path}")
                    if path.endswith(".html") and len(re.findall(rb'<script\b[^>]*src="https://static\.cloudflareinsights\.com/beacon\.min\.js"[^>]*>', data)) != 1:
                        raise ValueError(f"Unexpected number of Web Analytics tags in {path}")
                    destination = tmp / path
                    destination.parent.mkdir(exist_ok=True, parents=True)
                    destination.write_bytes(data)
            finally:
                blobs.stdin.close()
        before_visuals = release.digests(tmp)
        maps.apply(tmp)
        map_entry_links.apply(tmp)
        editorial.apply(tmp)
        share_images.apply(tmp)
        identity.apply(tmp)
        studio.apply(tmp)
        kuni.apply(tmp)
        credit_links.apply(tmp)
        fix_route_retry(tmp)
        bundle_urls = release.rekey_bundles(tmp, before_visuals)
        retained = set()
        for index, snapshot in enumerate(retain_from):
            retained.update(release.retain_previous_assets(tmp, snapshot, retain_dotted=index == 0))
        for old, new in bundle_urls.items():
            if f"assets/{old}" in retained:
                continue
            # Original export aliases point to the new modules. Previously
            # deployed edition URLs keep their exact bytes instead.
            redirects[f"/assets/{old}"] = f"/assets/{new} 302"
        assets = [(p.relative_to(tmp / "assets")).as_posix()
                  for p in (tmp / "assets").rglob("*") if p.is_file()]
        headers, security = make_headers(config, assets)
        if adsense_publisher_id:
            homepage = tmp / "index.html"
            homepage.write_bytes(with_adsense_verification(homepage.read_bytes(), adsense_publisher_id))
        if adsense_ads_txt:
            publisher = adsense_publisher_id.removeprefix("ca-")
            (tmp / "ads.txt").write_text(
                f"google.com, {publisher}, DIRECT, f08c47fec0942fa0\n", encoding="ascii", newline="\n"
            )
        (tmp / "_headers").write_text(headers, encoding="utf-8", newline="\n")
        (tmp / "_redirects").write_text("".join(f"{src} {dst}\n" for src, dst in redirects.items()), encoding="utf-8", newline="\n")
        routes = {"version": 1, "include": ["/api/community", "/api/community/", *credit_links.SECTIONS], "exclude": []}
        (tmp / "_routes.json").write_text(json.dumps(routes) + "\n", encoding="utf-8")
        if dist.exists() and (dist.is_symlink() or dist.is_junction() or not (dist / "_routes.json").is_file()):
            raise ValueError("Destination is not the generated Pages distribution")
        previous = tmp.with_name(tmp.name + "-old")
        if dist.exists():
            dist.rename(previous)
        try:
            tmp.rename(dist)
        except OSError:
            if previous.exists():
                previous.rename(dist)
            raise
        if previous.exists():
            shutil.rmtree(previous)
        (PAGES / "security-headers.json").write_text(json.dumps(security, indent=2) + "\n", encoding="utf-8")
    finally:
        if tmp.exists():
            shutil.rmtree(tmp)
    print(f"{commit}: {len(public)} published files; {sum(p.endswith('.html') for p in public)} HTML; {len(redirects)} redirects.")
    if retain_from:
        print(f"Retained {len(retained)} assets from {len(retain_from)} previous Pages exports.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", type=Path)
    parser.add_argument("--adsense-publisher-id", help="Add the AdSense verification tag to the homepage")
    parser.add_argument("--adsense-ads-txt", action="store_true", help="Also publish the Google ads.txt entry")
    parser.add_argument("--retain-from", action="append", default=[], type=Path, metavar="DIST",
                        help="Keep assets from a prior deployed Pages export (most recent first, repeatable)")
    args = parser.parse_args()
    settings_path = PAGES / "adsense.json"
    settings = json.loads(settings_path.read_text(encoding="utf-8")) if settings_path.is_file() else {}
    publisher = args.adsense_publisher_id or settings.get("publisherId")
    ads_txt = args.adsense_ads_txt or (not args.adsense_publisher_id and settings.get("adsTxt", False))
    build((args.source or default_source()).resolve(), publisher, ads_txt, args.retain_from)
