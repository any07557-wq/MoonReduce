#!/usr/bin/env python3
"""Reproduce stage 0 checks, including a real SIGINT from outside MoonBit."""
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def run(*argv):
    print("+", " ".join(map(str, argv)), flush=True)
    subprocess.run(argv, cwd=ROOT, check=True, timeout=60)


def check_interrupt(binary, stubborn=False):
    with tempfile.TemporaryDirectory(prefix="moonreduce interrupt ") as directory:
        evidence = Path(directory)
        # An external timeout protects this test from a broken cancellation path.
        with (evidence / "probe-output.log").open("wb") as output:
            probe = subprocess.Popen(
                [str(binary), "--interrupt-stubborn" if stubborn else "--interrupt", directory], cwd=ROOT,
                stdout=output, stderr=subprocess.STDOUT, start_new_session=True,
            )
            pids = []
            passed = False
            try:
                deadline = time.monotonic() + 5
                while not (evidence / "ready").exists():
                    if probe.poll() is not None or time.monotonic() >= deadline:
                        raise AssertionError("interrupt fixture did not become ready")
                    time.sleep(0.01)
                pids = json.loads((evidence / "pids.json").read_text())
                assert len(pids) == (1 if stubborn else 3), pids
                probe.send_signal(signal.SIGINT)
                code = probe.wait(timeout=5)
                assert code in {-signal.SIGINT, 128 + signal.SIGINT}, code
                assert (evidence / "cleanup-finished").exists()
                if not stubborn:
                    assert (evidence / "reaped").exists()
                    assert (evidence / "worker-reaped").exists()
                assert all(not Path(f"/proc/{pid}").exists() for pid in pids), pids
                kind = "SIGKILL escalation" if stubborn else "three-level process tree reaped"
                print(f"PASS SIGINT: protected cleanup, {kind}, signal exit", flush=True)
                passed = True
            except BaseException:
                print((evidence / "probe-output.log").read_text(errors="replace"))
                raise
            finally:
                # Failure-only test hygiene, never used as evidence of success.
                if probe.poll() is None:
                    os.killpg(probe.pid, signal.SIGKILL)
                    probe.wait(timeout=5)
                if not passed:
                    for pid in pids:
                        try:
                            os.kill(pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass


def main():
    assert platform.system() == "Linux" and platform.machine() == "x86_64"
    versions = subprocess.check_output(["moon", "version", "--all"], text=True, timeout=10)
    assert "moon 0.1.20261012 (748b63c" in versions, versions
    assert "moonc v0.10.15+943464bfa" in versions, versions
    run("moon", "check", "--target", "native", "--deny-warn")
    dependency = ROOT / ".mooncakes/moonbitlang/async/moon.mod"
    assert 'version = "0.22.4"' in dependency.read_text(), dependency
    run("moon", "check", "src/core", "--target", "wasm-gc", "--deny-warn")
    run("moon", "build", "--target", "native", "--deny-warn")
    binary = ROOT / "_build/native/debug/build/probe/probe.exe"
    assert binary.is_file(), binary
    before = set(Path(tempfile.gettempdir()).glob("moonreduce probe .*"))
    run(str(binary))
    after = set(Path(tempfile.gettempdir()).glob("moonreduce probe .*"))
    assert after == before, f"temporary directories leaked: {after - before}"
    print("PASS normal-run temporary directories and logs removed", flush=True)
    check_interrupt(binary)
    check_interrupt(binary, stubborn=True)
    run("moon", "fmt", "--check")
    print("Stage 0 acceptance probes passed.")


if __name__ == "__main__":
    main()
