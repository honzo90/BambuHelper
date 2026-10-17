"""Synthetic Improv protocol/privacy tests. These never open a serial port."""
import contextlib
import importlib.util
import io
from pathlib import Path
import sys
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[1] / "configure_wifi.py"
spec = importlib.util.spec_from_file_location("configure_wifi", PATH)
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)

SSID = "synthetic-private-ssid"
PASSWORD = "synthetic-private-password"


def reply(command, values):
    data = b"".join(bytes((len(v),)) + v for v in values)
    return setup.frame(setup.RPC_RESPONSE, bytes((command, len(data))) + data)


def info(firmware=setup.FIRMWARE, version=setup.FIRMWARE_VERSION, chip=setup.CHIP, name=b"BambuHelper-ABCD"):
    return reply(setup.GET_DEVICE_INFO, [firmware, version, chip, name])


def state(value):
    return setup.frame(setup.CURRENT_STATE, bytes((value,)))


def success():
    return state(3) + setup.frame(setup.ERROR_STATE, b"\0") + state(4) + reply(1, [b"http://192.168.1.123/"])


class Port:
    def __init__(self, responses):
        self.responses = list(responses)
        self.buffer = bytearray()
        self.writes = []
        self.elapsed = 0

    def read(self, length):
        self.elapsed += 0.05
        result = bytes(self.buffer[:length])
        del self.buffer[:length]
        return result

    def write(self, data):
        self.writes.append(bytes(data))
        if self.responses:
            self.buffer.extend(self.responses.pop(0))
        return len(data)

    def flush(self):
        pass

    def clock(self):
        return self.elapsed


def client(responses):
    port = Port(responses)
    return setup.Client(port, clock=port.clock), port


def commands(port):
    return [value[9] for value in port.writes]


class ImprovTests(unittest.TestCase):

    def test_actual_vendored_parser_accepts_host_frames_in_sequence(self):
        compiler = shutil.which("c++") or shutil.which("clang++")
        if not compiler:
            self.skipTest("Native C++ compiler required")
        repo = PATH.parents[3]
        vendor = repo / "lib/ImprovWiFi/src"
        source = (vendor / "ImprovWiFiLibrary.cpp").read_text()
        def section(start, end):
            begin = source.index(start)
            return source[begin:source.index(end, begin)]
        methods = section("void ImprovWiFi::handleSerial()", "void ImprovWiFi::onErrorCallback")
        methods += section("bool ImprovWiFi::parseImprovSerial(", "ImprovTypes::ImprovCommand ImprovWiFi::parseImprovData(const std::vector")
        methods += section("ImprovTypes::ImprovCommand ImprovWiFi::parseImprovData(const uint8_t", "void ImprovWiFi::setState(")
        ssid, password = b"n" * 32, b"a" * 64
        traffic = setup.rpc(3) + setup.rpc(2) + setup.rpc(1, (ssid, password)) + setup.rpc(3)
        harness = r'''
#include <cassert>
#include <deque>
#include "ImprovTypes.h"
struct FakeStream {
  std::deque<uint8_t> bytes;
  size_t available() { return bytes.size(); }
  uint8_t read() { auto v=bytes.front();bytes.pop_front();return v; }
};
class ImprovWiFi {
public:
  uint8_t _buffer[128]{};
  uint8_t _position=0;
  FakeStream* serial;
  std::vector<ImprovTypes::ImprovCommand> received;
  unsigned errors=0;
  void handleSerial();
  bool parseImprovSerial(size_t,uint8_t,const uint8_t*);
  ImprovTypes::ImprovCommand parseImprovData(const uint8_t*,size_t,bool);
  bool onCommandCallback(ImprovTypes::ImprovCommand cmd) { received.push_back(cmd);return true; }
  void onErrorCallback(ImprovTypes::Error) { ++errors; }
};
''' + methods
        harness += "\nint main(){FakeStream s; s.bytes={" + ",".join(str(b) for b in traffic) + "};\n"
        harness += r'''
ImprovWiFi library; library.serial=&s;
while(s.available()) library.handleSerial();
assert(library.errors==0 && library.received.size()==4);
assert(library.received[0].command==ImprovTypes::GET_DEVICE_INFO);
assert(library.received[1].command==ImprovTypes::GET_CURRENT_STATE);
assert(library.received[2].command==ImprovTypes::WIFI_SETTINGS);
assert(library.received[2].ssid==std::string(32,'n'));
assert(library.received[2].password==std::string(64,'a'));
assert(library.received[3].command==ImprovTypes::GET_DEVICE_INFO);
assert(library._position==0);
}
'''
        with tempfile.TemporaryDirectory(prefix="bambu-improv-vendor-") as folder:
            cpp, binary = Path(folder) / "vendor.cpp", Path(folder) / "vendor"
            cpp.write_text(harness)
            subprocess.run([compiler, "-std=c++20", "-I", str(vendor), str(cpp), "-o", str(binary)],
                           check=True, capture_output=True, text=True)
            subprocess.run([str(binary)], check=True, capture_output=True, text=True)

    def test_golden_get_commands_and_separator(self):
        # Literal frames match vendored Improv v1 (sum includes header).
        self.assertEqual(setup.rpc(3), b"IMPROV\x01\x03\x02\x03\x00\xe6\n")
        self.assertEqual(setup.rpc(2), b"IMPROV\x01\x03\x02\x02\x00\xe5\n")
        for cmd in (0, 4, 255):
            with self.assertRaises(setup.SetupError):
                setup.rpc(cmd)

    def test_wifi_frame_utf8_lengths_and_checksum(self):
        values = setup.credentials("sieć-test", "hasło-test")
        data = setup.rpc(1, values)
        self.assertEqual(len(data), 11 + 2 + 2 + len(values[0]) + len(values[1]))
        self.assertEqual(sum(data[:-2]) & 255, data[-2])
        self.assertEqual(data[9], 1)
        self.assertEqual(data[11], len(values[0]))
        self.assertLess(len(data), 128)

    def test_decoder_fragmentation_noise_and_multiple_frames(self):
        decoder, results = setup.Decoder(), []
        traffic = b"Improv: " + PASSWORD.encode() + b"\n" + state(2) + info()
        for byte in traffic:
            results.extend(decoder.feed(bytes((byte,))))
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0], (setup.CURRENT_STATE, b"\2"))
        self.assertEqual(setup.identity(results[1][1])[0], setup.FIRMWARE)
        self.assertLessEqual(len(decoder.buffer), 5)

    def test_bad_checksum_version_type_and_state_length(self):
        corrupt = bytearray(state(2)); corrupt[-1] ^= 1
        wrong_version = bytearray(state(2)); wrong_version[6] = 2
        wrong_type = setup.frame(setup.RPC, b"\3\0")
        bad_length = setup.frame(setup.CURRENT_STATE, b"\2\2")
        for value in (corrupt, wrong_version, wrong_type, bad_length):
            with self.subTest(value_type=len(value)), self.assertRaises(setup.SetupError):
                setup.Decoder().feed(value)

    def test_malformed_rpc_fields_rejected_without_contents(self):
        for data in (b"", b"\3", b"\2\0", b"\3\4\x0fabc", b"\3\1\x05"):
            with self.assertRaises(setup.SetupError):
                setup.response(data, 3)

    def test_strict_application_version_chip_identity(self):
        for raw in (info(firmware=b"BambuHelper"), info(version=b"v3.8.4"),
                    info(chip=b"ESP32"), info(name=b"injected\n" + PASSWORD.encode())):
            c, p = client([raw])
            with self.assertRaises(setup.SetupError) as error:
                c.configure(SSID, PASSWORD)
            self.assertEqual(commands(p), [3])
            self.assertNotIn(PASSWORD, str(error.exception))

    def test_no_wifi_before_authorized_identity(self):
        c, p = client([])
        with self.assertRaises(setup.SetupError):
            c.send(1, (b"test", b"password"))
        self.assertEqual(p.writes, [])
        c.verified = (setup.FIRMWARE, setup.FIRMWARE_VERSION, setup.CHIP, b"BambuHelper-ABCD")
        with self.assertRaises(setup.SetupError):
            c.send(1, (b"test", b"password"))
        self.assertEqual(p.writes, [])

    def test_success_single_wifi_command_no_secret_output(self):
        c, p = client([info(), state(2), info(), state(2), success()])
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            c.identify(); self.assertIsNone(c.current_state())
            self.assertEqual(c.configure(SSID, PASSWORD), "http://192.168.1.123/")
        self.assertEqual(commands(p), [3, 2, 3, 2, 1])
        self.assertEqual(output.getvalue(), "")
        with self.assertRaises(setup.SetupError):
            c.send(1, (b"test", b"password"))
        self.assertEqual(commands(p).count(1), 1)

    def test_existing_connection_cannot_be_overwritten(self):
        c, p = client([info(), state(4) + reply(2, [b"http://192.168.1.2/"])])
        with self.assertRaises(setup.SetupError):
            c.configure(SSID, PASSWORD)
        self.assertEqual(commands(p), [3, 2])

    def test_unsolicited_response_wrong_order_and_command(self):
        for bad in (state(4), reply(4, [PASSWORD.encode()]), state(2) + success()):
            c, p = client([info(), bad])
            with self.assertRaises(setup.SetupError):
                c.configure(SSID, PASSWORD)
            self.assertNotIn(1, commands(p))
        for result in (state(4) + reply(1, [b"http://192.168.1.2/"]),
                       state(3) + state(0) + setup.frame(2, b"\3"),
                       state(3) + setup.frame(2, b"\0") + state(4) + reply(2, [b"http://192.168.1.2/"])):
            c, p = client([info(), state(2), result])
            with self.assertRaises(setup.SetupError):
                c.configure(SSID, PASSWORD)
            self.assertEqual(commands(p).count(1), 1)

    def test_truncated_frame_and_timeout_do_not_send_credentials(self):
        for raw in (b"", info()[:-1], state(2)):
            c, p = client([raw])
            with self.assertRaises(setup.SetupError):
                c.configure(SSID, PASSWORD)
            self.assertEqual(commands(p), [3])

    def test_device_changed_after_private_prompt(self):
        c, p = client([info(), info(name=b"BambuHelper-1234")])
        c.identify()
        with self.assertRaises(setup.SetupError):
            c.configure(SSID, PASSWORD)
        self.assertEqual(commands(p), [3, 3])

    def test_credential_limits_control_characters_and_exact_bytes(self):
        for name, secret in (("", PASSWORD), ("ą" * 17, PASSWORD), ("a\n", PASSWORD),
                             (SSID, "short"), (SSID, "x" * 64), (SSID, "pass\0word")):
            with self.assertRaises(setup.SetupError) as error:
                setup.credentials(name, secret)
            self.assertNotIn(PASSWORD, str(error.exception))
        self.assertEqual(setup.credentials("  ssid  ", "  password  "), (b"  ssid  ", b"  password  "))
        self.assertEqual(setup.credentials("a" * 32, "f" * 64), (b"a" * 32, b"f" * 64))
        self.assertEqual(setup.credentials(SSID, "")[1], b"")

    def test_url_is_numeric_http_only_and_not_an_instruction(self):
        for value in (b"https://example.com/", b"http://user:secret@192.168.1.2/", b"http://192.168.1.2/?" + PASSWORD.encode(),
                      b"http://127.0.0.1/", b"http://0.0.0.0/", b"http://192.168.1.2/\n" + PASSWORD.encode()):
            with self.assertRaises(setup.SetupError) as error:
                setup.portal_url(reply(1, [value])[9:-1], 1)
            self.assertNotIn(PASSWORD, str(error.exception))

    def test_cli_rejects_secret_arguments_without_echo(self):
        output = io.StringIO()
        with contextlib.redirect_stderr(output), self.assertRaises(SystemExit):
            setup.main(["--ssid", SSID, "--password", PASSWORD])
        self.assertNotIn(SSID, output.getvalue())
        self.assertNotIn(PASSWORD, output.getvalue())

    def test_non_private_terminal_fails_before_fallback_input(self):
        def warn(_):
            import warnings
            warnings.warn("hidden-test", setup.getpass.GetPassWarning)
        with patch.object(setup.getpass, "getpass", warn), self.assertRaises(setup.SetupError):
            setup.private_input("prompt")


if __name__ == "__main__":
    unittest.main()
