#!/usr/bin/env python3
"""Provision smoke Wi-Fi in RAM and collect only its bounded diagnostic records.
Run only after the explicitly approved smoke flash. Never sends printer commands.
"""

import argparse
import getpass
from pathlib import Path
import re
import time
import warnings
import serial
from serial.tools import list_ports


SMOKE_IDS = frozenset(f'SMOKE_ID waveshare43b-v{version} 800x480' for version in (1, 2, 3, 4))
DIAGNOSTIC_FRESH_SECONDS = 12
# Arduino-ESP32 3.3.11 libraries/WiFi/src/WiFiType.h: wl_status_t.
WIFI_STATUSES = {
    0: 'oczekiwanie',
    1: 'sieć niedostępna',
    2: 'skan zakończony',
    3: 'połączono',
    4: 'łączenie nie powiodło się',
    5: 'połączenie utracone',
    6: 'rozłączono',
    254: 'Wi-Fi zatrzymane',
    255: 'brak interfejsu',
}
# ESP32 3.3.11 esp_wifi_types_generic.h: wifi_err_reason_t (not a password verdict).
WIFI_REASONS = {
    2: 'AUTH_EXPIRE: wygasło uwierzytelnienie',
    15: '4WAY_HANDSHAKE_TIMEOUT: przekroczono czas uzgadniania kluczy',
    36: 'STA_LEAVING: stacja opuszcza sieć; kod nie rozstrzyga pierwotnej przyczyny',
    200: 'BEACON_TIMEOUT: brak ramek sygnalizacyjnych punktu dostępu',
    201: 'NO_AP_FOUND: nie znaleziono punktu dostępu',
    202: 'AUTH_FAIL: uwierzytelnienie nie powiodło się; kod nie rozstrzyga, czy hasło jest błędne',
    203: 'ASSOC_FAIL: skojarzenie z punktem dostępu nie powiodło się',
    204: 'HANDSHAKE_TIMEOUT: przekroczono czas uzgadniania połączenia',
    205: 'CONNECTION_FAIL: połączenie nie powiodło się',
    210: 'NO_AP_FOUND_W_COMPATIBLE_SECURITY: brak punktu dostępu ze zgodnymi zabezpieczeniami',
    211: 'NO_AP_FOUND_IN_AUTHMODE_THRESHOLD: brak punktu dostępu w progu trybu uwierzytelniania',
    212: 'NO_AP_FOUND_IN_RSSI_THRESHOLD: brak punktu dostępu w progu siły sygnału',
}


def safe_record(line):
    """Accept only the smoke protocol, never arbitrary USB/debug output."""
    if line.startswith('SCAN_RESULT '):
        match = re.fullmatch(
            r'SCAN_RESULT boot=[0-9a-f]{8} total=([0-9]{1,5}) matches=([0-9]{1,5}) '
            r'best_rssi=(-?[0-9]{1,3}) best_channel=([0-9]{1,2}) '
            r'best_auth=(-?[0-9]{1,3}) elapsed_ms=([0-9]{1,10})',
            line,
        )
        if match is None:
            return False
        total, matches, rssi, channel, auth, elapsed = map(int, match.groups())
        return (
            0 <= matches <= total <= 65535
            and elapsed <= 0xFFFFFFFF
            and (
                (matches == 0 and rssi == 0 and channel == 0 and auth == -1)
                or (matches > 0 and -127 <= rssi <= 0 and 1 <= channel <= 14 and 0 <= auth <= 255)
            )
        )
    if line.startswith('SCAN_ERROR '):
        match = re.fullmatch(
            r'SCAN_ERROR boot=[0-9a-f]{8} stage=(START|POLL|TIMEOUT) code=(-?[0-9]{1,10})',
            line,
        )
        return match is not None and -(2**31) <= int(match[2]) <= 2**31 - 1
    if line.startswith('WIFI_EVENT '):
        match = re.fullmatch(
            r'WIFI_EVENT boot=[0-9a-f]{8} seq=([1-9][0-9]{0,9}) '
            r'uptime_ms=([0-9]{1,10}) '
            r'event=(START|STOP|CONNECTED|DISCONNECTED|GOT_IP|LOST_IP) '
            r'reason=(-1|[0-9]{1,3})',
            line,
        )
        if match is None:
            return False
        sequence, uptime, event, reason = match.groups()
        return (
            int(sequence) <= 0xFFFFFFFF
            and int(uptime) <= 0xFFFFFFFF
            and (
                (event == 'DISCONNECTED' and 0 <= int(reason) <= 255)
                or (event != 'DISCONNECTED' and reason == '-1')
            )
        )
    if line.startswith('WIFI_TRACE '):
        match = re.fullmatch(r'WIFI_TRACE boot=[0-9a-f]{8} queued_dropped=([0-9]{1,10})', line)
        return match is not None and int(match[1]) <= 0xFFFFFFFF
    patterns = (
        r'SMOKE_ID waveshare43b-v[1234] 800x480',
        r'SCAN_BEGIN boot=[0-9a-f]{8}',
        r'SCAN_REJECTED boot=[0-9a-f]{8} reason=(?:SSID|BUSY)',
        r'WIFI_ACCEPTED|WIFI_REJECTED|COMMAND_REJECTED',
        r'WIFI_BEGIN boot=[0-9a-f]{8} status=[0-9]+',
        r'WIFI_DIAG boot=[0-9a-f]{8} status=[0-9]+ last_reason=(?:-1|[0-9]+) reason_age_ms=(?:-1|[0-9]+) disconnects=[0-9]+ associations=[0-9]+ got_ip_events=[0-9]+',
        r'BOOT boot=[0-9a-f]{8} reset=\d+ reset_name=[A-Z_]+ flash=\d+ psram_physical=\d+ psram_heap=\d+ sdk=v[0-9.]+',
        r'DIAG boot=[0-9a-f]{8} uptime_ms=\d+ run_ms=\d+ wifi=[01] wifi_ms=\d+ drops=\d+ heap=\d+ min_heap=\d+ largest=\d+ psram_free=\d+ targets=\d+ touch_errors=\d+ memory_errors=\d+',
        r'TOUCH boot=[0-9a-f]{8} x=\d+ y=\d+ targets=\d+',
        r'RUN_BEGIN boot=[0-9a-f]{8}',
        r'FATAL boot=[0-9a-f]{8} reason=(?:COREDUMP_PARTITION_FORBIDDEN|PSRAM_EXPECTED_8M|FLASH_EXPECTED_16M|PSRAM_ALLOC|PSRAM_PATTERN|BOARD_INIT|LCD_OR_TOUCH_MISSING|WRONG_RESOLUTION|FRAMEBUFFER_CONFIG|BOUNCE_CONFIG|BOARD_BEGIN|FRAMEBUFFER_NOT_RGB565|LCD_DRAW|WIFI_TRACE_QUEUE_ALLOC)',
        r'WINDOW_READY requires human visual confirmation; NOT_HARDWARE_PASS',
    )
    return any(re.fullmatch(pattern, line) for pattern in patterns)


def record(log, line):
    log.write(f'{time.monotonic():.3f} {line}\n')
    log.flush()


def status_description(status):
    return f"{status} ({WIFI_STATUSES.get(int(status), 'nieznany kod')})"


def wifi_description(values):
    """Describe a current status and historical events without inventing a cause."""
    state = (
        f"Stan Wi-Fi={status_description(values['status'])}; "
        f"skojarzenia={values['associations']}, zdarzenia adresu IP={values['got_ip_events']}, "
        f"rozłączenia={values['disconnects']}. "
    )
    reason, age = int(values['last_reason']), int(values['reason_age_ms'])
    if reason < 0 or age < 0:
        return state + 'Brak zarejestrowanej przyczyny rozłączenia.'
    description = WIFI_REASONS.get(reason, 'nieopisany kod sterownika')
    return state + (
        f'Ostatnie zdarzenie rozłączenia: {reason} ({description}), {age} ms temu. '
        'To zapis historyczny, nie bieżący stan połączenia.'
    )


def line_boot(line):
    if line.startswith(
        (
            'DIAG ',
            'BOOT ',
            'WIFI_BEGIN ',
            'WIFI_DIAG ',
            'WIFI_EVENT ',
            'WIFI_TRACE ',
            'RUN_BEGIN ',
            'TOUCH ',
            'FATAL ',
            'SCAN_BEGIN ',
            'SCAN_RESULT ',
            'SCAN_REJECTED ',
            'SCAN_ERROR ',
        )
    ):
        return line.split()[1].split('=', 1)[1]
    return None


class WifiTrace:
    """Track only validated event metadata; diagnostic loss is not a Wi-Fi drop."""

    def __init__(self):
        self.first_disconnect = None
        self.last_sequence = None
        self.dropped = 0
        self.sequence_gap = False
        self.later_leaving_reported = False

    def first_description(self):
        if self.first_disconnect is None:
            return ''
        values = self.first_disconnect
        reason = int(values['reason'])
        return (
            f"Pierwsze odebrane rozłączenie w tej fazie: seq={values['seq']}, "
            f"uptime={values['uptime_ms']} ms, kod {reason} "
            f"({WIFI_REASONS.get(reason, 'nieopisany kod sterownika')}). "
            'Kolejność zapisu sama nie dowodzi pierwotnej przyczyny.'
        )

    def loss_description(self):
        if not self.dropped and not self.sequence_gap:
            return ''
        return (
            f'Niepełny ślad zdarzeń: utracone rekordy kolejki/USB={self.dropped}, '
            f"luka lub nieciągłość numeracji={'tak' if self.sequence_gap else 'nie'}. "
            'To utrata diagnostyki, nie licznik rozłączeń Wi-Fi.'
        )

    def receive(self, line):
        if not line.startswith(('WIFI_EVENT ', 'WIFI_TRACE ')) or not safe_record(line):
            return
        values = dict(item.split('=', 1) for item in line.split()[1:])
        if line.startswith('WIFI_TRACE '):
            dropped = int(values['queued_dropped'])
            if dropped > self.dropped:
                self.dropped = dropped
                print(self.loss_description())
            return
        sequence = int(values['seq'])
        if self.last_sequence is not None and sequence != self.last_sequence + 1:
            if not self.sequence_gap:
                self.sequence_gap = True
                print(self.loss_description())
        self.last_sequence = sequence
        if values['event'] == 'DISCONNECTED':
            if self.first_disconnect is None:
                self.first_disconnect = values
                print(self.first_description())
            elif (
                values['reason'] == '36'
                and self.first_disconnect['reason'] != '36'
                and not self.later_leaving_reported
            ):
                self.later_leaving_reported = True
                print(
                    'Późniejsze rozłączenie: 36 (STA_LEAVING); zachowano wcześniejsze zdarzenie w logu.'
                )
        elif values['event'] in ('CONNECTED', 'GOT_IP', 'LOST_IP', 'STOP'):
            labels = {
                'CONNECTED': 'skojarzenie z punktem dostępu',
                'GOT_IP': 'otrzymano adres IP',
                'LOST_IP': 'utracono adres IP',
                'STOP': 'zatrzymano Wi-Fi',
            }
            print(f"Zdarzenie Wi-Fi: {labels[values['event']]} (uptime={values['uptime_ms']} ms).")


def record_observation(log, line, boot, trace=None):
    """Record safe observation traffic, including v2/v3, and reject a changed boot."""
    if safe_record(line) and line.startswith(
        (
            'RUN_BEGIN ',
            'DIAG ',
            'WIFI_BEGIN ',
            'WIFI_DIAG ',
            'WIFI_EVENT ',
            'WIFI_TRACE ',
            'TOUCH ',
            'FATAL ',
            'WINDOW_READY',
            'BOOT ',
        )
    ):
        record(log, line)
        current_boot = line_boot(line)
        if current_boot is not None:
            if boot is not None and current_boot != boot:
                raise RuntimeError('Restart podczas obserwacji; wymagany nowy nieprzerwany pomiar.')
            boot = current_boot
        if trace is not None:
            trace.receive(line)
        if not line.startswith(('TOUCH ', 'WIFI_EVENT ', 'WIFI_TRACE ')):
            print(line)
    return boot


def wait_wifi(port, log, timeout=60, trace=None):
    """Check acceptance separately from usable Wi-Fi; keep pre-START evidence."""
    deadline = time.monotonic() + timeout
    accepted = False
    last_diag = None
    last_diag_time = None
    last_wifi_diag = None
    last_wifi_diag_time = None
    boot = None
    trace = trace if trace is not None else WifiTrace()
    while time.monotonic() < deadline:
        line = port.readline().decode('utf-8', errors='replace').strip()
        if not safe_record(line):
            continue
        # Touch traffic is irrelevant before START and need not fill the log.
        if line.startswith('TOUCH '):
            continue
        record(log, line)
        if line.startswith('FATAL '):
            raise SystemExit('Firmware zgłosił FATAL; szczegóły w bezpiecznym logu.')
        if line in ('WIFI_REJECTED', 'COMMAND_REJECTED'):
            raise SystemExit('Firmware odrzucił komendę Wi-Fi; nie rozpoczęto próby.')
        if line_boot(line) is not None:
            values = dict(item.split('=', 1) for item in line.split()[1:])
            current_boot = values['boot']
            if boot is not None and boot != current_boot:
                raise SystemExit(
                    'Restart podczas oczekiwania na Wi-Fi; dane w RAM mogły zostać utracone.'
                )
            boot = current_boot
        trace.receive(line)
        if line == 'WIFI_ACCEPTED':
            accepted = True
            print('Płytka przyjęła dane Wi-Fi; oczekiwanie na połączenie i adres IP.')
        if line.startswith('WIFI_BEGIN '):
            print(
                f"WiFi.begin zwróciło {status_description(values['status'])}; to wynik rozpoczęcia próby, nie końcowy wynik połączenia."
            )
        if line.startswith('WIFI_DIAG '):
            last_wifi_diag, last_wifi_diag_time = values, time.monotonic()
            print(wifi_description(values))
        if line.startswith('DIAG '):
            last_diag, last_diag_time = values, time.monotonic()
            print(
                f"Wi-Fi={values['wifi']}, rozłączenia={values['drops']}, uptime={int(values['uptime_ms']) // 1000} s"
            )
            if accepted and values['wifi'] == '1':
                return boot
    trace_detail = ' '.join(
        part for part in (trace.first_description(), trace.loss_description()) if part
    )
    trace_suffix = ' ' + trace_detail if trace_detail else ''
    if not accepted:
        raise SystemExit(
            'Brak WIFI_ACCEPTED: nie potwierdzono przyjęcia komendy przez płytkę. Szczegóły w logu.'
            + trace_suffix
        )
    if last_diag is None or time.monotonic() - last_diag_time > DIAGNOSTIC_FRESH_SECONDS:
        raise SystemExit(
            'Dane Wi-Fi przyjęte, ale brak aktualnej diagnostyki DIAG. Szczegóły w logu.'
            + trace_suffix
        )
    detail = 'Obecny firmware nie podaje przyczyny (sieć/uwierzytelnienie/DHCP).'
    if last_wifi_diag is not None:
        if time.monotonic() - last_wifi_diag_time <= DIAGNOSTIC_FRESH_SECONDS:
            detail = wifi_description(last_wifi_diag)
        else:
            detail = (
                'Brak aktualnego WIFI_DIAG; historyczny zapis nie rozstrzyga bieżącej przyczyny.'
            )
    raise SystemExit(
        f"Dane Wi-Fi przyjęte; po {timeout} s nadal wifi={last_diag['wifi']}, rozłączenia={last_diag['drops']}. "
        'Test 10 minut nie rozpoczął się. ' + detail + trace_suffix
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--list', action='store_true', help='List USB ports without opening them')
    ap.add_argument('--port')
    ap.add_argument('--seconds', type=int, default=660)
    args = ap.parse_args()
    if args.list:
        for p in list_ports.comports():
            print(f'{p.device}  {p.description}  VID={p.vid!s} PID={p.pid!s}')
        return
    if not args.port or args.seconds < 610:
        ap.error('Use --port /dev/cu... and --seconds >= 610 (default 660).')
    # Both prompts stay out of terminal history, process args, firmware and logs.
    warnings.simplefilter('error', getpass.GetPassWarning)
    ssid = getpass.getpass('SSID Wi-Fi 2.4 GHz (ukryte): ')
    password = getpass.getpass('Hasło Wi-Fi (ukryte): ')
    if not 1 <= len(ssid.encode()) <= 32 or len(password.encode()) > 64:
        ap.error('Nieprawidłowa długość SSID/hasła.')
    if any(c in ssid + password for c in '\t\r\n\x00'):
        ap.error('Tabulator, NUL i nowa linia nie są obsługiwane.')
    folder = Path(__file__).resolve().parent / 'local'
    folder.mkdir(mode=0o700, exist_ok=True)
    logfile = folder / time.strftime('observation-%Y%m%d-%H%M%S.log')
    port = serial.Serial(port=None, baudrate=115200, timeout=1, write_timeout=3)
    port.dtr = False
    port.rts = False
    port.port = args.port
    print('Otwarcie USB może zresetować płytkę; pomiar rozpocznie się dopiero po połączeniu Wi-Fi.')
    with port, logfile.open('x') as log:
        logfile.chmod(0o600)
        print('Log diagnostyczny:', logfile)
        record(log, 'PHASE name=identify')
        port.reset_input_buffer()
        port.write(b'STATUS\n')
        deadline = time.monotonic() + 10
        identified = False
        while time.monotonic() < deadline:
            line = port.readline().decode('utf-8', errors='replace').strip()
            # Firmware-specific reply required before sending any credentials.
            if line in SMOKE_IDS:
                record(log, line)
                identified = True
                break
        if not identified:
            record(log, 'PREFLIGHT_ERROR code=IDENTIFICATION_TIMEOUT')
            raise SystemExit('Brak identyfikacji testowego firmware. Nie wysłano danych Wi-Fi.')
        record(log, 'PHASE name=wifi')
        try:
            try:
                port.write(('WIFI\t' + ssid + '\t' + password + '\n').encode())
            finally:
                del ssid, password
            trace = WifiTrace()
            boot = wait_wifi(port, log, trace=trace)
        except (SystemExit, serial.SerialException, OSError, KeyboardInterrupt):
            record(log, 'PREFLIGHT_ERROR code=WIFI_STAGE_FAILED')
            raise
        record(log, 'PHASE name=observe')
        port.write(b'START\n')
        print('Dotknij kolejno celów 1–5 i sprawdź zgodność krzyżyka z palcem.')
        print('Przez 10 minut obserwuj kolory, orientację i brak zakłóceń. Log:', logfile)
        deadline = time.monotonic() + args.seconds
        try:
            while time.monotonic() < deadline:
                line = port.readline().decode('utf-8', errors='replace').strip()
                boot = record_observation(log, line, boot, trace=trace)
        except (serial.SerialException, OSError, KeyboardInterrupt, RuntimeError):
            log.write(f'{time.monotonic():.3f} OBSERVATION_ERROR\n')
            log.flush()
            raise SystemExit('Obserwacja przerwana; zapisano OBSERVATION_ERROR.')
        log.write(f'{time.monotonic():.3f} OBSERVATION_END\n')
    print('Zapisano:', logfile)
    print(
        'Uruchom check_log.py. Ocena obrazu/dotyku należy do człowieka; log sam nie daje hardware PASS.'
    )


if __name__ == '__main__':
    main()
