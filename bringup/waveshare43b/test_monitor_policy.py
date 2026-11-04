#!/usr/bin/env python3
"""Offline policy checks using the actual C++ route-registration/send functions.

Uses temporary C++ stubs only; no serial port, network, firmware or credentials.
"""
import pathlib
import re
import shutil
import subprocess
import tempfile
import unittest

REPO = pathlib.Path(__file__).resolve().parents[2]


def function_span(source, start, end):
    return source[source.index(start):source.index(end, source.index(start))]


def native_run(source, monitor):
    compiler = shutil.which("c++") or shutil.which("clang++")
    if not compiler:
        raise unittest.SkipTest("A native C++ compiler is required")
    with tempfile.TemporaryDirectory(prefix="bambu-monitor-policy-") as folder:
        cpp = pathlib.Path(folder) / "policy.cpp"
        binary = pathlib.Path(folder) / "policy"
        cpp.write_text(source)
        subprocess.run([compiler, "-std=c++17", f"-DBAMBU_MONITOR_ONLY={monitor}",
                        "-DHAS_CLOUD_LOGIN=1", "-DENABLE_OTA_AUTO=1", str(cpp),
                        "-o", str(binary)], check=True, capture_output=True, text=True)
        subprocess.run([str(binary)], check=True, capture_output=True, text=True)


class MonitorPolicyTests(unittest.TestCase):
    def test_monitor_route_allowlist_and_legacy_routes(self):
        src = (REPO / "src/web_server.cpp").read_text()
        init = function_span(src, "void initWebServer() {", "void handleWebServer()")
        handlers = set(re.findall(r"\b(handle\w+)\b", init))
        declarations = "\n".join("void " + h + "() {}" for h in sorted(handlers)
                                 if h != "handleMonitorBlocked")
        denied = function_span(src, "static void handleMonitorBlocked() {", "\n#endif")
        harness = r'''
#include <cassert>
#include <map>
#include <string>
#include <utility>
using Handler = void(*)();
enum { HTTP_GET=0, HTTP_POST=1 };
struct MockServer {
  std::map<std::pair<std::string,int>,Handler> routes;
  Handler missing=nullptr;
  int status=0;
  void sendHeader(const char*,const char*) {}
  void send(int code,const char*,const char*) { status=code; }
  void on(const char* path,int method,Handler fn) { routes[{path,method}]=fn; }
  void on(const char* path,int method,Handler fn,Handler upload) { on(path,method,fn); }
  void onNotFound(Handler h) { missing=h; }
  void collectHeaders(const char**,int) {}
  void begin() {}
  Handler get(const char* path,int method) {
    auto p=routes.find({path,method});return p==routes.end()?missing:p->second;
  }
} server;
struct MockSerial { void println(const char*) {} } Serial;
'''
        harness += declarations + "\n" + denied + "\n" + init
        harness += r'''
int main() {
  initWebServer();
  assert(server.get("/save/printer",HTTP_POST)==handleSavePrinter);
  assert(server.get("/save/wifi",HTTP_POST)==handleSaveWifi);
  assert(server.get("/status",HTTP_GET)==handleStatus);
  assert(server.get("/printer/config",HTTP_GET)==handlePrinterConfig);
#if BAMBU_MONITOR_ONLY
  assert(server.routes.size()==10);
  const char* blocked[]={"/power/control","/save/power","/light/set","/light/config",
    "/buzzer/test","/led/preview","/led/test","/save/rotation","/save/gaugelayout",
    "/debug","/debug/toggle","/save/toggle","/settings/export","/settings/import",
    "/ota/upload","/ota/auto","/ota/rollback","/cloud/login/selftest","/reset"};
  for(auto path:blocked) {
    assert(server.get(path,HTTP_GET)==handleMonitorBlocked);
    assert(server.get(path,HTTP_POST)==handleMonitorBlocked);
    server.status=0;
    server.get(path,HTTP_POST)();
    assert(server.status==403);
  }
#else
  assert(server.get("/power/control",HTTP_POST)==handlePowerControl);
  assert(server.get("/led/preview",HTTP_POST)==handleLedPreview);
  assert(server.get("/ota/upload",HTTP_POST)==handleOtaFinish);
  assert(server.get("/ota/auto",HTTP_POST)==handleOtaAuto);
  assert(server.get("/settings/export",HTTP_GET)==handleSettingsExport);
#endif
}
'''
        native_run(harness, 1)
        native_run(harness, 0)

    def test_plug_command_boundary_has_no_network_dependency(self):
        src = (REPO / "src/tasmota.cpp").read_text()
        fn = function_span(src, "static bool sendPowerCommand(", "static bool sendPowerOff(")
        # No HTTP/socket/settings symbols are stubbed: a monitor build must not
        # compile any of the relay-network implementation at this final boundary.
        harness = "#include <cstdint>\n#include <cassert>\n" + fn
        harness += "\nint main(){for(int i=0;i<256;++i){assert(!sendPowerCommand(i,false));assert(!sendPowerCommand(i,true));}}\n"
        native_run(harness, 1)

    def test_portal_javascript_syntax(self):
        node = shutil.which("node")
        if not node:
            raise unittest.SkipTest("Node required for syntax checking")
        src = (REPO / "src/web_server.cpp").read_text()
        page = function_span(src, 'R"MONITOR(', ')MONITOR";')
        script = re.search(r"<script>(.*?)</script>", page, re.S).group(1)
        with tempfile.TemporaryDirectory(prefix="bambu-monitor-js-") as folder:
            js = pathlib.Path(folder) / "monitor.js"
            js.write_text(script)
            subprocess.run([node, "--check", str(js)], check=True, capture_output=True, text=True)


if __name__ == "__main__":
    unittest.main()
