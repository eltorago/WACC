"""Build an unsigned offline Windows folder and inventory its actual files."""
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default=str(ROOT / 'data/local/offline-build'))
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    for relative in ('dist/wacc','work','wacc.spec'):
        if output not in (output/relative).resolve().parents:
            raise ValueError('Build target escapes the selected output directory.')
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--onedir', '--noupx', '--name', 'wacc',
                    '--paths', str(ROOT), '--distpath', str(output / 'dist'), '--workpath', str(output / 'work'),
                    '--specpath', str(output), '--add-data', str(ROOT / 'packaging/trusted-corpus-keys.json') + ';packaging',
                    '--add-data', str(ROOT / 'sources/permissions.json') + ';sources',
                    '--add-data', str(ROOT / 'data/wa-audit-context.json') + ';data',
                    '--add-data', str(ROOT / 'data/policy') + ';data/policy',
                    '--collect-all', 'pypdf', '--hidden-import', 'cryptography.hazmat.primitives.asymmetric.ed25519',
                    str(ROOT / 'packaging/policy_entry.py')], check=True, cwd=ROOT)
    payload = output / 'dist/wacc'
    # Preserve the installed distributions' licence notices in the payload.
    for name in ('pypdf','pdfplumber','pdfminer.six','Pillow','pypdfium2','charset-normalizer','cryptography','cffi','pyinstaller'):
        dist=importlib.metadata.distribution(name)
        for entry in dist.files or ():
            if 'license' in str(entry).lower() or 'copying' in str(entry).lower():
                source=Path(dist.locate_file(entry))
                if source.is_file() and source.suffix.lower() not in ('.py','.pyc'):
                    target=payload/'_internal/licenses'/name/source.name
                    target.parent.mkdir(parents=True,exist_ok=True)
                    target.write_bytes(source.read_bytes())
    python_notice=Path(sys.base_prefix)/'LICENSE.txt'
    if python_notice.is_file():
        target=payload/'_internal/licenses/Python-LICENSE.txt';target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(python_notice.read_bytes())
    inventory = []
    for path in sorted(payload.rglob('*')):
        if path.is_file():
            inventory.append(dict(path=path.relative_to(payload).as_posix(), size=path.stat().st_size,
                                  sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                                  trust='Signing status not verified; pilot build and agency approval required',
                                  role='executable dependency' if path.suffix.lower() in ('.exe','.dll','.pyd') else 'runtime asset',
                                  expectedLoadLocation='Approved installation folder'))
    components = []
    for name in ('pypdf','pdfplumber','pdfminer.six','Pillow','pypdfium2','charset-normalizer','cryptography','pyinstaller','cffi'):
        dist = importlib.metadata.distribution(name)
        components.append(dict(type='library', name=name, version=dist.version, purl='pkg:pypi/' + name + '@' + dist.version))
    manifest = dict(status='Unsigned engineering pilot — not an approved deployment package',
                    repositoryRevision=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                    python=sys.version, files=inventory,
                    workingTreeChanges=subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).splitlines(),
                    sourceCorpus='Not bundled. Use Framework updates or set WACC_LIBRARY to an authorised local source collection.',
                    blockers=['Production signing identity', 'Managed installer', 'Human-approved signed corpus', 'Clean-machine and enforced application-control tests', 'Accessibility acceptance'])
    (output / 'release-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    (output / 'sbom.cdx.json').write_text(json.dumps(dict(bomFormat='CycloneDX', specVersion='1.5', version=1,
        metadata={'component': {'type':'application', 'name':'WACC', 'version':'0.1.0-pilot'}}, components=components), indent=2), encoding='utf-8')
    (output / 'SHA256SUMS.txt').write_text('\n'.join(f['sha256'] + '  ' + f['path'] for f in inventory), encoding='utf-8')
    print(str(payload / 'wacc.exe'))


if __name__ == '__main__':
    main()
