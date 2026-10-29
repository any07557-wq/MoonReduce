#!/usr/bin/env python3
"""Real CLI reliability matrix, externally counted starts and bounded watchdogs."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
BINARY = ROOT / "_build/native/debug/build/cmd/moonreduce/moonreduce.exe"
ORACLE = ROOT / "tests/fixtures/reliability_oracle.py"
EXIT_CODES = {
    "completed": 0, "budget_exhausted": 1, "unresolved": 1,
    "initial_not_interesting": 3, "initial_unresolved": 3,
    "final_not_interesting": 4, "final_unresolved": 4,
    "execution_error": 4, "interrupted": 130,
}


def segments(data):
    # Independent LF contract; do not use splitlines() which strips CR/other bytes.
    pieces = data.split(b"\n")
    return [piece + b"\n" for piece in pieces[:-1]] + ([pieces[-1]] if pieces[-1] else [])


def rows(path):
    return [json.loads(row) for row in path.read_text().splitlines()] if path.exists() else []


def wait_for(check, process, log, timeout=5):
    deadline = time.monotonic() + timeout
    while not check():
        assert process.poll() is None, log.read_text(errors="replace")
        assert time.monotonic() < deadline, log.read_text(errors="replace")
        time.sleep(.01)


def gone(pids):
    deadline = time.monotonic() + 3
    while any(Path(f"/proc/{pid}").exists() for pid in pids):
        assert time.monotonic() < deadline, f"processes not reaped: {pids}"
        time.sleep(.01)


class Case:
    def __init__(self, work, name, original=b"a\nBUG\nc\n", *, calls=None,
                 predicate="contains", budget=1000, timeout=1500, fault=None):
        self.path = work / name
        self.path.mkdir()
        self.input = self.path / "input"
        self.output_dir = self.path / "results"
        self.report_dir = self.path / "reports"
        self.output_dir.mkdir()
        self.report_dir.mkdir()
        self.output = self.output_dir / "output"
        self.report = self.report_dir / "report.json"
        self.trace = self.path / "calls.jsonl"
        self.audit = self.path / "spawns"
        self.log = self.path / "cli.log"
        self.original = original
        self.input.write_bytes(original)
        self.budget = budget
        self.expect_oracle_trace = True
        self.calls = calls or {}
        plan = {"output": str(self.output), "original_hex": original.hex(),
                "calls": self.calls, "predicate": predicate}
        (self.path / "plan.json").write_text(json.dumps(plan))
        self.env = {**os.environ, "LD_PRELOAD": str(work / "faults.so"),
                    "MOONREDUCE_TEST_SPAWN_LOG": str(self.audit)}
        if fault:
            self.env["MOONREDUCE_TEST_FAIL_SPAWN"] = fault
        self.argv = [str(arg) for arg in [
            BINARY, self.input, "--output", self.output, "--report", self.report,
            "--timeout-ms", timeout, "--max-tests", budget, "--", ORACLE, self.path,
        ]]

    def run(self, expected, *, report=True):
        result = subprocess.run(self.argv, cwd=ROOT, env=self.env, capture_output=True,
                                text=True, timeout=12)
        try:
            assert result.returncode == expected, (result.returncode, result.stdout, result.stderr)
            if report:
                return self.check(result)
            assert not self.report.exists(), result.stdout
            assert "execution_error" in result.stdout and "exit code: 4" in result.stdout
            assert str(self.report) not in result.stdout
            assert result.stderr
        finally:
            self.restore_permissions()

    def restore_permissions(self):
        self.output_dir.chmod(0o700)
        self.report_dir.chmod(0o700)

    def check(self, result):
        data = json.loads(self.report.read_text())
        expected = EXIT_CODES[data["stop_reason"]]
        assert result.returncode == data["exit_code"] == expected, data
        assert f"MoonReduce: {data['stop_reason']}\n" in result.stdout
        assert f"Final revalidation: {data['final_revalidation']}; minimality: {data['minimality']}" in result.stdout
        assert f"Result: {data['result_status']}" in result.stdout
        assert f"minimality reason: {data['minimality_reason']}; exit code: {expected}" in result.stdout
        assert f"oracle starts: {data['tests_started']}/{self.budget}" in result.stdout
        assert f"timeouts: {data['timeouts']}" in result.stdout
        assert str(self.report) in result.stdout
        assert self.input.read_bytes() == self.original
        assert data["input"] == str(self.input)
        assert data["original_bytes"] == len(self.original)
        assert data["original_segments"] == len(segments(self.original))
        assert isinstance(data["elapsed_ms"], (int, float)) and data["elapsed_ms"] >= 0
        assert data["tool_version"] == "0.1.0-dev" and data["schema_version"] == 1
        assert data["cache_enabled"] is False and data["cache_hits"] == 0
        assert 0 <= data["tests_started"] <= self.budget
        counts = data["tests_by_phase"]
        assert sum(counts.values()) == data["tests_started"]
        assert set(counts) == {"initial", "search", "minimality", "final"}
        assert data["tests_counting_unit"] == "controlled_launcher_start"
        assert counts.get("initial", 0) <= 1 and counts.get("final", 0) <= 1
        assert sum(data[key] for key in (
            "interesting", "not_interesting", "unresolved", "oracle_errors", "interrupted_tests",
        )) == data["tests_started"], data
        assert data["timeouts"] <= data["unresolved"]
        assert data["had_unresolved"] == (data["unresolved"] > 0)
        assert data["launch_attempts"] == data["tests_started"] + data["launch_failures"]
        # This counter observes the actual libc posix_spawn result in the parent,
        # including setsid -> missing-command exec failures and launcher failures.
        audit = [list(map(int, row.split())) for row in self.audit.read_text().splitlines()] if self.audit.exists() else []
        assert sum(code == 0 for _, code in audit) == data["tests_started"], (audit, data)
        assert sum(code != 0 for _, code in audit) == data["launch_failures"]
        trace = rows(self.trace)
        if data["launch_failures"] == 0 and self.expect_oracle_trace:
            assert len(trace) == data["tests_started"]
        if counts.get("final"):
            assert trace[-1]["path"] == str(self.output), trace
        assert data["output_saved"] == (data["output"] is not None)
        assert data["only_previously_observed_interesting"] == (
            data["output_saved"] and data["final_revalidation"] != "interesting"
        )
        if data["output_saved"]:
            assert str(self.output) in result.stdout and data["output"] == str(self.output)
            positions = data["best_positions"]
            assert positions == sorted(set(positions))
            parts = segments(self.original)
            expected_bytes = b"".join(parts[index] for index in positions)
            assert self.output.read_bytes() == expected_bytes
            assert data["best_bytes"] == len(expected_bytes)
            assert data["best_segments"] == len(positions)
            status = "revalidated_interesting" if data["final_revalidation"] == "interesting" else "previously_interesting"
            assert data["result_status"] == status
            if data["only_previously_observed_interesting"]:
                assert "Minimality describes earlier checks." in result.stdout
        else:
            assert not self.output.exists()
            assert data["best_positions"] is None and data["best_bytes"] is None and data["best_segments"] is None
            assert data["result_status"] == "no_saved_result"
        if data["stop_reason"] == "completed":
            assert data["final_revalidation"] == "interesting" and data["minimality"] == "verified"
        if data["stop_reason"] == "execution_error":
            assert data["error"] and result.stderr
        else:
            assert data["error"] is None
        assert not list(self.path.rglob("*.moonreduce-*")), self.path
        return data


def budgets(work):
    baseline = Case(work, "normal")
    full = baseline.run(0)
    count = full["tests_started"]
    assert baseline.output.read_bytes() == b"BUG\n"
    # Independent target and 1-minimal checks on bytes, not the report flag.
    assert b"BUG" in baseline.output.read_bytes()
    assert all(b"BUG" not in b"".join(parts[:i] + parts[i + 1:])
               for parts in [segments(baseline.output.read_bytes())] for i in range(len(parts)))
    for budget in range(2, count + 2):
        case = Case(work, f"budget-{budget}", budget=budget)
        data = case.run(1 if budget < count else 0)
        assert data["tests_started"] == min(budget, count)
        assert data["tests_by_phase"]["final"] == 1
        if budget < count:
            assert data["minimality"] != "verified"
            assert data["minimality_reason"] == "budget_exhausted"
            assert data["search_stop_reason"] == "budget_exhausted"
    for name, original, budget, expected, predicate in [
        ("empty-exact", b"", 2, 0, "always"),
        ("one-empty-exact", b"x", 3, 0, "always"),
        ("one-needs-proof", b"x", 2, 1, "always"),
        ("one-proof-exact", b"BUG", 3, 0, "contains"),
    ]:
        case = Case(work, name, original, budget=budget, predicate=predicate)
        data = case.run(expected)
        if expected == 0:
            assert data["tests_started"] == budget
    print("PASS exact budgets at every main-flow boundary, empty and single results", flush=True)


def verdicts(work):
    for code, reason in [(1, "initial_not_interesting"), (2, "initial_unresolved")]:
        case = Case(work, f"initial-{code}", calls={"1": {"verdict": code}})
        data = case.run(3)
        assert data["stop_reason"] == reason and data["tests_started"] == 1
    case = Case(work, "all-proper-unresolved", predicate="only-original")
    data = case.run(1)
    assert case.output.read_bytes() == case.original
    assert data["minimality"] == "blocked_by_unresolved"
    assert data["minimality_checked"] == data["minimality_required"] == 3
    assert data["minimality_reason"] == "unresolved_single_deletions"
    assert data["not_interesting"] == 0 and data["unresolved"] > 0
    case = Case(work, "historical-unresolved", calls={"2": {"verdict": 2}})
    data = case.run(0)
    assert data["had_unresolved"] and data["minimality"] == "verified"
    for code in [1, 2, 7, 124, 137]:
        case = Case(work, f"final-{code}", b"BUG", budget=3, calls={"3": {"verdict": code}})
        data = case.run(4)
        assert data["final_revalidation"] == {1: "not_interesting", 2: "unresolved"}.get(code, "error")
        assert data["search_stop_reason"] == "completed"
        assert data["minimality"] == "verified" and data["only_previously_observed_interesting"]
        assert case.output.read_bytes() == b"BUG"
    for code in [1, 2]:
        case = Case(work, f"budget-final-{code}", budget=2, calls={"2": {"verdict": code}})
        data = case.run(4)
        assert data["search_stop_reason"] == "budget_exhausted"
        assert data["minimality_reason"] == "budget_exhausted"
        assert data["final_revalidation"] == ("not_interesting" if code == 1 else "unresolved")
    for phase, call in [("search", 2), ("minimality", 2), ("final", 3)]:
        original = b"BUG" if phase != "search" else b"a\nBUG\n"
        case = Case(work, f"{phase}-signal", original, calls={str(call): {"signal": 15}})
        data = case.run(4)
        assert data["last_signal"] == 15 and data["last_exit_code"] is None
        assert data["oracle_errors"] == 1 and data["timeouts"] == 0
        if phase != "final":
            assert data["final_revalidation"] == "not_run"
        assert case.output.read_bytes() == original
    case = Case(work, "final-mutates", b"BUG", calls={"3": {"mutate": True, "verdict": 0}})
    data = case.run(4)
    assert data["final_revalidation"] == "error" and case.output.read_bytes() == b"BUG"
    print("PASS initial/search/minimality/final verdicts and errors; explicit historical evidence", flush=True)


def minimality_continues(work):
    # Artificial availability changes cover the driver path already proven
    # against deterministic truth tables in the pure core tests.
    original = b"A\nB\n"
    calls = {str(i): {"verdict": 2} for i in range(2, 7)}
    calls.update({
        "1": {"verdict": 0, "expect_hex": original.hex()},
        "7": {"verdict": 0, "expect_hex": b"B\n".hex()},
        "8": {"verdict": 1, "expect_hex": ""},
        "9": {"verdict": 0, "expect_hex": b"B\n".hex()},
    })
    case = Case(work, "minimality-improves", original, calls=calls)
    data = case.run(0)
    assert data["tests_started"] == 9 and case.output.read_bytes() == b"B\n"
    assert data["tests_by_phase"]["minimality"] == 2
    assert data["minimality_checked"] == data["minimality_required"] == 1
    assert data["unresolved"] == 5 and data["had_unresolved"]
    assert rows(case.trace)[7]["saved_hex"] == b"B\n".hex()
    # Same improvement consumes the last search/proof slot; reserve final call.
    case = Case(work, "minimality-improves-budget", original, calls={
        key: value for key, value in calls.items() if key != "8"
    }, budget=8)
    case.calls["8"] = {"verdict": 0, "expect_hex": b"B\n".hex()}
    plan = json.loads((case.path / "plan.json").read_text())
    plan["calls"] = case.calls
    (case.path / "plan.json").write_text(json.dumps(plan))
    data = case.run(1)
    assert data["minimality"] == "incomplete" and data["minimality_checked"] == 0
    assert case.output.read_bytes() == b"B\n"
    print("PASS Interesting during final single-delete checks continues and resets proof; budget still reserves final", flush=True)


def io_failures(work):
    for name, call, target in [("initial-save-fails", 1, "output"),
                               ("improved-save-fails", 2, "output"),
                               ("report-save-fails", 3, "report")]:
        case = Case(work, name, b"BUG", predicate="always")
        directory = case.output_dir if target == "output" else case.report_dir
        plan = json.loads((case.path / "plan.json").read_text())
        plan["calls"] = {str(call): {"chmod": str(directory), "verdict": 0}}
        (case.path / "plan.json").write_text(json.dumps(plan))
        data = case.run(4, report=target != "report")
        if target == "output":
            assert data["final_revalidation"] == "not_run"
            assert data["tests_started"] == call
            if call == 2:
                assert case.output.read_bytes() == b"BUG" and data["best_bytes"] == 3
                assert data["minimality_reason"] == "execution_error"
            else:
                assert data["initial_check"] == "interesting" and not case.output.exists()
    case = Case(work, "diagnostic-read-fails", calls={"1": {"break_log": True}})
    data = case.run(4)
    assert data["initial_check"] == "error" and data["final_revalidation"] == "not_run"
    print("PASS real output/report permission failures and diagnostic read failure; previous best survives", flush=True)


def spawn_and_cleanup_failures(work):
    case = Case(work, "launcher-spawn-fails", fault="/usr/bin/setsid")
    data = case.run(4)
    assert data["tests_started"] == 0 and data["launch_attempts"] == data["launch_failures"] == 1
    case = Case(work, "oracle-exec-fails")
    case.argv = case.argv[:-2] + [str(case.path / "no-such-command")]
    case.expect_oracle_trace = False
    data = case.run(4)
    assert data["tests_started"] == 1 and data["launch_failures"] == 0
    assert data["oracle_errors"] == 1 and data["last_exit_code"] == 127
    case = Case(work, "cleanup-helper-fails", calls={"1": {"leave_child": True}},
                fault="/usr/bin/kill")
    data = case.run(4)
    assert data["oracle_errors"] == 1
    gone(json.loads((case.path / "evidence/pids.json").read_text()))
    case = Case(work, "timeout-cleanup-helper-fails", calls={"1": {"tree": "stubborn-tree"}},
                fault="/usr/bin/kill", timeout=750)
    data = case.run(4)
    assert data["timeouts"] == data["unresolved"] == 1
    gone(json.loads((case.path / "evidence/pids.json").read_text()))
    case = Case(work, "successful-leader-leaves-child", calls={"1": {"leave_child": True}}, budget=2)
    data = case.run(1)
    gone(json.loads((case.path / "evidence/pids.json").read_text()))
    print("PASS actual launcher failure counting; helper failure fallback and exited-leader descendant cleanup", flush=True)


def atomic_publication(work):
    case = Case(work, "partial-write-fails")
    arm = case.path / "arm"
    plan = json.loads((case.path / "plan.json").read_text())
    plan["calls"] = {"3": {"touch": str(arm)}}
    (case.path / "plan.json").write_text(json.dumps(plan))
    case.env.update({
        "MOONREDUCE_TEST_WRITE_PREFIX": str(case.output) + ".moonreduce-",
        "MOONREDUCE_TEST_ARM_WRITE": str(arm),
    })
    data = case.run(4)
    assert data["tests_started"] == 3 and case.output.read_bytes() == case.original
    assert data["best_bytes"] == len(case.original) and data["final_revalidation"] == "not_run"
    assert "No space left" in data["error"]
    case = Case(work, "interrupt-during-save", b"BUG")
    gate = case.path / "write-gate"
    case.env.update({
        "MOONREDUCE_TEST_WRITE_PREFIX": str(case.output) + ".moonreduce-",
        "MOONREDUCE_TEST_WRITE_GATE": str(gate),
    })
    with case.log.open("wb") as stream:
        process = subprocess.Popen(case.argv, cwd=ROOT, env=case.env, stdout=stream,
                                   stderr=stream, start_new_session=True)
        try:
            wait_for(lambda: Path(str(gate) + ".ready").exists(), process, case.log)
            assert not case.output.exists()  # complete staged write not published yet
            process.send_signal(signal.SIGINT)
            Path(str(gate) + ".release").touch()
            code = process.wait(timeout=6)
            text = case.log.read_text()
            data = case.check(subprocess.CompletedProcess(case.argv, code, text, text))
            assert code == 130 and case.output.read_bytes() == b"BUG"
            assert data["initial_check"] == "interesting" and data["tests_started"] == 1
            assert data["final_revalidation"] == "not_run"
        finally:
            Path(str(gate) + ".release").touch()
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
    for destination in ["output", "report"]:
        case = Case(work, f"concurrent-{destination}", b"BUG", budget=2)
        target = case.output if destination == "output" else case.report
        plan = json.loads((case.path / "plan.json").read_text())
        plan["calls"] = {"1": {"create_file": str(target)}}
        (case.path / "plan.json").write_text(json.dumps(plan))
        result = subprocess.run(case.argv, cwd=ROOT, env=case.env, capture_output=True,
                                text=True, timeout=12)
        assert result.returncode == 4 and target.read_bytes() == b"concurrent file: preserve me"
        assert case.input.read_bytes() == b"BUG" and not list(case.path.rglob("*.moonreduce-*"))
        if destination == "output":
            data = json.loads(case.report.read_text())
            assert not data["output_saved"] and data["result_status"] == "no_saved_result"
        else:
            assert case.output.read_bytes() == b"BUG"
            assert "Report:" not in result.stdout and "execution_error" in result.stdout
    print("PASS partial-write ENOSPC, SIGINT during atomic save, and concurrent destination preservation", flush=True)


def timeout_and_interrupt(work):
    for name, original, call, tree, code in [
        ("ordinary-initial", b"BUG", 1, "tree", 3),
        ("stubborn-child-initial", b"BUG", 1, "stubborn-tree", 3),
        ("search-timeout", b"a\nBUG\n", 2, "tree", 0),
        ("minimality-timeout", b"BUG", 2, "stubborn", 1),
        ("final-timeout", b"BUG", 3, "tree", 4),
    ]:
        case = Case(work, name, original, calls={str(call): {"tree": tree}}, timeout=750)
        data = case.run(code)
        assert data["timeouts"] == 1 and data["unresolved"] >= 1
        gone(json.loads((case.path / "evidence/pids.json").read_text()))
        if tree == "tree":
            assert (case.path / "evidence/reaped").exists()
            assert (case.path / "evidence/worker-reaped").exists()
    for phase, call, fault in [("initial", 1, None), ("search", 2, None),
                               ("minimality", 2, None), ("final", 3, None),
                               ("search", 2, "/usr/bin/kill")]:
        original = b"a\nBUG\n" if phase == "search" else b"BUG"
        case = Case(work, f"interrupt-{phase}" + ("-helper-fails" if fault else ""),
                    original, calls={str(call): {"tree": "stubborn-tree"}},
                    timeout=30000, fault=fault)
        arm = case.path / "arm-helper"
        if fault:
            case.env["MOONREDUCE_TEST_FAIL_SPAWN_ARM"] = str(arm)
        with case.log.open("wb") as stream:
            process = subprocess.Popen(case.argv, cwd=ROOT, env=case.env, stdout=stream,
                                       stderr=stream, start_new_session=True)
            try:
                wait_for(lambda: (case.path / "evidence/ready").exists(), process, case.log)
                if phase != "initial":
                    assert case.output.read_bytes() == original
                if fault:
                    arm.touch()
                process.send_signal(signal.SIGINT)
                code = process.wait(timeout=6)
                text = case.log.read_text()
                data = case.check(subprocess.CompletedProcess(case.argv, code, text, text))
                assert code == (4 if fault else 130) and data["interrupted"]
                assert data["interrupted_tests"] == (0 if fault else 1)
                assert data["final_revalidation"] == ("interrupted" if phase == "final" else "not_run")
                if phase == "final":
                    assert data["search_stop_reason"] == "completed"
                gone(json.loads((case.path / "evidence/pids.json").read_text()))
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)
    print("PASS nested timeouts and SIGINT in all four phases, including TERM-ignoring children and final call", flush=True)


def closed_summary_pipe(work):
    case = Case(work, "closed-stdout", b"BUG")
    process = subprocess.Popen(case.argv, cwd=ROOT, env=case.env,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    process.stdout.close()
    try:
        code = process.wait(timeout=8)
        message = process.stderr.read().decode()
        data = json.loads(case.report.read_text())
        assert code == data["exit_code"] == 4
        assert data["stop_reason"] == "execution_error" and "Broken pipe" in data["error"]
        assert data["final_revalidation"] == "interesting" and data["minimality"] == "verified"
        assert "exit code: 4" in message and case.output.read_bytes() == b"BUG"
        assert case.input.read_bytes() == b"BUG"
    finally:
        process.stderr.close()
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
    print("PASS closed summary pipe updates JSON to the actual exit code without another oracle call", flush=True)


def saving_and_output(work):
    case = Case(work, "saved-each-improvement")
    data = case.run(0)
    trace = rows(case.trace)
    best = None
    for row in trace:
        if best is not None:
            assert bytes.fromhex(row["saved_hex"]) == best
        current = bytes.fromhex(row["hex"])
        if b"BUG" in current and (best is None or len(segments(current)) < len(segments(best))):
            best = current
    assert case.output.read_bytes() == best
    case = Case(work, "large-output", b"BUG", budget=2,
                calls={"1": {"large": True}, "2": {"large": True}})
    data = case.run(1)
    diagnostics = data["diagnostics"]
    for stream in ["stdout", "stderr"]:
        assert len(diagnostics[stream].encode()) == 4096 and diagnostics[stream + "_truncated"]
    assert case.report.stat().st_size < 14000
    assert case.output.read_bytes() == b"BUG"
    print("PASS every accepted improvement saved before next start; 32 MiB per stream with 4096-byte diagnostics", flush=True)


def main():
    global BINARY
    if len(sys.argv) == 2:
        BINARY = Path(sys.argv[1]).resolve()
    else:
        subprocess.run(["moon", "build", "--target", "native", "--deny-warn"], cwd=ROOT, check=True, timeout=60)
    # ld.so splits LD_PRELOAD on spaces; path/argv spacing is covered in stage 2.
    with tempfile.TemporaryDirectory(prefix="moonreduce-stage3-") as directory:
        work = Path(directory)
        subprocess.run(["cc", "-shared", "-fPIC", "-Wall", "-Wextra", "-Werror",
                        str(ROOT / "tests/fixtures/faults.c"), "-ldl", "-o", str(work / "faults.so")],
                       check=True, timeout=30)
        before = set(Path(tempfile.gettempdir()).glob("moonreduce oracle *")) | set(Path(tempfile.gettempdir()).glob("moonreduce signal *"))
        passed = False
        try:
            for check in [
                budgets, verdicts, minimality_continues, io_failures,
                spawn_and_cleanup_failures, atomic_publication,
                timeout_and_interrupt, saving_and_output, closed_summary_pipe,
            ]:
                check(work)
            after = set(Path(tempfile.gettempdir()).glob("moonreduce oracle *")) | set(Path(tempfile.gettempdir()).glob("moonreduce signal *"))
            assert after == before, f"temporary candidate/log directories leaked: {after - before}"
            passed = True
        finally:
            if not passed:
                # Failure-only hygiene, performed after assertions and never
                # counted as proof that MoonReduce cleaned up its own children.
                for evidence in work.glob("*/evidence/pids.json"):
                    for pid in json.loads(evidence.read_text()):
                        try:
                            os.kill(pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                for directory in [*work.glob("*/results"), *work.glob("*/reports")]:
                    directory.chmod(0o700)
    print("Stage 3 reliability and report matrix passed. Stage 4 workflow/consumer and final clean-environment acceptance remain pending.")


if __name__ == "__main__":
    main()
