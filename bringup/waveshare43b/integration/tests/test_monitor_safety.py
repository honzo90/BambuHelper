"""Offline checks of the actual MQTT translation unit after preprocessing.

No sockets, serial ports, payload captures or printer credentials are used.
"""
import re
import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
SOURCE = REPO / 'src/bambu_mqtt.cpp'


def preprocess(monitor, board=False):
    # Preprocessing does not need declarations or dependency headers. Removing
    # includes lets us inspect every own-code path with both feature variants.
    source = re.sub(r'^\s*#include[^\n]*\n', '', SOURCE.read_text(), flags=re.M)
    result = subprocess.run(
        ['clang++', '-E', '-P', '-x', 'c++', f'-DBAMBU_MONITOR_ONLY={monitor}',
         '-DHAS_HMS_UI=1', '-DBOARD_HAS_PSRAM=1', *(['-DBOARD_IS_WS43B=1'] if board else []), '-'],
        input=source, text=True, capture_output=True, check=True)
    return result.stdout


def function_body(source, signature):
    start = source.index(signature)
    brace = source.index('{', start)
    depth = 1
    end = brace + 1
    while depth:
        if source[end] == '{':
            depth += 1
        elif source[end] == '}':
            depth -= 1
        end += 1
    return source[brace + 1:end - 1]


class MonitorSafety(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.monitor = preprocess(1)
        cls.normal = preprocess(0)

    def test_no_publish_survives_monitor_preprocessing(self):
        self.assertNotRegex(self.monitor, r'->\s*publish\s*\(')
        self.assertEqual(len(re.findall(r'->\s*publish\s*\(', self.normal)), 2)

    def test_no_mqtt_payload_or_identity_logging(self):
        self.assertNotRegex(self.monitor, r'\bSerial\s*\.\s*(print|printf|println|write)\s*\(')
        self.assertIn('Serial.printf', self.normal)

    def test_light_queue_and_task_refresh_are_inert(self):
        light = function_body(self.monitor, 'void requestLightCommand(')
        refresh = function_body(self.monitor, 'void requestCloudRefreshFromTask(')
        self.assertNotIn('g_lightCmdReq', light)
        self.assertNotIn('g_extRefreshReq', refresh)
        self.assertNotIn('sendLightCtrl(', self.monitor)
        self.assertIn('g_lightCmdReq', function_body(self.normal, 'void requestLightCommand('))

    def test_monitor_never_synthesizes_idle_from_staleness(self):
        handler = function_body(self.monitor, 'static void handleConn(')
        self.assertNotIn('GCODE_IDLE', handler)
        self.assertNotIn('requestPushall(', handler)
        self.assertIn('s.connected = isConnected', handler)
        self.assertIn('GCODE_IDLE', function_body(self.normal, 'static void handleConn('))

    def test_only_explicit_slot_zero_can_connect(self):
        enabled = function_body(self.monitor, 'static bool isPrinterSlotEnabled(')
        self.assertIn('if (slot != 0) return false', enabled)
        self.assertNotIn('if (slot != 0) return false', function_body(self.normal, 'static bool isPrinterSlotEnabled('))

    def test_monitor_cannot_relogin_using_an_old_stored_password(self):
        for symbol in ('tryStoredPasswordRelogin(', 'cloudLoginCanAutoRefresh(',
                       'cloudLoginRefreshStored('):
            self.assertNotIn(symbol, self.monitor)
            self.assertIn(symbol, self.normal)

    def test_session_reset_before_connected_exposed(self):
        self.assertIn('acceptMqttSession(c)', function_body(self.monitor, 'static void reconnectConn('))
        reconnect = function_body(self.monitor, 'static void acceptMqttSession(')
        self.assertLess(reconnect.index('.monitor.newSession()'), reconnect.index('.state.connected = true'))
        self.assertNotIn('.monitor.newSession()', self.normal)


if __name__ == '__main__':
    unittest.main()

class Ws43bReconnect(unittest.TestCase):
    def test_native_cache_is_reset_before_new_connection_exposed(self):
        body=function_body(preprocess(0,True),'static void acceptMqttSession(')
        self.assertLess(body.index('.monitor.newSession()'),body.index('.state.connected = true'))
        self.assertNotIn('.state.printing = false',body)
