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


def terminal_violations(data):
    """Necessary control-flow relations, after schema validation; not a trace verifier."""
    errors = []

    def require(condition, message):
        if not condition:
            errors.append(message)

    reason = data["stop_reason"]
    initial, final = data["initial_check"], data["final_revalidation"]
    phases = data["tests_by_phase"]
    exceptional = ("execution_error", "interrupted")
    for counter in ("oracle_errors", "launch_failures"):
        if data[counter]:
            require(reason == "execution_error",
                    f"{counter}={data[counter]} requires stop_reason=execution_error, got {reason}")
    if data["interrupted_tests"]:
        require(data["interrupted"], "interrupted_tests>0 requires interrupted=true")
        require(reason in exceptional,
                f"interrupted_tests>0 requires stop_reason=interrupted/execution_error, got {reason}")
    if data["interrupted"]:
        require(reason in exceptional,
                f"interrupted=true requires stop_reason=interrupted/execution_error, got {reason}")
    for field, value in [("initial_check", initial), ("final_revalidation", final),
                         ("search_stop_reason", data["search_stop_reason"])]:
        if value in ("error", "execution_error"):
            require(reason == "execution_error",
                    f"{field}={value} requires stop_reason=execution_error, got {reason}")
        elif value == "interrupted":
            require(data["interrupted"] and reason in exceptional,
                    f"{field}=interrupted requires interrupted=true and "
                    "stop_reason=interrupted/execution_error")
    if initial != "interesting":
        for phase in ("search", "minimality", "final"):
            require(phases[phase] == 0,
                    f"initial_check={initial} forbids tests_by_phase.{phase}={phases[phase]}")
        require(not data["output_saved"],
                f"initial_check={initial} requires output_saved=false")
        require(data["minimality"] == "not_checked" and data["minimality_checked"] == 0,
                f"initial_check={initial} requires minimality=not_checked and minimality_checked=0")
        if initial in ("not_interesting", "unresolved"):
            rejected = "initial_not_interesting" if initial == "not_interesting" else "initial_unresolved"
            require(reason in (*exceptional, rejected),
                    f"initial_check={initial} permits only stop_reason={rejected}/interrupted/execution_error")
            require(data["launch_failures"] == 0,
                    f"initial_check={initial} forbids launch_failures after its successful initial start")
    if not data["output_saved"]:
        require(all(phases[phase] == 0 for phase in ("search", "minimality", "final")),
                "output_saved=false forbids search/minimality/final starts")
        require(final == "not_run", "output_saved=false requires final_revalidation=not_run")
        require(data["minimality"] == "not_checked",
                "output_saved=false requires minimality=not_checked")
    search = data["search_stop_reason"]
    if search == "completed":
        require(data["minimality"] in ("verified", "blocked_by_unresolved"),
                "search_stop_reason=completed requires minimality=verified/blocked_by_unresolved")
    elif search == "budget_exhausted":
        require(data["minimality"] in ("not_checked", "incomplete") and
                data["minimality_reason"] == "budget_exhausted",
                "search_stop_reason=budget_exhausted requires unfinished minimality "
                "and minimality_reason=budget_exhausted")
        require(data["tests_started"] == data["max_tests"] - 1 + phases["final"],
                "search_stop_reason=budget_exhausted requires "
                "tests_started=max_tests-1+tests_by_phase.final (reserved final start)")

    # invoke clears the previous status before even preparing a new call. It
    # publishes None for a timed-out wait, not the subsequent cleanup signal.
    # A known final verdict, or initial NI/U (no later invoke), determines the
    # last status. Initial I alone cannot: a later failed preparation clears it.
    codes = {"interesting": 0, "not_interesting": 1, "unresolved": 2}
    endpoint = ("final_revalidation", final) if final in codes else (
        ("initial_check", initial) if initial in ("not_interesting", "unresolved") else None
    )
    status, signal = data["last_exit_code"], data["last_signal"]
    if endpoint:
        field, verdict = endpoint
        if field == "final_revalidation":
            require(search in ("completed", "budget_exhausted"),
                    f"final_revalidation={verdict} requires "
                    "search_stop_reason=completed/budget_exhausted")
            for counter in ("oracle_errors", "launch_failures", "interrupted_tests"):
                require(data[counter] == 0,
                        f"final_revalidation={verdict} requires {counter}=0; "
                        "no recovery after a failed/cancelled judgment start")
        require(signal is None, f"{field}={verdict} requires last_signal=null, got {signal}")
        if verdict == "unresolved":
            require(status in (None, 2),
                    f"{field}=unresolved requires last_exit_code=2/null, got {status}")
            if status is None:
                require(data["timeouts"] > 0,
                        f"{field}=unresolved with last_exit_code=null requires timeouts>0")
        else:
            require(status == codes[verdict],
                    f"{field}={verdict} requires last_exit_code={codes[verdict]}, got {status}")
    if signal is not None or status not in (None, 0, 1, 2):
        require(reason in exceptional,
                f"last_signal={signal}, last_exit_code={status} require "
                f"stop_reason=execution_error/interrupted, got {reason}")
    # Do not require oracle_errors>0 for every execution_error, or infer a
    # terminal class from a status in an interrupted call: IO/cancellation can
    # happen after wait returns but before the status is classified.
    return errors


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
    checked = data["minimality_checked"]
    require(checked <= phases["minimality"],
            f"minimality_checked={checked} exceeds tests_by_phase.minimality="
            f"{phases['minimality']}; current-round checks require distinct actual starts")
    if minimality == "not_checked":
        require(checked == 0 and phases["minimality"] == 0,
                "minimality=not_checked requires minimality_checked=0 and "
                "tests_by_phase.minimality=0")
    if minimality in ("verified", "blocked_by_unresolved"):
        require(saved and data["minimality_checked"] == required,
                "completed minimality check lacks saved result or full progress")
        reason = ("unresolved_single_deletions" if minimality == "blocked_by_unresolved"
                  else "empty_result" if required == 0 else "all_single_deletions_not_interesting")
        require(data["minimality_reason"] == reason, "minimality reason mismatch")
    if minimality == "blocked_by_unresolved":
        require(data["had_unresolved"], "blocked minimality requires unresolved evidence")
        require(checked > 0, "minimality=blocked_by_unresolved requires minimality_checked>0; "
                "empty-result proof cannot be blocked by historical unresolved calls")
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
    # Initial/final observations and current-round singles refer to disjoint
    # actual calls. Error/interrupted states can occur before spawn or after a
    # verdict (e.g. diagnostic I/O failure); do not infer their terminal class.
    observed = {"interesting": 0, "not_interesting": 0, "unresolved": 0}
    evidence = {kind: [] for kind in observed}
    for phase, field in [("initial", "initial_check"), ("final", "final_revalidation")]:
        verdict = data[field]
        if verdict in observed:
            require(phases[phase] == 1,
                    f"{field}={verdict} requires tests_by_phase.{phase}=1")
            observed[verdict] += 1
            evidence[verdict].append(f"{field}={verdict}")
        elif verdict == "not_run":
            require(phases[phase] == 0,
                    f"{field}=not_run requires tests_by_phase.{phase}=0")
    if saved:
        require(data["initial_check"] == "interesting",
                "output_saved=true requires initial_check=interesting")
    lower = observed.copy()
    if saved and data["best_segments"] is not None and data["best_segments"] < original:
        lower["interesting"] += 1
        evidence["interesting"].append("best_segments < original_segments (saved improvement)")
    if minimality == "verified" and checked:
        lower["not_interesting"] += checked
        evidence["not_interesting"].append(f"minimality_checked={checked} with minimality=verified")
    elif minimality == "blocked_by_unresolved":
        lower["unresolved"] += 1
        evidence["unresolved"].append("minimality=blocked_by_unresolved (current-round witness)")
    for kind, minimum in lower.items():
        require(data[kind] >= minimum,
                f"{kind}={data[kind]} < {minimum} required by " + "; ".join(evidence[kind]))
    # Every accepted current-round single is NI or U; I would reset progress.
    # Partial/U rounds do not reveal the exact NI/U split. Reserve endpoints
    # first so their verdicts cannot also serve as deletion evidence.
    remaining = (data["not_interesting"] + data["unresolved"] -
                 observed["not_interesting"] - observed["unresolved"])
    require(remaining >= checked,
            f"not_interesting + unresolved after reserving initial_check/final_revalidation "
            f"observations = {remaining} < minimality_checked={checked}")
    if data["stop_reason"] != "execution_error":
        require(data["error"] is None, "non-error stop contains execution error")
    if data["stop_reason"] in ("completed", "budget_exhausted", "unresolved"):
        require(not data["interrupted"], "successful/partial completion cannot claim interruption")
    errors.extend(terminal_violations(data))
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
