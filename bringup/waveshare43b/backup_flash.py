#!/usr/bin/env python3
"""Read and compare two complete 16 MiB flash backups; never writes/erases flash.
The ROM download-mode reset temporarily stops the running firmware. Disconnect
other ESP boards and verify the port before invoking. Backups may contain secrets.
"""

import argparse
import hashlib
from pathlib import Path
import subprocess
import os


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--port', required=True)
    ap.add_argument(
        '--output', type=Path, required=True, help='New directory OUTSIDE every Git worktree'
    )
    ap.add_argument(
        '--esptool',
        type=Path,
        default=Path.home() / 'Library/Arduino15/packages/esp32/tools/esptool_py/5.3.1/esptool',
    )
    args = ap.parse_args()
    dest = args.output.expanduser().resolve()
    if dest.exists():
        ap.error('Output must be a new directory; existing backups are never overwritten.')
    if any((p / '.git').exists() for p in (dest, *dest.parents)):
        ap.error('Backups must be outside all Git worktrees.')
    if not args.esptool.is_file():
        ap.error('Pinned esptool 5.3.1 is missing.')
    os.umask(0o077)
    base = [
        str(args.esptool),
        '--chip',
        'esp32s3',
        '--port',
        args.port,
        '--baud',
        '115200',
        '--after',
        'no-reset',
    ]
    result = subprocess.run(
        base + ['flash-id'], check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    )
    print(result.stdout)
    if 'Detected flash size: 16MB' not in result.stdout:
        raise SystemExit('Nie potwierdzono Flash 16MB. Przerwano; niczego nie zapisano w Flash.')
    # Read security status for human review, without any eFuse mutation.
    subprocess.run(base + ['get-security-info'], check=True)
    dest.mkdir(parents=True, mode=0o700)
    digests = []
    for name in ('flash-read1.bin', 'flash-read2.bin'):
        file = dest / name
        subprocess.run(base + ['read-flash', '0', '0x1000000', str(file)], check=True)
        if file.stat().st_size != 16 * 1024 * 1024:
            raise SystemExit(f'Błędny rozmiar kopii: {file}. Kopie pozostawiono do oceny.')
        digests.append(hashlib.sha256(file.read_bytes()).hexdigest())
    (dest / 'SHA256SUMS').write_text(
        ''.join(f'{d}  flash-read{i + 1}.bin\n' for i, d in enumerate(digests))
    )
    if digests[0] != digests[1]:
        raise SystemExit('BACKUP_FAIL: dwa odczyty mają różne SHA256. Nie wgrywaj nowego firmware.')
    print('BACKUP_OK:', dest)
    print('Dwa odczyty 16 MiB zgodne SHA256:', digests[0])
    print('Płytka pozostaje w download mode; RESET przywraca start dotychczasowego firmware.')
    print('Kopia Flash nie jest kopią eFuse ani dowodem odtwarzalności firmware szyfrowanego.')


if __name__ == '__main__':
    main()
