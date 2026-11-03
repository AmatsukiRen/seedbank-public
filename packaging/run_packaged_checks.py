"""Explicit isolated checks of the actual Windows executable, not desktop input."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def run(executable, output, model=""):
    executable, output = Path(executable).resolve(), Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    report = {"ok": False, "runtime_sha256": hashlib.sha256(executable.read_bytes()).hexdigest(), "checks": []}

    def save():
        (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    with tempfile.TemporaryDirectory(prefix="seedbank-package-acceptance-", ignore_cleanup_errors=True) as directory:
        base = Path(directory)
        env = {k: v for k, v in os.environ.items() if k.upper() in {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP"}}
        env.update(HOME=directory, USERPROFILE=directory, APPDATA=str(base / "Roaming"),
                   LOCALAPPDATA=str(base / "Local"), PYTHONUTF8="1")

        def execute(label, args, timeout):
            print("Starting " + label, flush=True)
            with (output / (label + ".stdout.log")).open("wb") as stdout, \
                 (output / (label + ".stderr.log")).open("wb") as stderr:
                process = subprocess.Popen([str(executable), *map(str, args)], cwd=directory, env=env,
                    stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                try:
                    code = process.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    # Only the process tree created by this check is terminated.
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=False)
                    process.wait(timeout=15)
                    raise
            report["checks"].append({"name": label, "exit_code": code})
            save()
            if code != 0:
                raise RuntimeError(label + " exited " + str(code))

        try:
            execute("ui", ["--ui-self-test", output / "ui.json"], 120)
            if json.loads((output / "ui.json").read_text(encoding="utf-8"))["ok"] is not True:
                raise RuntimeError("UI report did not pass")

            sys.path.insert(0, str(ROOT / "tools/seed"))
            from seedbank.plugins import PluginManager
            manager = PluginManager(base / "plugins")
            identifier = manager.install(ROOT / "examples/plugins/hello")
            if manager.list()[0]["enabled"]:
                raise RuntimeError("New plugin was enabled automatically")
            manager.enable(identifier, True)
            manager.configure(identifier, {"prefix": "人工验收"})
            with mock.patch.dict(os.environ, env, clear=True), \
                 mock.patch.object(sys, "frozen", True, create=True), \
                 mock.patch.object(sys, "executable", str(executable)):
                text = manager.run(identifier, "带伞\n钥匙", timeout=30)
            if text != "人工验收\n• 带伞\n• 钥匙":
                raise RuntimeError("Packaged plugin worker returned unexpected text")
            reopened = PluginManager(base / "plugins")
            if reopened.list()[0]["config"]["prefix"] != "人工验收":
                raise RuntimeError("Plugin setting did not survive reopen")
            report["checks"].append({"name": "frozen_plugin_worker", "ok": True, "persistent_config": True})
            save()

            if model:
                execute("native-avatar", ["--avatar-self-test", output / "avatar.json", Path(model).resolve()], 360)
                if not json.loads((output / "avatar.json").read_text(encoding="utf-8"))["ok"]:
                    raise RuntimeError("Native avatar report did not pass")
            execute("showcase", ["--capture-showcase", output / "showcase", *([Path(model).resolve()] if model else [])], 150)
            captures = json.loads((output / "showcase/capture.json").read_text(encoding="utf-8"))
            if not captures.get("completed") or len(captures.get("captures", [])) != 5:
                raise RuntimeError("Five-page capture did not finish")
            report["ok"] = True
        except Exception as error:
            report["error"] = str(error)
            raise
        finally:
            save()
    print("Packaged checks passed: " + str(output / "report.json"), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("executable")
    parser.add_argument("output")
    parser.add_argument("--model", default="")
    args = parser.parse_args()
    run(args.executable, args.output, args.model)
