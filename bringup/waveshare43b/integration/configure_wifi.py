#!/usr/bin/env python3
"""Private first-boot Wi-Fi setup using the project's existing Improv Serial.

Only GET_DEVICE_INFO, GET_CURRENT_STATE and one WIFI_SETTINGS are sent. No
flashing, reset command, network request, raw serial output or credential file.
The application's own successful Improv callback saves Wi-Fi and restarts it.
Protocol source: lib/ImprovWiFi/src/{ImprovTypes.h,ImprovWiFiLibrary.cpp}.
"""
import argparse
from collections import deque
import getpass
import ipaddress
import re
import sys
import time
import warnings
from urllib.parse import urlsplit

MAGIC = b"IMPROV"
VERSION = 1
CURRENT_STATE, ERROR_STATE, RPC, RPC_RESPONSE = 1, 2, 3, 4
WIFI_SETTINGS, GET_CURRENT_STATE, GET_DEVICE_INFO = 1, 2, 3
AUTHORIZED, PROVISIONING, PROVISIONED = 2, 3, 4
FIRMWARE = b"BambuHelper-WS43B-Monitor"
FIRMWARE_VERSION = b"v3.8.3"
CHIP = b"ESP32-S3"


class SetupError(Exception):
    """Messages are fixed descriptions, never serial data or user input."""


def frame(kind, payload):
    if kind not in (CURRENT_STATE, ERROR_STATE, RPC, RPC_RESPONSE) or len(payload) > 255:
        raise SetupError("Nieprawidłowy rozmiar lub typ ramki Improv.")
    data = MAGIC + bytes((VERSION, kind, len(payload))) + bytes(payload)
    return data + bytes((sum(data) & 255,))


def rpc(command, values=()):
    if command not in (GET_DEVICE_INFO, GET_CURRENT_STATE, WIFI_SETTINGS):
        raise SetupError("Niedozwolona komenda konfiguratora.")
    if command != WIFI_SETTINGS and values:
        raise SetupError("Komenda odczytu nie może zawierać danych Wi-Fi.")
    if command == WIFI_SETTINGS and len(values) != 2:
        raise SetupError("Niepełne dane Wi-Fi.")
    if any(not isinstance(value, bytes) or len(value) > 255 for value in values):
        raise SetupError("Nieprawidłowe pole komendy Improv.")
    data = b"".join(bytes((len(value),)) + value for value in values)
    if len(data) > 253:
        raise SetupError("Dane Improv są zbyt długie.")
    packet = frame(RPC, bytes((command, len(data))) + data)
    # The vendored parser leaves _position=1 after accepting a command; a
    # non-header separator puts it back at 0 before the next standard frame.
    return packet + b"\n"


class Decoder:
    """Bounded binary decoder; discards interleaved console text without echo."""
    def __init__(self):
        self.buffer = bytearray()

    def feed(self, data):
        self.buffer.extend(data)
        result = []
        while self.buffer:
            start = self.buffer.find(MAGIC)
            if start < 0:
                # Retain only a possible partial header, never entire log lines.
                keep = 0
                for n in range(1, len(MAGIC)):
                    if self.buffer.endswith(MAGIC[:n]):
                        keep = n
                self.buffer[:] = self.buffer[-keep:] if keep else b""
                break
            if start:
                del self.buffer[:start]
            if len(self.buffer) < 9:
                break
            if self.buffer[6] != VERSION or self.buffer[7] not in (CURRENT_STATE, ERROR_STATE, RPC_RESPONSE):
                raise SetupError("Nieprawidłowy nagłówek odpowiedzi Improv.")
            size = 10 + self.buffer[8]
            if len(self.buffer) < size:
                break
            raw = bytes(self.buffer[:size])
            del self.buffer[:size]
            if sum(raw[:-1]) & 255 != raw[-1]:
                raise SetupError("Nieprawidłowa suma kontrolna Improv; przerwano konfigurację.")
            kind, payload = raw[7], raw[9:-1]
            if kind in (CURRENT_STATE, ERROR_STATE) and len(payload) != 1:
                raise SetupError("Nieprawidłowa długość stanu Improv.")
            result.append((kind, payload))
        return result


def response(payload, expected_command):
    if len(payload) < 2 or payload[0] != expected_command or payload[1] != len(payload) - 2:
        raise SetupError("Odpowiedź Improv nie pasuje do wysłanej komendy.")
    values, offset = [], 2
    while offset < len(payload):
        length = payload[offset]
        offset += 1
        if offset + length > len(payload):
            raise SetupError("Nieprawidłowa długość pola odpowiedzi Improv.")
        values.append(payload[offset:offset + length])
        offset += length
    return values


def identity(payload):
    values = response(payload, GET_DEVICE_INFO)
    if (len(values) != 4 or values[:3] != [FIRMWARE, FIRMWARE_VERSION, CHIP]
            or not re.fullmatch(rb"BambuHelper-[0-9A-F]{4}", values[3])):
        raise SetupError("Nie potwierdzono BambuHelper WS43B Monitor v3.8.3. Nie wysłano danych Wi-Fi.")
    return tuple(values)


def portal_url(payload, command):
    values = response(payload, command)
    if len(values) != 1:
        raise SetupError("Brak jednoznacznego adresu panelu w odpowiedzi Improv.")
    if not re.fullmatch(rb"http://(?:[0-9]{1,3}\.){3}[0-9]{1,3}/?", values[0]):
        raise SetupError("Odrzucono nieprawidłowy adres panelu; jego treść nie została wyświetlona.")
    try:
        url = urlsplit(values[0].decode("ascii"))
        address = ipaddress.IPv4Address(url.hostname)
        valid = (url.scheme == "http" and url.netloc == str(address)
                 and url.path in ("", "/") and not url.query and not url.fragment
                 and not address.is_multicast and not address.is_unspecified
                 and not address.is_loopback and str(address) != "255.255.255.255")
    except (ValueError, UnicodeError, TypeError):
        valid = False
    if not valid:
        raise SetupError("Odrzucono nieprawidłowy adres panelu; jego treść nie została wyświetlona.")
    return "http://" + str(address) + "/"


def credentials(ssid, password):
    try:
        name, secret = ssid.encode("utf-8"), password.encode("utf-8")
    except UnicodeError:
        raise SetupError("Dane Wi-Fi muszą być poprawnym UTF-8.") from None
    if not 1 <= len(name) <= 32 or any(ord(c) < 32 or ord(c) == 127 for c in ssid):
        raise SetupError("SSID musi mieć 1–32 bajty UTF-8, bez znaków sterujących.")
    valid_password = (len(secret) == 0 or 8 <= len(secret) <= 63
                      or (len(secret) == 64 and re.fullmatch(rb"[0-9A-Fa-f]{64}", secret)))
    if not valid_password or any(ord(c) < 32 or ord(c) == 127 for c in password):
        raise SetupError("Hasło musi mieć 8–63 bajty, 64 cyfry hex albo być puste dla sieci otwartej.")
    return name, secret


class Client:
    def __init__(self, port, clock=time.monotonic):
        self.port, self.clock = port, clock
        self.decoder, self.pending = Decoder(), deque()
        self.verified = None
        self.sent_credentials = False
        self.authorized = False

    def read(self, deadline):
        while self.clock() < deadline:
            if self.pending:
                return self.pending.popleft()
            self.pending.extend(self.decoder.feed(self.port.read(128)))
        raise SetupError("Brak kompletnej odpowiedzi Improv. Nie ponowiono wysyłania danych Wi-Fi.")

    def send(self, command, values=()):
        if self.pending or self.decoder.buffer:
            raise SetupError("Nieoczekiwane lub niepełne dane Improv przed kolejną komendą.")
        if command == WIFI_SETTINGS:
            if self.verified is None or not self.authorized or self.sent_credentials:
                raise SetupError("Zablokowano niepotwierdzone lub ponowne wysłanie danych Wi-Fi.")
            self.sent_credentials = True
            self.authorized = False
        packet = bytearray(rpc(command, values))
        try:
            written = self.port.write(packet)
            if written != len(packet):
                raise SetupError("Niepełny zapis USB. Nie ponowiono wysyłania danych Wi-Fi.")
            self.port.flush()
        finally:
            packet[:] = b"\0" * len(packet)

    @staticmethod
    def checked(frame_value):
        kind, payload = frame_value
        if kind == ERROR_STATE:
            # Even a forged/unknown error byte can never add text to the output.
            raise SetupError("Płytka odrzuciła żądanie Improv; sprawdź stan konfiguracji na ekranie.")
        return kind, payload

    def identify(self, timeout=15):
        self.authorized = False
        self.send(GET_DEVICE_INFO)
        kind, payload = self.checked(self.read(self.clock() + timeout))
        if kind != RPC_RESPONSE:
            raise SetupError("Nieoczekiwany stan zamiast identyfikacji firmware.")
        result = identity(payload)
        if self.verified is not None and result != self.verified:
            raise SetupError("Identyfikacja urządzenia zmieniła się; nie wysłano danych Wi-Fi.")
        self.verified = result

    def current_state(self, timeout=5):
        self.authorized = False
        self.send(GET_CURRENT_STATE)
        deadline = self.clock() + timeout
        kind, payload = self.checked(self.read(deadline))
        if kind != CURRENT_STATE or payload[0] not in (AUTHORIZED, PROVISIONED):
            raise SetupError("Płytka nie jest gotowa na konfigurację Wi-Fi.")
        if payload[0] == AUTHORIZED:
            self.authorized = True
            return None
        kind, payload = self.checked(self.read(deadline))
        if kind != RPC_RESPONSE:
            raise SetupError("Brak adresu już skonfigurowanego panelu.")
        return portal_url(payload, GET_CURRENT_STATE)

    def configure(self, ssid, password, timeout=45):
        values = credentials(ssid, password)
        # Revalidate after the private prompts, which may outlast the 3-minute
        # first-boot window. Only the same expected application may receive data.
        self.identify()
        if self.current_state() is not None:
            raise SetupError("Panel ma już Wi-Fi. Nie nadpisano konfiguracji; użyj jego portalu.")
        self.send(WIFI_SETTINGS, values)
        del values, ssid, password
        deadline = self.clock() + timeout
        expected = [(CURRENT_STATE, bytes((PROVISIONING,))),
                    (ERROR_STATE, b"\0"), (CURRENT_STATE, bytes((PROVISIONED,)))]
        for item in expected:
            if self.read(deadline) != item:
                raise SetupError("Połączenie Wi-Fi nie zostało potwierdzone. Nie ponowiono wysyłania danych.")
        kind, payload = self.checked(self.read(deadline))
        if kind != RPC_RESPONSE:
            raise SetupError("Brak odpowiedzi końcowej konfiguracji Wi-Fi.")
        return portal_url(payload, WIFI_SETTINGS)


class PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse would otherwise echo unknown arguments (possibly a password).
        self.exit(2, "Nieprawidłowe argumenty. Użyj --port PORT albo --list. Dane Wi-Fi wpisuje się prywatnie.\n")


def private_input(prompt):
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        try:
            return getpass.getpass(prompt)
        except getpass.GetPassWarning:
            raise SetupError("Terminal nie zapewnia ukrytego wpisywania. Uruchom program w interaktywnym SSH.") from None


def main(argv=None):
    parser = PrivateArgumentParser(description="Prywatna konfiguracja Wi-Fi przez Improv; bez flashowania i logowania sekretów.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--port")
    group.add_argument("--list", action="store_true")
    args = parser.parse_args(argv)
    try:
        import serial
        from serial.tools import list_ports
    except ImportError:
        print("Brak pyserial. Użyj środowiska Python przygotowanego do testu płytki.", file=sys.stderr)
        return 2
    if args.list:
        for port in list_ports.comports():
            vid = f"{port.vid:04x}" if port.vid is not None else "----"
            pid = f"{port.pid:04x}" if port.pid is not None else "----"
            print(f"{port.device} VID:PID={vid}:{pid}")
        return 0
    port = None
    try:
        print("Konfigurator wymaga wgranego BambuHelper WS43B Monitor, nie programu smoke v4.")
        print("Improv działa przez pierwsze 3 minuty rozruchu bez zapisanej sieci Wi-Fi.")
        print("Otwarcie USB może zresetować płytkę. Program nie wysyła komendy resetu ani flashowania.")
        port = serial.Serial(port=None, baudrate=115200, timeout=0.1, write_timeout=3, exclusive=True)
        port.dtr, port.rts = False, False
        port.port = args.port
        port.open()
        port.reset_input_buffer()
        client = Client(port)
        client.identify()
        existing = client.current_state()
        if existing:
            print("Panel jest już połączony. Nie zmieniono danych Wi-Fi. Portal: " + existing)
            return 0
        print("Potwierdzono BambuHelper WS43B Monitor v3.8.3 / ESP32-S3. Dane pozostaną prywatne.")
        ssid = private_input("SSID Wi-Fi 2.4 GHz (ukryte): ")
        password = private_input("Hasło Wi-Fi (ukryte): ")
        try:
            address = client.configure(ssid, password)
        finally:
            del ssid, password
        print("Płytka zgłosiła połączenie Wi-Fi. Portal: " + address)
        print("Aplikacja zapisuje konfigurację i sama restartuje panel. Potwierdź adres na ekranie po restarcie.")
        print("To nie potwierdza połączenia z drukarką, telemetrii ani testu sprzętowego.")
        return 0
    except SetupError as error:
        print(str(error), file=sys.stderr)
        return 1
    except (serial.SerialException, OSError):
        print("Błąd dostępu USB. Zamknij inne programy używające portu i sprawdź wskazany port.", file=sys.stderr)
        return 1
    except (EOFError, KeyboardInterrupt):
        print("Przerwano konfigurację. Dane Wi-Fi nie zostaną wysłane ponownie.", file=sys.stderr)
        return 1
    finally:
        if port is not None:
            try:
                port.close()
            except (serial.SerialException, OSError):
                pass  # No raw exception, buffer or credential output on USB loss.


if __name__ == "__main__":
    raise SystemExit(main())
