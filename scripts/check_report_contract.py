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
from validate_report import load_report, make_validator, violations

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
            ]:
                reliability.Case(work, name, **kwargs).run(code)
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
            command = [sys.executable, ROOT / "scripts/validate_report.py"]
            result = subprocess.run([*command, ROOT / "docs/report.example.json", *paths],
                                    capture_output=True, text=True, timeout=10)
            assert result.returncode == 0, result.stderr
            relations = counter_and_proof_mutations(reports, validator, work, command)
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
          "with specific diagnostics and validator exits 0/1/2")


if __name__ == "__main__":
    main()
