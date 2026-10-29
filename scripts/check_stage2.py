#!/usr/bin/env python3
"""Real Native CLI checks. Synthetic markers are not production bug findings."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
BINARY = ROOT / "_build/native/debug/build/cmd/moonreduce/moonreduce.exe"
ORACLE = ROOT / "tests/fixtures/reduce_oracle.py"
TREE = ROOT / "tests/fixtures/oracle.py"


def call(argv, *, expected=0, env=None, timeout=15):
    result = subprocess.run(
        [str(arg) for arg in argv], cwd=ROOT, env=env,
        capture_output=True, text=True, timeout=timeout,
    )
    assert result.returncode == expected, (
        result.returncode, expected, result.stdout, result.stderr, argv
    )
    return result


def records(path):
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def paths(case):
    case.mkdir()
    return case / "input file", case / "output file", case / "report.json", case / "calls.jsonl"


def reduce(source, output, report, command, *, trace=None, extra=(), expected=0):
    env = os.environ.copy()
    if trace is not None:
        env["MOONREDUCE_CALL_LOG"] = str(trace)
    result = call(
        [BINARY, source, "--output", output, "--report", report, *extra, "--", *command],
        expected=expected, env=env,
    )
    # Usage rejection may deliberately name an existing unrelated report file.
    data = json.loads(report.read_text()) if expected != 2 and report.exists() else None
    if data is not None:
        assert data["cache_enabled"] is False and data["cache_hits"] == 0
        assert data["tests_started"] <= data["max_tests"]
        assert sum(data["tests_by_phase"].values()) == data["tests_started"]
        assert isinstance(data["elapsed_ms"], (int, float))
        assert data["error"] is None or isinstance(data["error"], str)
    return result, data


def byte_workflows(work):
    cases = [
        ("lf", b"noise\nBUG\nmore\n", b"BUG\n", ["contains", "BUG"]),
        ("crlf", b"noise\r\nBUG\r\nmore\r\n", b"BUG\r\n", ["contains", "BUG"]),
        ("blank", b"noise\n\nmore\n", b"\n", ["has-empty-line"]),
        ("no-final-lf", b"noise\nBUG", b"BUG", ["contains", "BUG"]),
        ("empty", b"", b"", ["always"]),
        ("one-to-empty", b"only one line", b"", ["always"]),
        ("one-kept", b"BUG", b"BUG", ["contains", "BUG"]),
        ("bytes", b"\x00noise\n\xffBUG\r\nend\xfe", b"\xffBUG\r\n", ["contains-hex", "ff425547"]),
    ]
    for name, original, expected, args in cases:
        source, output, report, trace = paths(work / name)
        source.write_bytes(original)
        before = hashlib.sha256(source.read_bytes()).digest()
        _, data = reduce(source, output, report, [ORACLE, *args], trace=trace)
        assert output.read_bytes() == expected, name
        assert source.read_bytes() == original
        assert hashlib.sha256(source.read_bytes()).digest() == before
        assert data["stop_reason"] == "completed"
        assert data["final_revalidation"] == "interesting"
        assert data["minimality"] == "verified"
        trace_rows = records(trace)
        assert len(trace_rows) == data["tests_started"]
        assert trace_rows[-1]["path"] == str(output.resolve()), trace_rows
        assert data["tests_by_phase"]["initial"] == 1
        assert data["tests_by_phase"]["final"] == 1
        # Independent real invocation after MoonReduce has exited.
        call([ORACLE, *args, output.resolve()])
        # Independently verify every one-line deletion on these simple cases.
        segments = expected.split(b"\n")
        parts = [part + b"\n" for part in segments[:-1]]
        if segments[-1]:
            parts.append(segments[-1])
        for deleted in range(len(parts)):
            candidate = source.parent / f"audit-{deleted}"
            candidate.write_bytes(b"".join(parts[:deleted] + parts[deleted + 1:]))
            call([ORACLE, *args, candidate.resolve()], expected=1)
    print("PASS LF/CRLF/blank/no-final-LF/empty/single/binary workflows and independent oracle reruns")


def argv_and_aliases(work):
    source, output, report, trace = paths(work / "spaces")
    original = b"noise\nBUG\nmore\n"
    source.write_bytes(original)
    spaced = source.parent / "oracle executable with spaces.py"
    shutil.copy2(ORACLE, spaced)
    spaced.chmod(0o700)
    fixed = ["contains", "BUG", "two words", "literal;$(echo unsafe)*",
             "quote\"and'quote", "line\nbreak", "--help", "--max-tests", "1", "--"]
    _, data = reduce(source, output, report, [spaced, *fixed], trace=trace)
    assert output.read_bytes() == b"BUG\n"
    for row in records(trace):
        assert row["argv"][:-1] == fixed
        assert Path(row["path"]).is_absolute()
    assert data["oracle_argv"] == [str(spaced), *fixed]
    assert data["max_tests"] == 1000

    case = work / "aliases"
    case.mkdir()
    source = case / "original"
    source.write_bytes(original)
    hard = case / "hard"
    os.link(source, hard)
    soft = case / "soft"
    soft.symlink_to(source)
    dangling = case / "dangling"
    dangling.symlink_to(case / "absent")
    existing = case / "existing"
    existing.write_bytes(b"DO NOT OVERWRITE")
    for index, target in enumerate([source, hard, soft, dangling, existing]):
        report = case / f"report-{index}"
        result, data = reduce(source, target, report, [ORACLE, "always"], expected=2)
        assert "refus" in result.stderr or "input file" in result.stderr
        assert data is None and not report.exists()
        assert source.read_bytes() == original and hard.read_bytes() == original
    assert dangling.is_symlink() and not dangling.exists()
    assert existing.read_bytes() == b"DO NOT OVERWRITE"
    reduce(source, case / "unused-report-output", existing, [ORACLE, "always"], expected=2)
    assert existing.read_bytes() == b"DO NOT OVERWRITE"
    assert not (case / "unused-report-output").exists()
    reduce(source, case / "unused", hard, [ORACLE, "always"], expected=2)
    reduce(source, case / "same", case / "./same", [ORACLE, "always"], expected=2)
    # An input symlink is readable, and canonicalization does not modify it.
    _, data = reduce(soft, case / "new", case / "new-report", [ORACLE, "contains", "BUG"])
    assert soft.is_symlink() and source.read_bytes() == original
    assert data["input"] == str(source.resolve())
    print("PASS literal argv and spaced paths; symlink/hardlink identity and no-overwrite")


def failures_and_limits(work):
    for code, reason in [(1, "initial_not_interesting"), (2, "initial_unresolved")]:
        source, output, report, trace = paths(work / f"initial-{code}")
        source.write_bytes(b"BUG\n")
        _, data = reduce(source, output, report, [ORACLE, "exit", str(code)], trace=trace, expected=3)
        assert not output.exists()
        assert data["stop_reason"] == reason and data["final_revalidation"] == "not_run"
        assert data["tests_started"] == len(records(trace)) == 1
    for code in [7, 124, 137]:
        source, output, report, _ = paths(work / f"abnormal-{code}")
        source.write_bytes(b"BUG\n")
        result, data = reduce(source, output, report, [ORACLE, "exit", str(code)], expected=4)
        assert not output.exists()
        assert data["stop_reason"] == "execution_error" and data["timeouts"] == 0
        assert data["last_exit_code"] == code and data["last_signal"] is None
        assert str(code) in result.stderr
    for signum in [9, 15]:
        source, output, report, _ = paths(work / f"signal-{signum}")
        source.write_bytes(b"BUG\n")
        _, data = reduce(source, output, report, [ORACLE, "signal", str(signum)], expected=4)
        assert data["last_signal"] == signum and data["timeouts"] == 0
        assert data["last_exit_code"] is None
        assert not output.exists()
    source, output, report, _ = paths(work / "missing-command")
    source.write_bytes(b"BUG\n")
    result, data = reduce(source, output, report, [source.parent / "no such command"], expected=4)
    assert data["stop_reason"] == "execution_error" and "127" in result.stderr
    assert not output.exists()
    source, output, report, _ = paths(work / "modified-candidate")
    source.write_bytes(b"BUG\n")
    result, data = reduce(source, output, report, [ORACLE, "mutate"], expected=4)
    assert "modified the candidate" in result.stderr
    assert not output.exists() and source.read_bytes() == b"BUG\n"
    assert data["initial_check"] == "error" and data["final_revalidation"] == "not_run"
    source, output, report, _ = paths(work / "missing-input")
    result, data = reduce(source, output, report, [ORACLE, "always"], expected=4)
    assert result.stderr and data is None and not output.exists()

    source, output, report, trace = paths(work / "budget")
    original = b"noise\nBUG\nmore\n"
    source.write_bytes(original)
    _, data = reduce(source, output, report, [ORACLE, "contains", "BUG"], trace=trace,
                     extra=["--max-tests", "2"], expected=1)
    assert output.read_bytes() == original
    assert data["tests_started"] == len(records(trace)) == 2
    assert data["stop_reason"] == "budget_exhausted"
    assert data["final_revalidation"] == "interesting" and data["minimality"] != "verified"

    source, output, report, _ = paths(work / "final-failure")
    source.write_bytes(original)
    _, data = reduce(source, output, report, [ORACLE, "path-sensitive", output.resolve()], expected=4)
    assert data["stop_reason"] == "final_not_interesting"
    assert data["final_revalidation"] == "not_interesting" and output.exists()

    source, output, report, _ = paths(work / "unresolved-minimality")
    source.write_bytes(b"one\ntwo\n")
    _, data = reduce(source, output, report, [ORACLE, "unresolved-small"], expected=1)
    assert data["final_revalidation"] == "interesting"
    assert data["minimality"] == "blocked_by_unresolved"
    print("PASS initial rejection/unresolved, launch/exit/signal errors, budget reserve and final failure")


def timeout_regression(work):
    # A raising timeout is nested under the driver and process task groups.
    # Require real cleanup rather than accepting the outer watchdog as timeout.
    source, output, report, _ = paths(work / "nested-timeout")
    source.write_bytes(b"BUG\n")
    evidence = source.parent / "evidence"
    evidence.mkdir()
    started = time.monotonic()
    _, data = reduce(source, output, report, [TREE, "tree", evidence],
                     extra=["--timeout-ms", "500"], expected=3)
    assert time.monotonic() - started < 5
    assert data["initial_check"] == "unresolved" and data["timeouts"] == 1
    assert data["tests_started"] == 1 and data["final_revalidation"] == "not_run"
    pids = json.loads((evidence / "pids.json").read_text())
    assert len(pids) == 3 and all(not Path(f"/proc/{pid}").exists() for pid in pids)
    assert (evidence / "reaped").exists() and (evidence / "worker-reaped").exists()
    assert not output.exists()
    source, output, report, _ = paths(work / "stubborn-timeout")
    source.write_bytes(b"BUG\n")
    evidence = source.parent / "evidence"
    evidence.mkdir()
    started = time.monotonic()
    _, data = reduce(source, output, report, [TREE, "stubborn", evidence],
                     extra=["--timeout-ms", "500"], expected=3)
    assert time.monotonic() - started < 5
    assert data["timeouts"] == 1
    pids = json.loads((evidence / "pids.json").read_text())
    assert all(not Path(f"/proc/{pid}").exists() for pid in pids)
    print("PASS nested timeout regression: 500ms timer, full three-level process tree reaped")


def interruption_and_output(work):
    source, output, report, trace = paths(work / "interrupt")
    original = b"noise\nBUG\n"
    source.write_bytes(original)
    evidence = source.parent / "evidence"
    evidence.mkdir()
    counter = source.parent / "counter"
    env = {**os.environ, "MOONREDUCE_CALL_LOG": str(trace)}
    log = source.parent / "cli.log"
    with log.open("wb") as stream:
        process = subprocess.Popen(
            [str(arg) for arg in [
                BINARY, source, "--output", output, "--report", report,
                "--timeout-ms", "30000", "--", ORACLE, "hang-after-first", counter, evidence,
            ]], cwd=ROOT, env=env, stdout=stream, stderr=stream, start_new_session=True,
        )
        pids = []
        passed = False
        try:
            deadline = time.monotonic() + 5
            while not (evidence / "ready").exists():
                assert process.poll() is None, log.read_text()
                assert time.monotonic() < deadline, log.read_text()
                time.sleep(.01)
            pids = json.loads((evidence / "pids.json").read_text())
            assert output.read_bytes() == original  # saved before starting the next call
            process.send_signal(signal.SIGINT)
            assert process.wait(timeout=5) == 130, log.read_text()
            data = json.loads(report.read_text())
            assert data["stop_reason"] == "interrupted" and data["interrupted"]
            assert data["final_revalidation"] == "not_run"
            assert data["minimality"] != "verified"
            assert output.read_bytes() == original and source.read_bytes() == original
            assert all(not Path(f"/proc/{pid}").exists() for pid in pids)
            passed = True
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            if not passed:
                for pid in pids:
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
    source, output, report, _ = paths(work / "large-output")
    source.write_bytes(b"BUG\n")
    result, data = reduce(source, output, report, [ORACLE, "large", "BUG"])
    assert output.read_bytes() == b"BUG\n"
    assert len(result.stdout) < 4096
    assert data["diagnostics"]["stdout_truncated"] and data["diagnostics"]["stderr_truncated"]
    assert len(data["diagnostics"]["stdout"]) == len(data["diagnostics"]["stderr"]) == 4096
    print("PASS saved best and tree cleanup on Ctrl-C; large output uses bounded diagnostics")


def arguments(work):
    assert "candidate path" in call([BINARY, "--help"]).stdout
    assert "0.1.0-dev" in call([BINARY, "--version"]).stdout
    source = work / "args-input"
    source.write_bytes(b"BUG\n")
    prefix = [BINARY, source, "--output", work / "args-output", "--report", work / "args-report"]
    bad = [
        [BINARY], prefix,
        [*prefix, "--"],
        [*prefix, "--timeout-ms", "0", "--", ORACLE, "always"],
        [*prefix, "--max-tests", "1", "--", ORACLE, "always"],
        [*prefix, "--max-tests", "nonsense", "--", ORACLE, "always"],
        [*prefix, "--timeout-ms", "2147483648", "--", ORACLE, "always"],
        [*prefix, "--output", work / "duplicate", "--", ORACLE, "always"],
    ]
    for argv in bad:
        diagnostic = call(argv, expected=2).stderr
        assert diagnostic and "args.mbt" not in diagnostic
    assert not (work / "args-output").exists() and not (work / "args-report").exists()
    print("PASS help/version and argument errors before any oracle execution")


def main():
    global BINARY
    if len(sys.argv) == 2:
        BINARY = Path(sys.argv[1]).resolve()
    else:
        call(["moon", "build", "--target", "native", "--deny-warn"])
    with tempfile.TemporaryDirectory(prefix="moonreduce stage2 ") as directory:
        work = Path(directory)
        arguments(work)
        byte_workflows(work)
        argv_and_aliases(work)
        failures_and_limits(work)
        timeout_regression(work)
        interruption_and_output(work)
        assert not list(work.rglob("*.moonreduce-*")), "atomic write staging files leaked"
    print("Stage 2 CLI workflows passed. Run check_stage3.py for the reliability matrix; final release acceptance is separate.")


if __name__ == "__main__":
    main()
