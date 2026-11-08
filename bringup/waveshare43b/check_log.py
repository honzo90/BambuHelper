#!/usr/bin/env python3
"""Validate one uninterrupted smoke observation; never claims visual hardware PASS."""

import argparse
from pathlib import Path


def evaluate(text):
    rows = []
    runs = 0
    boot = None
    end = None
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        kind = parts[1]
        if end is not None:
            return False, 'Dane po znaczniku zakończenia'
        if kind == 'OBSERVATION_ERROR':
            return False, 'Obserwacja została przerwana'
        if kind == 'OBSERVATION_END':
            try:
                end = float(parts[0])
            except ValueError:
                return False, 'Błędny czas zakończenia'
        values = dict(x.split('=', 1) for x in parts[2:] if '=' in x)
        if kind == 'FATAL':
            return False, 'FATAL w logu'
        if kind == 'RUN_BEGIN':
            runs += 1
            boot = values.get('boot')
        if kind == 'BOOT' and runs:
            return False, 'Restart/nowy BOOT podczas obserwacji'
        if kind == 'DIAG' and runs:
            try:
                row = {
                    k: int(values[k])
                    for k in (
                        'uptime_ms',
                        'run_ms',
                        'wifi',
                        'wifi_ms',
                        'drops',
                        'targets',
                        'touch_errors',
                        'memory_errors',
                    )
                }
                row['boot'] = values['boot']
                row['host'] = float(parts[0])
            except (KeyError, ValueError):
                return False, 'Niepełny/błędny rekord DIAG'
            rows.append(row)
    if runs != 1 or len(rows) < 120 or not boot or end is None:
        return False, 'Wymagany jeden RUN_BEGIN i co najmniej 120 rekordów DIAG'
    if rows[0]['run_ms'] > 10000:
        return False, 'Brak początku obserwacji'
    for r in rows:
        if (
            r['boot'] != boot
            or r['wifi'] != 1
            or any(r[k] for k in ('drops', 'touch_errors', 'memory_errors'))
        ):
            return False, 'Restart, utrata Wi-Fi lub błąd dotyku/pamięci'
    for a, b in zip(rows, rows[1:]):
        if not 0 < b['uptime_ms'] - a['uptime_ms'] <= 10000 or not 0 < b['host'] - a['host'] <= 12:
            return False, 'Luka >10 s w firmware / >12 s w przechwytywaniu lub cofnięcie czasu'
    last = rows[-1]
    if not 0 <= end - last['host'] <= 12:
        return False, 'Brak danych przy zakończeniu obserwacji'
    if min(last['run_ms'], last['wifi_ms']) < 600000 or last['targets'] != 31:
        return False, 'Nie osiągnięto 600 s ciągłego Wi-Fi i wszystkich pięciu celów'
    if (last['host'] - rows[0]['host']) < 600 or (
        last['uptime_ms'] - rows[0]['uptime_ms']
    ) < 600000:
        return False, 'Za krótka rzeczywista obserwacja (wymagane 600 s między rekordami)'
    return True, 'LOG_OK; nadal wymagane 10 min wizualnego potwierdzenia obrazu i zgodności dotyku'


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('log', type=Path)
    args = ap.parse_args()
    ok, reason = evaluate(args.log.read_text())
    print(('LOG_OK: ' if ok else 'LOG_FAIL: ') + reason)
    raise SystemExit(0 if ok else 1)


if __name__ == '__main__':
    main()
