"""Record GUI startup before dependency runtime hooks, without importing Qt."""
import sys

if len(sys.argv) == 1 or sys.argv[1:] == ["--safe-graphics"]:
    from seedbank import startup_log

    startup_log.enable()
    startup_log.mark("runtime_hook.entered")
