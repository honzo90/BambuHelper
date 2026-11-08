"""WebUI security: host / cross-site / PIN policy and how the firmware wires it in."""

import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
SRC = ROOT / "src"

POLICY = r"""
#include <cassert>
#include "ws43b_web_policy.h"
using namespace ws43b_web_policy;
int main(){
 const char *ip="10.0.0.5", *name="bambuhelper";
 // Host: the panel's IP or name, any port; empty Host from old tools passes.
 assert(hostAllowed("10.0.0.5",ip,name));
 assert(hostAllowed("10.0.0.5:80",ip,name));
 assert(hostAllowed("BambuHelper.local",ip,name));
 assert(hostAllowed("bambuhelper",ip,name));
 assert(hostAllowed("bambuhelper.fritz.box",ip,name));
 assert(hostAllowed("bambuhelper.lan:80",ip,name));
 assert(hostAllowed("bambuhelper.home.arpa",ip,name));
 assert(!hostAllowed("bambuhelper.box",ip,name));
 assert(!hostAllowed("bambuhelper.evil.example",ip,name));
 assert(!hostAllowed("bambuhelperlan",ip,name));
 assert(!hostAllowed("other.lan",ip,name));
 assert(hostAllowed("",ip,name));
 assert(hostAllowed(nullptr,ip,name));
 // DNS rebinding: a foreign name pointing at the panel is refused.
 assert(!hostAllowed("evil.example",ip,name));
 assert(!hostAllowed("bambuhelper.local.evil.example",ip,name));
 assert(!hostAllowed("10.0.0.50",ip,name));
 assert(!hostAllowed("10.0.0.5.evil.example",ip,name));
 assert(!hostAllowed("bambuhelper.localx",ip,name));
 assert(!hostAllowed("10.0.0.5/x",ip,name));
 // Cross-site: Origin, else Referer, must match the Host authority exactly.
 assert(originAllowed("http://10.0.0.5",nullptr,"10.0.0.5"));
 assert(originAllowed("http://bambuhelper.local","","bambuhelper.local"));
 assert(originAllowed("","http://10.0.0.5/#settings","10.0.0.5"));
 assert(originAllowed("",nullptr,"10.0.0.5"));            // curl, scripts
 assert(!originAllowed("http://evil.example","","10.0.0.5"));
 assert(!originAllowed("null","","10.0.0.5"));
 assert(!originAllowed("http://10.0.0.5:8080","","10.0.0.5"));
 assert(!originAllowed("http://10.0.0.50","","10.0.0.5"));
 assert(!originAllowed("","http://evil.example/?http://10.0.0.5","10.0.0.5"));
 assert(!originAllowed("http://evil.example","http://10.0.0.5/","10.0.0.5")); // Origin wins
 // PIN: empty = off, else 4-8 digits.
 assert(pinValid("")); assert(pinValid("1234")); assert(pinValid("12345678"));
 assert(!pinValid("123")); assert(!pinValid("123456789"));
 assert(!pinValid("12a4")); assert(!pinValid(" 1234")); assert(!pinValid(nullptr));
 return 0;
}
"""


class Policy(unittest.TestCase):
    def test_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "p.cpp"
            src.write_text(POLICY)
            exe = Path(tmp) / "p"
            subprocess.run(
                [
                    "clang++",
                    "-std=c++17",
                    "-Wall",
                    "-Werror",
                    "-I",
                    str(SRC),
                    str(src),
                    "-o",
                    str(exe),
                ],
                check=True,
            )
            subprocess.run([str(exe)], check=True)


class Wiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.web = (SRC / "web_server.cpp").read_text()
        cls.gate = (SRC / "ws43b_web_security.cpp").read_text()

    def ws43b_routes(self):
        """Route table of the full (non monitor-only) 4.3B WebUI."""
        init = self.web.split("void initWebServer() {", 1)[1]
        return init.split("server.onNotFound(handleMonitorBlocked);", 1)[1]

    def test_gate_installed_as_middleware_with_origin_headers(self):
        init = self.web.split("void initWebServer() {", 1)[1]
        self.assertIn("ws43b_web_security::begin(server);", init)
        self.assertIn('{"X-MD5", "Origin", "Referer"}', init)
        self.assertIn("server.addMiddleware(", self.gate)
        self.assertIn("return allow(s) ? next() : true;", self.gate)

    def test_ota_upload_checked_before_first_flash_write(self):
        upload = self.web.split("static void handleOtaUpload() {", 1)[1]
        start = upload.split("UPLOAD_FILE_WRITE", 1)[0]
        gate = start.index("ws43b_web_security::allow(server, false)")
        self.assertLess(gate, start.index("Update.begin("))
        self.assertLess(gate, start.index("disconnectBambuMqtt()"))

    def test_factory_reset_is_post_only(self):
        routes = self.ws43b_routes()
        self.assertIn('server.on("/reset", HTTP_POST, handleReset);', routes)
        ws43b = routes.split("#if defined(BOARD_IS_WS43B)", 1)[1].split("#else", 1)[0]
        self.assertNotIn('"/reset", HTTP_GET', ws43b)
        app = (ROOT / "web" / "app.js").read_text()
        self.assertIn("fetch('/reset',{method:'POST'})", app)
        self.assertNotIn("location = '/reset'", app)

    def test_pin_route_and_storage(self):
        self.assertIn('server.on("/security/pin", HTTP_POST,', self.ws43b_routes())
        self.assertIn("pinValid(value.c_str())", self.gate)
        self.assertIn('"w43_pin"', self.gate)

    def test_export_has_no_access_code_on_ws43b(self):
        export = self.web.split("static void handleSettingsExport() {", 1)[1].split("\n}\n", 1)[0]
        guarded = re.search(
            r'#if !defined\(BOARD_IS_WS43B\)\s*p\["accessCode"\] = cfg\.accessCode;\s*#endif',
            export,
        )
        self.assertTrue(guarded, "accessCode must not be exported on 4.3B")

    def test_cloud_requests_never_retry_without_tls_verification(self):
        cloud = (SRC / "bambu_cloud.cpp").read_text()
        blocks = re.findall(r"#if ([^\n]*)\n(?:(?!#endif).)*setInsecure\(\)", cloud, re.S)
        self.assertEqual(len(blocks), cloud.count("setInsecure()"), "unguarded setInsecure()")
        for block in blocks:
            self.assertIn("!defined(BOARD_IS_WS43B)", block)

    def test_panel_shows_pin_for_recovery(self):
        display = (SRC / "display_ws43b.cpp").read_text()
        screen = display.split("void generalSettingsScreen() {", 1)[1].split("\n}\n", 1)[0]
        self.assertIn("ws43b_web_security::pin()", screen)


if __name__ == "__main__":
    unittest.main()
