#!/usr/bin/env python3
"""One private visibility scan with approved v4 firmware; no password or connection.

Only STATUS and SCAN are sent. Numeric aggregate results cannot prove Wi-Fi
connection, correct credentials, or the ten-minute hardware acceptance test.
"""
import argparse
import getpass
import os
from pathlib import Path
import time
import warnings

import serial
from serial.tools import list_ports

from observe import SMOKE_IDS, line_boot, record, safe_record


SCAN_ID = 'SMOKE_ID waveshare43b-v4 800x480'
SCAN_PREFIXES = ('SCAN_BEGIN', 'SCAN_RESULT', 'SCAN_REJECTED', 'SCAN_ERROR')


def valid_ssid(ssid):
    return 1 <= len(ssid.encode('utf-8')) <= 32 and not any(c in ssid for c in '\t\r\n\x00')


def read_record(port):
    """Never expose a raw line, including a malformed record with secret text."""
    raw = port.readline().decode('utf-8', errors='replace').strip()
    if raw.startswith(SCAN_PREFIXES) and not safe_record(raw):
        raise RuntimeError('Nieprawidłowy rekord skanu; jego treść nie została zapisana.')
    return raw if safe_record(raw) else None


def identify_v4(port, log, timeout=10):
    """Require the exact v4 identity followed by a valid BOOT before target upload."""
    port.reset_input_buffer()
    port.write(b'STATUS\n')
    deadline = time.monotonic() + timeout
    identified = False
    boot = None
    while time.monotonic() < deadline:
        line = read_record(port)
        if line is None:
            continue
        if line.startswith(SCAN_PREFIXES):
            raise RuntimeError('Nieoczekiwany rekord wcześniejszego skanu; nie wysłano SSID.')
        if line in SMOKE_IDS:
            record(log, line)
            if line != SCAN_ID:
                raise RuntimeError('Skan wymaga zatwierdzonego firmware v4; nie wysłano SSID.')
            identified = True
            continue
        current_boot = line_boot(line)
        if current_boot is not None:
            if boot is not None and current_boot != boot:
                raise RuntimeError('Zmiana identyfikatora rozruchu podczas identyfikacji; nie wysłano SSID.')
            boot = current_boot
        if line.startswith('FATAL '):
            record(log, line)
            raise RuntimeError('Firmware zgłosił FATAL; nie wysłano SSID.')
        if identified and line.startswith('BOOT '):
            record(log, line)
            return boot
    raise RuntimeError('Brak pełnej identyfikacji v4 i BOOT; nie wysłano SSID.')


def wait_scan(port, log, boot, timeout=30):
    """Require one BEGIN and one RESULT from the identified boot, in that order."""
    deadline = time.monotonic() + timeout
    begun = False
    while time.monotonic() < deadline:
        line = read_record(port)
        if line is None:
            continue
        current_boot = line_boot(line)
        if current_boot is not None and current_boot != boot:
            record(log, line)
            raise RuntimeError('Restart podczas skanu; wynik odrzucony.')
        if line in SMOKE_IDS:
            if line != SCAN_ID:
                raise RuntimeError('Zmiana identyfikacji firmware podczas skanu; wynik odrzucony.')
            # A repeated v4 identity alone cannot replace its BOOT or SCAN_BEGIN.
            continue
        if line == 'COMMAND_REJECTED':
            record(log, line)
            raise RuntimeError('Firmware odrzucił komendę skanu.')
        if line.startswith('FATAL '):
            record(log, line)
            raise RuntimeError('Firmware zgłosił FATAL; skan przerwany.')
        if line.startswith('SCAN_BEGIN '):
            record(log, line)
            if begun:
                raise RuntimeError('Powtórzony SCAN_BEGIN; wynik odrzucony.')
            begun = True
            print('Płytka rozpoczęła jednorazowy skan; SSID i nazwy sieci nie trafią do logu.')
        elif line.startswith('SCAN_RESULT '):
            record(log, line)
            if not begun:
                raise RuntimeError('Wynik bez SCAN_BEGIN; wynik odrzucony.')
            return {key: int(value) if key != 'boot' else value
                    for key, value in (item.split('=', 1) for item in line.split()[1:])}
        elif line.startswith('SCAN_REJECTED '):
            record(log, line)
            if line.endswith('reason=BUSY'):
                raise RuntimeError('Skan odrzucony: użyto już skanu lub rozpoczęto Wi-Fi w tym rozruchu. Wymagany świeży rozruch.')
            raise RuntimeError('Skan odrzucony: nieprawidłowy SSID.')
        elif line.startswith('SCAN_ERROR '):
            record(log, line)
            values = dict(item.split('=', 1) for item in line.split()[1:])
            raise RuntimeError(f"Błąd skanu: etap={values['stage']}, kod={values['code']}; brak wyniku widoczności.")
        elif line.startswith(('BOOT ', 'DIAG ', 'WIFI_DIAG ', 'WIFI_EVENT ', 'WIFI_TRACE ')):
            record(log, line)
    raise RuntimeError('Brak pełnego wyniku skanu w wyznaczonym czasie; widoczność sieci nieustalona.')


def run_scan(port, log, ssid):
    if not valid_ssid(ssid):
        raise RuntimeError('Nieprawidłowy SSID: wymagane 1–32 bajty UTF-8, bez tabulatora, NUL i nowej linii.')
    record(log, 'PHASE name=scan_identify')
    boot = identify_v4(port, log)
    # Firmware allows SCAN only once per fresh boot and before WIFI. Clear any
    # trailing STATUS traffic before that single request; no resends or retries.
    port.reset_input_buffer()
    record(log, 'PHASE name=scan')
    try:
        port.write(('SCAN\t' + ssid + '\n').encode('utf-8'))
    finally:
        del ssid
    return wait_scan(port, log, boot)


def describe_result(result):
    total, matches = result['total'], result['matches']
    if total == 0:
        detail = ('Skan nie wykrył żadnego punktu dostępu 2,4 GHz. '
                  'Sam ten wynik nie rozstrzyga między otoczeniem radiowym a torem antenowym.')
    elif matches == 0:
        detail = (f'Wykryto punktów dostępu 2,4 GHz: {total}; zgodnych z podanym SSID: 0. '
                  'Radio odbiera inne punkty, ale w tym skanie nie znalazło dokładnie tej nazwy.')
    else:
        detail = (f"Wykryto punktów dostępu 2,4 GHz: {total}; zgodnych z podanym SSID: {matches}. "
                  f"Najsilniejszy zgodny: RSSI={result['best_rssi']} dBm, kanał={result['best_channel']}, "
                  f"tryb zabezpieczeń (kod sterownika)={result['best_auth']}.")
    return detail + (
        f" Czas skanu: {result['elapsed_ms']} ms. Licznik dotyczy punktów dostępu, nie unikalnych nazw. "
        'Skan ESP32-S3 dotyczy 2,4 GHz; brak dopasowania nie wyklucza sieci ukrytej ani emisji tylko w 5 GHz. '
        'To wynik widoczności, nie potwierdzenie połączenia Wi-Fi ani sprzętowy PASS. '
        'Przed observe.py wymagany jest nowy rozruch płytki; skan blokuje łączenie w tym rozruchu.'
    )


def open_private_log(folder):
    folder.mkdir(mode=0o700, exist_ok=True)
    logfile = folder / time.strftime('wifi-scan-%Y%m%d-%H%M%S.log')
    descriptor = os.open(logfile, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    return logfile, os.fdopen(descriptor, 'w', encoding='utf-8')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--list', action='store_true', help='List USB ports without opening them')
    ap.add_argument('--port')
    args = ap.parse_args()
    if args.list:
        for port_info in list_ports.comports():
            print(f'{port_info.device}  {port_info.description}  VID={port_info.vid!s} PID={port_info.pid!s}')
        return
    if not args.port:
        ap.error('Use --port /dev/cu... or --list.')
    warnings.simplefilter('error', getpass.GetPassWarning)
    ssid = getpass.getpass('Dokładny SSID do sprawdzenia (ukryte, bez hasła): ')
    if not valid_ssid(ssid):
        ap.error('SSID musi mieć 1–32 bajty UTF-8, bez tabulatora, NUL i nowej linii.')
    folder = Path(__file__).resolve().parent / 'local'
    logfile, log = open_private_log(folder)
    port = serial.Serial(port=None, baudrate=115200, timeout=1, write_timeout=3, exclusive=True)
    port.dtr = False
    port.rts = False
    port.port = args.port
    print('Otwarcie USB może zresetować płytkę. Skan wymaga świeżego rozruchu zatwierdzonego v4.')
    print('Log diagnostyczny:', logfile)
    with log:
        try:
            with port:
                print('Masz teraz 10 sekund: wróć na iPhonie do Ustawienia → Hotspot osobisty i pozostaw ten ekran otwarty.')
                # Identify only after this pause, so the target is never sent
                # based on a BOOT observed before a possible intervening reset.
                time.sleep(10)
                result = run_scan(port, log, ssid)
            record(log, 'SCAN_HOST_END result=VISIBILITY_ONLY')
        except (RuntimeError, serial.SerialException, OSError, KeyboardInterrupt) as error:
            record(log, 'SCAN_HOST_ERROR code=SCAN_STAGE_FAILED')
            if isinstance(error, RuntimeError):
                raise SystemExit(str(error)) from None
            raise SystemExit('Skan przerwany lub błąd portu; brak potwierdzonego wyniku. Szczegóły bez danych sieci w logu.') from None
        finally:
            del ssid
    print(describe_result(result))


if __name__ == '__main__':
    main()
