#!/usr/bin/env python3
"""Independent output/1-minimal audit: never imports oracle or reducer code."""
import argparse
import json
from pathlib import Path
import re
import subprocess


def run_target(path, values):
    payload = f"{len(values)}\n" + " ".join(str(value) for value in values) + "\n"
    result = subprocess.run(
        [str(path.resolve())], input=payload, capture_output=True, text=True,
        timeout=3, check=True,
    )
    assert re.fullmatch(r"(0|[1-9][0-9]*)\n", result.stdout), result.stdout
    return int(result.stdout)


def check_targets(reference, buggy, values):
    expected = 0
    for start in range(len(values)):
        subtotal = 0
        for value in values[start:]:
            subtotal += value
            expected = max(expected, subtotal)
    actual_reference = run_target(reference, values)
    assert actual_reference == expected, (values, actual_reference, expected)
    actual_buggy = run_target(buggy, values)
    return actual_reference, actual_buggy


def audit(reference, buggy, result):
    raw = result.read_bytes()
    # Generated workflow values use one canonical integer per LF segment.
    chunks = raw.split(b"\n")
    parts = [chunk + b"\n" for chunk in chunks[:-1]]
    if chunks[-1]:
        parts.append(chunks[-1])
    values = [int(part.decode("ascii")) for part in parts]
    reference_value, buggy_value = check_targets(reference, buggy, values)
    assert reference_value > buggy_value, (reference_value, buggy_value)
    deletions = []
    for removed in range(len(values)):
        remaining = values[:removed] + values[removed + 1:]
        expected, actual = check_targets(reference, buggy, remaining)
        assert expected == actual, (removed, expected, actual)
        deletions.append({"removed_index": removed, "reference": expected, "buggy": actual})
    return {
        "reference": reference_value, "buggy": buggy_value,
        "single_deletions_checked": len(values),
        "all_single_deletions_not_interesting": True,
        "reference_cross_checked_by_exhaustive_subarrays": True,
        "deletion_results": deletions,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--buggy", required=True, type=Path)
    parser.add_argument("result", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.reference, args.buggy, args.result), sort_keys=True))


if __name__ == "__main__":
    main()
