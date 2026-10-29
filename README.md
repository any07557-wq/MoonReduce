# MoonReduce

MoonReduce 面向已有失败输入的算法对拍、解析器和命令行开发者，按行删除文件内容并输出经复验的较小反例，同时提供纯 MoonBit 缩减核心。

**Ready for local v0.1 review**：已用干净 Git 源码、全新固定 SDK 和空注册表完成构建、测试、CLI 案例及库消费。验证由实现者在同一台 WSL2 主机执行，未冒称另一位用户或另一台机器试用。案例为人工缺陷，没有外部采用，差异化仍有限；工程交付验收结论不代表月赛审核结果。工具版本保留 0.1.0-dev 表示尚未发布，模块 0.1.0 是本地源码元数据。

下面是调用形式；未安装到 PATH 时，把 moonreduce 换为构建产物 `_build/native/release/build/cmd/moonreduce/moonreduce.exe`。本项目尚未发布安装包。

```sh
moonreduce failing.txt --output reduced.txt --report report.json \
  --timeout-ms 2000 --max-tests 1000 -- ./oracle.py 'fixed argument'
```

INPUT、--output、--report 和 -- 后的命令必填。判断程序收到其固定参数加上**最后一个参数：候选文件的绝对路径**，工作目录保持不变，stdin 为 /dev/null。通过参数数组启动，不隐式运行 shell。oracle 正常退出 0/1/2 分别代表 Interesting / NotInteresting / Unresolved；超时也为 Unresolved，其他退出码、oracle 自身崩溃或启动失败属于执行错误。判断程序须只读候选，用错误签名等定义“同一个问题”。

被测程序的崩溃应由判断脚本识别特定签名后转换成相应判定；不能将任意非零退出或判断程序自身的崩溃当作成功复现。

编写新判断程序可从[可运行的错误签名模板与正反例](examples/oracle/README.md)开始：明确目标退出状态、完整 stderr 签名和独立的无效输入签名，防止把缺失脚本的退出 2 当成格式无效。它复用外部命令执行，不实现缩减算法。

文件按 LF 字节切分，保留 CRLF、空白、编码字节和末尾换行原状。原始输入不修改，已有输出／报告一律拒绝覆盖，也会拒绝符号链接、硬链接和同一路径别名。每次改进先完整写入临时文件，再原子发布；首次发布不覆盖并发创建的目标，不留下空占位文件。最终直接对输出路径再次实际调用 oracle。

--timeout-ms 默认 2000，范围 1–2147483647；--max-tests 默认 1000，范围 2–2147483647，包含初始检查、搜索、单删检查和最终复验，并预留最后一次调用。没有缓存。

例如 max-tests=2 时，非空输入仅做初始检查和输出复验，不能声称 1-minimal；预算刚好足以完成全部检查则可以返回 0。实际次数统计成功启动的 setsid 判断启动器，包含后续 exec 失败；启动器自身无法启动另记 launch_failures，kill 等辅助调用不计入判断预算。

**1-minimal** 仅指相对于确定 oracle、当前 LF 行粒度，逐个删除结果中的任意一个段都明确得到 NotInteresting；空结果的删除条件为空真。它不是全局最短或最少字节。最终一轮单删含 Unresolved 就不标 verified，预算中断只交付当前已知结果。历史 Unresolved 单独记录；后来取得完整明确证据时可以 verified。最终输出实际复验和这些单删证据分别报告，任何最终 NI/U/错误都不能返回成功。

| 工具退出码 | 含义（与 oracle 退出码分开） |
| --- | --- |
| 0 | 输出复验 Interesting 且行粒度 1-minimal 已验证 |
| 1 | 输出复验 Interesting，但预算或 Unresolved 阻止完整最小性证明 |
| 2 | 参数或输出冲突等用法错误 |
| 3 | 初始输入不满足条件或无法判断，未生成反例输出 |
| 4 | 执行错误或输出复验失败／无法判断 |
| 130 | 中断；保留已知结果，报告未完成的验证 |

## 已验证的具体用法

| 场景 | 实测结果与入口 |
| --- | --- |
| 算法对拍：删除整数段，由 oracle 重建 n 和数组，运行两个提前编译的实现 | [人工最大子段和缺陷](examples/algorithm/README.md)：96 段／310 字节 → 3 段／9 字节；98 次 CLI 判断，最终答案 33/19；外部逐删 3 次均 NotInteresting |
| MoonBit 类型集成：直接传业务操作与判定回调 | [独立账本消费工程](examples/moonbit-consumer/README.md)：8 个 Entry → 2 个，23 次回调；复用 Credit/Debit/Reset 和错误分类，本地依赖公开核心，不复制源码或依赖作者构建缓存 |

这支持了“已有失败输入可以走完整调试闭环”和“MoonBit 调用者可以直接复用类型／谓词”两条采用理由。QuickCheck、Picire、Lithium 已有相近能力；[任务比较与证据边界](examples/README.md)明确列出剩余差异。没有测量更快、更轻、更易用，也没有证明真实用户迁移或采用，参赛差异化仍有限。

## 实测环境与构建

本次支持与实测范围为 **WSL2 内 Ubuntu 26.04、Linux x86_64 Native**（内核 `6.18.33.2-microsoft-standard-WSL2`）。普通非 WSL Linux、其他发行版、ARM、macOS、Windows 原生均未验证，不列为本次已验证平台。组合固定为：

- `moon 0.1.20261012 (748b63c)`，`moonc v0.10.15+943464bfa`，随工具链的 core 同版本。
- `moonbitlang/async@0.22.4`，在 [moon.mod](moon.mod) 精确声明；无其他第三方 MoonBit 依赖。
- GCC 15.2.0、glibc 2.43；运行组管理依赖 `/usr/bin/setsid`（util-linux 2.41.3）和 `/usr/bin/kill`（procps-ng 4.0.4）；文件身份检查使用 `/usr/bin/test -ef`（本机 uutils coreutils 0.8.0）。不依赖 GNU timeout。
- 探针另用 `/usr/bin/python3`（本机 3.14.4）和 `/usr/bin/sleep`；故障矩阵需要普通用户权限及支持 LD_PRELOAD 的 C 编译器。CLI 本身不依赖 Python，示例 oracle 使用 Python。

在仓库根目录执行：

```sh
moon version --all
moon update
moon check --target native --deny-warn
moon build --target native --deny-warn
moon run src/cmd/moonreduce --target native -- --help
moon test src/core --target native --deny-warn
moon test src/core --target native --release --deny-warn
python3 scripts/check_stage0.py
python3 scripts/check_stage2.py
python3 scripts/check_stage3.py
python3 scripts/check_stage4.py
```

首次使用空注册表时必须先 moon update 初始化索引；这是阶段 5 用新 SDK 实测发现并补齐的步骤，不是升级依赖。随后 check/build 自动获取已声明的 async@0.22.4，不需要 moon upgrade。依赖下载归档 SHA-256 为 2ffdb85cb229cfe9219161a7f2b959215a79a0d75b7e642cb346713f168a1457。

环境不明时可先运行 `python3 scripts/doctor.py`。它只读检查实际 moon／moonc／moonrun 与锁定版本、core bundle、async 版本／归档哈希、Native C 编译器及必需系统路径，并解释缺执行权限、PATH 或首次索引初始化问题；不会安装、联网更新或改权限。返回 0 表示必要检查通过，1 表示缺失／不匹配；WARN 不扩展支持平台，也不代替测试。Python 供示例／验证使用；当前算法目标是 C，C++ 仅作为可选诊断。诊断自身的正常／缺依赖回归为 `python3 scripts/check_doctor.py`。

核心测试独立重建子序列、重新判断结果并逐个删除元素复查，枚举小规模布尔／三态谓词；Debug 和 Release 使用同一套检查。也可执行 `moon test src/core --target wasm-gc --deny-warn`；这不代表 Native CLI 已跨平台验证。当前没有云 CI，云端执行未验证；以上本地固定版本命令已实跑。

阶段 0 探针脚本核对工具链与 async 版本，执行 Native 字节/进程探针、纯核心 Wasm 检查、超时树清理、外部 SIGINT 和格式检查。成功末行是 `Stage 0 acceptance probes passed...`；临时候选和日志在结束时删除。也可单独运行 `moon run src/probe --target native`，但它不包含外部 SIGINT 验收。

阶段 3 脚本通过外部 libc 启动计数器、真实权限失败和测试专用 LD_PRELOAD 故障注入验证报告；测试库只编译到临时目录，不进入 CLI，也不增加 CLI 运行依赖。脚本为每次调用设置看门狗，覆盖写到一半后 ENOSPC、保存过程中 SIGINT、强制终止子进程和关闭摘要管道。Release 矩阵可运行：

```sh
moon build --target native --release --deny-warn
python3 scripts/check_stage2.py _build/native/release/build/cmd/moonreduce/moonreduce.exe
python3 scripts/check_stage3.py _build/native/release/build/cmd/moonreduce/moonreduce.exe
python3 scripts/check_stage4.py _build/native/release/build/cmd/moonreduce/moonreduce.exe
```

## 已实跑的构建和缩减示例

下面用人工 BUG 标记保留基础 CLI 回归，不是生产 bug，也不承担算法调试案例的论证；完整案例见上面的 examples。构建后运行的 Native 文件名由 MoonBit 生成为 moonreduce.exe：

```sh
moon build --target native --release --deny-warn
moonreduce_demo_dir="$(mktemp -d)"
printf 'noise\nBUG\nmore noise\n' > "$moonreduce_demo_dir/failing.txt"
_build/native/release/build/cmd/moonreduce/moonreduce.exe \
  "$moonreduce_demo_dir/failing.txt" \
  --output "$moonreduce_demo_dir/reduced.txt" \
  --report "$moonreduce_demo_dir/report.json" \
  --timeout-ms 2000 --max-tests 1000 -- \
  /usr/bin/python3 tests/fixtures/reduce_oracle.py contains BUG
/usr/bin/python3 tests/fixtures/reduce_oracle.py contains BUG "$moonreduce_demo_dir/reduced.txt"
cat "$moonreduce_demo_dir/reduced.txt"
```

结果为 BUG 加原有 LF：21 字节缩到 4 字节，CLI 最终复验及单删验证通过；随后独立运行 oracle 也退出 0。示例目录由 mktemp 创建，便于检查输出和 JSON；重复运行应使用新输出路径。

每次 oracle 的候选和日志在私有临时目录中，stdout/stderr 直接写文件，诊断每流最多读 4096 原始字节并以 UTF-8 容错显示，完成后删除完整临时日志；不设日志磁盘配额。每流 32 MiB 输出已实测通过。超时／Ctrl-C 先发进程组 TERM，100ms 后需要时发 KILL；组长已退出也清理其后代，辅助 kill 启动失败会尝试 async 强制终止后备并报错。真实树和忽略 TERM 的子进程都以 /proc PID 消失验证。直接判断进程由工具等待，强制终止后孤儿后代的回收依赖实测环境的 init/reaper。

初始拒绝不生成反例文件。搜索或保存失败、中断时保留最后一次成功保存的 Interesting 文件，但不额外启动最终复验。JSON 的 final_revalidation 和 minimality 分别记录目标行为与单删证据；result_status=previously_interesting、only_previously_observed_interesting=true 表示文件仅曾被观察为 Interesting，不能当作本次已复验的反例。最终复验为 NI/U/异常时返回 4，即使此前最小性检查完整，也不输出成功结论。

报告包含实际启动数、四阶段分项、三态／异常／中断分类、超时数、字节／行段变化、停止原因、最小性未验证原因及自身 exit_code。参数／路径预检和初始读文件错误仅写 stderr，不创建 JSON；报告写入失败也以 stderr 和退出码 4 明示，不留下空报告或宣称报告已保存。输出与报告分别原子写入，不是跨文件事务，不保证断电持久化。工具不提供沙箱，不保证恶意脱离进程组的程序或 SIGKILL 后的清理。

## 实际 JSON 报告与解释

报告的机器可检验契约见 [JSON Schema 与跨字段检查](docs/report-contract.md)。可运行 `python3 scripts/validate_report.py docs/report.example.json`，或传入自己的报告路径；该开发工具使用 jsonschema 4.19.2，不增加 CLI 运行依赖。真实边界报告回归为 `python3 scripts/check_report_contract.py`。

[完整实录](docs/report.example.json)来自阶段 5 干净源码与新 SDK 上的算法对拍运行，只做 JSON 缩进，不改写字段；其中临时绝对路径和 elapsed_ms 属于那一次运行，重新运行会不同。以下为字段节选：

```json
{
  "tool_version": "0.1.0-dev",
  "original_bytes": 310,
  "original_segments": 96,
  "best_bytes": 9,
  "best_segments": 3,
  "stop_reason": "completed",
  "exit_code": 0,
  "final_revalidation": "interesting",
  "minimality": "verified",
  "minimality_checked": 3,
  "minimality_required": 3,
  "tests_started": 98,
  "tests_by_phase": {"initial": 1, "search": 93, "minimality": 3, "final": 1},
  "result_status": "revalidated_interesting",
  "only_previously_observed_interesting": false
}
```

final_revalidation 说明实际输出路径仍触发目标；minimality 说明单删证据。预算或 U 阻止证明时，即使目标复验通过，也返回 1。最终 NI/U/异常返回 4，并保留此前的最小性字段作为历史证据；未复验／失败的输出标 previously_interesting，不宣称成功。历史 U 另看 had_unresolved；它不是最终最小性字段的别名。

## 两三分钟演示

这是讲解顺序，不是性能保证。先按[算法案例](examples/algorithm/README.md)的命令块准备一个新目录、两个提前编译的目标与初始文件；也可整块运行该案例后，复用其 shell 变量，在以下全新输出名上演示：

1. 展示初始 96 段文件，运行 oracle，说明两个程序都正常退出但答案不同。
2. 启动 MoonReduce，展示自动删除与输出摘要。
3. 独立运行 oracle 和 audit，展示输出仍有指定差异、任意单删均无差异。
4. 解释报告中的复验、最小性、98 次启动分项；说明人工缺陷、无外部采用和已知边界。

```sh
python3 examples/algorithm/oracle.py --reference "$moonreduce_case_dir/reference" --buggy "$moonreduce_case_dir/buggy" "$moonreduce_case_dir/initial.txt"
_build/native/release/build/cmd/moonreduce/moonreduce.exe "$moonreduce_case_dir/initial.txt" --output "$moonreduce_case_dir/demo-reduced.txt" --report "$moonreduce_case_dir/demo-report.json" --timeout-ms 5000 --max-tests 500 -- python3 examples/algorithm/oracle.py --reference "$moonreduce_case_dir/reference" --buggy "$moonreduce_case_dir/buggy"
python3 examples/algorithm/oracle.py --reference "$moonreduce_case_dir/reference" --buggy "$moonreduce_case_dir/buggy" "$moonreduce_case_dir/demo-reduced.txt"
python3 examples/algorithm/audit.py --reference "$moonreduce_case_dir/reference" --buggy "$moonreduce_case_dir/buggy" "$moonreduce_case_dir/demo-reduced.txt"
python3 -m json.tool "$moonreduce_case_dir/demo-report.json"
```

初次演示使用新案例目录，已有输出不会被覆盖。[SUBMISSION.md](docs/SUBMISSION.md)汇总“值得做、做得对、做得完”的证据，并将工程完成与需求／采用证据分开。

## 固定工具链的独立安装

如果已有上面完全相同的版本，可跳过此节。下面使用[官方归档](https://docs.moonbitlang.com/en/latest/download-and-install.html)，安装到新的临时目录，保留现有安装；只适用于本次已验证环境。另需 curl、tar、sha256sum 和前述系统编译／运行依赖。两个归档已经实际下载、核对哈希、解包并完成 Native／Wasm core bundle。

```sh
moonreduce_sdk="$(mktemp -d)"
curl --fail --location --connect-timeout 10 --max-time 180 --output "$moonreduce_sdk/moonbit.tar.gz" 'https://cli.moonbitlang.com/binaries/0.10.15%2B943464bfa/moonbit-linux-x86_64.tar.gz'
curl --fail --location --connect-timeout 10 --max-time 60 --output "$moonreduce_sdk/core.tar.gz" 'https://cli.moonbitlang.com/cores/core-0.10.15%2B943464bfa.tar.gz'
printf '%s  %s\n' '24b93a5409d2a4fb8e3d1b84b473f27b63476cef4418094764df96cb26b03c09' "$moonreduce_sdk/moonbit.tar.gz" '96d30f4dbcc6a9e1736ef26fbdd0e8fb0e97cb01d50e55d2a0072208b8061ae5' "$moonreduce_sdk/core.tar.gz" | sha256sum --check -
tar -xzf "$moonreduce_sdk/moonbit.tar.gz" -C "$moonreduce_sdk"
mkdir -p "$moonreduce_sdk/lib"
tar -xzf "$moonreduce_sdk/core.tar.gz" -C "$moonreduce_sdk/lib"
chmod +x "$moonreduce_sdk"/bin/* "$moonreduce_sdk/bin/internal/tcc"
export MOON_HOME="$moonreduce_sdk"
export PATH="$MOON_HOME/bin:$PATH"
moon -C "$MOON_HOME/lib/core" bundle --target native --warn-list -a
moon -C "$MOON_HOME/lib/core" bundle --target wasm-gc --warn-list -a
moon version --all
```

然后回到仓库根目录，执行构建节的 moon update 和其余命令。不要省略固定版本或把 URL 换为 latest。实测没有使用作者工程 _build、未跟踪文件、原 SDK 或原注册表缓存；宿主系统的 C 编译器、glibc 和 init/reaper 仍是同一台机器的环境，不能据此宣称另一操作系统或外部用户已验证。

## 范围、证据与来源

首版只做单文件、LF 字节保真、按行、串行删除；不是语法解析器、自动修复器或沙箱。只有 Interesting 候选替换最佳结果。最终实际复验与最小性验证分开报告；不保证全局最短或解决随机故障。

完整输入保存在内存中，没有超大文件性能承诺；临时日志不设磁盘配额，默认清理后仅留有界诊断。原子发布不保证断电持久化；强制终止的孤儿后代最终由实测系统 init/reaper 回收。解析器等其他实际案例、外部用户试用、独立机器、其他平台及云 CI 均未验证。当前两个缺陷均为人工植入，没有生产 bug 发现经历可宣称。

- [行为规格](docs/SPEC.md)：两套退出码、预算预留、停止原因、复验及最小性状态。
- [阶段计划](docs/PLAN.md)、[实际验证与事实记录](docs/STATUS.md)。
- [QuickCheck shrinking、Picire、Lithium 的任务比较](examples/README.md)与 [C-Reduce](https://github.com/csmith-project/creduce)说明已有替代能力；本地 Mooncakes 索引也已发现 `Ag108/MoonReduce`，没有声称生态空白或选题必然获准。
- 文件/进程复用 [moonbitlang/async](https://github.com/moonbitlang/async)，参数/JSON 复用 [moonbitlang/core](https://github.com/moonbitlang/core)；二者为 Apache-2.0 依赖，保留其原许可证，不改成 MIT。

本项目原创代码使用 [MIT](LICENSE)。算法概念参考 [The Debugging Book](https://www.debuggingbook.org/html/DeltaDebugger.html)；核心按本项目契约独立实现，没有复制其 Python 代码。测试 oracle 是人工编写的夹具，不是新发现的生产 bug。来源和赛事公开信息见 STATUS。
