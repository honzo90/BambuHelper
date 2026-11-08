"""Synthetic negative tests for evidence validation, never hardware evidence."""

import unittest
from check_log import evaluate


def sample():
    lines = ['1.000 RUN_BEGIN boot=12345678']
    for i in range(1, 133):
        ms = i * 5000
        lines.append(
            f'{i * 5 + 1:.3f} DIAG boot=12345678 uptime_ms={ms + 20000} run_ms={ms} wifi=1 wifi_ms={ms} drops=0 targets=31 touch_errors=0 memory_errors=0'
        )
    return '\n'.join(lines) + '\n662.000 OBSERVATION_END'


class LogCheckerTest(unittest.TestCase):
    def test_valid_log_is_only_log_ok(self):
        ok, msg = evaluate(sample())
        self.assertTrue(ok)
        self.assertIn('wizualnego', msg)

    def test_rejects_faults(self):
        cases = {
            'no_run': sample().replace('RUN_BEGIN', 'IGNORED'),
            'changed_boot': sample().replace('DIAG boot=12345678', 'DIAG boot=87654321', 1),
            'reboot': sample() + '\n670.000 BOOT boot=12345678',
            'wifi_loss': sample().replace('wifi=1', 'wifi=0', 1),
            'short_disconnect': sample().replace('drops=0', 'drops=1', 1),
            'missing_touch': sample().replace('targets=31', 'targets=15'),
            'memory_error': sample().replace('memory_errors=0', 'memory_errors=1', 1),
            'touch_error': sample().replace('touch_errors=0', 'touch_errors=1', 1),
            'short_window': '\n'.join(sample().splitlines()[:100]),
            'gap': '\n'.join(
                line for i, line in enumerate(sample().splitlines()) if not 30 <= i <= 35
            ),
            'truncated_diag': sample().replace(' wifi=1', '', 1),
            'fatal': sample() + '\n670.000 FATAL reason=PSRAM',
            'second_run': sample() + '\n670.000 RUN_BEGIN boot=12345678',
            'no_end': sample().replace('OBSERVATION_END', 'IGNORED'),
            'serial_error': sample().replace('OBSERVATION_END', 'OBSERVATION_ERROR'),
            'hung_at_end': sample().replace('662.000 OBSERVATION_END', '680.000 OBSERVATION_END'),
        }
        for name, data in cases.items():
            with self.subTest(name=name):
                self.assertFalse(evaluate(data)[0])


if __name__ == '__main__':
    unittest.main()
