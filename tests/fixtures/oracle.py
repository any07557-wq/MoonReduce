#!/usr/bin/python3
"""Synthetic capability fixtures. These are not discovered production bugs."""
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import time

resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
mode = sys.argv[1]
if mode == "exit":
    sys.exit(int(sys.argv[2]))
elif mode == "signal":
    os.kill(os.getpid(), int(sys.argv[2]))
elif mode == "argv":
    assert Path(sys.argv[-1]).is_absolute()
    assert Path(sys.argv[-1]).read_bytes().startswith(bytes(range(256)))
    print(json.dumps(sys.argv[2:]))
elif mode == "large":
    block = b"x" * 65536
    for _ in range(128):
        sys.stdout.buffer.write(block)
        sys.stderr.buffer.write(block)
elif mode in {"tree", "tree-worker"}:
    evidence = Path(sys.argv[2])
    if mode == "tree":
        child = subprocess.Popen([sys.executable, __file__, "tree-worker", str(evidence)])
    else:
        child = subprocess.Popen(["/usr/bin/sleep", "60"])

    def terminate(_signum, _frame):
        # Ordinary parent: reap its child when its group receives TERM.
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        child.terminate()
        child.wait(timeout=2)
        marker = "reaped" if mode == "tree" else "worker-reaped"
        (evidence / marker).write_text("child reaped")
        sys.exit(0)

    signal.signal(signal.SIGTERM, terminate)
    if mode == "tree":
        deadline = time.monotonic() + 2
        while not (evidence / "worker-pids.json").exists():
            if time.monotonic() >= deadline:
                raise TimeoutError("worker startup")
            time.sleep(0.01)
        pids = [os.getpid()] + json.loads((evidence / "worker-pids.json").read_text())
        (evidence / "pids.json").write_text(json.dumps(pids))
        (evidence / "ready").write_text("ready")
    else:
        staged = evidence / "worker-pids.tmp"
        staged.write_text(json.dumps([os.getpid(), child.pid]))
        staged.rename(evidence / "worker-pids.json")
    while True:
        time.sleep(1)
elif mode in {"stubborn-tree", "stubborn-worker"}:
    evidence = Path(sys.argv[2])
    if mode == "stubborn-worker":
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        (evidence / "worker-ready").write_text(str(os.getpid()))
    else:
        child = subprocess.Popen([sys.executable, __file__, "stubborn-worker", str(evidence)])

        def wait_for_stubborn_child(_signum, _frame):
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            child.wait()
            (evidence / "reaped").write_text("stubborn child reaped")
            sys.exit(0)

        signal.signal(signal.SIGTERM, wait_for_stubborn_child)
        deadline = time.monotonic() + 3
        while not (evidence / "worker-ready").exists():
            if time.monotonic() >= deadline:
                raise TimeoutError("stubborn child startup")
            time.sleep(.01)
        (evidence / "pids.json").write_text(json.dumps([os.getpid(), child.pid]))
        (evidence / "ready").write_text("ready")
    while True:
        time.sleep(1)
elif mode == "stubborn":
    # Direct oracle ignores TERM, requiring KILL. No orphan grandchildren.
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    evidence = Path(sys.argv[2])
    (evidence / "pids.json").write_text(json.dumps([os.getpid()]))
    (evidence / "ready").write_text("ready")
    while True:
        time.sleep(1)
elif mode == "check-tree":
    evidence = Path(sys.argv[2])
    pids = json.loads((evidence / "pids.json").read_text())
    # Require /proc disappearance, not just a successful kill() or no heartbeat.
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        if all(not Path(f"/proc/{pid}").exists() for pid in pids):
            sys.exit(0)
        time.sleep(0.01)
    print(f"processes not reaped: {pids}", file=sys.stderr)
    sys.exit(7)
else:
    raise ValueError(mode)
