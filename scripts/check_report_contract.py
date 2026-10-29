#!/usr/bin/env python3
"""Check real report shapes and reject contradictory copies, reusing stage 3."""
from copy import deepcopy
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile

import check_stage3 as reliability
from validate_report import load_report, make_validator, terminal_violations, violations

ROOT = Path(__file__).resolve().parents[1]


def counter_and_proof_mutations(reports, validator, work, command):
    """Keep schema/count sums valid; assert the specific missing relation and CLI error."""
    checked = []

    def reject(name, data, *messages):
        assert not list(validator.iter_errors(data)), f"{name}: mutation must pass the schema"
        assert data["tests_started"] == sum(data["tests_by_phase"].values()), name
        assert data["tests_started"] == sum(data[key] for key in (
            "interesting", "not_interesting", "unresolved", "oracle_errors", "interrupted_tests"
        )), name
        assert data["launch_attempts"] == data["tests_started"] + data["launch_failures"], name
        errors = violations(data, validator)
        for message in messages:
            assert any(message in error for error in errors), (name, message, errors)
        path = work / (name + ".json")
        path.write_text(json.dumps(data))
        result = subprocess.run([*command, path], capture_output=True, text=True, timeout=10)
        assert result.returncode == 1, (name, result.stdout, result.stderr)
        assert all(message in result.stderr for message in messages), (name, result.stderr)
        checked.append(name)

    def transfer(data, source, target, amount):
        data[source] -= amount
        data[target] += amount
        data["had_unresolved"] = data["unresolved"] > 0

    # The exact two transformations recorded by the original fixed-HEAD review.
    sample = load_report(ROOT / "docs/report.example.json")
    data = deepcopy(sample)
    transfer(data, "interesting", "not_interesting", data["interesting"])
    reject("zero-interesting", data, "interesting=0 <", "initial_check=interesting",
           "final_revalidation=interesting")
    data = deepcopy(sample)
    phases = data["tests_by_phase"]
    phases["search"] += phases["minimality"]
    phases["minimality"] = 0
    reject("no-minimality-calls", data,
           "minimality_checked=3 exceeds tests_by_phase.minimality=0")
    # Even one I is insufficient for two independently executed I endpoints.
    data = deepcopy(reports["budget"])
    transfer(data, "interesting", "not_interesting", 1)
    reject("one-interesting-for-two-checks", data, "interesting=1 < 2 required by",
           "initial_check=interesting", "final_revalidation=interesting")
    data = deepcopy(sample)
    transfer(data, "interesting", "not_interesting", data["interesting"] - 2)
    reject("saved-reduction-without-improvement-I", data, "interesting=2 < 3 required by",
           "best_segments < original_segments (saved improvement)")
    for name, category, other, field, verdict in [
        ("initial-NI", "not_interesting", "unresolved", "initial_check", "not_interesting"),
        ("initial-U", "unresolved", "not_interesting", "initial_check", "unresolved"),
        ("final-U", "unresolved", "not_interesting", "final_revalidation", "unresolved"),
    ]:
        data = deepcopy(reports[name])
        transfer(data, category, other, data[category])
        reject(name + "-without-count", data, f"{category}=0 <", f"{field}={verdict}")
    # Endpoint verdicts cannot double as deletion witnesses, even in the same category.
    data = deepcopy(reports["final-NI"])
    transfer(data, "not_interesting", "unresolved", data["not_interesting"] - 1)
    reject("final-NI-reused-as-proof", data, "not_interesting=1 < 2 required by",
           "final_revalidation=not_interesting", "minimality_checked=1 with minimality=verified")
    data = deepcopy(reports["blocked-final-U"])
    transfer(data, "unresolved", "not_interesting", data["unresolved"] - 1)
    reject("final-U-reused-as-witness", data, "unresolved=1 < 2 required by",
           "final_revalidation=unresolved", "minimality=blocked_by_unresolved (current-round witness)")
    data = deepcopy(sample)
    transfer(data, "not_interesting", "unresolved", data["not_interesting"] - 2)
    reject("verified-proof-lacks-NI", data, "not_interesting=2 < 3 required by",
           "minimality_checked=3 with minimality=verified")
    data = deepcopy(reports["partial-proof-budget"])
    for category in ("not_interesting", "unresolved"):
        transfer(data, category, "interesting", data[category])
    reject("partial-proof-lacks-NI-U", data,
           "not_interesting + unresolved after reserving initial_check/final_revalidation "
           "observations = 0 < minimality_checked=")
    data = deepcopy(reports["partial-proof-budget"])
    data["tests_by_phase"]["minimality"] = data["minimality_checked"] - 1
    data["tests_by_phase"]["search"] += 1
    reject("partial-progress-without-starts", data,
           f"minimality_checked={data['minimality_checked']} exceeds tests_by_phase.minimality=")
    for phase, field in [("initial", "initial_check"), ("final", "final_revalidation")]:
        data = deepcopy(sample)
        data["tests_by_phase"][phase] = 0
        data["tests_by_phase"]["search"] += 1
        reject(phase + "-verdict-without-start", data,
               f"{field}=interesting requires tests_by_phase.{phase}=1")
    data = deepcopy(reports["execution-error"])
    data["tests_by_phase"]["search"] -= 1
    data["tests_by_phase"]["final"] = 1
    reject("not-run-with-final-start", data,
           "final_revalidation=not_run requires tests_by_phase.final=0")
    data = deepcopy(reports["budget"])
    data["minimality_checked"] = 1
    reject("not-checked-with-progress", data, "minimality=not_checked requires minimality_checked=0")
    data = deepcopy(reports["budget"])
    for field in ("tests_started", "launch_attempts", "max_tests", "not_interesting"):
        data[field] += 1
    data["tests_by_phase"]["minimality"] = 1
    reject("not-checked-with-start", data, "minimality=not_checked requires minimality_checked=0 "
           "and tests_by_phase.minimality=0")
    data = deepcopy(reports["historical-U"])
    data.update(best_positions=[], best_segments=0, best_bytes=0, minimality_checked=0,
                minimality_required=0, minimality="blocked_by_unresolved", stop_reason="unresolved",
                minimality_reason="unresolved_single_deletions", exit_code=1)
    reject("empty-proof-blocked-by-old-U", data,
           "minimality=blocked_by_unresolved requires minimality_checked>0")
    data = deepcopy(reports["unresolved"])
    data["initial_check"] = "not_interesting"
    reject("saved-without-initial-I", data, "output_saved=true requires initial_check=interesting")
    return len(checked)


def terminal_mutations(reports, validator, work, command):
    count = 0

    def reject(name, data, message):
        nonlocal count
        assert not list(validator.iter_errors(data)), name
        assert data["tests_started"] == sum(data["tests_by_phase"].values()), name
        assert data["tests_started"] == sum(data[key] for key in (
            "interesting", "not_interesting", "unresolved", "oracle_errors", "interrupted_tests"
        )), name
        assert data["launch_attempts"] == data["tests_started"] + data["launch_failures"], name
        terminal = terminal_violations(data)
        errors = violations(data, validator)
        # No earlier schema/count/proof rule may be the reason for rejection.
        assert errors == terminal and any(message in error for error in errors), (name, errors)
        path = work / ("terminal-" + name + ".json")
        path.write_text(json.dumps(data))
        result = subprocess.run([*command, path], capture_output=True, text=True, timeout=10)
        assert result.returncode == 1 and message in result.stderr, (name, result.stdout, result.stderr)
        count += 1

    for counter in ("oracle_errors", "interrupted_tests"):
        data = deepcopy(reports["normal"])
        data[counter] += 1
        data["not_interesting"] -= 1
        reject("completed-" + counter, data, counter + ("=1 requires" if counter == "oracle_errors"
                                                        else ">0 requires interrupted=true"))
    data = deepcopy(reports["normal"])
    data["launch_failures"] = 1
    data["launch_attempts"] += 1
    reject("completed-launch-failure", data, "launch_failures=1 requires stop_reason=execution_error")
    for name in ("initial-NI", "initial-U"):
        data = deepcopy(reports[name])
        data["tests_by_phase"]["search"] = 1
        for field in ("tests_started", "launch_attempts", "not_interesting"):
            data[field] += 1
        reject(name + "-searched", data, f"initial_check={data['initial_check']} forbids tests_by_phase.search=1")
    data = deepcopy(reports["initial-save-error"])
    data["tests_by_phase"]["search"] = 1
    for field in ("tests_started", "launch_attempts", "not_interesting"):
        data[field] += 1
    reject("unsaved-searched", data, "output_saved=false forbids search/minimality/final starts")
    data = deepcopy(reports["initial-save-error"])
    data["minimality"] = "incomplete"
    reject("unsaved-proof-started", data, "output_saved=false requires minimality=not_checked")
    data = deepcopy(reports["initial-NI-summary-error"])
    data["launch_failures"] = 1
    data["launch_attempts"] += 1
    reject("initial-NI-later-launch-failure", data, "initial_check=not_interesting forbids launch_failures")
    for counter in ("oracle_errors", "interrupted_tests"):
        data = deepcopy(reports["closed-stdout"])
        data[counter] += 1
        data["not_interesting"] -= 1
        if counter == "interrupted_tests":
            data["interrupted"] = True
        reject("final-known-after-" + counter, data, "final_revalidation=interesting requires " + counter + "=0")
    data = deepcopy(reports["closed-stdout"])
    data["launch_failures"] = 1
    data["launch_attempts"] += 1
    reject("final-known-after-launch-failure", data, "final_revalidation=interesting requires launch_failures=0")
    for value in (1, 2, 137):
        data = deepcopy(reports["normal"])
        data["last_exit_code"] = value
        reject(f"final-I-exit-{value}", data, f"final_revalidation=interesting requires last_exit_code=0, got {value}")
    data = deepcopy(reports["normal"])
    data.update(last_exit_code=None, last_signal=9)
    reject("final-I-signal", data, "final_revalidation=interesting requires last_signal=null, got 9")
    for name, value in (("final-NI", 0), ("initial-NI", 0), ("initial-U", 1), ("final-U", 1)):
        data = deepcopy(reports[name])
        data["last_exit_code"] = value
        reject(name + "-wrong-exit", data, f"{('initial_check' if name.startswith('initial') else 'final_revalidation')}="
               f"{data['initial_check'] if name.startswith('initial') else data['final_revalidation']} requires last_exit_code=")
    data = deepcopy(reports["final-U"])
    data["last_exit_code"] = None
    assert data["timeouts"] == 0
    reject("final-U-null-without-timeout", data, "last_exit_code=null requires timeouts>0")
    data = deepcopy(reports["budget"])
    data["max_tests"] += 1
    reject("budget-before-limit", data, "tests_started=max_tests-1+tests_by_phase.final")
    data = deepcopy(reports["final-NI"])
    data["search_stop_reason"] = "not_started"
    reject("final-without-search-stop", data,
           "final_revalidation=not_interesting requires search_stop_reason=completed/budget_exhausted")
    data = deepcopy(reports["closed-stdout"])
    data["minimality"] = "incomplete"
    reject("completed-search-incomplete-proof", data,
           "search_stop_reason=completed requires minimality=verified/blocked_by_unresolved")
    data = deepcopy(reports["budget-final-U"])
    data["minimality_reason"] = "not_completed"
    reject("budget-proof-reason", data,
           "search_stop_reason=budget_exhausted requires unfinished minimality")
    for name, field, value in [("interrupt-initial", "initial_check", "error"),
                                ("interrupt-final", "final_revalidation", "error"),
                                ("interrupt-search", "search_stop_reason", "execution_error")]:
        data = deepcopy(reports[name])
        data[field] = value
        reject(name + "-error-marker", data, f"{field}={value} requires stop_reason=execution_error")
    data = deepcopy(reports["execution-error"])
    data["search_stop_reason"] = "interrupted"
    reject("interrupted-marker-without-flag", data, "search_stop_reason=interrupted requires interrupted=true")
    data = deepcopy(reports["final-U"])
    data["interrupted"] = True
    reject("final-U-interrupted-flag", data,
           "interrupted=true requires stop_reason=interrupted/execution_error")
    return count


def interrupt_during_save(work):
    # Gate the existing test-only write interposer, not a millisecond race.
    case = reliability.Case(work, "interrupt-save-observed-I", b"BUG")
    gate = case.path / "save-gate"
    case.env.update({"MOONREDUCE_TEST_WRITE_PREFIX": str(case.output) + ".moonreduce-",
                     "MOONREDUCE_TEST_WRITE_GATE": str(gate)})
    with case.log.open("wb") as stream:
        process = subprocess.Popen(case.argv, cwd=ROOT, env=case.env, stdout=stream,
                                   stderr=stream, start_new_session=True)
        try:
            reliability.wait_for(lambda: Path(str(gate) + ".ready").exists(), process, case.log)
            process.send_signal(signal.SIGINT)
            Path(str(gate) + ".release").touch()
            code = process.wait(timeout=6)
            log = case.log.read_text()
            data = case.check(subprocess.CompletedProcess(case.argv, code, log, log))
            assert code == 130 and data["initial_check"] == "interesting"
            assert data["interrupted_tests"] == 0 and data["final_revalidation"] == "not_run"
        finally:
            Path(str(gate) + ".release").touch()
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)


def summary_failures(work):
    # Confirmed rejection/verdict can survive a later summary IO error. These
    # are real reports, not hand-edited execution_error compatibility fixtures.
    for name, calls in [("closed-stdout", None), ("initial-NI-summary-error", {"1": {"verdict": 1}}),
                        ("initial-U-summary-error", {"1": {"verdict": 2}})]:
        case = reliability.Case(work, name, calls=calls)
        process = subprocess.Popen(case.argv, cwd=ROOT, env=case.env,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        process.stdout.close()
        try:
            code = process.wait(timeout=8)
            message = process.stderr.read(8192).decode()
            data = load_report(case.report)
            assert code == data["exit_code"] == 4 and data["stop_reason"] == "execution_error"
            assert "Broken pipe" in data["error"] and "exit code: 4" in message
            assert case.input.read_bytes() == case.original and data["oracle_errors"] == 0
            assert len(reliability.rows(case.trace)) == data["tests_started"]
            if calls is None:
                assert data["final_revalidation"] == "interesting" and data["minimality"] == "verified"
            else:
                assert not data["output_saved"] and data["tests_started"] == 1
        finally:
            process.stderr.close()
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)


def main():
    validator = make_validator()
    if len(sys.argv) == 2:
        reliability.BINARY = Path(sys.argv[1]).resolve()
    else:
        subprocess.run(["moon", "build", "--target", "native", "--deny-warn"],
                       cwd=ROOT, check=True, timeout=60)
    sample = load_report(ROOT / "docs/report.example.json")
    assert not violations(sample, validator)
    with tempfile.TemporaryDirectory(prefix="moonreduce-report-contract-") as directory:
        work = Path(directory)
        subprocess.run(["cc", "-shared", "-fPIC", "-Wall", "-Wextra", "-Werror",
                        str(ROOT / "tests/fixtures/faults.c"), "-ldl", "-o", str(work / "faults.so")],
                       check=True, timeout=30)
        passed = False
        try:
            for name, kwargs, code in [
                ("normal", {}, 0), ("budget", {"budget": 2}, 1),
                ("unresolved", {"predicate": "only-original"}, 1),
                ("empty", {"original": b"", "predicate": "always", "budget": 2}, 0),
                ("historical-U", {"calls": {"2": {"verdict": 2}}}, 0),
                ("initial-NI", {"calls": {"1": {"verdict": 1}}}, 3),
                ("initial-U", {"calls": {"1": {"verdict": 2}}}, 3),
                ("final-NI", {"original": b"BUG", "calls": {"3": {"verdict": 1}}}, 4),
                ("final-U", {"original": b"BUG", "calls": {"3": {"verdict": 2}}}, 4),
                ("execution-error", {"calls": {"2": {"verdict": 7}}}, 4),
                ("search-to-empty", {"predicate": "always", "budget": 3}, 0),
                ("single-to-empty", {"original": b"x", "predicate": "always", "budget": 3}, 0),
                ("launcher-error", {"fault": "/usr/bin/setsid"}, 4),
                ("diagnostic-error", {"calls": {"1": {"break_log": True}}}, 4),
                ("budget-final-NI", {"budget": 2, "calls": {"2": {"verdict": 1}}}, 4),
                ("budget-final-U", {"budget": 2, "calls": {"2": {"verdict": 2}}}, 4),
                ("initial-signal", {"calls": {"1": {"signal": 15}}}, 4),
                ("search-signal", {"calls": {"2": {"signal": 15}}}, 4),
                ("minimality-signal", {"original": b"BUG", "calls": {"2": {"signal": 15}}}, 4),
                ("final-signal", {"original": b"BUG", "calls": {"3": {"signal": 15}}}, 4),
                ("initial-exit-137", {"calls": {"1": {"verdict": 137}}}, 4),
                ("empty-final-U", {"original": b"", "predicate": "always", "budget": 2,
                                   "calls": {"2": {"verdict": 2}}}, 4),
                ("empty-final-timeout", {"original": b"", "predicate": "always", "budget": 2,
                                         "timeout": 750, "calls": {"2": {"tree": "stubborn-tree"}}}, 4),
            ]:
                reliability.Case(work, name, **kwargs).run(code)
            for name, call, budget in [("final-launcher-error", 2, 1000),
                                       ("budget-final-launcher-error", 1, 2)]:
                arm = work / name / "arm-launch-failure"
                case = reliability.Case(work, name, b"BUG", budget=budget,
                                        calls={str(call): {"touch": str(arm)}}, fault="/usr/bin/setsid")
                case.env["MOONREDUCE_TEST_FAIL_SPAWN_ARM"] = str(arm)
                case.run(4)
            directory = work / "initial-save-error/results"
            reliability.Case(work, "initial-save-error", b"BUG",
                             calls={"1": {"chmod": str(directory)}}).run(4)
            summary_failures(work)
            interrupt_during_save(work)
            full = load_report(work / "unresolved/reports/report.json")
            partial = reliability.Case(work, "partial-proof-budget", predicate="only-original",
                                       budget=full["tests_started"] - 1).run(1)
            assert 0 < partial["minimality_checked"] < partial["minimality_required"]
            reliability.Case(work, "blocked-final-U", predicate="only-original",
                             calls={str(full["tests_started"]): {"verdict": 2}}).run(4)
            reliability.minimality_continues(work)
            # Existing fixtures/checks handle readiness, signal timing and process reaping.
            reliability.timeout_and_interrupt(work)
            paths = sorted(work.glob("*/reports/report.json"))
            reasons = set()
            reports = {}
            for path in paths:
                data = load_report(path)
                errors = violations(data, validator)
                assert not errors, (path, errors)
                reasons.add(data["stop_reason"])
                reports[path.parent.parent.name] = data
            assert reasons == set(reliability.EXIT_CODES), reasons
            for name in ("empty", "search-to-empty"):
                data = reports[name]
                assert data["best_segments"] == data["minimality_checked"] == 0
                assert data["tests_by_phase"]["minimality"] == 0
            restart = reports["minimality-improves"]
            assert restart["tests_by_phase"]["minimality"] > restart["minimality_checked"] > 0
            assert reports["launcher-error"]["tests_started"] == 0
            assert reports["diagnostic-error"]["initial_check"] == "error"
            assert reports["diagnostic-error"]["interesting"] == 1
            assert reports["diagnostic-error"]["oracle_errors"] == 0
            assert reports["historical-U"]["had_unresolved"] and reports["historical-U"]["exit_code"] == 0
            assert reports["initial-exit-137"]["last_exit_code"] == 137
            assert reports["initial-exit-137"]["last_signal"] is None
            for name in ("initial-signal", "search-signal", "minimality-signal", "final-signal"):
                assert reports[name]["last_signal"] == 15 and reports[name]["last_exit_code"] is None
            for name in ("empty-final-timeout", "final-timeout", "ordinary-initial", "stubborn-child-initial"):
                assert reports[name]["last_exit_code"] is None and reports[name]["last_signal"] is None
                assert reports[name]["timeouts"] == 1
            reliability.gone(json.loads((work / "empty-final-timeout/evidence/pids.json").read_text()))
            for name in ("final-launcher-error", "budget-final-launcher-error"):
                assert reports[name]["output_saved"] and reports[name]["final_revalidation"] == "error"
                assert reports[name]["tests_by_phase"]["final"] == 0 and reports[name]["last_exit_code"] is None
            assert reports["final-launcher-error"]["minimality"] == "verified"
            assert reports["budget-final-launcher-error"]["tests_started"] == 1
            assert reports["closed-stdout"]["final_revalidation"] == "interesting"
            assert reports["closed-stdout"]["oracle_errors"] == 0
            for name in ("empty-final-U", "empty-final-timeout"):
                assert reports[name]["minimality"] == "verified" and reports[name]["minimality_checked"] == 0
            command = [sys.executable, ROOT / "scripts/validate_report.py"]
            result = subprocess.run([*command, ROOT / "docs/report.example.json", *paths],
                                    capture_output=True, text=True, timeout=10)
            assert result.returncode == 0, result.stderr
            relations = counter_and_proof_mutations(reports, validator, work, command)
            terminals = terminal_mutations(reports, validator, work, command)
            passed = True
        finally:
            if not passed:
                # Failure hygiene only; successful checks above require the CLI to reap.
                for path in work.glob("*/evidence/pids.json"):
                    for pid in json.loads(path.read_text()):
                        try:
                            os.kill(pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
        invalid = []

        def reject(name, **updates):
            data = {**deepcopy(sample), **updates}
            assert violations(data, validator), f"accepted contradictory report: {name}"
            invalid.append(name)

        reject("string counter", tests_started=str(sample["tests_started"]))
        reject("boolean counter", interesting=True)
        reject("wrong exit", exit_code=1)
        reject("false verified completion", minimality="incomplete")
        reject("lost final verdict", final_revalidation="not_run")
        reject("incomplete proof", minimality_checked=0)
        reject("bad phase counts", tests_by_phase={**sample["tests_by_phase"], "final": 0})
        reject("outcome counts", oracle_errors=1)
        reject("hidden launch", launch_attempts=sample["launch_attempts"] + 1)
        reject("budget overrun", max_tests=2)
        reject("timeout without unresolved", timeouts=1)
        reject("unknown schema", schema_version=2)
        reject("reordered identities", best_positions=list(reversed(sample["best_positions"])))
        reject("out of range identity", best_positions=[46, 47, 99999])
        reject("signal and exit", last_signal=9)
        reject("missing save", output_saved=False)
        reject("lost provenance", only_previously_observed_interesting=True)
        reject("final failure claims success", stop_reason="final_not_interesting",
               exit_code=4, final_revalidation="not_interesting")
        reject("unresolved calls verified", stop_reason="unresolved", exit_code=1)
        reject("unbounded diagnosis", diagnostics={**sample["diagnostics"], "stderr": "x" * 4097})
        reject("infinite duration", elapsed_ms=float("inf"))
        bad = work / "contradictory.json"
        bad.write_text(json.dumps({**sample, "exit_code": 130}))
        result = subprocess.run([*command, bad], capture_output=True, text=True, timeout=10)
        assert result.returncode == 1 and "FAIL" in result.stderr
        bad.write_text('{"elapsed_ms": NaN}')
        result = subprocess.run([*command, bad], capture_output=True, text=True, timeout=10)
        assert result.returncode == 1 and "non-JSON" in result.stderr
        result = subprocess.run([sys.executable, "-S", *command[1:], bad],
                                capture_output=True, text=True, timeout=10)
        assert result.returncode == 2 and "jsonschema==4.19.2" in result.stderr
    print(f"PASS {len(paths)} real reports (all stop reasons), recorded algorithm report, "
          f"{len(invalid)} legacy copies, {relations} targeted counter/proof mutations "
          f"and {terminals} terminal mutations with specific diagnostics and validator exits 0/1/2")


if __name__ == "__main__":
    main()
