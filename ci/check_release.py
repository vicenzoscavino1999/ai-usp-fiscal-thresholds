"""Export and verify only the manifested source payload; this is not a model run."""
from pathlib import Path
import argparse, hashlib, json, shutil, subprocess, sys

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--destination',type=Path,required=True)
    ap.add_argument('--report',type=Path,required=True)
    args=ap.parse_args()
    root=Path(__file__).resolve().parents[1]
    dest=args.destination.resolve()
    if dest.exists() or dest==root or root in dest.parents:
        raise RuntimeError('Use a new destination outside the source checkout')
    manifest=json.loads((root/'SOURCE_MANIFEST.json').read_text(encoding='utf-8'))
    dest.mkdir(parents=True)
    for name in [*manifest['files'],'SOURCE_MANIFEST.json']:
        source=(root/name).resolve();target=(dest/name).resolve()
        if not source.is_relative_to(root) or not target.is_relative_to(dest):
            raise RuntimeError('Nonportable source path')
        if name in manifest['files']:
            with source.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
            if digest!=manifest['files'][name]:raise RuntimeError('Source hash differs: '+name)
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
    return subprocess.call([sys.executable,'-B',str(dest/'verify_package.py'),'--root',str(dest),'--source-only','--report',str(args.report.resolve())])

if __name__=='__main__':raise SystemExit(main())
