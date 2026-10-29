#!/usr/bin/env python3
"""Reproducible synthetic debugging workflow and developer-run library integration."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples/algorithm"
CONSUMER = ROOT / "examples/moonbit-consumer"
DEFAULT_BINARY = ROOT / "_build/native/debug/build/cmd/moonreduce/moonreduce.exe"


def call(argv, *, expected=0, cwd=ROOT, env=None, timeout=60):
    result = subprocess.run(
        [str(arg) for arg in argv], cwd=cwd, env=env, capture_output=True,
        text=True, timeout=timeout,
    )
    assert result.returncode == expected, (argv, result.returncode, result.stdout, result.stderr)
    return result


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def workflow(work, binary):
    case = work / "algorithm workflow"
    case.mkdir()
    reference, buggy = case / "reference program", case / "buggy program"
    # Both compiles finish before the first oracle. No compiler in oracle.py.
    for destination, injected in [(reference, 0), (buggy, 1)]:
        call(["cc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
              f"-DINJECT_BUG={injected}", EXAMPLE / "max_subarray.c", "-o", destination])
    binaries_before = [(sha256(path), path.stat().st_mtime_ns) for path in (reference, buggy)]
    source, output, report = case / "initial.txt", case / "reduced.txt", case / "report.json"
    call([sys.executable, EXAMPLE / "generate.py", source])
    original = source.read_bytes()
    oracle = [sys.executable, EXAMPLE / "oracle.py", "--reference", reference, "--buggy", buggy]
    call([*oracle, source])
    trace = case / "oracle-calls.jsonl"
    result = call([
        binary, source, "--output", output, "--report", report,
        "--timeout-ms", "5000", "--max-tests", "500", "--", *oracle,
    ], env={**os.environ, "MOONREDUCE_EXAMPLE_CALL_LOG": str(trace)}, timeout=60)
    data = json.loads(report.read_text())
    trace_rows = [json.loads(line) for line in trace.read_text().splitlines()]
    assert data["stop_reason"] == "completed" and data["exit_code"] == 0
    assert data["final_revalidation"] == "interesting" and data["minimality"] == "verified"
    assert data["tests_started"] == len(trace_rows)
    assert trace_rows[-1]["candidate"] == str(output)
    assert trace_rows[0]["n"] == original.count(b"\n")
    assert data["tests_by_phase"]["initial"] == data["tests_by_phase"]["final"] == 1
    assert source.read_bytes() == original
    assert output.stat().st_size < len(original)
    # Actual, separate oracle call after the reducer exited.
    rerun = call([*oracle, output])
    audit = json.loads(call([
        sys.executable, EXAMPLE / "audit.py", "--reference", reference,
        "--buggy", buggy, output,
    ]).stdout)
    assert audit["all_single_deletions_not_interesting"]
    assert audit["single_deletions_checked"] == data["best_segments"]
    assert binaries_before == [(sha256(path), path.stat().st_mtime_ns) for path in (reference, buggy)]
    measurement = {
        "case": "artificial_max_subarray_bug",
        "original_bytes": len(original), "original_segments": original.count(b"\n"),
        "initial_sha256": sha256(source),
        "best_bytes": output.stat().st_size, "best_segments": data["best_segments"],
        "reduced_text": output.read_text(), "tests_started": data["tests_started"],
        "tests_by_phase": data["tests_by_phase"], "final_revalidation": data["final_revalidation"],
        "independent_oracle": rerun.stdout.strip(), "audit": audit,
    }
    print(json.dumps(measurement, ensure_ascii=False, sort_keys=True), flush=True)
    print("PASS precompiled targets, n regeneration, actual reduction, independent target/1-minimal checks, unchanged original/binaries", flush=True)
    return case, reference, buggy, oracle


def oracle_contract(case, reference, buggy, oracle, binary):
    candidate = case / "contract-candidate"
    for content in [b"\n", b"1\n\n2\n", b"not an integer\n", b"1001\n", b"\xff\n",
                    b"1\x002\n", b"0\n" * 4097, b"1" * 32769]:
        candidate.write_bytes(content)
        result = call([*oracle, candidate], expected=2)
        assert "invalid candidate" in result.stderr
    for content, expected in [(b"", 1), (b"19\n", 1), (b"17\r\n-3\r\n19", 0)]:
        candidate.write_bytes(content)
        call([*oracle, candidate], expected=expected)
    candidate.write_bytes(b"17\n-3\n19\n")
    # Errors must not silently become NI/U or successful crash reproduction.
    call([sys.executable, EXAMPLE / "oracle.py", candidate], expected=3)
    missing = case / "absent target"
    call([sys.executable, EXAMPLE / "oracle.py", "--reference", reference,
          "--buggy", missing, candidate], expected=3)
    call([sys.executable, EXAMPLE / "oracle.py", "--reference", buggy,
          "--buggy", reference, candidate], expected=3)
    for name, body in [
        ("exit7", "raise SystemExit(7)"),
        ("crash", "import os, signal; os.kill(os.getpid(), signal.SIGKILL)"),
        ("empty", "pass"),
        ("garbage", "print('not an answer')"),
        ("negative", "print(-1)"),
        ("out-of-range", "print(9999999)"),
        ("large", "import sys; sys.stdout.write('x' * 65536)"),
        ("hang", "import time; time.sleep(10)"),
    ]:
        target = case / f"broken-{name}"
        target.write_text("#!/usr/bin/python3\n" + body + "\n")
        target.chmod(0o700)
        result = call([sys.executable, EXAMPLE / "oracle.py", "--reference", reference,
                       "--buggy", target, candidate], expected=3, timeout=6)
        assert "oracle execution error" in result.stderr
        assert len(result.stdout) + len(result.stderr) < 4096
    # Through the real CLI, an empty target output is execution_error/4, not I.
    empty_target = case / "broken-empty"
    output, report = case / "failed-output", case / "failed-report"
    call([binary, candidate, "--output", output, "--report", report,
          "--timeout-ms", "5000", "--", sys.executable, EXAMPLE / "oracle.py",
          "--reference", reference, "--buggy", empty_target], expected=4)
    data = json.loads(report.read_text())
    assert data["initial_check"] == "error" and data["oracle_errors"] == 1
    assert not output.exists() and candidate.read_bytes() == b"17\n-3\n19\n"
    print("PASS example oracle invalid/empty/CRLF inputs; missing, crash, abnormal, empty/invalid output and timeout errors", flush=True)


def consumer(work):
    # Native integration via actual workspace package resolution; never copy the
    # core, import its private files, or use its author's _build artifacts.
    for command in ["check", "build", "test", "run"]:
        result = call(["moon", "-C", CONSUMER, command, "src", "--target", "native", "--deny-warn"])
        if command == "run":
            print(result.stdout.strip(), flush=True)
    call(["moon", "-C", CONSUMER, "test", "src", "--target", "native", "--release", "--deny-warn"])
    call(["moon", "-C", CONSUMER, "run", "src", "--target", "native", "--release", "--deny-warn"])
    relocated = work / "relocated-consumer"
    shutil.copytree(CONSUMER, relocated, ignore=shutil.ignore_patterns("_build", ".mooncakes", ".repos"))
    (relocated / "moon.work").write_text("members = [\".\", " + json.dumps(str(ROOT)) + "]\n")
    fresh_target = work / "consumer-fresh-build"
    tree = call(["moon", "-C", relocated, "tree"]).stdout
    assert f"(local {ROOT})" in tree and "[workspace member]" in tree
    assert not fresh_target.exists()
    planned = call(["moon", "-C", relocated, "build", "src", "--target", "native",
                    "--target-dir", fresh_target, "--deny-warn", "--dry-run"])
    commands = planned.stdout + planned.stderr
    assert str(ROOT / "_build") not in commands
    assert str(fresh_target) in commands and str(ROOT / "src/core") in commands
    call(["moon", "-C", relocated, "build", "src", "--target", "native",
          "--target-dir", fresh_target, "--deny-warn"])
    assert any(fresh_target.rglob("*.exe"))
    assert (fresh_target / "native/debug/build/moonreduce/moonreduce/core/core.core").is_file()
    output = call(["moon", "-C", relocated, "run", "src", "--target", "native",
                   "--target-dir", fresh_target, "--deny-warn"]).stdout
    assert "target independently replayed" in output and "deletions NotInteresting" in output
    print("PASS independent consumer check/build/test/run, Debug/Release, relocated project with fresh build artifacts and local public dependency", flush=True)


def main():
    binary = Path(sys.argv[1]).resolve() if len(sys.argv) == 2 else DEFAULT_BINARY
    if len(sys.argv) == 1:
        call(["moon", "build", "--target", "native", "--deny-warn"])
    with tempfile.TemporaryDirectory(prefix="moonreduce stage4 ") as directory:
        work = Path(directory)
        case, reference, buggy, oracle = workflow(work, binary)
        oracle_contract(case, reference, buggy, oracle, binary)
        consumer(work)
    print("Stage 4 examples passed. Synthetic defects and developer integration only; no external adoption or clean-environment release acceptance claimed.")


if __name__ == "__main__":
    main()
