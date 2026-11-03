"""Local repository readiness checks. Never prints matched secret values."""
import argparse
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
SECRET = re.compile(rb"(?:sk-[A-Za-z0-9_-]{32,}|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)")
FORBIDDEN = re.compile(r"(?i)(?:\.life/|\.dpapi$|\.moc3$|\.model3\.json$|\.motion3\.json$|(?:^|/)\.env(?:\.|$)|\.(?:exe|zip|log|dmp)$)")


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def check(history=False):
    paths = sorted(set(git("ls-files", "--cached", "--others", "--exclude-standard", "-z").decode().split("\0")) - {""})
    issues = []
    for name in paths:
        path = ROOT / name
        if not path.is_file():
            continue
        if FORBIDDEN.search(name):
            issues.append("Excluded private/generated path: " + name)
        data = path.read_bytes()
        if SECRET.search(data):
            issues.append("Potential credential: " + name)
        if path.suffix == ".json":
            json.loads(data.decode("utf-8-sig"))
        if path.suffix != ".md":
            continue
        content = re.sub(r"```.*?```", "", data.decode("utf-8"), flags=re.S)
        links = re.findall(r"\[[^\]]*\]\(([^)]+)\)", content)
        links += re.findall(r'(?:src|href)="([^"#]+)"', content)
        for link in links:
            link = link.strip("<>").split("#", 1)[0]
            if not link or re.match(r"[a-zA-Z][\w+.-]*:", link):
                continue
            if not (path.parent / unquote(link)).exists():
                issues.append("Missing link: " + name + " -> " + link)
    blobs = 0
    if history:
        objects = git("rev-list", "--objects", "--all").decode().splitlines()
        # Batch-read every historical blob once. Inspect only in memory; never
        # extract credentials or personal files into an audit artifact.
        payload = "\n".join(row.split(" ", 1)[0] for row in objects).encode() + b"\n"
        sizes = subprocess.check_output(["git", "cat-file", "--batch-check"], input=payload, cwd=ROOT).decode().splitlines()
        process = subprocess.Popen(["git", "cat-file", "--batch"], cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        try:
            for row, info in zip(objects, sizes):
                fields = info.split()
                if len(fields) != 3 or fields[1] != "blob":
                    continue
                identifier, _, size = fields
                name = row.partition(" ")[2]
                if FORBIDDEN.search(name):
                    issues.append("Historical excluded path: " + name)
                process.stdin.write(identifier.encode() + b"\n")
                process.stdin.flush()
                process.stdout.readline()
                data = process.stdout.read(int(size))
                process.stdout.read(1)
                if SECRET.search(data):
                    issues.append("Historical potential credential: " + identifier[:12] + " " + name)
                blobs += 1
        finally:
            process.stdin.close()
            process.stdout.close()
            process.wait()
    report = {"ok": not issues, "current_files": len(paths), "historical_blobs": blobs,
              "scope": "local links, JSON, excluded paths and common credential patterns; not exhaustive secret detection",
              "issues": sorted(set(issues))}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report["ok"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--history", action="store_true")
    options = parser.parse_args()
    raise SystemExit(0 if check(options.history) else 1)
