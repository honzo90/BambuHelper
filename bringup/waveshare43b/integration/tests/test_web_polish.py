"""Offline localization contracts; no network, printer commands or device writes."""
import ast
from collections import Counter
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import localize_web as loc
from pygments.lexers import JavascriptLexer
from pygments.token import String

class Tags(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.feed(text)
    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, [(k,v) for k,v in attrs if k not in {'lang','title','placeholder','aria-label','alt'}]))

class PolishWeb(unittest.TestCase):
    def test_ui_labels_and_protocol_keys_are_distinct(self):
        s = '''const o={"seconds":10}; let x=o["seconds"]; let names=['Info','Common']; let label='seconds';'''
        out=loc.javascript(s)
        self.assertIn('"seconds":10',out)
        self.assertIn('o["seconds"]',out)
        self.assertIn('"Informacja"',out)
        self.assertIn('"Ogólny"',out)
        self.assertIn('label="sekundy"',out)
        self.assertEqual(loc.cpp('doc["seconds"] = 10;'), 'doc["seconds"] = 10;')

    def test_cpp_char_literals_and_json(self):
        s = '''char quote='"'; const char* msg="Connected";'''
        self.assertIn('"Połączono"',loc.cpp(s))
        payload = '{"status":"error","message":"Invalid JSON","seconds":20}'
        out=json.loads(loc.literal(payload,loc.catalog()))
        self.assertEqual(out,{'status':'error','message':'Nieprawidłowy JSON','seconds':20})

    def test_html_controls_and_template_tokens_preserved(self):
        source=(ROOT/'include/web_pages.h').read_text()
        translated=loc.cpp(source)
        token=lambda s: Counter(re.findall(r'%[A-Z][A-Z0-9_]*%',s))
        self.assertEqual(token(source),token(translated))
        original_raw=[m for m in loc.CPP.finditer(source) if m[0].startswith('R"')]
        polish_raw=[m for m in loc.CPP.finditer(translated) if m[0].startswith('R"')]
        self.assertEqual(len(original_raw),len(polish_raw))
        for a,b in zip(original_raw,polish_raw):
            self.assertEqual(Tags(a[0]).tags,Tags(b[0]).tags)
        self.assertIn('<html lang="pl" data-theme="dark">',translated)
        self.assertNotIn('<html lang="en"',translated)
        self.assertIn('Ustawienia',translated)
        self.assertNotIn('>Printer Settings<',translated)

    def test_javascript_syntax_and_executable_tokens(self):
        source=(ROOT/'web/app.js').read_text();out=loc.javascript(source)
        def code(s):
            return [(k,t) for _,k,t in JavascriptLexer().get_tokens_unprocessed(s) if k not in (String.Single,String.Double)]
        self.assertEqual(code(source),code(out))
        def endpoints(s):
            return [ast.literal_eval(t) for _,k,t in JavascriptLexer().get_tokens_unprocessed(s)
                    if k in (String.Single,String.Double) and t[1:2] == '/']
        self.assertEqual(endpoints(source),endpoints(out))
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'app.js';p.write_text(out)
            subprocess.run(['node','--check',str(p)],check=True,capture_output=True)

    def test_user_values_are_never_runtime_translated(self):
        source=(ROOT/'web/app.js').read_text();out=loc.javascript(source)
        self.assertIn('esc(d.state)',out)
        self.assertIn('d.name',out)
        self.assertNotIn('MutationObserver',out)
        # The localizer consumes only source literals. No server settings or
        # live telemetry enters its input; the CSS is copied byte for byte.
        self.assertIn('write_bytes((web_source',Path(loc.__file__).read_text())

if __name__=='__main__': unittest.main()
