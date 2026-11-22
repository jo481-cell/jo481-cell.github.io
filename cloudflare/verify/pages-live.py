"""Compare the Pages alias to the built static export without executing any page scripts."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import threading
import time
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

import requests


ROOT = Path(__file__).resolve().parents[2]
STABLE = "hyrule-atlas.pages.dev"
CANONICAL = "https://hyruleatlas.com"
LOCAL = threading.local()


def digest(content):
    return hashlib.sha256(content).hexdigest()


class Document(HTMLParser):
    def __init__(self):
        super().__init__()
        self.canonicals = []
        self.assets = set()

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        rel = (attrs.get("rel") or "").lower().split()
        if tag == "link" and "canonical" in rel:
            self.canonicals.append(attrs.get("href"))
        if tag == "link" and any(x in rel for x in ("stylesheet", "icon", "modulepreload")):
            asset = attrs.get("href")
        elif tag in ("script", "img"):
            asset = attrs.get("src")
        else:
            return
        if asset and asset.startswith("/assets/") and not urlsplit(asset).netloc:
            self.assets.add(urlsplit(asset).path)


def fetch(host, path, method, expected):
    if not hasattr(LOCAL, "session"):
        LOCAL.session = requests.Session()
        LOCAL.session.headers.update({"User-Agent": "HyruleAtlas-Pages-Preflight/1.0"})
        LOCAL.session.auth = lambda request: request  # never add ambient .netrc credentials
    session = LOCAL.session
    for attempt in range(4):
        # Do not preserve a cookie received in an earlier response from any host.
        session.cookies.clear()
        try:
            response = session.request(method, "https://" + host + path, timeout=(7, 18),
                                       allow_redirects=False)
        except (requests.ConnectionError, requests.Timeout):
            if attempt == 3:
                raise
            time.sleep(0.6 * 2 ** attempt)
            continue
        transient = response.status_code == 429 or 500 <= response.status_code <= 599
        if not transient or response.status_code in expected or attempt == 3:
            return response, attempt
        wait = response.headers.get("Retry-After", "")
        time.sleep(min(20, int(wait)) if wait.isdecimal() else 0.6 * 2 ** attempt)


def expectation(group, path, status, **more):
    if not path.startswith("/") or path.startswith("//"):
        raise ValueError(f"Invalid local request path: {path}")
    return dict(group=group, path=path, status=status, host=STABLE, **more)


def make_checks(dist, deployment):
    sitemap = ET.parse(dist / "sitemap.xml")
    checks = []
    indexed = set()
    for loc in sitemap.findall(".//{*}loc"):
        url = urlsplit(loc.text)
        if url.scheme != "https" or url.netloc != "hyruleatlas.com" or url.query or url.fragment:
            raise ValueError("Unexpected sitemap domain or URL")
        if url.path in indexed:
            raise ValueError("Duplicate sitemap URL " + url.path)
        indexed.add(url.path)
        checks.append(expectation("sitemap_pages", url.path, 200, canonical=loc.text,
                                  file=dist / url.path.strip("/") / "index.html"))
    for page in sorted(dist.rglob("index.html")):
        relative = page.relative_to(dist).as_posix()[:-len("index.html")]
        path = "/" + relative
        if path not in indexed:
            checks.append(expectation("other_html", path, 200, file=page))
    for line in (dist / "_redirects").read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        source, target, status = line.split()
        if not target.startswith("/") or "*" in source or ":" in source:
            raise ValueError("Unsupported redirect fixture: " + source)
        checks.append(expectation("redirects", source, int(status), location=target))
    keys = {"/robots.txt", "/sitemap.xml", "/feed.xml", "/site.webmanifest"}
    for sample in ("/", "/fr/ocarina-of-time-switch-2/map/", "/ja/zelda-64/"):
        doc = Document()
        doc.feed((dist / sample.strip("/") / "index.html").read_text(encoding="utf-8"))
        keys.update(doc.assets)
    keys.update("/" + asset.relative_to(dist).as_posix() for asset in dist.rglob("*.glb"))
    fonts = sorted(dist.rglob("*.woff2"))
    if fonts:
        keys.add("/" + fonts[0].relative_to(dist).as_posix())
    for key in sorted(keys):
        checks.append(expectation("assets", key, 200, file=dist / key[1:]))
    checks.append(expectation("not_found", "/__atlas-preflight-missing-page__/", 404,
                              file=dist / "404.html"))
    for kind, host in (("stable", STABLE), ("immutable", deployment)):
        if kind == "immutable":
            alias_check = expectation("immutable_html", "/", 200, file=dist / "index.html",
                                      canonical=CANONICAL + "/")
            alias_check["host"] = host
            checks.append(alias_check)
        for method, path, mode in (("GET", "/api/community?op=status", "status"),
                                   ("GET", "/api/community/?op=status", "status"),
                                   ("HEAD", "/api/community?op=status", "status"),
                                   ("GET", "/api/community?probe=threads", "read"),
                                   ("GET", "/api/community?probe=fan-art", "read"),
                                   ("GET", "/api/community?op=threads", "closed"),
                                   ("GET", "/api/community?op=fan-art", "closed"),
                                   ("POST", "/api/community?op=status", "closed")):
            # op=status has no write operation, even if the gateway is misconfigured.
            c = expectation("api_" + kind, path, 503, method=method, api=True,
                            mode=mode if kind == "stable" else "closed")
            c["host"] = host
            checks.append(c)
    return checks


def assess(c, expect_configured):
    method = c.get("method", "GET")
    result = {"group": c["group"], "path": c["path"], "host": c["host"], "method": method}
    mode = c.get("mode")
    expected = {c["status"]}
    if expect_configured and mode in ("status", "read"):
        expected = {200 if mode == "status" else 204}
    errors = []
    try:
        response, retries = fetch(c["host"], c["path"], method, expected)
        result.update(status=response.status_code, retries=retries)
        if response.status_code not in expected:
            errors.append("status " + str(response.status_code))
        noindex = "noindex" in response.headers.get("X-Robots-Tag", "").lower()
        if not noindex:
            errors.append("preview missing noindex")
        if "file" in c:
            actual = digest(response.content)
            result["sha256"] = actual
            if actual != digest(c["file"].read_bytes()):
                errors.append("body hash mismatch")
        if "canonical" in c:
            doc = Document()
            doc.feed(response.content.decode("utf-8"))
            if doc.canonicals != [c["canonical"]]:
                errors.append("canonical mismatch")
        if "location" in c:
            location = response.headers.get("Location", "")
            if urlsplit(location).netloc and urlsplit(location).netloc != c["host"]:
                errors.append("redirect leaves alias")
            if location != c["location"] and location != "https://" + c["host"] + c["location"]:
                errors.append("redirect target mismatch")
        if c.get("api"):
            marker = response.headers.get("X-Hyrule-Community")
            result["binding_reached"] = marker == "reached"
            if "no-store" not in response.headers.get("Cache-Control", ""):
                errors.append("API response can be cached")
            if "Set-Cookie" in response.headers:
                errors.append("API cookie exposed")
            if (mode == "status" and marker != "reached") or (mode != "status" and marker is not None):
                errors.append("unexpected service binding marker")
            if mode == "read" or method == "HEAD":
                if response.content:
                    errors.append("probe returned a body")
            elif mode == "status":
                body = response.json()
                if not isinstance(body, dict) or set(body) != {"configured"} or body["configured"] is not expect_configured:
                    errors.append("unexpected service readiness response")
            elif response.json() != {"configured": False, "turnstileSiteKey": "", "user": None}:
                errors.append("unexpected closed-alias response")
    except (requests.RequestException, ValueError, OSError) as exc:
        errors.append(type(exc).__name__)
    if errors:
        result["errors"] = errors
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deployment", required=True, help="Immutable Cloudflare Pages hostname")
    parser.add_argument("--dist", type=Path, default=ROOT / "cloudflare/pages/dist")
    parser.add_argument("--receipt", type=Path, default=ROOT / "cloudflare/verify/checks/pages-preflight.json")
    parser.add_argument("--expect-configured", action="store_true")
    parser.add_argument("--api-only", action="store_true", help="Only test the stable and immutable API gateways")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9-]+\.hyrule-atlas\.pages\.dev", args.deployment):
        parser.error("deployment must be a hostname under hyrule-atlas.pages.dev")
    checks = make_checks(args.dist, args.deployment)
    if args.api_only:
        checks = [c for c in checks if c.get("api")]
    start = datetime.now(timezone.utc)
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda c: assess(c, args.expect_configured), checks))
    groups = {}
    for group in sorted({r["group"] for r in results}):
        rows = [r for r in results if r["group"] == group]
        file_hashes = sorted(f"{r['path']} {r['sha256']}" for r in rows if "sha256" in r)
        groups[group] = {"checks": len(rows), "passed": sum("errors" not in r for r in rows),
                         "http_statuses": dict(Counter(r.get("status", 0) for r in rows))}
        if file_hashes:
            groups[group]["path_sha256_list_digest"] = digest("\n".join(file_hashes).encode())
    api_rows = [r for r in results if r["group"].startswith("api_")]
    ready_probe, denied_probe = (next(r for r in api_rows if r["group"] == group and
                                      r["path"] == "/api/community?op=status" and r["method"] == "GET")
                                 for group in ("api_stable", "api_immutable"))
    indistinguishable = (ready_probe.get("status") == denied_probe.get("status") and
                         ready_probe.get("binding_reached") == denied_probe.get("binding_reached"))
    report = {"started_utc": start.isoformat(), "finished_utc": datetime.now(timezone.utc).isoformat(),
              "stable": STABLE, "deployment": args.deployment, "concurrency": 6,
              "redirects_followed": False, "javascript_executed": False,
              "sitemap_sha256": digest((args.dist / "sitemap.xml").read_bytes()),
              "groups": groups, "retries": sum(r.get("retries", 0) for r in results),
              "api_observations": api_rows,
              "stable_status_indistinguishable_from_closed_alias": indistinguishable,
              "remote_branch_alias_scope": "Immutable deployment alias; no separate Git preview branch queried.",
              "failures": [r for r in results if "errors" in r]}
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for group, outcome in groups.items():
        print(f"{group}: {outcome['passed']}/{outcome['checks']}")
    print(f"Receipt: {args.receipt}")
    return bool(report["failures"])


if __name__ == "__main__":
    raise SystemExit(main())
