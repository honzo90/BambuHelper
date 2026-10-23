"""Synthetic integration checks; no GitHub/device requests or firmware writes."""
from pathlib import Path
import subprocess
import unittest
import json
import sys
from test_full_webui import function

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import localize_web

NO = 'No stable release has been published for this channel yet.'
YES = 'Update available!'



class OtaChannel(unittest.TestCase):
    def test_js_channel(self):
        source = (ROOT / 'web/app.js').read_text()
        for lang in ('en', 'pl'):
            with self.subTest(lang=lang):
                src = localize_web.javascript(source) if lang == 'pl' else source
                js = '\n'.join(function(src, 'function ' + name + '(') for name in ('compareWs43bVersions', 'selectWs43bRelease', 'changeWs43bOtaChannel', 'checkWs43bUpdates', 'checkForUpdates'))
                expected = [NO, YES] if lang == 'en' else [localize_web.catalog()[NO], localize_web.catalog()[YES]]
                harness = 'const labels=' + json.dumps(expected) + ';\n' + r'''
const assert=require('assert');
let fields={}, release={}, lastUrl='', _autoOtaUrl='', status=200;
let DEV={board:'ws_lcd_43b',fw:'v3.9.0',otaSlot:'3145728',flashMb:'16'};
const document={getElementById(id){return fields[id] ||= {style:{},textContent:''};}};
const fetch=async(url)=>{
 lastUrl=url;
 if(status===-1) throw new Error('fetch failed');
 return {ok:status===200,status,json:async()=>release};
};
''' + js + r'''
async function check(nextStatus){
 status=nextStatus;
 release={tag_name:'v3.9.1',draft:false,prerelease:false,assets:[{name:'BambuHelper-ws_lcd_43b-v3.9.1-ota.bin',size:2400000,browser_download_url:'https://github.com/honzo90/BambuHelper/releases/download/v3.9.1/BambuHelper-ws_lcd_43b-v3.9.1-ota.bin'}],published_at:'2026-10-11'};
 checkForUpdates();
 await new Promise(r=>setImmediate(r));
 return fields.updateResult.textContent;
}
(async()=>{
 assert.equal(await check(200), labels[1]);
 assert.equal(lastUrl, 'https://api.github.com/repos/honzo90/BambuHelper/releases/latest');
 assert.equal(_autoOtaUrl, 'https://github.com/honzo90/BambuHelper/releases/download/v3.9.1/BambuHelper-ws_lcd_43b-v3.9.1-ota.bin');
 assert.equal(fields.updateInfo.style.display, 'block');
 assert.notEqual(fields.installBtn.style.display, 'none');

 assert.equal(await check(404), labels[0]);
 assert.equal(fields.updateResult.style.color, 'var(--info)');
 assert.equal(_autoOtaUrl, '');
 assert.equal(fields.updateInfo.style.display, 'none');
 assert.equal(fields.installBtn.style.display, 'none');
 assert.equal(fields.updateLink.style.display, 'none');

 await check(403);
 assert.equal(fields.updateResult.style.color, 'var(--danger)');
 assert.equal(_autoOtaUrl, '');
 assert.notEqual(fields.updateResult.textContent, labels[0]);

 await check(-1);
 assert.equal(fields.updateResult.style.color, 'var(--danger)');
 assert.equal(_autoOtaUrl, '');
 assert.notEqual(fields.updateResult.textContent, labels[0]);

 DEV.board='esp32s3';
 assert.notEqual(await check(404), labels[0]);
 assert.equal(lastUrl, 'https://api.github.com/repos/Keralots/BambuHelper/releases/latest');
 assert.equal(fields.updateResult.style.color, 'var(--danger)');
})().catch(e=>{console.error(e);process.exit(1)});
'''
                subprocess.run(['node', '-e', harness], check=True)


class OtaBackend(unittest.TestCase):
    def test_cpp_channel(self):
        import tempfile

        actual = function(
            (ROOT / 'src/web_server.cpp').read_text(),
            'static bool isExpectedOtaAssetUrl('
        )

        harness = r"""
#include <string>
#include <algorithm>
#include <cstdlib>

struct String : std::string {
    using std::string::string;
    String(const std::string& s) : std::string(s) {}

    bool startsWith(const std::string& s) const {
        return rfind(s, 0) == 0;
    }

    bool endsWith(const std::string& s) const {
        return size() >= s.size() && compare(size() - s.size(), s.size(), s) == 0;
    }

    int indexOf(char c) const {
        auto p = find(c);
        return p == npos ? -1 : static_cast<int>(p);
    }

    int lastIndexOf(char c) const {
        auto p = rfind(c);
        return p == npos ? -1 : static_cast<int>(p);
    }

    String substring(unsigned a) const {
        return substr(std::min<size_t>(a, size()));
    }

    String substring(unsigned a, unsigned b) const {
        if (a > b) std::swap(a, b);
        a = std::min<size_t>(a, size());
        b = std::min<size_t>(b, size());
        return substr(a, b - a);
    }
};

""" + actual + r"""

int main(int argc, char** argv) {
    if (argc != 2) return 2;
    return isExpectedOtaAssetUrl(String(argv[1])) ? 0 : 1;
}
"""

        P = "https://github.com/honzo90/BambuHelper/releases/download/"
        F = "BambuHelper-ws_lcd_43b-v3.9.1-ota.bin"

        ws_valid = [P + "v3.9.1/" + F,
                    P + "v3.9.1-alpha.1/" + "BambuHelper-ws_lcd_43b-v3.9.1-alpha.1-ota.bin",
                    P + "v3.9.1-beta.1/" + "BambuHelper-ws_lcd_43b-v3.9.1-beta.1-ota.bin"]
        ws_invalid = [
            "https://github.com/Keralots/BambuHelper/releases/download/v3.9.1/" + F,
            "https://github.com/honzo90/Other/releases/download/v3.9.1/" + F,
            "http://github.com/honzo90/BambuHelper/releases/download/v3.9.1/" + F,
            "https://example.com/honzo90/BambuHelper/releases/download/v3.9.1/" + F,
            "https://objects.githubusercontent.com/honzo90/BambuHelper/releases/download/v3.9.1/" + F,
            "https://release-assets.githubusercontent.com/honzo90/BambuHelper/releases/download/v3.9.1/" + F,
            P + "v3.9.1/" + F + "?x=1",
            P + "v3.9.1/" + F + "#frag",
            P + "v3.9.1/" + F + "%20",
            P + "v3.9.1/" + F + "\\x",
            P + F,
            P + "/" + F,
            P + "extra/v3.9.1/" + F,
            P + "./" + F,
            P + "../" + F,
            P + "%2e%2e/" + F,
            P + "v3.9.1/BambuHelper-esp32s3-v3.9.1-ota.bin",
            P + "v3.9.1/BambuHelper-ws_lcd_43b-v3.9.1-Full.bin",
            P + "v3.9.1/BambuHelper-ws_lcd_43b-ota.bin",
            P + "v3.9.1/BambuHelper-ws_lcd_43b-none-ota.bin",
        ]

        legacy_valid = [
            "https://github.com/Keralots/BambuHelper/releases/download/v3.9.1/BambuHelper-esp32s3-v3.9.1-ota.bin",
            "https://objects.githubusercontent.com/Keralots/BambuHelper/releases/download/v3.9.1/BambuHelper-esp32s3-v3.9.1-ota.bin",
            "https://release-assets.githubusercontent.com/Keralots/BambuHelper/releases/download/v3.9.1/BambuHelper-esp32s3-v3.9.1-ota.bin",
        ]
        legacy_invalid = [
            "https://github.com/Keralots/BambuHelper/releases/download/v3.9.1/BambuHelper-ws_lcd_43b-v3.9.1-ota.bin",
        ]

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "ota_validator.cpp"
            source.write_text(harness)

            ws_exe = tmp_path / "ota_ws"
            legacy_exe = tmp_path / "ota_legacy"

            subprocess.run(
                [
                    "clang++",
                    "-std=c++17",
                    str(source),
                    "-o",
                    str(ws_exe),
                    "-DBOARD_IS_WS43B=1",
                    '-DBOARD_VARIANT="ws_lcd_43b"',
                ],
                check=True,
            )

            subprocess.run(
                [
                    "clang++",
                    "-std=c++17",
                    str(source),
                    "-o",
                    str(legacy_exe),
                    '-DBOARD_VARIANT="esp32s3"',
                ],
                check=True,
            )

            for url in ws_valid:
                with self.subTest(board="ws", url=url):
                    result = subprocess.run([str(ws_exe), url], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0)

            for url in ws_invalid:
                with self.subTest(board="ws", url=url):
                    result = subprocess.run([str(ws_exe), url], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 1)

            for url in legacy_valid:
                with self.subTest(board="legacy", url=url):
                    result = subprocess.run([str(legacy_exe), url], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0)

            for url in legacy_invalid:
                with self.subTest(board="legacy", url=url):
                    result = subprocess.run([str(legacy_exe), url], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 1)


if __name__ == '__main__':
    unittest.main()
