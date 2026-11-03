"""Assemble dependency license texts for a private candidate; no app imports."""
from importlib import metadata
import ast
import json
from pathlib import Path
import shutil
import sys

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[1]


def copy_qt_notices(destination, pyside_version):
    """Keep LGPL texts even when a wheel ships only a commercial reference."""
    folder = ROOT / 'packaging/licenses/qt'
    provenance = json.loads((folder / 'sources.json').read_text(encoding='utf-8'))
    if provenance['pyside_version'] != pyside_version:
        raise ValueError('Update Qt source/notice provenance for this PySide6 version.')
    copied = []
    for name in ('LGPL-3.0-only.txt', 'GPL-3.0-only.txt', 'NOTICE.md', 'sources.json'):
        target = destination / 'qt' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(folder / name, target)
        copied.append(target.relative_to(destination).as_posix())
    return copied


def assemble(destination: Path):
    destination.mkdir(parents=True, exist_ok=True)
    qt_notices = copy_qt_notices(destination, metadata.version('PySide6'))
    queue = ['PyInstaller', 'PySide6', 'shiboken6', 'live2d-py', 'PyOpenGL',
             'Pillow', 'numpy', 'discord.py', 'lark-oapi', 'dingtalk-stream']
    # Some optional imports (voice/crypto, for example) are collected by the
    # freezer even though they are not mandatory Requires-Dist dependencies.
    # Read its assembly manifest, never import those packages to discover them.
    toc = ROOT / 'build/seedbank/Analysis-00.toc'
    if toc.is_file():
        packages = metadata.packages_distributions()
        for node in ast.walk(ast.parse(toc.read_text(encoding='utf-8'))):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                value = node.value.replace('\\', '/')
                if '/site-packages/' in value:
                    package = value.split('/site-packages/', 1)[1].split('/', 1)[0].split('.')[0]
                    queue.extend(packages.get(package, ()))
    seen, inventory = set(), []
    while queue:
        name = canonicalize_name(queue.pop())
        if name in seen:
            continue
        seen.add(name)
        dist = metadata.distribution(name)
        copied = []
        for file in dist.files or ():
            # Preserve original notices only: no direct_url.json or environment data.
            leaf = file.name.lower()
            if not (leaf.startswith(('license', 'copying', 'notice', 'copyright')) or '/licenses/' in str(file).lower()):
                continue
            source = Path(dist.locate_file(file))
            if not source.is_file():
                continue
            safe_parts = [part for part in file.parts if part not in ('..', '.', '/')]
            target = destination / name / Path(*safe_parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            copied.append(target.relative_to(destination).as_posix())
        supplemental = ROOT / 'packaging/licenses' / f'{dist.metadata["Name"]}-{dist.version}.txt'
        if supplemental.is_file():
            target = destination / name / supplemental.name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(supplemental, target)
            copied.append(target.relative_to(destination).as_posix())
        if name == 'shiboken6' or name.startswith('pyside6'):
            copied.extend(qt_notices)
        inventory.append({'name': dist.metadata['Name'], 'version': dist.version,
                          'license_expression': dist.metadata.get('License-Expression', ''),
                          'license_metadata': dist.metadata.get('License', ''),
                          'homepage': dist.metadata.get('Home-page', ''),
                          'project_urls': dist.metadata.get_all('Project-URL') or [],
                          'license_files': sorted(copied)})
        for value in dist.requires or ():
            requirement = Requirement(value)
            if requirement.marker is None or requirement.marker.evaluate({'extra': ''}):
                queue.append(requirement.name)
    for folder in (Path(sys.base_prefix), Path(sys.executable).parent):
        source = folder / 'LICENSE.txt'
        if source.is_file():
            shutil.copyfile(source, destination / 'PYTHON-LICENSE.txt')
            break
    inventory.sort(key=lambda row: row['name'].lower())
    (destination / 'inventory.json').write_text(json.dumps({
        'python': sys.version.split()[0], 'dependencies': inventory,
        'shared_qt_notices': qt_notices,
        'scope': 'Build dependency metadata and original notices; publication clearance pending.'
    }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return inventory


if __name__ == '__main__':
    assemble(ROOT / 'build' / 'third-party')
