"""Read-only HTTP checks for Hyrule Atlas after the apex/www DNS switch."""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import re
from urllib.parse import urljoin, urlsplit

import requests


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("pages_live", HERE / "pages-live.py")
common = importlib.util.module_from_spec(spec)
spec.loader.exec_module(common)
APEX = common.CANONICAL
WWW = "www.hyruleatlas.com"
GUIDES = ("/fr/series/a-link-to-the-past/bottle-locations/", "/zelda-64/deku-tree/")
QUERY = "?utm_source=atlas-preflight&lang=fr&place=coffre%20bleu"
BEACON = re.compile(rb"""<script\b[^>]*\bsrc=["'](?:https:)?//static\.cloudflareinsights\.com/beacon\.min\.js(?:[/?][^"']*)?["'][^>]*>\s*</script>""", re.I)
INJECTION = re.compile(rb"""(?:<!--\s*Cloudflare Web Analytics\s*-->\s*)?""" + BEACON.pattern +
                       rb"""(?:\s*<!--\s*End Cloudflare Web Analytics\s*-->)?""", re.I)


def compare(local, remote, *, html):
    result = {"expected_sha256": common.digest(local), "received_sha256": common.digest(remote)}
    if html:
        result["analytics_scripts"] = len(BEACON.findall(remote))
    if local == remote:
        return result, []
    if html:
        # Remove one candidate at a time for diagnosis only. A detector cannot
        # excuse a changed page, and the shipped beacon must never be removed.
        for match in INJECTION.finditer(remote):
            without = remote[:match.start()] + remote[match.end():]
            if without == local:
                result["difference"] = "one extra Cloudflare Web Analytics tag"
                break
        if "difference" not in result and b"/cdn-cgi/" in remote and b"/cdn-cgi/" not in local:
            result["difference"] = "Cloudflare edge markup present; cause of the byte difference unverified"
    return result, ["response bytes differ from the published Git export"]


def get(url, method="GET"):
    parts = urlsplit(url)
    if parts.hostname not in {"hyruleatlas.com", WWW, common.STABLE} or parts.username or parts.password or parts.port:
        raise ValueError("Unexpected host in verification request")
    with requests.Session() as session:
        session.auth = lambda request: request  # never use local account credentials
        return session.request(method, url, allow_redirects=False, timeout=(7, 22),
                               headers={"User-Agent": "HyruleAtlas-Cutover-ReadOnly/1.0", "Accept-Encoding": "identity"})


def inspect_page(name, url, source, status, canonical=None, preview=False, immutable=False):
    response = get(url)
    html = source.suffix == ".html"
    row, issues = compare(source.read_bytes(), response.content, html=html)
    row.update(name=name, url=url, status=response.status_code,
               cloudflare_edge=bool(response.headers.get("CF-Ray")),
               vercel_headers=any(key in response.headers for key in ("X-Vercel-Id", "X-Vercel-Cache")))
    if response.status_code != status:
        issues.append("unexpected HTTP status")
    if row["vercel_headers"]:
        issues.append("Vercel response headers still visible")
    noindex = "noindex" in response.headers.get("X-Robots-Tag", "").lower()
    if canonical:
        doc = common.Document()
        doc.feed(response.content.decode("utf-8"))
        row.update(canonical=doc.canonicals, noindex=noindex)
        if doc.canonicals != [canonical]:
            issues.append("canonical mismatch")
        if noindex != preview:
            issues.append("unexpected X-Robots-Tag")
        if row["analytics_scripts"] != 1:
            issues.append("expected one shipped Web Analytics beacon")
    if preview:
        csp = response.headers.get("Content-Security-Policy", "")
        if "connect-src 'self'" not in csp or "cloudflareinsights.com" in csp:
            issues.append("unexpected preview analytics policy")
    if immutable:
        directives = {v.strip().lower() for v in response.headers.get("Cache-Control", "").split(",")}
        row["cache_control"] = sorted(directives)
        if not {"public", "max-age=31536000", "immutable"}.issubset(directives):
            issues.append("unexpected cache policy for fingerprinted asset")
    return {**row, "issues": issues}


def inspect_redirect(start):
    parts = urlsplit(start)
    target = APEX + parts.path + "?" + parts.query
    chain, seen, issues = [], set(), []
    current = start
    while current not in seen and len(chain) < 4:
        seen.add(current)
        response = get(current, "HEAD")
        status = response.status_code
        hop = {"url": current, "status": status}
        chain.append(hop)
        if current == target:
            if status != 200:
                issues.append("canonical endpoint did not terminate with 200")
            break
        dest = urljoin(current, response.headers.get("Location", ""))
        allowed = {target}
        if current.startswith("http://" + WWW + "/"):
            allowed.add("https://" + WWW + parts.path + "?" + parts.query)
        if dest not in allowed:
            issues.append("Location changes the host, path or original query unexpectedly")
            break
        hop["location"] = dest
        from_www_to_apex = urlsplit(current).hostname == WWW and dest == target
        if (from_www_to_apex and status != 308) or (not from_www_to_apex and status not in (301, 308)):
            issues.append("unexpected redirect status")
            break
        current = dest
    else:
        issues.append("redirect loop or too many hops")
    return {"name": "redirect", "url": start, "hops": chain, "issues": issues}


def run(dist):
    rows = []
    def perform(name, func, *args, **kwargs):
        try:
            rows.append(func(name, *args, **kwargs) if func is inspect_page else func(*args))
        except (requests.RequestException, OSError, ValueError) as exc:
            rows.append({"name": name, "issues": [type(exc).__name__]})

    for path in GUIDES:
        url = APEX + path
        perform("guide", inspect_page, url, dist / path.strip("/") / "index.html", 200, canonical=url)
    path = GUIDES[0]
    local = dist / path.strip("/") / "index.html"
    doc = common.Document()
    doc.feed(local.read_text(encoding="utf-8"))
    matches = sorted(s for s in doc.assets if re.fullmatch(r"/assets/[a-zA-Z0-9_-]+-[a-zA-Z0-9_-]{8,}\.(js|css)", s))
    if not matches:
        raise ValueError("Guide has no fingerprinted asset to test")
    perform("immutable_asset", inspect_page, APEX + matches[0], dist / matches[0][1:], 200, immutable=True)
    perform("404", inspect_page, APEX + "/__atlas-cutover-unavailable-20261122__/", dist / "404.html", 404)
    perform("preview", inspect_page, "https://" + common.STABLE + path, local, 200, canonical=APEX + path, preview=True)
    for origin in ("http://hyruleatlas.com", "http://" + WWW, "https://" + WWW):
        perform("redirect", inspect_redirect, origin + path + QUERY)
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, default=HERE.parent / "pages/dist")
    parser.add_argument("--receipt", type=Path, default=HERE / "checks/pages-post-cutover.json")
    args = parser.parse_args()
    rows = run(args.dist)
    report = {"observed_utc": datetime.now(timezone.utc).isoformat(), "checks": rows,
              "passed": sum(not r["issues"] for r in rows), "total": len(rows)}
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for row in rows:
        print("FAIL" if row["issues"] else "PASS", row["name"], row.get("url", ""), ", ".join(row["issues"]))
    print(f"{report['passed']}/{report['total']} checks; receipt: {args.receipt}")
    raise SystemExit(report["passed"] != report["total"])
