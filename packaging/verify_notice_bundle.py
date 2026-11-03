"""User-run check of the assembled ZIP, never imports or starts the application."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile


def verify(executable):
    runtime = Path(executable).resolve()
    receipt = json.loads((runtime.parent / 'runtime-build.json').read_text(encoding='utf-8'))
    archives = list(runtime.parent.glob('SeedBank-*-windows-x64.zip'))
    if len(archives) != 1:
        raise ValueError('Expected one Windows candidate ZIP beside the executable.')
    with zipfile.ZipFile(archives[0]) as archive:
        names = archive.namelist()
        prefixes = {name.split('/', 1)[0] for name in names}
        if len(prefixes) != 1:
            raise ValueError('Unexpected ZIP layout.')
        prefix = prefixes.pop() + '/'
        if archive.testzip() is not None:
            raise ValueError('Corrupt ZIP member.')
        for filename, heading in (
            ('LGPL-3.0-only.txt', b'GNU LESSER GENERAL PUBLIC LICENSE'),
            ('GPL-3.0-only.txt', b'GNU GENERAL PUBLIC LICENSE'),
        ):
            if heading not in archive.read(prefix + 'third-party/qt/' + filename):
                raise ValueError('Missing license text: ' + filename)
        for filename in ('NOTICE.md', 'sources.json'):
            archive.read(prefix + 'third-party/qt/' + filename)
        inventory = json.loads(archive.read(prefix + 'third-party/inventory.json'))
        if 'qt/LGPL-3.0-only.txt' not in inventory.get('shared_qt_notices', []):
            raise ValueError('Inventory does not expose Qt LGPL notice.')
        build = json.loads(archive.read(prefix + 'build-info.json'))
        runtime_hash = hashlib.sha256(runtime.read_bytes()).hexdigest()
        archived_hash = hashlib.sha256(archive.read(prefix + 'seedbank.exe')).hexdigest()
        if not (runtime_hash == archived_hash == receipt['runtime_sha256'] == build['runtime_sha256']):
            raise ValueError('Executable, receipt and ZIP do not match.')
        if build['source_commit'] != receipt['source_commit']:
            raise ValueError('Runtime source commit mismatch.')
    print(json.dumps({'ok': True, 'runtime_sha256': runtime_hash,
                      'scope': 'ZIP bytes and Qt notice presence, not complete license clearance'}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('executable')
    verify(parser.parse_args().executable)
