"""Internal one-shot worker. No life pack/session, provider or UI is loaded here."""
import contextlib
import json
from pathlib import Path
import runpy
import sys

from .plugins import PROTOCOL


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        return 2
    try:
        request = json.loads(sys.stdin.buffer.read(20001).decode("utf-8"))
        if not isinstance(request, dict) or request.get("protocol") != PROTOCOL:
            return 2
        entry = Path(args[0]).resolve()
        sys.path.insert(0, str(entry.parent))
        # Plugin prints go to diagnostics, never mixed into the response protocol.
        with contextlib.redirect_stdout(sys.stderr):
            module = runpy.run_path(str(entry), run_name="seedbank_user_plugin")
            result = module["handle"](request)
        if not isinstance(result, dict) or not isinstance(result.get("text"), str) or len(result["text"]) > 12000:
            return 3
        sys.stdout.write(json.dumps({"protocol": PROTOCOL, "text": result["text"]}, ensure_ascii=False))
        sys.stdout.flush()
        return 0
    except Exception:
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
