"""Synthetic host-side Wi-Fi tests; no serial ports, networks or real secrets."""

from contextlib import redirect_stdout
import io
import unittest
from unittest.mock import patch

import observe
from check_log import evaluate


def diag(wifi=0, boot='12345678', uptime_ms=5000):
    return (
        f'DIAG boot={boot} uptime_ms={uptime_ms} run_ms=0 wifi={wifi} '
        'wifi_ms=0 drops=0 heap=200000 min_heap=190000 largest=170000 '
        'psram_free=6500000 targets=0 touch_errors=0 memory_errors=0'
    )


def wifi_diag(status=6, reason=202, age=1000, boot='12345678'):
    return (
        f'WIFI_DIAG boot={boot} status={status} last_reason={reason} '
        f'reason_age_ms={age} disconnects=4 associations=1 got_ip_events=0'
    )


def wifi_event(seq=1, event='DISCONNECTED', reason=201, boot='12345678', uptime=1234):
    return f'WIFI_EVENT boot={boot} seq={seq} uptime_ms={uptime} event={event} reason={reason}'


def wifi_trace(dropped=0, boot='12345678'):
    return f'WIFI_TRACE boot={boot} queued_dropped={dropped}'


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def monotonic(self):
        return self.now


class FakePort:
    """Each read takes five simulated seconds, including an empty read."""

    def __init__(self, lines, clock):
        self.lines = iter(lines)
        self.clock = clock
        self.reads = 0

    def readline(self):
        self.clock.now += 5
        self.reads += 1
        return (next(self.lines, '') + '\n').encode('utf-8')


class WaitWifiTest(unittest.TestCase):
    def run_wait(self, lines, timeout=30):
        clock = FakeClock()
        port = FakePort(lines, clock)
        log, output = io.StringIO(), io.StringIO()
        failure = None
        with patch.object(observe.time, 'monotonic', clock.monotonic), redirect_stdout(output):
            try:
                observe.wait_wifi(port, log, timeout=timeout)
            except SystemExit as exc:
                failure = str(exc)
        return failure, log.getvalue(), output.getvalue(), port.reads

    def test_exact_v1_v2_v3_and_v4_identity_only(self):
        for version in (1, 2, 3, 4):
            line = f'SMOKE_ID waveshare43b-v{version} 800x480'
            self.assertIn(line, observe.SMOKE_IDS)
            self.assertTrue(observe.safe_record(line))
        for line in (
            'SMOKE_ID waveshare43b-v5 800x480',
            'SMOKE_ID waveshare43b-v2 1024x600',
            'SMOKE_ID waveshare43b-v20 800x480',
            'SMOKE_ID waveshare43b-v2 800x480 SYNTHETIC-SECRET',
            'SMOKE_ID waveshare43b-v2 800x480\n',
        ):
            self.assertNotIn(line, observe.SMOKE_IDS)
            self.assertFalse(observe.safe_record(line))

    def test_success_requires_confirmation_then_connected_diagnostic(self):
        failure, log, output, reads = self.run_wait(
            [
                diag(wifi=1),
                'WIFI_ACCEPTED',
                diag(wifi=0),
                diag(wifi=1),
            ]
        )
        self.assertIsNone(failure)
        self.assertEqual(reads, 4, 'An old connected record or ACK alone is insufficient')
        self.assertIn('WIFI_ACCEPTED', log)
        self.assertIn('Wi-Fi=1', output)

    def test_timeout_retains_disconnected_evidence_instead_of_empty_log(self):
        failure, log, output, _ = self.run_wait(['WIFI_ACCEPTED'] + [diag()] * 5)
        self.assertIn('nadal wifi=0', failure)
        self.assertIn('Test 10 minut nie rozpoczął się', failure)
        self.assertEqual(log.count('DIAG '), 5)
        self.assertIn('WIFI_ACCEPTED', log)
        self.assertIn('Wi-Fi=0', output)
        self.assertNotIn('RUN_BEGIN', log)

    def test_connected_records_without_ack_do_not_start_observation(self):
        failure, log, _, _ = self.run_wait([diag(wifi=1)] * 6)
        self.assertIn('Brak WIFI_ACCEPTED', failure)
        self.assertEqual(log.count('DIAG '), 6)

    def test_v2_begin_or_wifi_diag_never_replace_connected_diag(self):
        failure, log, output, reads = self.run_wait(
            [
                'WIFI_ACCEPTED',
                'WIFI_BEGIN boot=12345678 status=3',
                wifi_diag(status=3, reason=-1, age=-1),
                diag(),
                diag(),
                diag(),
            ]
        )
        self.assertIsNotNone(failure)
        self.assertIn('nadal wifi=0', failure)
        self.assertEqual(reads, 6)
        self.assertIn('WIFI_BEGIN', log)
        self.assertIn('WIFI_DIAG', log)
        self.assertIn('nie końcowy wynik', output)

    def test_v2_without_ack_cannot_connect(self):
        failure, _, _, _ = self.run_wait(
            [
                'WIFI_BEGIN boot=12345678 status=3',
                wifi_diag(status=3),
                diag(wifi=1),
                diag(wifi=1),
                diag(wifi=1),
                diag(wifi=1),
            ]
        )
        self.assertIn('Brak WIFI_ACCEPTED', failure)

    def test_historical_reason_does_not_override_later_connection(self):
        failure, log, output, reads = self.run_wait(
            [
                'WIFI_ACCEPTED',
                wifi_diag(status=3, reason=202, age=55000),
                diag(wifi=1),
            ]
        )
        self.assertIsNone(failure)
        self.assertEqual(reads, 3)
        self.assertIn('last_reason=202', log)
        self.assertIn('Stan Wi-Fi=3 (połączono)', output)
        self.assertIn('55000 ms temu', output)
        self.assertIn('zapis historyczny, nie bieżący stan', output)

    def test_v2_timeout_includes_fresh_diagnostic_without_password_verdict(self):
        failure, log, output, _ = self.run_wait(
            [
                'WIFI_ACCEPTED',
                'WIFI_BEGIN boot=12345678 status=0',
                diag(),
                wifi_diag(age=55000),
                diag(),
                wifi_diag(age=65000),
            ]
        )
        self.assertIn('nadal wifi=0', failure)
        self.assertIn('AUTH_FAIL', failure)
        self.assertIn('kod nie rozstrzyga, czy hasło jest błędne', failure)
        self.assertIn('65000 ms temu', failure)
        self.assertIn('zapis historyczny', failure)
        self.assertIn('WIFI_BEGIN', log)
        self.assertEqual(log.count('WIFI_DIAG'), 2)
        self.assertIn('WiFi.begin zwróciło 0', output)

    def test_expired_wifi_diag_does_not_claim_current_reason_at_timeout(self):
        failure, log, _, _ = self.run_wait(
            [
                'WIFI_ACCEPTED',
                wifi_diag(reason=202),
                diag(),
                diag(),
                diag(),
                diag(),
            ]
        )
        self.assertIn('Brak aktualnego WIFI_DIAG', failure)
        self.assertNotIn('AUTH_FAIL', failure)
        self.assertIn('last_reason=202', log)

    def test_absent_reason_and_unknown_numeric_code_are_safe(self):
        cases = [
            (wifi_diag(reason=-1, age=-1), 'Brak zarejestrowanej przyczyny'),
            (wifi_diag(status=999, reason=999), 'nieopisany kod sterownika'),
        ]
        for line, expected in cases:
            with self.subTest(line=line):
                failure, _, output, _ = self.run_wait(
                    ['WIFI_ACCEPTED', line, diag(), line, diag(), line],
                )
                self.assertIn(expected, failure)
                self.assertIn(expected, output)

    def test_rejected_command_and_fatal_abort_with_saved_reason(self):
        cases = {
            'WIFI_REJECTED': 'odrzucił',
            'COMMAND_REJECTED': 'odrzucił',
            'FATAL boot=12345678 reason=PSRAM_PATTERN': 'FATAL',
            'FATAL boot=12345678 reason=WIFI_TRACE_QUEUE_ALLOC': 'FATAL',
        }
        for line, expected in cases.items():
            with self.subTest(line=line):
                failure, log, _, reads = self.run_wait([line, 'WIFI_ACCEPTED', diag(wifi=1)])
                self.assertIn(expected, failure)
                self.assertIn(line, log)
                self.assertEqual(reads, 1)

    def test_boot_change_aborts_even_when_new_boot_reports_connected(self):
        failure, log, _, _ = self.run_wait(
            [
                'WIFI_ACCEPTED',
                diag(),
                diag(wifi=1, boot='87654321'),
            ]
        )
        self.assertIn('Restart', failure)
        self.assertIn('boot=12345678', log)
        self.assertIn('boot=87654321', log)

    def test_v2_boot_change_aborts_during_wifi_preflight(self):
        for line in ('WIFI_BEGIN boot=87654321 status=0', wifi_diag(boot='87654321')):
            with self.subTest(line=line):
                failure, log, _, reads = self.run_wait(
                    [
                        'WIFI_ACCEPTED',
                        wifi_diag(),
                        line,
                        diag(wifi=1),
                    ]
                )
                self.assertIn('Restart', failure)
                self.assertIn(line, log)
                self.assertEqual(reads, 3)

    def test_stale_diagnostic_is_not_presented_as_current_wifi_failure(self):
        failure, log, _, _ = self.run_wait(['WIFI_ACCEPTED', diag()])
        self.assertIn('brak aktualnej diagnostyki DIAG', failure)
        self.assertEqual(log.count('DIAG '), 1)
        self.assertNotIn('nadal wifi=0', failure)

    def test_untrusted_usb_lines_never_reach_logs_or_console(self):
        secret = 'SYNTHETIC-SECRET-DO-NOT-LOG'
        untrusted = [
            f'debug SSID={secret}',
            f'WIFI_ACCEPTED {secret}',
            f'{diag(wifi=1)} password={secret}',
            f'FATAL boot=12345678 reason={secret}',
            f'BOOT boot=12345678 reset=11 reset_name=USB flash=16777216 '
            f'psram_physical=8388608 psram_heap=8388608 sdk=v5.5.5 {secret}',
            f'WINDOW_READY requires human visual confirmation; NOT_HARDWARE_PASS {secret}',
            f'WIFI_BEGIN boot=12345678 status={secret}',
            f'WIFI_BEGIN boot=12345678 status=0 {secret}',
            f'{wifi_diag()} password={secret}',
            wifi_diag().replace('last_reason=202', f'last_reason={secret}'),
        ]
        for line in untrusted:
            with self.subTest(line=line):
                self.assertFalse(observe.safe_record(line))
        failure, log, output, _ = self.run_wait(
            untrusted + ['WIFI_ACCEPTED', diag(wifi=1)],
            timeout=90,
        )
        self.assertIsNone(failure)
        self.assertNotIn(secret, log)
        self.assertNotIn(secret, output)
        self.assertEqual(len(log.splitlines()), 2)

    def test_v2_whitelist_rejects_malformed_fields(self):
        for line in (
            'WIFI_BEGIN boot=12345678 status=-1',
            wifi_diag(reason=-2),
            wifi_diag(age=-2),
            wifi_diag().replace('status=6', 'status=６'),
            wifi_diag().replace('disconnects=4', 'disconnects=-1'),
            wifi_diag().replace('associations=1', 'associations=one'),
            wifi_diag().replace(' got_ip_events=0', ''),
        ):
            with self.subTest(line=line):
                self.assertFalse(observe.safe_record(line))

    def test_v2_observation_records_diagnostics_and_rejects_restart(self):
        log, output = io.StringIO(), io.StringIO()
        with redirect_stdout(output):
            for line in ('WIFI_BEGIN boot=12345678 status=0', wifi_diag()):
                self.assertEqual(observe.record_observation(log, line, '12345678'), '12345678')
            observe.record_observation(log, wifi_diag() + ' SYNTHETIC-SECRET', '12345678')
            with self.assertRaisesRegex(RuntimeError, 'Restart'):
                observe.record_observation(log, wifi_diag(boot='87654321'), '12345678')
        self.assertIn('WIFI_BEGIN', log.getvalue())
        self.assertEqual(log.getvalue().count('WIFI_DIAG'), 2)
        self.assertNotIn('SYNTHETIC-SECRET', log.getvalue())
        self.assertNotIn('SYNTHETIC-SECRET', output.getvalue())

    def test_v3_first_disconnect_survives_later_leaving_events_and_summary(self):
        first, later = wifi_event(), wifi_event(seq=2, reason=36, uptime=2500)
        failure, log, output, _ = self.run_wait(
            [
                'WIFI_ACCEPTED',
                first,
                later,
                diag(),
                wifi_diag(reason=36),
                diag(),
            ]
        )
        self.assertIn(first, log)
        self.assertIn(later, log)
        self.assertLess(log.index(first), log.index(later))
        self.assertIn('Pierwsze odebrane rozłączenie', failure)
        self.assertIn('seq=1, uptime=1234 ms, kod 201 (NO_AP_FOUND', failure)
        self.assertIn('Ostatnie zdarzenie rozłączenia: 36', failure)
        self.assertIn('nie dowodzi pierwotnej przyczyny', failure)
        self.assertEqual(output.count('Pierwsze odebrane rozłączenie'), 1)
        self.assertEqual(output.count('Późniejsze rozłączenie: 36'), 1)

    def test_v3_trace_overflow_is_reported_without_claiming_wifi_failure(self):
        failure, log, output, _ = self.run_wait(
            [
                'WIFI_ACCEPTED',
                wifi_event(),
                wifi_trace(dropped=3),
                diag(),
                wifi_diag(),
                diag(),
            ]
        )
        self.assertIn('queued_dropped=3', log)
        self.assertIn('Niepełny ślad zdarzeń', failure)
        self.assertIn('utracone rekordy kolejki/USB=3', failure)
        self.assertIn('utrata diagnostyki, nie licznik rozłączeń Wi-Fi', failure)
        self.assertIn('Niepełny ślad zdarzeń', output)
        # A subsequent connected DIAG remains usable despite incomplete diagnostic trace.
        failure, _, output, _ = self.run_wait(
            [
                'WIFI_ACCEPTED',
                wifi_trace(dropped=3),
                diag(wifi=1),
            ]
        )
        self.assertIsNone(failure)
        self.assertIn('Niepełny ślad zdarzeń', output)

    def test_v3_sequence_gap_after_first_received_event_is_reported(self):
        trace, output = observe.WifiTrace(), io.StringIO()
        with redirect_stdout(output):
            trace.receive(wifi_event(seq=4))
            self.assertFalse(trace.sequence_gap, 'Events before this host phase may be absent')
            trace.receive(wifi_event(seq=6, reason=36))
            trace.receive(wifi_event(seq=7, reason=36))
        self.assertTrue(trace.sequence_gap)
        self.assertEqual(output.getvalue().count('Niepełny ślad zdarzeń'), 1)
        self.assertEqual(trace.first_disconnect['seq'], '4')

    def test_v3_event_and_trace_boot_change_abort_in_both_phases(self):
        for line in (wifi_event(boot='87654321'), wifi_trace(boot='87654321')):
            with self.subTest(line=line):
                failure, log, _, reads = self.run_wait(
                    [
                        'WIFI_ACCEPTED',
                        wifi_event(),
                        line,
                        diag(wifi=1),
                    ]
                )
                self.assertIn('Restart', failure)
                self.assertEqual(reads, 3)
                self.assertIn(line, log)
                with (
                    redirect_stdout(io.StringIO()),
                    self.assertRaisesRegex(RuntimeError, 'Restart'),
                ):
                    observe.record_observation(io.StringIO(), line, '12345678', observe.WifiTrace())

    def test_v3_strict_numeric_enum_and_reason_validation(self):
        for event in ('START', 'STOP', 'CONNECTED', 'GOT_IP', 'LOST_IP'):
            self.assertTrue(observe.safe_record(wifi_event(event=event, reason=-1)))
            self.assertFalse(observe.safe_record(wifi_event(event=event, reason=0)))
        for reason in (0, 201, 255):
            self.assertTrue(observe.safe_record(wifi_event(reason=reason)))
        malformed = [
            wifi_event(reason=-1),
            wifi_event(reason=256),
            wifi_event(reason=-2),
            wifi_event(event='CUSTOM_SECRET'),
            wifi_event(seq=0),
            wifi_event(seq=-1),
            wifi_event(seq=4294967296),
            wifi_event(uptime=-1),
            wifi_event(uptime=4294967296),
            wifi_event().replace('reason=201', 'reason=２０１'),
            wifi_event().replace('seq=1', 'seq=１'),
            wifi_event().replace('boot=12345678', 'boot=SECRET'),
            wifi_trace(dropped=-1),
            wifi_trace(dropped=4294967296),
            wifi_trace(dropped='３'),
            wifi_trace() + ' password=SYNTHETIC-SECRET',
            wifi_event() + ' SSID=SYNTHETIC-SECRET',
            wifi_event().replace(' reason=201', ''),
        ]
        for line in malformed:
            with self.subTest(line=line):
                self.assertFalse(observe.safe_record(line))
        failure, log, output, _ = self.run_wait(
            malformed + ['WIFI_ACCEPTED', diag(wifi=1)],
            timeout=120,
        )
        self.assertIsNone(failure)
        self.assertNotIn('SECRET', log + output)
        self.assertEqual(len(log.splitlines()), 2)

    def test_v3_run_logs_events_and_trace_without_printing_raw_records(self):
        log, output, trace = io.StringIO(), io.StringIO(), observe.WifiTrace()
        with redirect_stdout(output):
            for line in (wifi_event(), wifi_trace(dropped=1)):
                self.assertEqual(
                    observe.record_observation(log, line, '12345678', trace),
                    '12345678',
                )
        self.assertIn('WIFI_EVENT boot=', log.getvalue())
        self.assertIn('WIFI_TRACE boot=', log.getvalue())
        self.assertNotIn('WIFI_EVENT boot=', output.getvalue())
        self.assertNotIn('WIFI_TRACE boot=', output.getvalue())
        self.assertIn('kod 201', output.getvalue())

    def test_v3_stale_diag_still_retains_first_event_and_trace_loss(self):
        failure, _, _, _ = self.run_wait(
            [
                'WIFI_ACCEPTED',
                wifi_event(),
                wifi_trace(dropped=1),
            ]
        )
        self.assertIn('brak aktualnej diagnostyki DIAG', failure)
        self.assertIn('kod 201', failure)
        self.assertIn('Niepełny ślad zdarzeń', failure)

    def test_disconnected_preflight_does_not_invalidate_later_complete_run(self):
        failure, preflight, _, _ = self.run_wait(
            [
                'WIFI_ACCEPTED',
                diag(wifi=0),
                diag(wifi=1),
            ]
        )
        self.assertIsNone(failure)
        lines = [preflight.rstrip(), '20.000 RUN_BEGIN boot=12345678']
        for index in range(1, 133):
            elapsed_ms = index * 5000
            lines.append(
                f'{20 + index * 5:.3f} DIAG boot=12345678 '
                f'uptime_ms={20000 + elapsed_ms} run_ms={elapsed_ms} '
                f'wifi=1 wifi_ms={elapsed_ms} drops=0 targets=31 '
                'touch_errors=0 memory_errors=0'
            )
            lines.append(f'{20 + index * 5 + 0.001:.3f} {wifi_trace()}')
        lines.insert(2, f'20.002 {wifi_event(event="GOT_IP", reason=-1)}')
        lines.append('681.000 OBSERVATION_END')
        ok, reason = evaluate('\n'.join(lines))
        self.assertTrue(ok, reason)
        self.assertIn('wizualnego', reason)


if __name__ == '__main__':
    unittest.main()
