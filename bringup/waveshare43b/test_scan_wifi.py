"""Synthetic scan protocol/privacy tests; never access real USB or Wi-Fi."""

from contextlib import redirect_stdout
import io
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import observe
import scan_wifi


BOOT = '12345678'
IDENTITY = 'SMOKE_ID waveshare43b-v4 800x480'
BOOT_RECORD = (
    'BOOT boot=12345678 reset=11 reset_name=USB flash=16777216 '
    'psram_physical=8388608 psram_heap=8388608 sdk=v5.5.5'
)
BEGIN = 'SCAN_BEGIN boot=12345678'


def result_record(total=3, matches=1, rssi=-54, channel=6, auth=3, elapsed=4200, boot=BOOT):
    return (
        f'SCAN_RESULT boot={boot} total={total} matches={matches} '
        f'best_rssi={rssi} best_channel={channel} best_auth={auth} elapsed_ms={elapsed}'
    )


class FakeClock:
    def __init__(self):
        self.now = 0

    def monotonic(self):
        return self.now


class FakePort:
    def __init__(self, clock, identity_lines, scan_lines):
        self.clock = clock
        self.identity_lines = identity_lines
        self.scan_lines = scan_lines
        self.pending = iter(())
        self.writes = []
        self.resets = 0

    def write(self, data):
        self.writes.append(data)
        if data == b'STATUS\n':
            self.pending = iter(self.identity_lines)
        elif data.startswith(b'SCAN\t'):
            self.pending = iter(self.scan_lines)
        else:
            raise AssertionError('Unexpected command')
        return len(data)

    def reset_input_buffer(self):
        self.resets += 1
        self.pending = iter(())

    def readline(self):
        self.clock.now += 0.5
        return (next(self.pending, '') + '\n').encode('utf-8')

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False


class ScanProtocolTests(unittest.TestCase):
    def run_scan(self, scan_lines, identity_lines=None, ssid='SYNTHETIC-PRIVATE-SSID'):
        clock = FakeClock()
        port = FakePort(
            clock, [IDENTITY, BOOT_RECORD] if identity_lines is None else identity_lines, scan_lines
        )
        log, output = io.StringIO(), io.StringIO()
        error, result = None, None
        with patch.object(scan_wifi.time, 'monotonic', clock.monotonic), redirect_stdout(output):
            try:
                result = scan_wifi.run_scan(port, log, ssid)
            except RuntimeError as exc:
                error = str(exc)
        return result, error, log.getvalue(), output.getvalue(), port

    def test_scan_parser_accepts_only_bounded_safe_numeric_records(self):
        for line in (
            BEGIN,
            result_record(),
            result_record(total=0, matches=0, rssi=0, channel=0, auth=-1),
            result_record(
                total=65535, matches=65535, rssi=-127, channel=14, auth=255, elapsed=0xFFFFFFFF
            ),
            'SCAN_REJECTED boot=12345678 reason=BUSY',
            'SCAN_REJECTED boot=12345678 reason=SSID',
            'SCAN_ERROR boot=12345678 stage=START code=-2147483648',
            'SCAN_ERROR boot=12345678 stage=POLL code=2147483647',
            'SCAN_ERROR boot=12345678 stage=TIMEOUT code=263',
        ):
            with self.subTest(line=line):
                self.assertTrue(observe.safe_record(line))
                self.assertEqual(observe.line_boot(line), BOOT)

    def test_scan_parser_rejects_inconsistent_bounds_or_private_fields(self):
        for line in (
            result_record(total=65536),
            result_record(matches=4),
            result_record(total=-1),
            result_record(rssi=-128),
            result_record(rssi=1),
            result_record(channel=0),
            result_record(channel=15),
            result_record(auth=-1),
            result_record(auth=256),
            result_record(elapsed=2**32),
            result_record(elapsed=-1),
            result_record(matches=0),
            result_record(matches=0, rssi=0, channel=0, auth=0),
            result_record(boot='1234567'),
            result_record() + ' ssid=SYNTHETIC-SECRET',
            result_record().replace('total=3', 'total=SYNTHETIC-SECRET'),
            'SCAN_BEGIN',
            'SCAN_BEGIN boot=12345678 ssid=SYNTHETIC-SECRET',
            'SCAN_REJECTED boot=12345678 reason=SYNTHETIC-SECRET',
            'SCAN_ERROR boot=12345678 stage=SSID code=0',
            'SCAN_ERROR boot=12345678 stage=START code=-2147483649',
            'SCAN_ERROR boot=12345678 stage=START code=2147483648',
        ):
            with self.subTest(line=line):
                self.assertFalse(observe.safe_record(line))

    def test_complete_matched_scan_sends_only_status_and_private_scan(self):
        result, error, log, output, port = self.run_scan([BEGIN, result_record()])
        self.assertIsNone(error)
        self.assertEqual(result['matches'], 1)
        self.assertEqual(result['best_channel'], 6)
        self.assertEqual(port.writes, [b'STATUS\n', b'SCAN\tSYNTHETIC-PRIVATE-SSID\n'])
        self.assertEqual(port.resets, 2)
        for secret in ('SYNTHETIC-PRIVATE-SSID', 'WIFI\t', 'START\n'):
            self.assertNotIn(secret, log + output)

    def test_all_visibility_outcomes_have_distinct_messages_without_pass(self):
        cases = [
            (dict(total=0, matches=0, rssi=0, channel=0, auth=-1), 'nie wykrył żadnego'),
            (dict(total=4, matches=0, rssi=0, channel=0, auth=-1), 'zgodnych z podanym SSID: 0'),
            (dict(total=4, matches=2, rssi=-42, channel=11, auth=3), 'RSSI=-42 dBm, kanał=11'),
        ]
        for kwargs, phrase in cases:
            with self.subTest(kwargs=kwargs):
                result, error, _, _, _ = self.run_scan([BEGIN, result_record(**kwargs)])
                self.assertIsNone(error)
                description = scan_wifi.describe_result(result)
                self.assertIn(phrase, description)
                self.assertIn('nie potwierdzenie połączenia Wi-Fi ani sprzętowy PASS', description)
                self.assertIn('nowy rozruch', description)
                self.assertIn('sieci ukrytej', description)

    def test_v1_v2_v3_do_not_receive_ssid(self):
        for version in (1, 2, 3):
            _, error, _, _, port = self.run_scan(
                [], [f'SMOKE_ID waveshare43b-v{version} 800x480', BOOT_RECORD]
            )
            self.assertIn('wymaga', error)
            self.assertEqual(port.writes, [b'STATUS\n'])

    def test_identity_or_boot_alone_cannot_authorize_ssid(self):
        for lines in (
            [IDENTITY],
            [BOOT_RECORD],
            ['SMOKE_ID waveshare43b-v4 1024x600', BOOT_RECORD],
        ):
            _, error, _, _, port = self.run_scan([], lines)
            self.assertIn('Brak pełnej identyfikacji', error)
            self.assertEqual(port.writes, [b'STATUS\n'])

    def test_scan_record_during_identification_is_unsolicited(self):
        _, error, _, _, port = self.run_scan([], [IDENTITY, BEGIN, BOOT_RECORD])
        self.assertIn('Nieoczekiwany', error)
        self.assertEqual(port.writes, [b'STATUS\n'])

    def test_result_before_begin_cannot_be_accepted(self):
        result, error, _, _, _ = self.run_scan([result_record(), BEGIN, result_record()])
        self.assertIsNone(result)
        self.assertIn('bez SCAN_BEGIN', error)

    def test_duplicate_begin_aborts(self):
        result, error, _, _, _ = self.run_scan([BEGIN, BEGIN, result_record()])
        self.assertIsNone(result)
        self.assertIn('Powtórzony', error)

    def test_changed_boot_from_any_relevant_record_aborts(self):
        for record in (
            BEGIN.replace(BOOT, '87654321'),
            result_record(boot='87654321'),
            BOOT_RECORD.replace(BOOT, '87654321'),
            'WIFI_TRACE boot=87654321 queued_dropped=0',
        ):
            result, error, _, _, _ = self.run_scan([BEGIN, record, result_record()])
            self.assertIsNone(result)
            self.assertIn('Restart', error)

    def test_changed_boot_during_identification_cannot_send_ssid(self):
        _, error, _, _, port = self.run_scan(
            [],
            [
                'WIFI_TRACE boot=87654321 queued_dropped=0',
                IDENTITY,
                BOOT_RECORD,
            ],
        )
        self.assertIn('Zmiana identyfikatora', error)
        self.assertEqual(port.writes, [b'STATUS\n'])

    def test_malformed_result_aborts_without_raw_usb_or_secret_in_log(self):
        result, error, log, output, _ = self.run_scan(
            [
                'random USB output password=SYNTHETIC-SECRET',
                BEGIN,
                result_record() + ' ssid=SYNTHETIC-SECRET',
                result_record(),
            ],
            ['boot rom password=SYNTHETIC-SECRET', IDENTITY, BOOT_RECORD],
        )
        self.assertIsNone(result)
        self.assertIn('Nieprawidłowy rekord', error)
        self.assertNotIn('SYNTHETIC-SECRET', log + output + error)
        self.assertNotIn('random USB', log + output)

    def test_rejection_errors_fatal_and_timeout_are_not_empty_success(self):
        cases = [
            (['SCAN_REJECTED boot=12345678 reason=BUSY'], 'świeży rozruch'),
            (['SCAN_REJECTED boot=12345678 reason=SSID'], 'nieprawidłowy SSID'),
            (['SCAN_ERROR boot=12345678 stage=START code=123'], 'etap=START, kod=123'),
            ([BEGIN, 'SCAN_ERROR boot=12345678 stage=POLL code=-1'], 'etap=POLL, kod=-1'),
            ([BEGIN, 'SCAN_ERROR boot=12345678 stage=TIMEOUT code=263'], 'etap=TIMEOUT, kod=263'),
            (['FATAL boot=12345678 reason=PSRAM_PATTERN'], 'FATAL'),
            (['COMMAND_REJECTED'], 'odrzucił'),
            ([], 'Brak pełnego wyniku'),
            ([BEGIN], 'Brak pełnego wyniku'),
        ]
        for lines, phrase in cases:
            with self.subTest(lines=lines):
                result, error, _, _, port = self.run_scan(lines)
                self.assertIsNone(result)
                self.assertIn(phrase, error)
                self.assertEqual(len(port.writes), 2, 'No resends/retries')

    def test_invalid_ssid_rejected_before_usb_status_or_upload(self):
        for ssid in ('', 'x' * 33, 'ą' * 17, 'a\tb', 'a\rb', 'a\nb', 'a\x00b'):
            _, error, log, output, port = self.run_scan([], ssid=ssid)
            self.assertIn('Nieprawidłowy SSID', error)
            self.assertEqual(port.writes, [])
            self.assertEqual(log + output, '')
        self.assertTrue(scan_wifi.valid_ssid('ą' * 16))
        self.assertTrue(scan_wifi.valid_ssid(' exact name '))

    def test_private_log_is_exclusive_and_owner_only_from_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / 'local'
            with patch.object(scan_wifi.time, 'strftime', return_value='synthetic'):
                logfile, handle = scan_wifi.open_private_log(folder)
                with handle:
                    handle.write('synthetic safe metadata\n')
                    self.assertEqual(stat.S_IMODE(logfile.stat().st_mode), 0o600)
                self.assertEqual(stat.S_IMODE(folder.stat().st_mode), 0o700)
                with self.assertRaises(FileExistsError):
                    scan_wifi.open_private_log(folder)
                self.assertEqual(logfile.read_text(), 'synthetic safe metadata\n')

    def test_list_never_opens_serial_or_prompts_for_ssid(self):
        output = io.StringIO()
        port = SimpleNamespace(
            device='/dev/cu.synthetic', description='Synthetic port', vid=0x303A, pid=0x1001
        )
        with (
            patch('sys.argv', ['scan_wifi.py', '--list']),
            patch.object(scan_wifi.list_ports, 'comports', return_value=[port]),
            patch.object(scan_wifi.serial, 'Serial') as serial_open,
            patch.object(scan_wifi.getpass, 'getpass') as prompt,
            redirect_stdout(output),
        ):
            scan_wifi.main()
        serial_open.assert_not_called()
        prompt.assert_not_called()
        self.assertIn('/dev/cu.synthetic', output.getvalue())

    def test_cli_waits_ten_seconds_then_fresh_identity_before_private_scan(self):
        clock = FakeClock()
        port = FakePort(clock, [IDENTITY, BOOT_RECORD], [BEGIN, result_record()])
        output = io.StringIO()

        def sleep(seconds):
            self.assertEqual(seconds, 10)
            self.assertEqual(port.writes, [], 'Identification must occur after the hotspot pause')
            clock.now += seconds

        with tempfile.TemporaryDirectory() as tmp:
            logfile = Path(tmp) / 'synthetic.log'
            with (
                patch('sys.argv', ['scan_wifi.py', '--port', '/dev/cu.synthetic']),
                patch.object(scan_wifi.getpass, 'getpass', return_value='SYNTHETIC-PRIVATE-SSID'),
                patch.object(scan_wifi.serial, 'Serial', return_value=port) as serial_open,
                patch.object(
                    scan_wifi, 'open_private_log', return_value=(logfile, logfile.open('w'))
                ),
                patch.object(scan_wifi.time, 'monotonic', clock.monotonic),
                patch.object(scan_wifi.time, 'sleep', side_effect=sleep) as pause,
                redirect_stdout(output),
            ):
                scan_wifi.main()
            pause.assert_called_once_with(10)
            serial_open.assert_called_once_with(
                port=None, baudrate=115200, timeout=1, write_timeout=3, exclusive=True
            )
            self.assertFalse(port.dtr)
            self.assertFalse(port.rts)
            self.assertEqual(port.writes, [b'STATUS\n', b'SCAN\tSYNTHETIC-PRIVATE-SSID\n'])
            self.assertEqual(port.resets, 2)
            self.assertIn('10 sekund', output.getvalue())
            self.assertIn('Hotspot osobisty', output.getvalue())
            self.assertIn('SCAN_HOST_END result=VISIBILITY_ONLY', logfile.read_text())
            self.assertNotIn('SYNTHETIC-PRIVATE-SSID', logfile.read_text() + output.getvalue())


if __name__ == '__main__':
    unittest.main()
