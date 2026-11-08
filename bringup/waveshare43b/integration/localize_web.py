"""Build-time Polish WebUI for 4.3B only; upstream sources/protocols stay unchanged."""

import ast
import html
import json
from pathlib import Path
import re
from pygments.lexers import JavascriptLexer
from pygments.token import String, Name, Comment, Text

CATALOG = Path(__file__).with_name('locale') / 'pl.json'
CPP_CHARS = r"'(?:\\.|[^'\\])*'|"
CPP = re.compile(
    CPP_CHARS
    + r'//[^\n]*|/\*.*?\*/|R"(?P<delim>[^ ()\\\t\r\n]{0,16})\(.*?\)(?P=delim)"|"(?:\\.|[^"\\])*"',
    re.S,
)


def catalog(language='pl'):
    entries = json.loads(CATALOG.with_name(language + '.json').read_text())
    # HTML entities and ordinary JS strings share translations, never keys/IDs.
    return {**entries, **{html.unescape(k): html.unescape(v) for k, v in entries.items()}}


def plain(text, entries):
    if text in entries:
        return entries[text]
    core = text.strip()
    if core in entries:
        return text[: len(text) - len(text.lstrip())] + entries[core] + text[len(text.rstrip()) :]
    return text


def markup(text, entries, language='pl'):
    # Only text nodes and human-facing attributes, never IDs, names, values,
    # URLs, CSS selectors, placeholders such as %FW_VER%, or user data.
    def chunk(value):
        value = re.sub(
            r'(?i)\b(title|placeholder|aria-label|alt)=("[^"<>]*"|\x27[^\x27<>]*\x27)',
            lambda m: m[1] + '=' + m[2][0] + plain(m[2][1:-1], entries) + m[2][-1],
            value,
        )
        wrapped = '<loc>' + value + '</loc>'
        wrapped = re.sub(r'>([^<>]+)<', lambda m: '>' + plain(m[1], entries) + '<', wrapped)
        return wrapped[5:-6]

    parts = re.split(r'(<(?:script|style)\b[^>]*>.*?</(?:script|style)>)', text, flags=re.S | re.I)
    for i, value in enumerate(parts):
        if re.match(r'<script\b', value, re.I):
            a = value.index('>') + 1
            b = value.lower().rindex('</script>')
            parts[i] = value[:a] + javascript(value[a:b], entries, language) + value[b:]
        elif not re.match(r'<style\b', value, re.I):
            parts[i] = chunk(value)
    return ''.join(parts).replace('<html lang="en"', '<html lang="' + language + '"')


def literal(value, entries, language='pl'):
    if value.lstrip().startswith('{'):
        try:
            obj = json.loads(value)
            if isinstance(obj, dict):
                for key in ('message', 'error', 'reason'):
                    if isinstance(obj.get(key), str):
                        obj[key] = plain(obj[key], entries)
                return json.dumps(obj, ensure_ascii=False, separators=(',', ':'))
        except ValueError:
            pass
    return (
        markup(value, entries, language) if '<' in value and '>' in value else plain(value, entries)
    )


def javascript(source, entries=None, language='pl'):
    if entries is None:
        entries = catalog(language)
    replacements = []
    tokens = list(JavascriptLexer().get_tokens_unprocessed(source))
    significant = []
    for pos, kind, token in tokens:
        prior = significant[-2:]
        if not token.isspace() and kind not in Comment:
            significant.append((kind, token))
        if kind not in (String.Single, String.Double):
            continue
        # Object keys and indexed properties are protocol identifiers.
        indexed = (
            len(prior) == 2
            and prior[-1][1] == '['
            and (prior[-2][0] in Name or prior[-2][1] in (']', ')'))
        )
        key = (
            prior
            and prior[-1][1] in ('{', ',')
            and source[pos + len(token) :].lstrip().startswith(':')
        )
        if indexed or key:
            continue
        try:
            value = ast.literal_eval(token)
        except (ValueError, SyntaxError):
            continue
        translated = literal(value, entries, language)
        if translated != value:
            replacements.append((pos, pos + len(token), json.dumps(translated, ensure_ascii=False)))
    for a, b, value in reversed(replacements):
        source = source[:a] + value + source[b:]
    return source


def cpp(source, entries=None, language='pl'):
    if entries is None:
        entries = catalog(language)

    def replace(m):
        token = m[0]
        if source[: m.start()].rstrip().endswith('['):
            return token
        if token.startswith(('//', '/*', "'")):
            return token
        if token.startswith('R"'):
            a = token.index('(') + 1
            b = token.rindex(')' + m['delim'] + '"')
            return token[:a] + markup(token[a:b], entries, language) + token[b:]
        try:
            value = ast.literal_eval(token)
        except (ValueError, SyntaxError):
            return token
        translated = literal(value, entries, language)
        return json.dumps(translated, ensure_ascii=False) if translated != value else token

    return CPP.sub(replace, source)


def runtime_cpp(source, entries):
    """Translate backend response literals at runtime, preserving JSON keys.

    Adjacent C++ strings are one expression; translate them as a group so
    concatenated messages stay valid C++. No source code or field is rewritten.
    """
    monitor_en = json.loads((CATALOG.parent / "monitor_en.json").read_text())
    de_entries = catalog('de')
    monitor_de = json.loads((CATALOG.parent / 'monitor_de.json').read_text())
    tokens = list(CPP.finditer(source))
    replacements = []
    i = 0
    while i < len(tokens):
        m = tokens[i]
        i += 1
        if not m[0].startswith('"') or source[: m.start()].rstrip().endswith('['):
            continue
        start, end = m.span()
        value = ast.literal_eval(m[0])
        while (
            i < len(tokens)
            and tokens[i][0].startswith('"')
            and not source[end : tokens[i].start()].strip()
        ):
            value += ast.literal_eval(tokens[i][0])
            end = tokens[i].end()
            i += 1
        translated = literal(value, entries, language='pl')
        if translated != value:
            PL = translated
            EN = value
            DE = literal(value, de_entries, language='de')
            replacements.append(
                (
                    start,
                    end,
                    'ws43bText('
                    + json.dumps(PL, ensure_ascii=False)
                    + ','
                    + json.dumps(EN, ensure_ascii=False)
                    + ','
                    + json.dumps(DE, ensure_ascii=False)
                    + ')',
                )
            )
        else:
            english = literal(value, monitor_en, language='en')
            if english != value:
                PL = value
                EN = english
                DE = literal(value, monitor_de, language='de')
                replacements.append(
                    (
                        start,
                        end,
                        'ws43bText('
                        + json.dumps(PL, ensure_ascii=False)
                        + ','
                        + json.dumps(EN, ensure_ascii=False)
                        + ','
                        + json.dumps(DE, ensure_ascii=False)
                        + ')',
                    )
                )
    for a, b, text in reversed(replacements):
        source = source[:a] + text + source[b:]
    return '#include "ws43b_language.h"\n' + source


COMPRESSED_PAGES = ('PAGE_HTML_1', 'PAGE_HTML_ERRORS', 'PAGE_HTML_2')
RAW_OPEN, RAW_CLOSE = 'R"rawliteral(', ')rawliteral"'


def compress_pages(header, names=COMPRESSED_PAGES):
    """Replace `static const char NAME[] PROGMEM = R"rawliteral(...)..." ;` page
    arrays by `NAME_Z` byte arrays: every raw-literal chunk becomes
    [compressed u32][raw u32][zlib], and preprocessor lines between chunks stay
    in place, so the compiler still selects the chunks exactly as before."""
    import zlib

    for name in names:
        start_decl = 'static const char ' + name + '[] PROGMEM ='
        start = header.find(start_decl)
        if start < 0:
            continue
        pos = start + len(start_decl)
        out = ['static const uint8_t ' + name + '_Z[] PROGMEM = {\n']
        while True:
            # Skip whitespace; copy preprocessor lines; stop at the final ';'.
            while header[pos] in ' \t\r\n':
                pos += 1
            if header.startswith(RAW_OPEN, pos):
                end = header.index(RAW_CLOSE, pos)
                raw = header[pos + len(RAW_OPEN) : end].encode('utf-8')
                z = zlib.compress(raw, 9)
                blob = len(z).to_bytes(4, 'little') + len(raw).to_bytes(4, 'little') + z
                for i in range(0, len(blob), 24):
                    out.append(' ' + ','.join('0x%02x' % b for b in blob[i : i + 24]) + ',\n')
                pos = end + len(RAW_CLOSE)
            elif header[pos] == '#':
                eol = header.index('\n', pos)
                out.append(header[pos:eol] + '\n')
                pos = eol + 1
            elif header[pos] == ';':
                pos += 1
                break
            else:
                raise ValueError('unexpected text in ' + name + ': ' + header[pos : pos + 40])
        out.append('};\n')
        header = header[:start] + ''.join(out) + header[pos:]
    return header


def readable_pages(header):
    """Inverse view of compress_pages() for checks: each NAME_Z array becomes
    the plain-text raw literals again (preprocessor lines kept in order)."""
    import re
    import zlib

    def expand(match):
        body = match.group(2)
        out = ['static const char ' + match.group(1) + '[] PROGMEM =\n']
        for line in body.splitlines():
            if line.startswith('#'):
                out.append(line + '\n')
                continue
            data = bytes(int(x, 16) for x in re.findall(r'0x([0-9a-f]{2})', line))
            if data:
                out.append(data.hex())
        # Rebuild chunk by chunk from the concatenated hex runs between #lines.
        text, pending = [], ''
        for piece in out:
            if piece.startswith('#') or piece.startswith('static'):
                if pending:
                    blob = bytes.fromhex(pending)
                    pos = 0
                    while pos < len(blob):
                        c = int.from_bytes(blob[pos : pos + 4], 'little')
                        text.append(
                            'R"rawliteral('
                            + zlib.decompress(blob[pos + 8 : pos + 8 + c]).decode('utf-8')
                            + ')rawliteral"\n'
                        )
                        pos += 8 + c
                    pending = ''
                text.append(piece)
            else:
                pending += piece
        if pending:
            blob = bytes.fromhex(pending)
            pos = 0
            while pos < len(blob):
                c = int.from_bytes(blob[pos : pos + 4], 'little')
                text.append(
                    'R"rawliteral('
                    + zlib.decompress(blob[pos + 8 : pos + 8 + c]).decode('utf-8')
                    + ')rawliteral"\n'
                )
                pos += 8 + c
        return ''.join(text) + ';'

    return re.sub(
        r'static const uint8_t (\w+)_Z\[\] PROGMEM = \{\n(.*?)\n\};', expand, header, flags=re.S
    )


SERVE_MAIN_RAW = """  const TemplateSegment segs[] = {
    { PAGE_HTML_1, sizeof(PAGE_HTML_1) - 1 },
#if HAS_HMS_WEB_UI
    { PAGE_HTML_ERRORS, sizeof(PAGE_HTML_ERRORS) - 1 },
#endif
    { PAGE_HTML_2, sizeof(PAGE_HTML_2) - 1 },
  };
  streamTemplate(segs, (uint8_t)(sizeof(segs) / sizeof(segs[0])));"""

SERVE_MAIN_Z = """  // Pages are stored compressed (ws43b_page_inflate.h); inflate them into
  // PSRAM for this request. If that fails, offer a minimal firmware upload so
  // the panel can always be updated or rolled back from the browser.
  size_t lengths[3] = {};
  char *pages[3] = {};
  pages[0] = ws43b_page::inflatePage(PAGE_HTML_1_Z, sizeof(PAGE_HTML_1_Z), lengths[0]);
#if HAS_HMS_WEB_UI
  pages[1] = ws43b_page::inflatePage(PAGE_HTML_ERRORS_Z, sizeof(PAGE_HTML_ERRORS_Z), lengths[1]);
  const bool errorsOk = pages[1] != nullptr;
#else
  const bool errorsOk = true;
#endif
  pages[2] = ws43b_page::inflatePage(PAGE_HTML_2_Z, sizeof(PAGE_HTML_2_Z), lengths[2]);
  if (!pages[0] || !errorsOk || !pages[2]) {
    for (char *page : pages) if (page) heap_caps_free(page);
    server.send(500, "text/html",
      "<!doctype html><meta name=viewport content='width=device-width'><title>BambuHelper</title>"
      "<h3>WebUI unavailable</h3><p>Upload a BambuHelper-ws_lcd_43b-*-ota.bin firmware file:</p>"
      "<form method=post action='/ota/upload' enctype='multipart/form-data'>"
      "<input type=file name=firmware accept='.bin'> <button>Upload and restart</button></form>"
      "<form method=post action='/ota/rollback'><button>Start the other firmware slot</button></form>");
    return;
  }
  const TemplateSegment segs[] = {
    { pages[0], lengths[0] },
#if HAS_HMS_WEB_UI
    { pages[1], lengths[1] },
#endif
    { pages[2], lengths[2] },
  };
  streamTemplate(segs, (uint8_t)(sizeof(segs) / sizeof(segs[0])));
  for (char *page : pages) if (page) heap_caps_free(page);"""


def stage(source_dir, web_source, web_target):
    entries = catalog('pl')
    entries_de = catalog('de')
    picker = (CATALOG.parent / 'language_picker.html').read_text()
    pages = (source_dir / 'web_pages.h').read_text()

    # Picker in the full portal sidebar and the initial AP provisioning page.
    pages = pages.replace('<div class="sidebar-footer">', '<div class="sidebar-footer">' + picker)
    pages = pages.replace('</head><body>', '</head><body>' + picker)
    (source_dir / 'web_pages.h').write_text(compress_pages(pages))
    (source_dir / 'web_pages_pl.h').write_text(compress_pages(cpp(pages, entries, language='pl')))
    (source_dir / 'web_pages_de.h').write_text(
        compress_pages(cpp(pages, entries_de, language='de'))
    )

    template = (source_dir / 'web_template.cpp').read_text()
    for lang in ('en', 'pl', 'de'):
        if lang == 'en':
            t = template
        else:
            t = cpp(template, entries if lang == 'pl' else entries_de, language=lang)

        if lang == 'pl':
            t = t.replace('"web_pages.h"', '"web_pages_pl.h"')
        elif lang == 'de':
            t = t.replace('"web_pages.h"', '"web_pages_de.h"')

        if SERVE_MAIN_RAW not in t:
            raise SystemExit('serveMainPage layout changed; update localize_web.SERVE_MAIN_RAW')
        t = t.replace(SERVE_MAIN_RAW, SERVE_MAIN_Z)
        t = '#include "ws43b_page_inflate.h"\n' + t

        for name in ('serveMainPage', 'serveApPage', 'webAssetJsVersion'):
            t = t.replace(name + '(', name + '_' + lang + '(')

        t = 'extern const char* webAssetJsVersion_' + lang + '();\n' + t
        (source_dir / ('web_template_' + lang + '.cpp')).write_text(t)

    (source_dir / 'web_template.cpp').write_text(
        '#include "ws43b_language.h"\n'
        'void serveMainPage_pl(); void serveMainPage_en(); void serveMainPage_de();\n'
        'void serveApPage_pl(); void serveApPage_en(); void serveApPage_de();\n'
        'void serveMainPage() {\n'
        '    if (ws43bLanguage() == 0) serveMainPage_pl();\n'
        '    else if (ws43bLanguage() == 2) serveMainPage_de();\n'
        '    else serveMainPage_en();\n'
        '}\n'
        'void serveApPage() {\n'
        '    if (ws43bLanguage() == 0) serveApPage_pl();\n'
        '    else if (ws43bLanguage() == 2) serveApPage_de();\n'
        '    else serveApPage_en();\n'
        '}\n'
    )

    for name in ('web_server.cpp', 'cloud_login.cpp'):
        p = source_dir / name
        p.write_text(runtime_cpp(p.read_text(), entries))

    p = source_dir / 'web_server.cpp'
    s = p.read_text()

    monitor_en = json.loads((CATALOG.parent / 'monitor_en.json').read_text())
    monitor_de = json.loads((CATALOG.parent / 'monitor_de.json').read_text())

    start = s.index('static const char MONITOR_PAGE[]')
    end = s.index(')MONITOR";', start) + len(')MONITOR";')
    original = s[start:end]

    english = cpp(original, monitor_en, language='en')
    english = english.replace('MONITOR_PAGE[]', 'MONITOR_PAGE_EN[]')
    english = english.replace('lang="pl"', 'lang="en"')

    german = cpp(original, monitor_de, language='de')
    german = german.replace('MONITOR_PAGE[]', 'MONITOR_PAGE_DE[]')
    german = german.replace('lang="pl"', 'lang="de"')

    s = s[:end] + '\n' + english + '\n' + german + s[end:]

    s = s.replace(
        '"text/html; charset=utf-8", MONITOR_PAGE)',
        '"text/html; charset=utf-8", ws43bLanguage() == 0 ? MONITOR_PAGE : (ws43bLanguage() == 2 ? MONITOR_PAGE_DE : MONITOR_PAGE_EN))',
    )

    s = s.replace(
        '#include "web_assets_gz.h"',
        '#include "web_assets_gz.h"\n#include "web_assets_en_gz.h"\n#include "web_assets_de_gz.h"',
    )

    s = s.replace(
        'const char* webAssetJsVersion()  { return WEB_APP_JS_VER; }',
        'const char* webAssetJsVersion_pl() { return WEB_APP_JS_VER; }\n'
        'const char* webAssetJsVersion_en() { return WEB_EN_APP_JS_VER; }\n'
        'const char* webAssetJsVersion_de() { return WEB_DE_APP_JS_VER; }\n'
        'const char* webAssetJsVersion() {\n'
        '    if (ws43bLanguage() == 0) return WEB_APP_JS_VER;\n'
        '    if (ws43bLanguage() == 2) return WEB_DE_APP_JS_VER;\n'
        '    return WEB_EN_APP_JS_VER;\n'
        '}',
    )

    s = s.replace(
        'sendGzipAsset("application/javascript", WEB_APP_JS_GZ, WEB_APP_JS_GZ_LEN);',
        'if (server.arg("v") == WEB_DE_APP_JS_VER || (!server.hasArg("v") && ws43bLanguage() == 2)) {\n'
        '    sendGzipAsset("application/javascript", WEB_DE_APP_JS_GZ, WEB_DE_APP_JS_GZ_LEN);\n'
        '} else if (server.arg("v") == WEB_EN_APP_JS_VER || (!server.hasArg("v") && ws43bLanguage() == 1)) {\n'
        '    sendGzipAsset("application/javascript", WEB_EN_APP_JS_GZ, WEB_EN_APP_JS_GZ_LEN);\n'
        '} else {\n'
        '    sendGzipAsset("application/javascript", WEB_APP_JS_GZ, WEB_APP_JS_GZ_LEN);\n'
        '}',
    )

    p.write_text(s)

    web_target.mkdir(parents=True, exist_ok=True)
    original_js = (web_source / 'app.js').read_text()
    (web_target / 'app.js').write_text(javascript(original_js, entries, language='pl'))
    (web_target / 'app.css').write_bytes((web_source / 'app.css').read_bytes())

    import gzip, zlib

    en_blob = gzip.compress(original_js.encode(), compresslevel=9, mtime=0)
    (source_dir / 'web_assets_en_gz.h').write_text(
        '#pragma once\n#include <Arduino.h>\n'
        'static const uint8_t WEB_EN_APP_JS_GZ[] PROGMEM = {'
        + ','.join(str(b) for b in en_blob)
        + '};\n'
        'static const size_t WEB_EN_APP_JS_GZ_LEN = ' + str(len(en_blob)) + ';\n'
        '#define WEB_EN_APP_JS_VER "'
        + format(zlib.crc32(original_js.encode()) & 0xFFFFFFFF, '08x')
        + '"\n'
    )

    de_js = javascript(original_js, entries_de, language='de')
    de_blob = gzip.compress(de_js.encode(), compresslevel=9, mtime=0)
    (source_dir / 'web_assets_de_gz.h').write_text(
        '#pragma once\n#include <Arduino.h>\n'
        'static const uint8_t WEB_DE_APP_JS_GZ[] PROGMEM = {'
        + ','.join(str(b) for b in de_blob)
        + '};\n'
        'static const size_t WEB_DE_APP_JS_GZ_LEN = ' + str(len(de_blob)) + ';\n'
        '#define WEB_DE_APP_JS_VER "'
        + format(zlib.crc32(de_js.encode()) & 0xFFFFFFFF, '08x')
        + '"\n'
    )
