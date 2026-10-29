#!/usr/bin/env python3
"""Artificial defect: POP on an empty stack should be a no-op, but asserts."""
from pathlib import Path
import re
import sys


def main():
    raw = Path(sys.argv[-1]).read_bytes()
    if len(raw) > 16384:
        print("MOONREDUCE_INVALID_INPUT", file=sys.stderr)
        return 2
    # Validate the whole input before executing; a later invalid line is not
    # silently hidden by an earlier artificial assertion.
    commands = raw.split(b"\n")
    if commands[-1] == b"":
        commands.pop()
    if any(line not in {b"POP", b"NOP"} and not re.fullmatch(rb"PUSH -?[0-9]{1,4}", line)
           for line in commands):
        print("MOONREDUCE_INVALID_INPUT", file=sys.stderr)
        return 2
    stack = []
    for line in commands:
        if line.startswith(b"PUSH "):
            stack.append(int(line[5:]))
        elif line == b"POP":
            if not stack:
                print("MOONREDUCE_EXAMPLE_ASSERT_EMPTY_POP", file=sys.stderr)
                return 42
            stack.pop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
