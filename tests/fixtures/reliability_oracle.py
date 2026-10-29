#!/usr/bin/python3
"""Synthetic, externally counted fault scenarios. Not a production bug example."""
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import subprocess
import sys
import time

resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
scenario = Path(sys.argv[1])
candidate = Path(sys.argv[-1])
assert candidate.is_absolute()
plan = json.loads((scenario / "plan.json").read_text())
trace = scenario / "calls.jsonl"
rows = trace.read_text().splitlines() if trace.exists() else []
number = len(rows) + 1
data = candidate.read_bytes()
saved = Path(plan["output"])
row = {
    "number": number, "pid": os.getpid(), "path": str(candidate),
    "hex": data.hex(), "sha256": hashlib.sha256(data).hexdigest(),
    "saved_hex": saved.read_bytes().hex() if saved.is_file() else None,
}
with trace.open("a") as log:
    log.write(json.dumps(row) + "\n")
    log.flush()
    os.fsync(log.fileno())
action = plan.get("calls", {}).get(str(number), {})
if "expect_hex" in action:
    assert data.hex() == action["expect_hex"], (row, action)
if "chmod" in action:
    os.chmod(action["chmod"], 0o500)
if "touch" in action:
    Path(action["touch"]).touch()
if "create_file" in action:
    Path(action["create_file"]).write_bytes(b"concurrent file: preserve me")
if action.get("break_log"):
    # Read diagnostic failure after the child has closed its inherited log.
    (candidate.parent / "stderr.log").unlink()
    (candidate.parent / "stderr.log").mkdir()
if action.get("large"):
    block = b"x" * 65536
    for _ in range(512):  # 32 MiB in each stream, no pipe back to the driver.
        sys.stdout.buffer.write(block)
        sys.stderr.buffer.write(block)
    sys.stdout.flush()
    sys.stderr.flush()
if "tree" in action:
    evidence = scenario / "evidence"
    evidence.mkdir(exist_ok=True)
    tree = Path(__file__).with_name("oracle.py")
    os.execv(sys.executable, [sys.executable, str(tree), action["tree"], str(evidence)])
if action.get("leave_child"):
    # An ordinary child remains in the inherited process group after its parent
    # exits. This also exercises cleanup after successful process.wait().
    evidence = scenario / "evidence"
    evidence.mkdir(exist_ok=True)
    tree = Path(__file__).with_name("oracle.py")
    child = subprocess.Popen([sys.executable, str(tree), "stubborn-worker", str(evidence)])
    deadline = time.monotonic() + 3
    while not (evidence / "worker-ready").exists():
        assert time.monotonic() < deadline
        time.sleep(.01)
    (evidence / "pids.json").write_text(json.dumps([os.getpid(), child.pid]))
if "signal" in action:
    os.kill(os.getpid(), action["signal"])
if action.get("mutate"):
    candidate.write_bytes(b"changed by test oracle")
if "verdict" in action:
    sys.exit(action["verdict"])
predicate = plan.get("predicate", "contains")
if predicate == "always":
    sys.exit(0)
if predicate == "only-original":
    sys.exit(0 if data.hex() == plan["original_hex"] else 2)
sys.exit(0 if b"BUG" in data else 1)
