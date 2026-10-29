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
            ]:
                reliability.Case(work, name, **kwargs).run(code)
            # Existing fixtures/checks handle readiness, signal timing and process reaping.
            reliability.timeout_and_interrupt(work)
            paths = sorted(work.glob("*/reports/report.json"))
            reasons = set()
            for path in paths:
                data = load_report(path)
                errors = violations(data, validator)
                assert not errors, (path, errors)
                reasons.add(data["stop_reason"])
            assert reasons == set(reliability.EXIT_CODES), reasons
            command = [sys.executable, ROOT / "scripts/validate_report.py"]
            result = subprocess.run([*command, ROOT / "docs/report.example.json", *paths],
                                    capture_output=True, text=True, timeout=10)
            assert result.returncode == 0, result.stderr
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
          f"{len(invalid)} contradictory copies and validator exits 0/1/2")


if __name__ == "__main__":
    main()
