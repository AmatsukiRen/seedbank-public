"""Network guard used only by the explicitly launched offline regression suite."""
import os
import sys


def block_network(event, args):
    if event in ("socket.connect", "socket.bind", "socket.getaddrinfo", "socket.sendto"):
        raise RuntimeError("Network access is disabled for the SEEDbank offline regression suite")


if os.environ.get("SEEDBANK_OFFLINE_REGRESSION") == "1":
    sys.addaudithook(block_network)
