"""Read a produced executable's archive and icon; never starts the application."""
import argparse
import hashlib
import json
from pathlib import Path

from PyInstaller.archive.readers import CArchiveReader
import pefile
from qt_distribution import excluded_qt_entry


def verify(executable):
    path = Path(executable).resolve()
    names = list(CArchiveReader(str(path)).toc)
    forbidden = [name for name in names if excluded_qt_entry(name) or
                 name.lower().endswith((".moc3", ".model3.json", ".motion3.json"))]
    pe = pefile.PE(str(path), fast_load=True)
    try:
        pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_RESOURCE"]])
        resource_ids = {entry.id for entry in pe.DIRECTORY_ENTRY_RESOURCE.entries}
        icon = 3 in resource_ids and 14 in resource_ids
    finally:
        pe.close()
    report = {"ok": not forbidden and icon, "executable": path.name,
              "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size,
              "archive_entries": len(names), "forbidden_entries": forbidden, "icon_resources": icon,
              "scope": "CArchive contents and Windows icon resources; not complete license clearance"}
    print(json.dumps(report, indent=2))
    return report["ok"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("executable")
    arguments = parser.parse_args()
    raise SystemExit(0 if verify(arguments.executable) else 1)
