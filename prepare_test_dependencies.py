#!/usr/bin/env python3
"""Fetch pinned ArduinoJson for native tests; no USB/firmware access."""
from pathlib import Path
import hashlib, io, shutil, tarfile, tempfile, urllib.request
ROOT=Path(__file__).resolve().parent
SHA='a2a8a277fc3cd0404499199bf1468682ea3688f354be0eaf6af8648366911257'
URL='https://codeload.github.com/bblanchon/ArduinoJson/tar.gz/refs/tags/v7.4.3'
DEST=ROOT/'bringup/waveshare43b/integration/vendor/ArduinoJson-7.4.3'
def main():
    if DEST.exists():
        raise SystemExit('Dependency directory already exists; refusing to overwrite.')
    with urllib.request.urlopen(URL,timeout=60) as response:
        data=response.read(10000000)
    if hashlib.sha256(data).hexdigest()!=SHA:
        raise SystemExit('Archive checksum mismatch; nothing extracted.')
    DEST.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(dir=DEST.parent) as tmp:
        target=Path(tmp)/'ArduinoJson-7.4.3';target.mkdir()
        with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as archive:
            for member in archive.getmembers():
                rel=Path(*Path(member.name).parts[1:])
                if member.issym() or member.islnk() or rel.is_absolute() or '..' in rel.parts:
                    raise RuntimeError('Unsafe archive member')
                if member.isdir():continue
                if not member.isfile():raise RuntimeError('Unexpected archive entry')
                path=target/rel;path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes(archive.extractfile(member).read())
        shutil.move(str(target),str(DEST))
    print('ArduinoJson 7.4.3 verified and ready for native tests.')
if __name__=='__main__':main()
