#!/usr/bin/env python3
"""Validate schema_version 1 plus count/position/state relations, offline."""
import argparse
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def make_validator():
    # Development-only dependency; neither CLI nor the old test entry points import it.
    from jsonschema import Draft202012Validator
    schema = json.loads((ROOT / "docs/report.schema.json").read_text())
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def violations(data, validator):
    errors = [f"schema {list(error.absolute_path)}: {error.message}"
              for error in validator.iter_errors(data)]
    if errors:
        return errors

    def require(condition, message):
        if not condition:
            errors.append(message)

    require(math.isfinite(data["elapsed_ms"]), "elapsed_ms must be finite")
    starts = data["tests_started"]
    phases = data["tests_by_phase"]
    require(starts == sum(phases.values()), "tests_started != sum(tests_by_phase)")
    require(starts == sum(data[key] for key in (
        "interesting", "not_interesting", "unresolved", "oracle_errors", "interrupted_tests"
    )), "tests_started != terminal outcome counts")
    require(starts <= data["max_tests"], "actual starts exceed max_tests")
    require(data["launch_attempts"] == starts + data["launch_failures"],
            "launch_attempts != tests_started + launch_failures")
    require(data["timeouts"] <= data["unresolved"], "timeouts exceed unresolved")
    require(data["had_unresolved"] == (data["unresolved"] > 0), "had_unresolved mismatch")
    require(data["last_exit_code"] is None or data["last_signal"] is None,
            "last_exit_code and last_signal cannot both be set")
    require(data["oracle_argv"][0] != "", "oracle command cannot be empty")
    require(data["input"] != data["requested_output"] and
            data["report"] not in (data["input"], data["requested_output"]),
            "input/output/report path strings must differ")
    # This offline check cannot stat historical files to check inode identity.
    original = data["original_segments"]
    require(original <= data["original_bytes"], "original segments exceed bytes")
    require((original == 0) == (data["original_bytes"] == 0), "empty input mismatch")
    saved = data["output_saved"]
    require(saved == (data["output"] is not None), "output_saved/output mismatch")
    best_keys = ["best_bytes", "best_segments", "best_positions"]
    if saved:
        require(data["output"] == data["requested_output"], "saved output != requested_output")
        require(all(data[key] is not None for key in best_keys), "saved output lacks best metadata")
        if all(data[key] is not None for key in best_keys):
            positions = data["best_positions"]
            require(positions == sorted(set(positions)), "best positions must strictly increase")
            require(all(index < original for index in positions), "position outside original input")
            require(len(positions) == data["best_segments"], "best position count mismatch")
            require(data["best_segments"] <= data["best_bytes"] <= data["original_bytes"],
                    "best byte/segment bounds violated")
            require((data["best_segments"] == 0) == (data["best_bytes"] == 0),
                    "empty best mismatch")
    else:
        require(all(data[key] is None for key in best_keys), "unsaved output has best metadata")
    required = data["best_segments"] if saved else 0
    require(data["minimality_required"] == required, "minimality_required != best size")
    require(data["minimality_checked"] <= data["minimality_required"],
            "minimality_checked exceeds required")
    minimality = data["minimality"]
    if minimality in ("verified", "blocked_by_unresolved"):
        require(saved and data["minimality_checked"] == required,
                "completed minimality check lacks saved result or full progress")
        reason = ("unresolved_single_deletions" if minimality == "blocked_by_unresolved"
                  else "empty_result" if required == 0 else "all_single_deletions_not_interesting")
        require(data["minimality_reason"] == reason, "minimality reason mismatch")
    if minimality == "blocked_by_unresolved":
        require(data["had_unresolved"], "blocked minimality requires unresolved evidence")
    if not saved:
        require(data["minimality_reason"] == "no_saved_interesting_result",
                "unsaved result minimality reason mismatch")
    final = data["final_revalidation"]
    previous = saved and final != "interesting"
    status = ("no_saved_result" if not saved else
              "previously_interesting" if previous else "revalidated_interesting")
    require(data["only_previously_observed_interesting"] == previous,
            "only_previously_observed_interesting mismatch")
    require(data["result_status"] == status, "result_status mismatch")
    if final in ("interesting", "not_interesting", "unresolved"):
        require(saved and phases["final"] == 1, "actual final verdict requires saved result and call")
    if data["stop_reason"] != "execution_error":
        require(data["error"] is None, "non-error stop contains execution error")
    if data["stop_reason"] in ("completed", "budget_exhausted", "unresolved"):
        require(not data["interrupted"], "successful/partial completion cannot claim interruption")
    return errors


def reject_constant(value):
    raise ValueError(f"non-JSON numeric constant {value}")


def load_report(path):
    return json.loads(Path(path).read_text(), parse_constant=reject_constant)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", type=Path, nargs="+")
    args = parser.parse_args()
    try:
        validator = make_validator()
    except ImportError:
        print("Missing development dependency: jsonschema==4.19.2; see docs/report-contract.md",
              file=sys.stderr)
        return 2
    failed = False
    for path in args.reports:
        try:
            errors = violations(load_report(path), validator)
        except (OSError, ValueError) as error:
            errors = [str(error)]
        if errors:
            failed = True
            print(f"FAIL {path}:\n" + "\n".join(errors), file=sys.stderr)
        else:
            print(f"PASS {path}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
