"""Internal one-shot worker. No life pack/session, provider or UI is loaded here."""
import contextlib
import json
from pathlib import Path
import runpy
import sys
import traceback

from .plugins import PROTOCOL


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        return 2
    stage = "request"
    try:
        request = json.loads(sys.stdin.buffer.read(20001).decode("utf-8"))
        if not isinstance(request, dict) or request.get("protocol") != PROTOCOL:
            return 2
        entry = Path(args[0]).resolve()
        stage = "load"
        sys.path.insert(0, str(entry.parent))
        # Plugin prints go to diagnostics, never mixed into the response protocol.
        with contextlib.redirect_stdout(sys.stderr):
            module = runpy.run_path(str(entry), run_name="seedbank_user_plugin")
            stage = "handle"
            result = module["handle"](request)
        stage = "response"
        if not isinstance(result, dict) or not isinstance(result.get("text"), str) or len(result["text"]) > 12000:
            return 3
        # JSON escapes preserve Unicode even under an embedding host's legacy
        # text encoding. The protocol bytes remain valid UTF-8/ASCII.
        sys.stdout.write(json.dumps({"protocol": PROTOCOL, "text": result["text"]}, ensure_ascii=True))
        sys.stdout.flush()
        return 0
    except Exception as error:
        # Diagnostics contain no exception values, source expressions, request
        # text or full paths. The UI keeps third-party stderr private.
        try:
            sys.stderr.write("Plugin worker failed: " + stage + " / " + type(error).__name__ + "\n")
            for frame in traceback.extract_tb(error.__traceback__):
                sys.stderr.write(Path(frame.filename).name + ":" + str(frame.lineno) + " " + frame.name + "\n")
            sys.stderr.flush()
        except (OSError, AttributeError):
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
