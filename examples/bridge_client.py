"""Offline reference client. Prepared, not executed or certified in this draft.

Requires an existing R&D delivery or source tree and an explicit artificial pack.
Never auto-discovers user configuration, creates a life, or retries a write.
"""
import argparse
import json
from pathlib import Path
import queue
import subprocess
import sys
import threading
import uuid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", type=Path, required=True)
    entry = parser.add_mutually_exclusive_group(required=True)
    entry.add_argument("--exe", type=Path)
    entry.add_argument("--seed-script", type=Path)
    parser.add_argument("--message", help="Optional artificial message to write")
    args = parser.parse_args()
    pack = args.pack.resolve()
    program = (args.exe or args.seed_script).resolve()
    if not program.is_file() or not (pack / "birth.json").is_file():
        parser.error("Provide an existing program and a separate artificial life pack.")
    command = [str(program)] if args.exe else [sys.executable, str(program)]
    command += ["bridge", str(pack), "--brain", "stub"]
    # stderr inherits the console so diagnostics cannot fill an unread pipe.
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                               text=True, encoding="utf-8", bufsize=1)
    responses = queue.Queue()

    def read_lines():
        try:
            for line in process.stdout:
                responses.put(line)
        finally:
            responses.put(None)

    reader = threading.Thread(target=read_lines, daemon=True)
    reader.start()

    def request(op, **fields):
        rid = uuid.uuid4().hex
        process.stdin.write(json.dumps({"id": rid, "op": op, **fields}, ensure_ascii=False) + "\n")
        process.stdin.flush()
        try:
            line = responses.get(timeout=30)
        except queue.Empty:
            raise RuntimeError("Response timed out. No automatic retry was made.") from None
        if line is None:
            raise RuntimeError("Bridge closed its output; see stderr for details.")
        reply = json.loads(line)
        if not isinstance(reply, dict) or reply.get("id") != rid:
            raise RuntimeError("Unexpected response correlation; stop rather than guessing.")
        if reply.get("ok") is not True:
            raise RuntimeError(reply.get("error", "Bridge rejected the request"))
        print(json.dumps(reply, ensure_ascii=False, indent=2))
        return reply

    try:
        hello = request("hello")
        if hello.get("protocol") != "seedbank/bridge@1":
            raise RuntimeError("Unsupported bridge protocol")
        request("lifecycle", action="status")
        if args.message:
            write_id = "example_" + uuid.uuid4().hex
            print("Write request_id:", write_id, file=sys.stderr, flush=True)
            request("message", text=args.message, speaker="Example user",
                    person_id="owner", request_id=write_id)
        request("stop")
        process.wait(timeout=10)
        return process.returncode
    finally:
        process.stdin.close()
        if process.poll() is None:
            # Own child only. The caller must investigate incomplete writes.
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        reader.join(timeout=1)
        process.stdout.close()


if __name__ == "__main__":
    raise SystemExit(main())
