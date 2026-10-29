#!/usr/bin/env python3
"""Exercise real diagnostic exit statuses without modifying the host SDK."""
import os
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
DOCTOR = ROOT / "scripts/doctor.py"


def run(env):
    return subprocess.run([sys.executable, "-B", str(DOCTOR)], env=env,
                          capture_output=True, text=True, timeout=30)


def main():
    healthy = run(os.environ.copy())
    assert healthy.returncode == 0, healthy.stdout + healthy.stderr
    assert "只读检查" in healthy.stdout and "PASS async" in healthy.stdout
    with tempfile.TemporaryDirectory(prefix="moonreduce doctor ") as directory:
        work = Path(directory)
        empty_path = work / "empty"
        empty_path.mkdir()
        absent = run({**os.environ, "PATH": str(empty_path)})
        assert absent.returncode == 1 and "FAIL Native C" in absent.stdout
        assert "FAIL moon:" in absent.stdout
        selected = work / "selected"
        selected.mkdir()
        for name in ["moon", "moonc", "moonrun", "cc"]:
            (selected / name).symlink_to(Path(shutil.which(name)).resolve())
        optional = run({**os.environ, "PATH": str(selected)})
        assert optional.returncode == 0 and "WARN C++（可选）" in optional.stdout
        sdk = work / "sdk"
        (sdk / "bin").mkdir(parents=True)
        blocked = sdk / "bin/moon"
        blocked.write_bytes(b"SDK execution-permission fixture\n")
        blocked.chmod(0o644)
        before = blocked.stat().st_mode
        denied = run({**os.environ, "MOON_HOME": str(sdk), "PATH": str(empty_path)})
        assert denied.returncode == 1 and "没有执行权限" in denied.stdout
        assert "先运行 moon update" in denied.stdout
        assert blocked.stat().st_mode == before and not (sdk / "registry").exists()
        assert sorted(path.relative_to(sdk).as_posix() for path in sdk.rglob("*")) == ["bin", "bin/moon"]
    print("PASS doctor: real environment=0; missing required=1; optional C++ absent=0; unexecutable SDK=1; no repair side effects")


if __name__ == "__main__":
    main()
