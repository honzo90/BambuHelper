#!/usr/bin/env python3
"""Download pinned sources/dependencies only. Never install tools, write USB or flash."""
from pathlib import Path
import ast,hashlib,io,json,subprocess,tarfile,tempfile,shutil,urllib.request
ROOT=Path(__file__).resolve().parent
HERE=ROOT/'bringup/waveshare43b/integration'
def assignments(path):
 tree=ast.parse(path.read_text());result={}
 for x in tree.body:
  if isinstance(x,ast.Assign) and isinstance(x.targets[0],ast.Name):
   try:result[x.targets[0].id]=ast.literal_eval(x.value)
   except (ValueError,TypeError):pass
 return result
def fetch(url):
 with urllib.request.urlopen(url,timeout=90) as r:return r.read()
def sha(data):return hashlib.sha256(data).hexdigest()
def main():
 cfg=assignments(HERE/'build.py');sdk=assignments(HERE/'cache64_sdk.py')
 urls={'LovyanGFX-1.2.26':'https://codeload.github.com/lovyan03/LovyanGFX/tar.gz/refs/tags/1.2.26',
 'ArduinoJson-7.4.3':'https://codeload.github.com/bblanchon/ArduinoJson/tar.gz/refs/tags/v7.4.3',
 'pubsubclient-2.8':'https://codeload.github.com/knolleary/pubsubclient/tar.gz/refs/tags/v2.8'}
 vendor=HERE/'vendor';vendor.mkdir(exist_ok=True)
 for name,(archive,expected,version) in cfg['LIBRARIES'].items():
  a=vendor/archive;data=a.read_bytes() if a.exists() else fetch(urls[name])
  if sha(data)!=expected:raise RuntimeError('Dependency checksum mismatch: '+name)
  if not a.exists():a.write_bytes(data)
  wanted={}
  with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as tar:
   for member in tar.getmembers():
    rel=Path(*Path(member.name).parts[1:])
    if rel.is_absolute() or '..' in rel.parts or member.issym() or member.islnk():raise RuntimeError('Unsafe archive member')
    if member.isdir():continue
    if not member.isfile():raise RuntimeError('Unexpected archive member')
    wanted[str(rel)]=tar.extractfile(member).read()
  dest=vendor/name
  if dest.exists():
   actual={str(p.relative_to(dest)):sha(p.read_bytes()) for p in dest.rglob('*') if p.is_file()}
   if actual!={k:sha(v) for k,v in wanted.items()}:raise RuntimeError('Existing dependency changed: '+name)
  else:
   with tempfile.TemporaryDirectory(dir=vendor) as tmp:
    stage=Path(tmp)/name;stage.mkdir()
    for rel,content in wanted.items():p=stage/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(content)
    shutil.move(str(stage),str(dest))
  print('Verified',name,flush=True)
 for rel,expected in sdk['SOURCES'].items():
  p=HERE/'cache64-inputs/esp-idf'/rel
  data=p.read_bytes() if p.exists() else fetch('https://raw.githubusercontent.com/espressif/esp-idf/'+sdk['IDF_COMMIT']+'/'+rel)
  if sha(data)!=expected:raise RuntimeError('IDF source checksum mismatch: '+rel)
  p.parent.mkdir(parents=True,exist_ok=True)
  if not p.exists():p.write_bytes(data)
 print('Verified five pinned IDF inputs',flush=True)
 ref=ROOT.parent/'waveshare-4.3b-reference';commit=cfg['REF_COMMIT']
 def git(*args):return subprocess.check_output(['git',*args],cwd=ref,text=True).strip()
 if not ref.exists():
  ref.mkdir();git('init');git('remote','add','origin','https://github.com/waveshareteam/ESP32-S3-Touch-LCD-4.3B.git')
  git('fetch','--depth','1','origin',commit);git('checkout','--detach',commit)
 if git('rev-parse','HEAD')!=commit or git('status','--porcelain'):raise RuntimeError('Reference checkout differs from pinned commit; not overwritten')
 print('Verified Waveshare reference',commit,flush=True)
if __name__=='__main__':main()
