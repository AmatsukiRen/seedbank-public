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


def package(acceptance=None):
    tree = ast.parse((ROOT / 'tools/seed/seedbank/__init__.py').read_text(encoding='utf-8-sig'))
    version = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == '__version__' for t in n.targets))
    label = f'SeedBank-{version}-windows-x64'
    dist = ROOT / 'dist'
    # A fresh directory prevents notices left by another build environment from
    # silently becoming part of this candidate's dependency inventory.
    notices = Path(tempfile.mkdtemp(prefix='candidate-notices-', dir=ROOT / 'build'))
    assemble(notices)
    evidence = json.loads(Path(acceptance).read_text(encoding='utf-8')) if acceptance else None
    executable_hash = hashlib.sha256((dist / 'seedbank.exe').read_bytes()).hexdigest()
    if evidence and (evidence.get('ok') is not True or evidence.get('runtime_sha256') != executable_hash):
        raise ValueError('Acceptance evidence does not match this executable.')
    acceptance_text = ('本候选已完成记录中的隔离程序检查；范围见 docs/acceptance.md，不代表真实服务或长期行为验收。'
                       if evidence else '尚未运行本候选的打包程序验收。')
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    archive = dist / (label + '.zip')
    files = {'seedbank.exe': dist / 'seedbank.exe', 'LICENSE': ROOT / 'LICENSE',
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
            'candidate': True, 'tests_executed_for_this_candidate': bool(evidence),
            'runtime_sha256': executable_hash,
            'checks': evidence.get('checks', []) if evidence else [],
            'third_party_model_bundled': False,
        }, indent=2) + '\n')
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    sums = dist / 'SHA256SUMS.txt'
    sums.write_text(checksum + '  ' + archive.name + '\n', encoding='ascii')
    print(archive)
    print(sums)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--acceptance', help='Successful run_packaged_checks report for this exact exe')
    package(parser.parse_args().acceptance)
