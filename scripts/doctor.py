#!/usr/bin/env python3
"""Read-only checks for the verified MoonReduce development environment."""
import hashlib
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
LOCKED = {
    "moon": "0.1.20261012 (748b63c",
    "moonc": "v0.10.15+943464bfa",
    "moonrun": "0.1.20261012 (748b63c",
}
ASYNC_SHA256 = "2ffdb85cb229cfe9219161a7f2b959215a79a0d75b7e642cb346713f168a1457"


def main():
    failures = 0
    warnings = 0

    def note(level, name, message):
        nonlocal failures, warnings
        failures += level == "FAIL"
        warnings += level == "WARN"
        print(f"{level} {name}: {message}")

    def command(name, argv, expected=None, failure_level="FAIL"):
        try:
            result = subprocess.run(argv, capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.TimeoutExpired) as error:
            note(failure_level, name, str(error))
            return
        output = (result.stdout + result.stderr).strip()
        if result.returncode != 0 or expected and expected not in output:
            note(failure_level, name, f"exit={result.returncode}; {output[:512]}; 锁定版本={expected}")
        else:
            note("PASS", name, output.splitlines()[0] if output else "命令可用")

    system = f"{platform.system()} {platform.machine()} {platform.release()}"
    if platform.system() != "Linux" or platform.machine() != "x86_64":
        note("FAIL", "platform", system + "; Native CLI 只在 WSL2 Linux x86_64 验证")
    else:
        level = "PASS" if "microsoft" in platform.release().lower() else "WARN"
        note(level, "platform", system + "; 其他发行版／内核组合未验证")

    moon = shutil.which("moon")
    sdk = Path(os.environ["MOON_HOME"]) if os.environ.get("MOON_HOME") else (
        Path(moon).resolve().parent.parent if moon else Path.home() / ".moon"
    )
    for name, version in LOCKED.items():
        executable = shutil.which(name)
        if executable:
            argv = [executable, "version", "--all"] if name == "moon" else [
                executable, "-v" if name == "moonc" else "--version",
            ]
            command(name, argv,
                    version)
        else:
            candidate = sdk / "bin" / name
            reason = "SDK 文件存在但没有执行权限；按 README chmod +x" if (
                candidate.is_file() and not os.access(candidate, os.X_OK)
            ) else "不在 PATH；按 README 安装固定 SDK 并设置 MOON_HOME/PATH"
            note("FAIL", name, reason)
    core = sdk / "lib/core/moon.mod"
    try:
        matched = re.search(r'^version\s*=\s*"([^"]+)"', core.read_text(), re.M)
        version = matched.group(1) if matched else "unknown"
        note("PASS" if version == "0.10.15+943464bfa" else "FAIL", "core", version)
    except OSError as error:
        note("FAIL", "core", f"{error}; SDK 不完整，参照 README 重新解包到新目录")
    for target, level in [("native", "FAIL"), ("wasm-gc", "WARN")]:
        bundle = sdk / f"lib/core/_build/{target}/release/bundle/prelude/prelude.mi"
        note("PASS" if bundle.is_file() else level, f"core/{target}",
             str(bundle) if bundle.is_file() else f"未 bundle；参照 README 的 bundle --target {target}")
    tcc = sdk / "bin/internal/tcc"
    note("PASS" if os.access(tcc, os.X_OK) else "FAIL", "SDK/internal/tcc",
         str(tcc) if os.access(tcc, os.X_OK) else "缺失或不可执行；按 README 解包／补执行权限")

    if shutil.which("cc"):
        command("Native C / 算法示例", ["cc", "--version"])
    else:
        note("FAIL", "Native C / 算法示例", "缺少 cc；需要系统 C 编译器，已验证 GCC 15.2.0")
    if shutil.which("c++"):
        command("C++（可选）", ["c++", "--version"], failure_level="WARN")
    else:
        note("WARN", "C++（可选）", "未找到 c++；现有算法示例是 C，不要求 C++，自定义 C++ 目标才需要")
    note("PASS" if sys.version_info[:3] == (3, 14, 4) else "WARN", "Python",
         f"{platform.python_version()} ({sys.executable}); 已验证 3.14.4，CLI 本身不依赖 Python")
    for path, flag in [("/usr/bin/setsid", "--version"), ("/usr/bin/kill", "--version")]:
        if os.access(path, os.X_OK):
            command(path, [path, flag])
        else:
            note("FAIL", path, "缺失或不可执行；CLI 需要此固定系统路径")
    if os.access("/usr/bin/test", os.X_OK):
        command("/usr/bin/test -ef", ["/usr/bin/test", str(core), "-ef", str(core)])
    else:
        note("FAIL", "/usr/bin/test", "缺少可执行的文件身份检查命令")
    note("PASS" if os.access("/usr/bin/sleep", os.X_OK) else "WARN", "probe/sleep",
         "探针需要 /usr/bin/sleep，CLI 不需要")
    index = sdk / "registry/index"
    note("PASS" if index.is_dir() else "FAIL", "registry index",
         str(index) if index.is_dir() else "尚未初始化；先运行 moon update，不是 moon upgrade")
    dependency = ROOT / ".mooncakes/moonbitlang/async/moon.mod"
    try:
        manifest = dependency.read_text()
        note("PASS" if re.search(r'^version\s*=\s*"0\.22\.4"', manifest, re.M) else "FAIL",
             "async", "已解析依赖必须为 0.22.4")
    except OSError:
        note("FAIL", "async", "尚未解析／下载；先 moon update，再 moon check --target native --deny-warn")
    archive = sdk / "registry/cache/moonbitlang/async/0.22.4.zip"
    if archive.is_file():
        try:
            with archive.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            note("PASS" if digest == ASYNC_SHA256 else "FAIL", "async archive SHA-256", digest)
        except OSError as error:
            note("FAIL", "async archive SHA-256", str(error))
    else:
        note("WARN", "async archive SHA-256", "没有下载归档可核对；不伪称哈希已通过")
    print(f"诊断结束：{failures} 个失败，{warnings} 个提示。只读检查，不安装、不更新、不改权限；不代替测试验收。")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
