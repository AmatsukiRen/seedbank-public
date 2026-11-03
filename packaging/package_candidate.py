"""Produce a private Windows ZIP and checksums. Does not execute its contents."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

from collect_notices import assemble

ROOT = Path(__file__).resolve().parents[1]


def package():
    tree = ast.parse((ROOT / 'tools/seed/seedbank/__init__.py').read_text(encoding='utf-8-sig'))
    version = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == '__version__' for t in n.targets))
    label = f'SeedBank-{version}-windows-x64'
    dist = ROOT / 'dist'
    notices = ROOT / 'build/third-party'
    assemble(notices)
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    archive = dist / (label + '.zip')
    files = {'seedbank.exe': dist / 'seedbank.exe', 'LICENSE': ROOT / 'LICENSE',
             'CONTRIBUTING.md': ROOT / 'CONTRIBUTING.md',
             'THIRD_PARTY_NOTICES.md': ROOT / 'THIRD_PARTY_NOTICES.md'}
    for document in (ROOT / 'docs').rglob('*.md'):
        files[document.relative_to(ROOT).as_posix()] = document
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as out:
        for name, path in files.items():
            out.write(path, label + '/' + name)
        out.writestr(label + '/README.md', f'''# SeedBank {version}

给 AI 完整的一生。

解压后双击 seedbank.exe。使用自己的模型服务 Key，并在设置中选择自己的本地角色模型。
程序包不含维护者账号、生命包或第三方 Live2D 模型。

[开始使用](docs/getting-started.md) · [用户验收](docs/acceptance.md) · [第三方说明](THIRD_PARTY_NOTICES.md)

本包为私有候选，未运行候选验收，尚未公开发布。
对应完整源码：https://github.com/AmatsukiRen/seedbank-public/tree/{commit}
''')
        for path in sorted(notices.rglob('*')):
            if path.is_file():
                out.write(path, label + '/third-party/' + path.relative_to(notices).as_posix())
        out.writestr(label + '/build-info.json', json.dumps({
            'product': 'SeedBank', 'version': version, 'source_commit': commit,
            'candidate': True, 'tests_executed_for_this_candidate': False,
            'third_party_model_bundled': False,
        }, indent=2) + '\n')
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    sums = dist / 'SHA256SUMS.txt'
    sums.write_text(checksum + '  ' + archive.name + '\n', encoding='ascii')
    print(archive)
    print(sums)


if __name__ == '__main__':
    package()
