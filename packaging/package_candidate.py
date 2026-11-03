"""Produce a private Windows ZIP and checksums. Does not execute its contents."""
import ast
import argparse
import hashlib
import json
import re
from pathlib import Path
import subprocess
import zipfile
import tempfile
from urllib.parse import quote, unquote

from collect_notices import assemble

ROOT = Path(__file__).resolve().parents[1]


def portable_markdown(content, name, files, commit):
    """Keep bundled links local; point developer-only links at matching source."""
    def replace(match):
        target = match.group(1).strip('<>')
        if not target or target.startswith('#') or re.match(r'[a-zA-Z][\w+.-]*:', target):
            return match.group(0)
        path, separator, anchor = target.partition('#')
        resolved = (ROOT / Path(name).parent / unquote(path)).resolve()
        try:
            relative = resolved.relative_to(ROOT).as_posix()
        except ValueError:
            raise ValueError('Documentation link escapes repository: ' + name)
        if relative in files:
            return match.group(0)
        if not resolved.exists():
            raise ValueError('Missing documentation target: ' + name + ' -> ' + target)
        kind = 'tree' if resolved.is_dir() else 'blob'
        url = f'https://github.com/AmatsukiRen/seedbank-public/{kind}/{commit}/{quote(relative)}'
        return '](' + url + (separator + anchor if separator else '') + ')'
    return re.sub(r'\]\(([^)\n]+)\)', replace, content)


def application_version():
    tree = ast.parse((ROOT / 'tools/seed/seedbank/__init__.py').read_text(encoding='utf-8-sig'))
    return next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == '__version__' for t in n.targets))


def package(acceptance=None, executable=None, output_dir=None):
    version = application_version()
    label = f'SeedBank-{version}-windows-x64'
    dist = Path(output_dir).resolve() if output_dir else ROOT / 'dist'
    dist.mkdir(parents=True, exist_ok=True)
    runtime = Path(executable).resolve() if executable else ROOT / 'dist/seedbank.exe'
    # A fresh directory prevents notices left by another build environment from
    # silently becoming part of this candidate's dependency inventory.
    notices = Path(tempfile.mkdtemp(prefix='candidate-notices-', dir=ROOT / 'build'))
    assemble(notices)
    evidence = json.loads(Path(acceptance).read_text(encoding='utf-8')) if acceptance else None
    executable_hash = hashlib.sha256(runtime.read_bytes()).hexdigest()
    receipt_path = runtime.parent / 'runtime-build.json'
    if not receipt_path.is_file():
        raise ValueError('Produce the runtime with build_windows.ps1 to record its source first.')
    receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
    if receipt.get('runtime_sha256') != executable_hash or receipt.get('source_worktree_clean') is not True:
        raise ValueError('Runtime must match a clean, recorded source build.')
    if evidence and (evidence.get('ok') is not True or evidence.get('runtime_sha256') != executable_hash):
        raise ValueError('Acceptance evidence does not match this executable.')
    acceptance_text = ('本候选已完成记录中的隔离程序检查；范围见 docs/acceptance.md，不代表真实服务或长期行为验收。'
                       if evidence else '尚未运行本候选的打包程序验收。')
    commit = receipt['source_commit']
    package_commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    if package_commit != commit:
        raise ValueError('Package from the recorded source commit so runtime, docs and source stay aligned.')
    if subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=normal'], cwd=ROOT, text=True).strip():
        raise ValueError('Commit source and documentation changes before assembling the candidate.')
    archive = dist / (label + '.zip')
    files = {'seedbank.exe': runtime, 'runtime-build.json': receipt_path, 'LICENSE': ROOT / 'LICENSE',
             'CONTRIBUTING.md': ROOT / 'CONTRIBUTING.md',
             'SECURITY.md': ROOT / 'SECURITY.md', 'CHANGELOG.md': ROOT / 'CHANGELOG.md',
             'THIRD_PARTY_NOTICES.md': ROOT / 'THIRD_PARTY_NOTICES.md'}
    for name in ('README.en.md', 'README.ja.md'):
        files[name] = ROOT / name
    for asset in (ROOT / 'assets').rglob('*'):
        if asset.is_file() and asset.suffix.lower() in ('.png', '.svg', '.ico', '.json'):
            files[asset.relative_to(ROOT).as_posix()] = asset
    for document in (ROOT / 'docs').rglob('*.md'):
        files[document.relative_to(ROOT).as_posix()] = document
    for example in (ROOT / 'examples' / 'plugins').rglob('*'):
        if example.is_file() and example.suffix in ('.py', '.json', '.md'):
            files[example.relative_to(ROOT).as_posix()] = example
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as out:
        for name, path in files.items():
            if path.suffix == '.md':
                out.writestr(label + '/' + name, portable_markdown(
                    path.read_text(encoding='utf-8'), name, files, commit))
            else:
                out.write(path, label + '/' + name)
        out.writestr(label + '/README.md', f'''# SeedBank {version}

给 AI 完整的一生。

解压后双击 seedbank.exe。使用自己的模型服务 Key，并在设置中选择自己的本地角色模型。
程序包不含维护者账号、生命包或第三方 Live2D 模型。

[开始使用](docs/getting-started.md) · [用户验收](docs/acceptance.md) · [第三方说明](THIRD_PARTY_NOTICES.md)

本包为私有候选，尚未公开发布。{acceptance_text}
对应完整源码：https://github.com/AmatsukiRen/seedbank-public/tree/{commit}
''')
        for path in sorted(notices.rglob('*')):
            if path.is_file():
                out.write(path, label + '/third-party/' + path.relative_to(notices).as_posix())
        out.writestr(label + '/build-info.json', json.dumps({
            'product': 'SeedBank', 'version': version, 'source_commit': commit,
            'package_documents_commit': package_commit,
            'candidate': True, 'tests_executed_for_this_candidate': bool(evidence),
            'runtime_sha256': executable_hash,
            'checks': evidence.get('checks', []) if evidence else [],
            'third_party_model_bundled': False,
        }, indent=2) + '\n')
    source_archive = dist / f'SeedBank-{version}-source.zip'
    subprocess.run(['git', 'archive', '--format=zip', f'--prefix=SeedBank-{version}-source/',
                    '-o', str(source_archive), commit], cwd=ROOT, check=True)
    sums = dist / 'SHA256SUMS.txt'
    sums.write_text(''.join(hashlib.sha256(path.read_bytes()).hexdigest() + '  ' + path.name + '\n'
                           for path in (archive, source_archive)), encoding='ascii')
    print(archive)
    print(source_archive)
    print(sums)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--acceptance', help='Successful run_packaged_checks report for this exact exe')
    parser.add_argument('--executable', help='Produced exe, with adjacent runtime-build.json')
    parser.add_argument('--output-dir', help='Separate output directory; defaults to dist')
    args = parser.parse_args()
    package(args.acceptance, args.executable, args.output_dir)
