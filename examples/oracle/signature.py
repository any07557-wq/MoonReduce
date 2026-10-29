#!/usr/bin/env python3
"""Map one target's explicit exit status and complete stderr signature to 0/1/2.

MoonReduce appends the candidate path after COMMAND [ARGS...] below.
This adapter never reduces inputs or invokes a shell.
"""
import argparse
from pathlib import Path
import subprocess
import sys
import tempfile


class ExecutionFailure(Exception):
    pass


class Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ExecutionFailure(message)


def main():
    try:
        args = sys.argv[1:]
        if "--" not in args:
            raise ExecutionFailure("expected options -- COMMAND [ARGS...] ABSOLUTE_CANDIDATE")
        separator = args.index("--")
        parser = Parser(description=__doc__)
        parser.add_argument("--failure-exit", required=True, type=int)
        parser.add_argument("--signature", required=True)
        parser.add_argument("--invalid-exit", type=int, default=2)
        parser.add_argument("--invalid-signature", default="MOONREDUCE_INVALID_INPUT")
        parser.add_argument("--target-timeout-ms", type=int, default=1000)
        options = parser.parse_args(args[:separator])
        command = args[separator + 1:]
        if len(command) < 2 or not command[0]:
            raise ExecutionFailure("COMMAND and candidate are required")
        candidate = Path(command[-1])
        if not candidate.is_absolute() or not candidate.is_file():
            raise ExecutionFailure("candidate must be an existing absolute file path")
        if not 0 <= options.failure_exit <= 255 or not 1 <= options.invalid_exit <= 255:
            raise ExecutionFailure("exit codes must be normal exit statuses; invalid-exit cannot be 0")
        if options.failure_exit == options.invalid_exit:
            raise ExecutionFailure("failure-exit and invalid-exit must differ")
        signature = options.signature.encode("utf-8")
        invalid_signature = options.invalid_signature.encode("utf-8")
        for literal in [signature, invalid_signature]:
            if not literal or len(literal) > 512 or b"\n" in literal or b"\r" in literal:
                raise ExecutionFailure("signatures must be nonempty literal lines, at most 512 bytes")
        if not 1 <= options.target_timeout_ms <= 2147483647:
            raise ExecutionFailure("target-timeout-ms must be in 1..2147483647")
        with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
            result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=stdout,
                                    stderr=stderr, timeout=options.target_timeout_ms / 1000)
            stderr.seek(0)
            prefix = stderr.read(4096)
            truncated = stderr.seek(0, 2) > len(prefix)
        status = result.returncode
        # A truncated final line must not be mistaken for a complete signature.
        lines = prefix.split(b"\n")
        if truncated:
            lines.pop()
        lines = [line.removesuffix(b"\r") for line in lines]
        if status < 0:
            raise ExecutionFailure(f"target died by signal {-status}; no implicit crash evidence")
        if status == options.invalid_exit:
            if invalid_signature in lines:
                print("target rejected candidate syntax/domain", file=sys.stderr)
                return 2
            raise ExecutionFailure("invalid-exit without the documented invalid-input signature")
        if status not in {0, options.failure_exit}:
            raise ExecutionFailure(f"unexpected target exit {status}")
        if status != options.failure_exit:
            return 1
        if signature in lines:
            return 0
        if truncated:
            print("stderr exceeds diagnostic bound; absence of signature is unresolved", file=sys.stderr)
            return 2
        return 1
    except subprocess.TimeoutExpired:
        print("target timeout: no target-behavior verdict", file=sys.stderr)
        return 2
    except (OSError, ExecutionFailure) as error:
        print(f"oracle execution error: {error}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
