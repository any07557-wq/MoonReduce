#!/usr/bin/python3
"""Synthetic CLI oracles; markers are plumbing examples, not production bugs."""
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import sys

resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
mode = sys.argv[1]
candidate = Path(sys.argv[-1])
assert candidate.is_absolute(), candidate
data = candidate.read_bytes()
if trace := os.environ.get("MOONREDUCE_CALL_LOG"):
    with open(trace, "a", encoding="utf-8") as output:
        output.write(json.dumps({
            "path": str(candidate), "argv": sys.argv[1:],
            "size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
        }) + "\n")

if mode == "exit":
    sys.exit(int(sys.argv[2]))
elif mode == "signal":
    os.kill(os.getpid(), int(sys.argv[2]))
elif mode == "always":
    sys.exit(0)
elif mode == "mutate":
    candidate.write_bytes(b"modified by oracle")
    sys.exit(0)
elif mode == "has-empty-line":
    sys.exit(0 if data.startswith(b"\n") or b"\n\n" in data else 1)
elif mode == "path-sensitive":
    sys.exit(1 if candidate == Path(sys.argv[2]) else 0)
elif mode == "unresolved-small":
    sys.exit(0 if len(data.splitlines()) >= 2 else 2)
elif mode == "hang-after-first":
    counter = Path(sys.argv[2])
    evidence = Path(sys.argv[3])
    count = int(counter.read_text()) if counter.exists() else 0
    counter.write_text(str(count + 1))
    if count == 0:
        sys.exit(0)
    tree = Path(__file__).with_name("oracle.py")
    os.execv(sys.executable, [sys.executable, str(tree), "tree", str(evidence), str(candidate)])
elif mode in {"contains", "contains-hex", "large"}:
    needle = bytes.fromhex(sys.argv[2]) if mode == "contains-hex" else sys.argv[2].encode()
    if mode == "large":
        block = b"x" * 65536
        for _ in range(128):
            sys.stdout.buffer.write(block)
            sys.stderr.buffer.write(block)
    sys.exit(0 if needle in data else 1)
else:
    raise ValueError(mode)
