"""Send public credit links to the corresponding section of the localized sources page."""

import json
from pathlib import Path
import re


SECTIONS = json.loads(
    (Path(__file__).parents[1] / "pages/functions/credit-sections.json").read_text(encoding="utf-8")
)
LOCALES = {"fr", "es", "ja", "zh"}
ILLUSTRATION_LABEL = {
    "en": "Illustration credits",
    "fr": "Crédits de l’illustration",
    "es": "Créditos de la ilustración",
    "ja": "イラストのクレジット",
    "zh": "插画署名",
}
ASSETS = "(?:" + "|".join(map(re.escape, SECTIONS)) + ")"
LINK = re.compile(r'<a\b[^>]*\bhref="(?P<path>' + ASSETS + r')"[^>]*>')
CREDIT_ROW = re.compile(r'<li><a\b[^>]*\bhref="' + ASSETS + r'"[^>]*>[^<]*</a>(?:(?!</li>).)*</li>')
JS_ASSET = re.compile(r"(?P<quote>[`\"'])(?P<path>" + ASSETS + r")(?P=quote)")
HTML_LOADER_CREDIT = re.compile(r'\bhref:' + JS_ASSET.pattern)
JS_CREDIT_ROW = re.compile(r'\{href:[`\"]' + ASSETS + r'[`\"],label:[`\"][^`\"]*[`\"],note:(?:`[^`]*`|"[^"\\]*(?:\\.[^"\\]*)*")\},?')
EDITION_ART = re.compile(r'(<a class="alttp-official-art"[^>]*><img[^>]*><small>)[^<]+(</small>)')
JS_EDITION_ART = re.compile(r'(className:`alttp-official-art`,[^\n]{0,600}?\(`small`,\{children:)`[^`]*`')
SOURCES_DATE = re.compile(r'<p class="archive-article__updated">[^<]*<!-- -->([^<]+)')


def js_reader_link(match):
    return f'{match["quote"]}/sources/#{SECTIONS[match["path"]]}{match["quote"]}'


def apply(root):
    dates = {}
    for path in root.rglob("*.html"):
        if "assets" in path.relative_to(root).parts:
            continue
        original = path.read_bytes()
        source = original.decode("utf-8")
        locale = path.relative_to(root).parts[0]
        prefix = f"/{locale}" if locale in LOCALES else ""
        if path.parent.name == "sources":
            date = SOURCES_DATE.search(source)
            if not date:
                raise ValueError(f"Missing localized review date in {path}")
            dates[locale if locale in LOCALES else "en"] = date[1]
            source = CREDIT_ROW.sub("", source)
        source = EDITION_ART.sub(lambda m: m[1] + ILLUSTRATION_LABEL.get(locale, ILLUSTRATION_LABEL["en"]) + m[2], source)

        def reader_link(match):
            section = "record-6" if 'class="atlas-triforce-source"' in match[0] else SECTIONS[match["path"]]
            return match[0].replace(f'href="{match["path"]}"', f'href="{prefix}/sources/#{section}"', 1)

        source = LINK.sub(reader_link, source)
        # TanStack embeds loader data in the initial document as JavaScript.
        revised = HTML_LOADER_CREDIT.sub(lambda m: "href:" + js_reader_link(m), source).encode("utf-8")
        if revised != original:
            path.write_bytes(revised)

    locale = 'document.documentElement.lang.split("-")[0]'
    review_dates = f'({json.dumps(dates, ensure_ascii=False)})[{locale}]'
    illustration_labels = f'({json.dumps(ILLUSTRATION_LABEL, ensure_ascii=False)})[{locale}]'
    for path in (root / "assets").glob("*.js"):
        original = path.read_bytes()
        source = original.decode("utf-8")
        if path.name.startswith("sources-"):
            source = JS_CREDIT_ROW.sub("", source)
            source = source.replace(f'updated:`{dates["en"]}`', f'updated:{review_dates}')
        source = JS_EDITION_ART.sub(lambda m: m[1] + illustration_labels, source)
        # The shared anchor renderer prefixes internal paths for the current language.
        revised = JS_ASSET.sub(js_reader_link, source).encode("utf-8")
        if revised != original:
            path.write_bytes(revised)
