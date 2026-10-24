"""German language boundary regressions: real handlers, catalog and VLW glyphs."""
from pathlib import Path
import json
import os
import re
import struct
import sys
import unittest

ROOT = Path(os.environ.get('BAMBUHELPER_TEST_ROOT', Path(__file__).resolve().parents[4]))
HERE = ROOT / 'bringup/waveshare43b/integration'
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_language_choice import compile_and_run


def braced(source, start):
    """Extract original C++ block, ignoring braces inside comments and literals."""
    first = source.index('{', start)
    tokens = re.compile(r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"|\x27(?:\\.|[^\x27\\])*\x27|[{}]', re.S)
    depth = 0
    for token in tokens.finditer(source, first):
        if token[0] == '{':
            depth += 1
        elif token[0] == '}':
            depth -= 1
            if not depth:
                return source[start:token.end()]
    raise AssertionError('Unclosed C++ block')


class GermanUi(unittest.TestCase):
    def test_real_language_http_and_backup_boundaries(self):
        source = (ROOT / 'src/web_server.cpp').read_text()
        handlers = '\n'.join(braced(source, source.index('static void ' + name + '()'))
                             for name in ('handleLanguageGet', 'handleLanguageSave'))
        export_line = re.search(r'^\s*native\["language"\]\s*=.*?;', source, re.M)[0]
        import_start = source.index('static void handleSettingsImportFinish()')
        import_source = source[import_start:]
        initial = re.search(r'uint8_t\s+importedLanguage\s*=.*?;', import_source)[0]
        validation = braced(import_source, import_source.index('if (!native["language"].isNull())'))
        save = braced(import_source, import_source.index('if (!saveWs43bLanguage(importedLanguage))'))
        harness = r'''
#include <string>
#include <utility>
#include <vector>
#include <ArduinoJson.h>
using String=std::string;
struct ServerStub {
 std::vector<std::pair<String,String>> fields;
 int code=0;String type,body,cache;
 int args(){return int(fields.size());}
 bool hasArg(const char* key){for(const auto& f:fields)if(f.first==key)return true;return false;}
 String arg(const char* key){for(const auto& f:fields)if(f.first==key)return f.second;return "";}
 void sendHeader(const char* key,const char* value){assert(String(key)=="Cache-Control");cache=value;}
 void send(int status,const char* contentType,const String& content){code=status;type=contentType;body=content;}
} server;
''' + handlers + r'''
String exportLanguage() {
 JsonDocument doc;JsonObject native=doc["waveshare43b"].to<JsonObject>();
''' + export_line + r'''
 String out;serializeJson(doc,out);return out;
}
void importLanguage(const JsonDocument& doc) {
''' + initial + r'''
 JsonObjectConst native=doc["waveshare43b"].as<JsonObjectConst>();
 if(!native.isNull()) {
''' + validation + r'''
 }
''' + save + r'''
 server.send(200,"application/json","{}");
}
void checkGet(const char* expected) {
 const auto previousWrites=writes,revision=ws43bLanguageRevision();
 server={};handleLanguageGet();assert(server.code==200 && server.type=="application/json");
 assert(server.cache=="no-store");JsonDocument doc;assert(!deserializeJson(doc,server.body));
 assert(doc.as<JsonObject>().size()==1 && doc["language"]==expected);
 assert(writes==previousWrites && ws43bLanguageRevision()==revision);
 JsonDocument backup;assert(!deserializeJson(backup,exportLanguage()));
 assert(backup["waveshare43b"]["language"]==expected);
}
void importJson(const char* text,int expected) {
 JsonDocument doc;assert(!deserializeJson(doc,text));server={};
 importLanguage(doc);assert(server.code==expected);
}
int main() {
 loadWs43bLanguage();checkGet("pl");
 for(const char* language:{"de","en","pl","de"}) {
  server={};server.fields={{"language",language}};handleLanguageSave();
  assert(server.code==200);assert(!strcmp(ws43bLanguageCode(),language));checkGet(language);
 }
 const auto deRevision=ws43bLanguageRevision(),deWrites=writes;
 for(const char* language:{"","DE","de-DE"," de","de ","pl\n","fr","2"}) {
  server={};server.fields={{"language",language}};handleLanguageSave();
  assert(server.code==400 && ws43bLanguage()==2);
  assert(writes==deWrites && ws43bLanguageRevision()==deRevision);
 }
 server={};handleLanguageSave();assert(server.code==400 && writes==deWrites);
 writeOk=false;server={};server.fields={{"language","en"}};handleLanguageSave();
 assert(server.code==500 && ws43bLanguage()==2 && ws43bLanguageRevision()==deRevision);
 checkGet("de");writeOk=true;
 // Execute the production import initializer, validation and save with real JSON.
 const auto beforeOmission=writes;
 for(const char* text:{"{}","{\"waveshare43b\":{}}","{\"waveshare43b\":{\"language\":null}}"}) {
  importJson(text,200);assert(ws43bLanguage()==2 && writes==beforeOmission);
 }
 for(const char* text:{"{\"waveshare43b\":{\"language\":0}}",
     "{\"waveshare43b\":{\"language\":true}}","{\"waveshare43b\":{\"language\":[]}}",
     "{\"waveshare43b\":{\"language\":{}}}","{\"waveshare43b\":{\"language\":\"DE\"}}",
     "{\"waveshare43b\":{\"language\":\"de-DE\"}}","{\"waveshare43b\":{\"language\":\"\"}}"}) {
  importJson(text,400);assert(ws43bLanguage()==2 && writes==beforeOmission);
 }
 importJson("{\"waveshare43b\":{\"language\":\"pl\"}}",200);checkGet("pl");
 importJson("{\"waveshare43b\":{\"language\":\"en\"}}",200);checkGet("en");
 importJson("{\"waveshare43b\":{\"language\":\"de\"}}",200);checkGet("de");
 loadWs43bLanguage();checkGet("de");
 const auto beforeFailure=ws43bLanguageRevision();writeOk=false;
 importJson("{\"waveshare43b\":{\"language\":\"pl\"}}",500);
 assert(ws43bLanguage()==2 && ws43bLanguageRevision()==beforeFailure);checkGet("de");
}
'''
        compile_and_run(self, harness, [HERE / 'vendor/ArduinoJson-7.4.3/src'])

    def test_german_catalog_preserves_placeholders_entities_and_whitespace(self):
        catalog = json.loads((HERE / 'locale/de.json').read_text())
        self.assertGreater(len(catalog), 300)
        polish = json.loads((HERE / 'locale/pl.json').read_text())
        self.assertEqual(set(catalog), set(polish), 'Only reviewed WebUI text keys may enter the runtime JS catalog')
        # UI percentages such as "10% steps" are not printf formats. A format
        # space flag would misread those fragments; real firmware formats here
        # use no such flag. Also check literal percent counts independently.
        formats = re.compile(r'%[A-Z][A-Z0-9_]*%|%%|%[+\-#0]*\d*(?:\.\d+)?(?:hh|ll|[hljztL])?[diuoxXfFeEgGaAcspn]')
        entities = re.compile(r'&(?:#[0-9]+|#x[0-9A-Fa-f]+|[A-Za-z][A-Za-z0-9]+);')
        for source, german in catalog.items():
            with self.subTest(source=source):
                self.assertIsInstance(german, str)
                self.assertTrue(german)
                self.assertEqual(formats.findall(source), formats.findall(german))
                self.assertEqual(source.count('%'), german.count('%'))
                self.assertEqual(entities.findall(source), entities.findall(german))
                self.assertEqual(re.findall(r'</?[A-Za-z][^>]*>', source), re.findall(r'</?[A-Za-z][^>]*>', german))
                self.assertEqual(re.match(r'\s*', source)[0], re.match(r'\s*', german)[0])
                self.assertEqual(re.search(r'\s*$', source)[0], re.search(r'\s*$', german)[0])
        for key in ('BambuHelper Setup', 'Configuration', 'Invalid language'):
            self.assertIn(key, catalog)
            self.assertNotEqual(key, catalog[key])

    def test_all_native_translations_keep_printf_arguments(self):
        # Native-only words must not be inserted in the broad JS translation
        # catalog: some, e.g. layer/none, are protocol/CSS values in the portal.
        literal = r'"(?:[^"\\]|\\.)*"'
        calls = re.compile(r'ws43bText\(\s*(' + literal + r')\s*,\s*(' + literal +
                           r')\s*,\s*(' + literal + r')\s*\)')
        formats = re.compile(r'%[A-Z][A-Z0-9_]*%|%%|%[+\-#0]*\d*(?:\.\d+)?(?:hh|ll|[hljztL])?[diuoxXfFeEgGaAcspn]')
        import ast
        for filename in ('src/display_ws43b.cpp', 'src/ws43b_weather.cpp'):
            source = (ROOT / filename).read_text()
            matches = calls.findall(source)
            self.assertEqual(len(matches), source.count('ws43bText('), filename)
            self.assertGreater(len(matches), 20)
            for pl, en, de in matches:
                english, german = ast.literal_eval(en), ast.literal_eval(de)
                with self.subTest(file=filename, english=english):
                    self.assertTrue(german)
                    self.assertEqual(formats.findall(english), formats.findall(german))
                    self.assertEqual(english.count('%'), german.count('%'))
                    self.assertNotIn('ẞ', german)

    def test_german_glyphs_in_actual_ui_font_arrays(self):
        required = set('äöüÄÖÜß')
        expected = {'ws43b_dash_14','ws43b_dash_18','ws43b_dash_24','ws43b_dash_30',
                    'ws43b_inter_body','ws43b_v2_12','ws43b_v2_13','ws43b_v2_b14',
                    'ws43b_v2_b15','ws43b_v2_b16','ws43b_v2_b17','ws43b_v2_b25'}
        found = set()
        for filename in ('ws43b_modern.h', 'ws43b_dashboard_v2.h'):
            text = (ROOT / 'include/fonts' / filename).read_text()
            for name, table in re.findall(r'const uint8_t (\w+)\[\].*?\{(.*?)\};', text, re.S):
                if name not in expected:
                    continue
                data = bytes(int(v, 16) for v in re.findall(r'0x([0-9a-f]{2})', table))
                n, version, size, _, asc, desc = struct.unpack_from('>6I', data)
                self.assertEqual(version, 6)
                records = [struct.unpack_from('>IIIIiiI', data, 24 + i * 28) for i in range(n)]
                chars = {chr(r[0]): r for r in records}
                self.assertTrue(required <= chars.keys(), (name, required - chars.keys()))
                self.assertEqual(24 + n * 28 + sum(r[1] * r[2] for r in records), len(data))
                found.add(name)
                if name == 'ws43b_dash_18':
                    for phrase, width in [('< Einstellungen', 150), ('Deutsch', 312),
                                           ('Sprache', 320), ('Sprache und Daten', 256)]:
                        self.assertTrue(set(phrase) <= chars.keys())
                        self.assertLess(sum(chars[c][3] for c in phrase), width)
        self.assertEqual(found, expected)


if __name__ == '__main__':
    unittest.main()
