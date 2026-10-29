#!/usr/bin/env python3
"""Execute the generic signature adapter against positive and failure cases."""
import json
from pathlib import Path
import signal
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "examples/oracle/signature.py"
TARGET = ROOT / "examples/oracle/assertion_target.py"
SIGNATURE = "MOONREDUCE_EXAMPLE_ASSERT_EMPTY_POP"


def call(argv, expected):
    result = subprocess.run([str(arg) for arg in argv], cwd=ROOT, capture_output=True,
                            text=True, timeout=8)
    assert result.returncode == expected, (argv, result.returncode, result.stdout, result.stderr)
    return result


def main():
    base = [sys.executable, TEMPLATE, "--failure-exit", "42", "--signature", SIGNATURE]
    with tempfile.TemporaryDirectory(prefix="moonreduce oracle guide ") as directory:
        work = Path(directory)
        source = work / "candidate file"
        for data, expected in [(b"NOP\n", 1), (b"", 1), (b"POP\n", 0),
                               (b"PUSH 7\nPOP\n", 1), (b"POP\ninvalid\n", 2), (b"\xff\n", 2)]:
            source.write_bytes(data)
            call([*base, "--", sys.executable, TARGET, source], expected)
        source.write_bytes(b"POP\n")
        for name, body, expected in [
            ("no-signature", "raise SystemExit(42)", 1),
            ("wrong-signature", "print('other assertion',file=sys.stderr); raise SystemExit(42)", 1),
            ("unknown-exit", f"print({SIGNATURE!r},file=sys.stderr); raise SystemExit(7)", 3),
            ("crash", f"print({SIGNATURE!r},file=sys.stderr,flush=True); os.kill(os.getpid(),signal.SIGKILL)", 3),
            ("invalid-unmarked", f"print({SIGNATURE!r},file=sys.stderr); raise SystemExit(2)", 3),
            ("invalid-marked", "print('MOONREDUCE_INVALID_INPUT',file=sys.stderr); raise SystemExit(2)", 2),
            ("stdout-only", f"print({SIGNATURE!r}); raise SystemExit(42)", 1),
            ("truncated", "sys.stderr.write('x'*65536); raise SystemExit(42)", 2),
            ("partial-line", f"sys.stderr.write('x'*(4095-len({SIGNATURE!r}))+'\\n'+{SIGNATURE!r}+'suffix'); raise SystemExit(42)", 2),
            ("large-with-signature", f"sys.stderr.write({SIGNATURE!r}+'\\n'+'x'*65536); raise SystemExit(42)", 0),
            ("timeout", "time.sleep(5)", 2),
        ]:
            target = work / name
            target.write_text("import os,signal,sys,time\n" + body + "\n")
            call([*base, "--target-timeout-ms", "200", "--", sys.executable, target, source], expected)
        call([*base, "--", work / "missing command", source], 3)
        call([*base, "--", sys.executable, work / "missing script.py", source], 3)
        call([*base, "--invalid-exit", "42", "--", sys.executable, TARGET, source], 3)
        call([sys.executable, TEMPLATE], 3)
        literal = work / "argv target.py"
        literal.write_text(
            "import sys\n"
            "assert sys.argv[1:3] == ['two words', 'literal;$(false)*']\n"
            f"print({SIGNATURE!r},file=sys.stderr)\nraise SystemExit(42)\n"
        )
        call([*base, "--", sys.executable, literal, "two words", "literal;$(false)*", source], 0)
        binary = ROOT / "_build/native/debug/build/cmd/moonreduce/moonreduce.exe"
        if not binary.exists():
            call(["moon", "build", "--target", "native", "--deny-warn"], 0)
        original = b"PUSH 7\nNOP\nPOP\nPOP\nNOP\n"
        source.write_bytes(original)
        output, report = work / "reduced", work / "report.json"
        call([binary, source, "--output", output, "--report", report, "--timeout-ms", "3000",
              "--", *base, "--", sys.executable, TARGET], 0)
        data = json.loads(report.read_text())
        assert output.read_bytes() == b"POP\n" and source.read_bytes() == original
        assert data["final_revalidation"] == "interesting" and data["minimality"] == "verified"
        call([*base, "--", sys.executable, TARGET, output], 0)
    print("PASS signature template: 0/1/2/3, exact signature/status, invalid input, crash/exec/timeout, bounded logs, literal argv and real CLI reduction")


if __name__ == "__main__":
    main()
