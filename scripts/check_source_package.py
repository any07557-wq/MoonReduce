#!/usr/bin/env python3
"""Verify the committed source archive, then build and smoke-test its extraction."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile

import package_source

ROOT = Path(__file__).resolve().parents[1]


def run(command, cwd, expected=0, timeout=60):
    result = subprocess.run([str(arg) for arg in command], cwd=cwd, capture_output=True,
                            text=True, timeout=timeout)
    assert result.returncode == expected, (command, result.returncode, result.stdout, result.stderr)
    return result


def check(work, ref):
    commit, selected = package_source.snapshot(ref)
    command = [sys.executable, ROOT / "scripts/package_source.py"]
    first, second = work / "first", work / "second"
    run([*command, first, "--ref", commit], ROOT)
    run([*command, second, "--ref", commit], ROOT)
    archives = list(first.glob("*.tar.gz"))
    assert len(archives) == 1
    archive = archives[0]
    checksum = first / (archive.name + ".sha256")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    assert digest == hashlib.sha256((second / archive.name).read_bytes()).hexdigest()
    assert checksum.read_text() == f"{digest}  {archive.name}\n"
    run(["sha256sum", "--check", checksum.name], first)
    before = {path.name: path.read_bytes() for path in first.iterdir()}
    run([*command, first, "--ref", commit], ROOT, expected=1)
    assert before == {path.name: path.read_bytes() for path in first.iterdir()}
    run([*command, work / "bad", "--ref", "not-a-moonreduce-ref"], ROOT, expected=1)
    assert not (work / "bad").exists()
    for name in ["_build/cmd/tool.exe", "src/_build/core.mbt", "src/core/secrets.mbt",
                 "scripts/.env.py", "examples/.aws/config", "examples/results/run.py",
                 "docs/runtime-report.json", "scripts/logs/oracle.py", "tests/private.key",
                 "src/core/../credentials.mbt", "/tmp/src/a.mbt", "README.md\nsecret"]:
        assert not package_source.include_source(name), name
    extracted = work / "extracted"
    extracted.mkdir()
    prefix = archive.name.removesuffix(".tar.gz") + "/"
    with tarfile.open(archive) as source:
        files = {member.name.removeprefix(prefix) for member in source.getmembers() if member.isfile()}
        assert files == set(selected) | {"SOURCE_COMMIT"}
        assert all(member.isdir() or member.isfile() for member in source.getmembers())
        for name in ["README.md", "src/core/reducer.mbt", "tests/fixtures/reduce_oracle.py"]:
            expected = package_source.git("show", f"{commit}:{name}")
            assert source.extractfile(prefix + name).read() == expected
        source.extractall(extracted, filter="data")
    checkout = extracted / prefix[:-1]
    assert (checkout / "SOURCE_COMMIT").read_text().strip() == commit
    assert not (checkout / "_build").exists() and not (checkout / ".mooncakes").exists()
    # Fresh source/build products, with the already-verified SDK and registry cache.
    run(["moon", "build", "--target", "native", "--release", "--deny-warn"], checkout)
    fixture = checkout / "tests/fixtures/reduce_oracle.py"
    assert fixture.stat().st_mode & 0o111, "archive lost the committed executable mode"
    sample = work / "sample"
    sample.mkdir()
    original = b"noise\nBUG\nmore noise\n"
    source_file, output, report = sample / "failing.txt", sample / "reduced.txt", sample / "report.json"
    source_file.write_bytes(original)
    oracle = ["/usr/bin/python3", fixture, "contains", "BUG"]
    binary = checkout / "_build/native/release/build/cmd/moonreduce/moonreduce.exe"
    run([*oracle, source_file], checkout)
    run([binary, source_file, "--output", output, "--report", report,
         "--timeout-ms", "2000", "--max-tests", "1000", "--", *oracle], checkout)
    run([*oracle, output], checkout)
    data = json.loads(report.read_text())
    assert source_file.read_bytes() == original and output.read_bytes() == b"BUG\n"
    assert data["exit_code"] == 0 and data["final_revalidation"] == "interesting"
    assert data["minimality"] == "verified" and data["original_bytes"] == len(original)
    assert data["best_bytes"] == 4 and data["tests_started"] <= data["max_tests"]
    # An independent deletion of the one remaining segment must not reproduce.
    empty = sample / "deleted.txt"
    empty.write_bytes(b"")
    run([*oracle, empty], checkout, expected=1)
    print(f"PASS source {commit}: deterministic archive, SHA-256, committed contents, "
          f"exclusions/refusal, fresh Release build; {len(original)} -> 4 bytes, "
          f"{data['tests_started']} starts, independent I and deletion NI")
    print(f"Local artifacts: {archive}\nSHA-256: {digest}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", default="HEAD")
    parser.add_argument("--work-dir", type=Path, help="new empty directory to retain local evidence")
    args = parser.parse_args()
    if args.work_dir:
        args.work_dir.mkdir(parents=True, exist_ok=False)
        check(args.work_dir.resolve(), args.ref)
    else:
        with tempfile.TemporaryDirectory(prefix="moonreduce-source-check-") as directory:
            check(Path(directory), args.ref)


if __name__ == "__main__":
    main()
