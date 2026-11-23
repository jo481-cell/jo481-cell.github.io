"""Send public credit links to the corresponding section of the localized sources page."""

from hashlib import sha256
from html import escape
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
FONTS = {
    "/assets/fonts/manrope-OFL.txt": "Manrope",
    "/assets/fonts/marcellus-OFL.txt": "Marcellus",
    "/assets/fonts/ibmplexmono-OFL.txt": "IBM Plex Mono",
}
ASSETS = "(?:" + "|".join(re.escape(path) for path in SECTIONS if path not in FONTS) + ")"
LINK = re.compile(r'<a\b[^>]*\bhref="(?P<path>' + ASSETS + r')"[^>]*>')
CREDIT_ROW = re.compile(r'<li><a\b[^>]*\bhref="' + ASSETS + r'"[^>]*>[^<]*</a>(?:(?!</li>).)*</li>')
JS_ASSET = re.compile(r"(?P<quote>[`\"'])(?P<path>" + ASSETS + r")(?P=quote)")
HTML_LOADER_CREDIT = re.compile(r'\bhref:' + JS_ASSET.pattern)
JS_CREDIT_ROW = re.compile(r'\{href:[`\"]' + ASSETS + r'[`\"],label:[`\"][^`\"]*[`\"],note:(?:`[^`]*`|"[^"\\]*(?:\\.[^"\\]*)*")\},?')
EDITION_ART = re.compile(r'(<a class="alttp-official-art"[^>]*><img[^>]*><small>)[^<]+(</small>)')
JS_EDITION_ART = re.compile(r'(className:`alttp-official-art`,[^\n]{0,600}?\(`small`,\{children:)`[^`]*`')
SOURCES_DATE = re.compile(r'<p class="archive-article__updated">[^<]*<!-- -->([^<]+)')
FONT_SECTION = re.compile(r'(<section id="record-9">.*?)(</section>)', re.DOTALL)
FONT_LINK = re.compile(r'<a href="(' + '|'.join(map(re.escape, FONTS)) + r')" rel="noreferrer" target="_blank">[^<]+</a>')
FONT_CREDIT = re.compile(r'\{heading:`Credits and licenses`,paragraphs:\[`[^`]+`\](?=\})')
FONT_ROWS = '...[`manrope`,`marcellus`,`ibmplexmono`].map(e=>({href:`/assets/fonts/${e}-OFL.txt`,label:e,note:`SIL Open Font License`}))'
SECTION_PARAGRAPHS = 'n.paragraphs.map(t=>e(`p`,{children:t},t))'
SOURCE_ANCHOR = 'href:n.href,rel:`noreferrer`,target:`_blank`,children:n.label'
FONT_DATA = "atlasFontLicenses"


def font_licenses(root):
    licenses = [
        {"id": SECTIONS[path], "name": name, "notice": (root / path[1:]).read_text(encoding="utf-8")}
        for path, name in FONTS.items()
    ]
    payload = f"export default {json.dumps(licenses, ensure_ascii=False)};\n".encode("utf-8")
    filename = f"font-licenses-{sha256(payload).hexdigest()[:16]}.js"
    # Keep this resource's content hash independent of the release's bundle renaming.
    (root / "assets/fonts" / filename).write_bytes(payload)
    return licenses, filename


def font_license_markup(licenses):
    return "".join(
        f'<details class="archive-font-license"><summary>{entry["name"]} · SIL Open Font License</summary>'
        f'<pre id="{entry["id"]}" lang="en">{escape(entry["notice"], quote=False)}</pre></details>'
        for entry in licenses
    )


def add_font_licenses_to_source(source, markup, path):
    source, sections = FONT_SECTION.subn(lambda match: match[1] + markup + match[2], source)
    source, links = FONT_LINK.subn(
        lambda match: f'<a href="#{SECTIONS[match[1]]}">{FONTS[match[1]]}</a>', source
    )
    if (sections, links) != (1, len(FONTS)):
        raise ValueError(f"Expected a license chapter and {len(FONTS)} font links in {path}")
    return source


def add_font_licenses_to_bundle(source, filename, path):
    if path.name.startswith("sources-") and FONT_ROWS in source:
        source, sections = FONT_CREDIT.subn(lambda match: match[0] + f",fontLicenses:{FONT_DATA}", source)
        if sections != 1 or source.count(FONT_ROWS) != 1:
            raise ValueError(f"Could not update font credits in {path}")
        rows = f'{FONT_DATA}.map(license=>({{href:`#${{license.id}}`,label:license.name,note:`SIL Open Font License`}}))'
        return f'import {FONT_DATA} from "./fonts/{filename}";\n' + source.replace(FONT_ROWS, "..." + rows)
    if path.name.startswith("archive-page-"):
        if source.count(SECTION_PARAGRAPHS) != 1 or source.count(SOURCE_ANCHOR) != 1:
            raise ValueError(f"Could not update archive rendering in {path}")
        details = (
            'n.fontLicenses?.map(license=>t(`details`,{className:`archive-font-license`,children:['
            'e(`summary`,{children:license.name+` · SIL Open Font License`}),'
            'e(`pre`,{id:license.id,lang:`en`,children:license.notice})]},license.id))'
        )
        font_link = 'n.href.startsWith(`#font-license-`)'
        anchor = f'href:n.href,rel:{font_link}?void 0:`noreferrer`,target:{font_link}?void 0:`_blank`,children:n.label'
        return source.replace(SECTION_PARAGRAPHS, SECTION_PARAGRAPHS + "," + details).replace(SOURCE_ANCHOR, anchor)
    return source


def js_reader_link(match):
    return f'{match["quote"]}/sources/#{SECTIONS[match["path"]]}{match["quote"]}'


def apply(root):
    licenses, filename = font_licenses(root)
    markup = font_license_markup(licenses)
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
            source = add_font_licenses_to_source(source, markup, path)
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
        source = add_font_licenses_to_bundle(source, filename, path)
        if path.name.startswith("sources-"):
            source = JS_CREDIT_ROW.sub("", source)
            source = source.replace(f'updated:`{dates["en"]}`', f'updated:{review_dates}')
        source = JS_EDITION_ART.sub(lambda m: m[1] + illustration_labels, source)
        # The shared anchor renderer prefixes internal paths for the current language.
        revised = JS_ASSET.sub(js_reader_link, source).encode("utf-8")
        if revised != original:
            path.write_bytes(revised)
