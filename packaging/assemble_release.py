"""Assemble release documents around an existing user-tested runtime; never run it.

The runtime source snapshot stays unchanged. Documentation has its own commit,
and upstream source archives are separate release assets, not application data.
"""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

from package_candidate import portable_markdown

ROOT = Path(__file__).resolve().parents[1]
REPO = 'https://github.com/AmatsukiRen/seedbank-public'


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def is_notice(name):
    path = PurePosixPath(name)
    leaf = path.name.lower()
    return (not path.is_absolute() and '..' not in path.parts
            and (any(part.lower() in ('licenses', 'license') for part in path.parts)
                 or re.match(r'^(licen[sc]e|copying|notice|copyright|authors|ftl)([._-]|$)', leaf)
                 or leaf == 'qt_attribution.json'
                 or ('3rdparty' in path.parts and leaf.startswith('readme'))))


def upstream_notices(path, group):
    if path.suffix == '.zip':
        with zipfile.ZipFile(path) as source:
            for info in source.infolist():
                if not info.is_dir() and is_notice(info.filename):
                    yield group + '/' + info.filename, source.read(info)
    else:
        with tarfile.open(path, 'r:xz') as source:
            for member in source:
                if member.isfile() and is_notice(member.name):
                    with source.extractfile(member) as stream:
                        yield group + '/' + member.name, stream.read()


def assemble(candidate, upstream, report, output):
    candidate, upstream, output = map(lambda p: Path(p).resolve(), (candidate, upstream, output))
    if output == candidate or output in candidate.parents:
        raise ValueError('Use a separate release output directory.')
    output.mkdir(parents=True, exist_ok=True)
    receipt = json.loads((candidate / 'runtime-build.json').read_text(encoding='utf-8'))
    evidence = json.loads(Path(report).read_text(encoding='utf-8'))
    runtime_hash = digest(candidate / 'seedbank.exe')
    if not (receipt['runtime_sha256'] == evidence['runtime_sha256'] == runtime_hash
            and evidence['ok'] is True and receipt['source_worktree_clean'] is True):
        raise ValueError('Use the exact runtime recorded by the user acceptance report.')
    docs_commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip():
        raise ValueError('Commit release documentation before assembly.')
    runtime_source = receipt['source_commit']
    changed = subprocess.check_output(['git', 'diff', '--name-only', runtime_source, docs_commit],
                                      cwd=ROOT, text=True).splitlines()
    if any(name.startswith(('tools/seed/', 'eggs/', 'examples/plugins/'))
           or name in ('packaging/seedbank.spec', 'packaging/windows_entry.py',
                       'packaging/startup_hook.py', 'packaging/qt_distribution.py',
                       'packaging/requirements-windows.lock') for name in changed):
        raise ValueError('Runtime inputs changed; produce and accept a new runtime instead.')

    provenance = json.loads((ROOT / 'packaging/licenses/qt/sources.json').read_text(encoding='utf-8'))
    source_assets = []
    notice_files = {}
    for item in provenance['upstream_source_candidates']:
        filename = item['url'].rsplit('/', 1)[-1]
        path = upstream / filename
        actual = digest(path)
        if actual != item['upstream_published_sha256'] or path.stat().st_size != item['upstream_published_bytes']:
            raise ValueError('Downloaded source bytes differ from upstream metadata: ' + filename)
        shutil.copyfile(path, output / filename)
        source_assets.append({**item, 'asset': filename, 'sha256': actual,
                              'download': f'{REPO}/releases/download/v0.0.1/{filename}'})
        group = 'qt' if filename.startswith('qt-') else 'pyside'
        for name, data in upstream_notices(path, group):
            notice_files['third-party/qt/upstream-notices/' + name] = data

    overlays = {}
    for name in ('README.md', 'README.en.md', 'README.ja.md', 'LICENSE', 'CHANGELOG.md',
                 'CONTRIBUTING.md', 'SECURITY.md', 'THIRD_PARTY_NOTICES.md'):
        overlays[name] = ROOT / name
    for base in ('docs', 'assets/brand'):
        for path in (ROOT / base).rglob('*.md'):
            overlays[path.relative_to(ROOT).as_posix()] = path
    for name in ('NOTICE.md', 'sources.json'):
        overlays['third-party/qt/' + name] = ROOT / 'packaging/licenses/qt' / name

    base_zip = candidate / 'SeedBank-0.0.1-windows-x64.zip'
    target = output / base_zip.name
    with zipfile.ZipFile(base_zip) as source:
        prefix = next(info.filename.split('/', 1)[0] for info in source.infolist()) + '/'
        available = {n[len(prefix):] for n in source.namelist()} | set(overlays) | set(notice_files)
        with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            replaced = set(overlays) | {'build-info.json', 'release-provenance.json'}
            for info in source.infolist():
                relative = info.filename[len(prefix):]
                if relative not in replaced:
                    archive.writestr(info, source.read(info))
            for name, path in overlays.items():
                if path.suffix == '.md':
                    content = portable_markdown(path.read_text(encoding='utf-8'),
                                                path.relative_to(ROOT).as_posix(), available, docs_commit)
                    archive.writestr(prefix + name, content)
                else:
                    archive.write(path, prefix + name)
            for name, data in notice_files.items():
                archive.writestr(prefix + name, data)
            build_info = json.loads(source.read(prefix + 'build-info.json'))
            build_info.update(package_documents_commit=docs_commit, candidate=False,
                              release_stage='preview', tests_executed_for_this_candidate=True,
                              checks=evidence['checks'], archive_after_document_update_tested=False)
            archive.writestr(prefix + 'build-info.json', json.dumps(build_info, indent=2) + '\n')
            publication = {
                'version': '0.0.1', 'runtime_source_commit': runtime_source,
                'documentation_commit': docs_commit, 'runtime_sha256': runtime_hash,
                'runtime_rebuilt': False, 'user_acceptance_date': '2026-11-04',
                'checks': evidence['checks'], 'original_windows_zip_sha256': digest(base_zip),
                'application_executed_during_release_assembly': False,
                'tests_executed_during_release_assembly': False,
                'third_party_model_bundled': False, 'upstream_sources': source_assets,
                'source_notice_files': len(notice_files),
                'source_notice_scope': 'Conservative upstream source notice collection; includes unused modules.',
            }
            archive.writestr(prefix + 'release-provenance.json', json.dumps(publication, indent=2) + '\n')
    for name in ('SeedBank-0.0.1-source.zip', 'runtime-build.json'):
        shutil.copyfile(candidate / name, output / name)
    shutil.copyfile(ROOT / 'THIRD_PARTY_NOTICES.md', output / 'THIRD_PARTY_NOTICES.md')
    (output / 'release-provenance.json').write_text(json.dumps(publication, indent=2) + '\n', encoding='utf-8')
    filenames = [base_zip.name, 'SeedBank-0.0.1-source.zip',
                 *[item['asset'] for item in source_assets], 'runtime-build.json',
                 'THIRD_PARTY_NOTICES.md', 'release-provenance.json']
    (output / 'SHA256SUMS.txt').write_text(''.join(digest(output / n) + '  ' + n + '\n' for n in filenames),
                                        encoding='ascii')
    print(json.dumps({'output': str(output), 'runtime_sha256': runtime_hash,
                      'source_notice_files': len(notice_files), 'assets': filenames,
                      'tests_run': False}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--candidate', required=True)
    parser.add_argument('--upstream', required=True)
    parser.add_argument('--report', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    assemble(args.candidate, args.upstream, args.report, args.output)
