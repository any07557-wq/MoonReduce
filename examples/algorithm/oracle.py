#!/usr/bin/env python3
"""Adapt integer lines to precompiled programs. Contains no reduction logic.

0: both complete normally and reference > buggy (the selected discrepancy).
1: both complete normally and outputs are equal.
2: invalid candidate format/domain.
3: execution/configuration/protocol error, never an interesting discrepancy.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile


class InvalidCandidate(Exception):
    pass


class ExecutionFailure(Exception):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ExecutionFailure(message)


def candidate_values(path):
    with path.open("rb") as source:
        data = source.read(32769)
    if len(data) > 32768:
        raise InvalidCandidate("candidate exceeds 4096 bounded integer segments")
    if not data:
        return []
    lines = data.split(b"\n")
    if lines[-1] == b"":
        lines.pop()
    if len(lines) > 4096:
        raise InvalidCandidate("at most 4096 integer segments")
    values = []
    for line in lines:
        if line.endswith(b"\r"):
            line = line[:-1]
        if len(line) > 6 or not re.fullmatch(rb"[+-]?[0-9]+", line):
            raise InvalidCandidate("each LF segment must be an integer; no blank lines")
        value = int(line)
        if not -1000 <= value <= 1000:
            raise InvalidCandidate("integer outside -1000..1000")
        values.append(value)
    return values


def execute(executable, payload, upper_bound):
    # stdout/stderr are bounded when inspected, even for a broken replacement
    # program used in regression tests. The example's C programs spawn no child.
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        result = subprocess.run(
            [str(executable)], input=payload, stdout=stdout, stderr=stderr,
            timeout=1, check=False,
        )
        stdout.seek(0)
        output = stdout.read(4097)
        stderr.seek(0)
        diagnostic = stderr.read(1024).decode("utf-8", errors="replace")
    if result.returncode != 0:
        raise ExecutionFailure(f"target {executable} exited {result.returncode}: {diagnostic}")
    if not re.fullmatch(rb"(0|[1-9][0-9]{0,6})\n", output):
        raise ExecutionFailure(f"target {executable} did not produce one canonical answer")
    answer = int(output)
    if answer > upper_bound:
        raise ExecutionFailure(f"target {executable} answer outside valid range")
    return answer


def main():
    try:
        parser = Parser(description=__doc__)
        parser.add_argument("--reference", required=True, type=Path)
        parser.add_argument("--buggy", required=True, type=Path)
        parser.add_argument("candidate", type=Path)
        args = parser.parse_args()
        if not args.candidate.is_absolute():
            raise ExecutionFailure("candidate path must be absolute")
        values = candidate_values(args.candidate)
        payload = (f"{len(values)}\n" + " ".join(map(str, values)) + "\n").encode("ascii")
        upper_bound = sum(max(0, value) for value in values)
        reference = execute(args.reference.resolve(), payload, upper_bound)
        buggy = execute(args.buggy.resolve(), payload, upper_bound)
        print(f"reference={reference}; buggy={buggy}; signature=reference_greater")
        if reference < buggy:
            raise ExecutionFailure("unexpected opposite discrepancy")
        verdict = 0 if reference > buggy else 1
        if trace := os.environ.get("MOONREDUCE_EXAMPLE_CALL_LOG"):
            with Path(trace).open("a") as log:
                log.write(json.dumps({
                    "candidate": str(args.candidate), "n": len(values),
                    "reference": reference, "buggy": buggy, "verdict": verdict,
                }) + "\n")
        return verdict
    except InvalidCandidate as error:
        print(f"invalid candidate: {error}", file=sys.stderr)
        return 2
    except (OSError, ExecutionFailure, subprocess.TimeoutExpired) as error:
        print(f"oracle execution error: {error}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
