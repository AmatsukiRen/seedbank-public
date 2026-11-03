"""Record the installed Windows build dependency closure, without secrets/paths."""
import importlib.metadata as metadata
import platform
import tomllib
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parents[1]


def freeze():
    project = tomllib.loads((ROOT / "tools/seed/pyproject.toml").read_text(encoding="utf-8"))
    pending = project["project"]["optional-dependencies"]["desktop"] + project["project"]["optional-dependencies"]["channels"]
    pending += ["PyInstaller==6.22.3", "setuptools", "numpy"]
    versions, visited = {}, set()
    while pending:
        requirement = Requirement(pending.pop())
        distribution = metadata.distribution(requirement.name)
        name = canonicalize_name(distribution.metadata["Name"])
        if requirement.specifier and distribution.version not in requirement.specifier:
            raise RuntimeError("Installed dependency does not satisfy " + str(requirement))
        versions[name] = distribution.version
        extras = {"", *requirement.extras}
        for extra in extras:
            if (name, extra) in visited:
                continue
            visited.add((name, extra))
            for value in distribution.requires or []:
                dependency = Requirement(value)
                if dependency.marker is None or dependency.marker.evaluate({"extra": extra}):
                    pending.append(str(dependency))
    target = ROOT / "packaging/requirements-windows.lock"
    target.write_text("# Windows x64; Python " + platform.python_version() + "\n"
        "# Generated from the installed build dependency closure; no model credentials.\n"
        + "\n".join(name + "==" + versions[name] for name in sorted(versions)) + "\n", encoding="utf-8")
    print(f"Recorded {len(versions)} pinned dependencies in {target.name}")


if __name__ == "__main__":
    freeze()
