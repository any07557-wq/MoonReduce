# MoonReduce

给一份失败文件和识别同一问题的外部判断程序，自动删除输入行，输出经过再次验证的较小反例；同时提供纯 MoonBit 可复用缩减核心。

**当前为阶段 4 开发版**：Native CLI 及执行边界已验收，新增可复现的人工缺陷对拍流程和独立 MoonBit 账本消费工程。两者已在 Debug／Release 实跑；这是开发者验证，没有真实外部采用或新发现的生产 bug。干净环境独立验收尚未完成，当前不宣称可以最终发布。

```sh
moonreduce failing.txt --output reduced.txt --report report.json \
  --timeout-ms 2000 --max-tests 1000 -- ./oracle.py 'fixed argument'
```

INPUT、--output、--report 和 -- 后的命令必填。判断程序收到其固定参数加上**最后一个参数：候选文件的绝对路径**，工作目录保持不变，stdin 为 /dev/null。通过参数数组启动，不隐式运行 shell。oracle 正常退出 0/1/2 分别代表 Interesting / NotInteresting / Unresolved；超时也为 Unresolved，其他退出码、oracle 自身崩溃或启动失败属于执行错误。判断程序须只读候选，用错误签名等定义“同一个问题”。

被测程序的崩溃应由判断脚本识别特定签名后转换成相应判定；不能将任意非零退出或判断程序自身的崩溃当作成功复现。

文件按 LF 字节切分，保留 CRLF、空白、编码字节和末尾换行原状。原始输入不修改，已有输出／报告一律拒绝覆盖，也会拒绝符号链接、硬链接和同一路径别名。每次改进先完整写入临时文件，再原子发布；首次发布不覆盖并发创建的目标，不留下空占位文件。最终直接对输出路径再次实际调用 oracle。

--timeout-ms 默认 2000，范围 1–2147483647；--max-tests 默认 1000，范围 2–2147483647，包含初始检查、搜索、单删检查和最终复验，并预留最后一次调用。没有缓存。

例如 max-tests=2 时，非空输入仅做初始检查和输出复验，不能声称 1-minimal；预算刚好足以完成全部检查则可以返回 0。实际次数统计成功启动的 setsid 判断启动器，包含后续 exec 失败；启动器自身无法启动另记 launch_failures，kill 等辅助调用不计入判断预算。

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

首个验证环境为 Linux x86_64、WSL2（内核 `6.18.33.2-microsoft-standard-WSL2`）。组合固定为：

- `moon 0.1.20261012 (748b63c)`，`moonc v0.10.15+943464bfa`，随工具链的 core 同版本。
- `moonbitlang/async@0.22.4`，在 [moon.mod](moon.mod) 精确声明；无其他第三方 MoonBit 依赖。
- GCC 15.2.0、glibc 2.43；运行组管理依赖 `/usr/bin/setsid`（util-linux 2.41.3）和 `/usr/bin/kill`（procps-ng 4.0.4）；文件身份检查使用 `/usr/bin/test -ef`（本机 uutils coreutils 0.8.0）。不依赖 GNU timeout。
- 探针另用 `/usr/bin/python3`（本机 3.14.4）和 `/usr/bin/sleep`；CLI 本身不依赖 Python，下面的示例 oracle 使用 Python。

在仓库根目录执行：

```sh
moon version --all
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

首次 check/build 自动获取固定依赖；不需要 `moon upgrade`。核心测试独立重建子序列、重新判断结果并逐个删除元素复查，枚举小规模布尔/三态谓词；Debug 和 Release 使用同一套检查。也可执行 `moon test src/core --target wasm-gc --deny-warn`。

阶段 0 探针脚本核对工具链与 async 版本，执行 Native 字节/进程探针、纯核心 Wasm 检查、超时树清理、外部 SIGINT 和格式检查。成功末行是 `Stage 0 acceptance probes passed...`；临时候选和日志在结束时删除。也可单独运行 `moon run src/probe --target native`，但它不包含外部 SIGINT 验收。

阶段 3 脚本通过外部 libc 启动计数器、真实权限失败和测试专用 LD_PRELOAD 故障注入验证报告；测试库只编译到临时目录，不进入 CLI，也不增加 CLI 运行依赖。脚本为每次调用设置看门狗，覆盖写到一半后 ENOSPC、保存过程中 SIGINT、强制终止子进程和关闭摘要管道。Release 矩阵可运行：

```sh
moon build --target native --release --deny-warn
python3 scripts/check_stage2.py _build/native/release/build/cmd/moonreduce/moonreduce.exe
python3 scripts/check_stage3.py _build/native/release/build/cmd/moonreduce/moonreduce.exe
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

新环境如需安装工具链，可按[官方安装说明](https://docs.moonbitlang.com/en/latest/download-and-install.html)使用固定构建版本（阶段 0 核对过官方脚本参数及两个归档 URL 的 HTTP 200，未重新安装工具链）：

```sh
curl --fail --location https://cli.moonbitlang.com/install/unix.sh -o /tmp/moonbit-install.sh
bash /tmp/moonbit-install.sh '0.10.15+943464bfa'
export PATH="$HOME/.moon/bin:$PATH"
```

这个官方安装步骤会写入默认工具链目录，应在新环境使用。阶段 0 没有执行干净机器独立验收；第三天按 README 独立复现是交付门槛。

## 范围、证据与来源

首版只做单文件、LF 字节保真、按行、串行删除；不是语法解析器、自动修复器或沙箱。只有 Interesting 候选替换最佳结果。最终实际复验与最小性验证分开报告；不保证全局最短或解决随机故障。

- [行为规格](docs/SPEC.md)：两套退出码、预算预留、停止原因、复验及最小性状态。
- [阶段计划](docs/PLAN.md)、[实际验证与事实记录](docs/STATUS.md)。
- [Picire](https://github.com/renatahodovan/picire) 和 [C-Reduce](https://github.com/csmith-project/creduce) 是已存在的相关工具；本地 Mooncakes 索引也已发现 `Ag108/MoonReduce`，没有声称生态空白或选题必然获准。
- 文件/进程复用 [moonbitlang/async](https://github.com/moonbitlang/async)，参数/JSON 复用 [moonbitlang/core](https://github.com/moonbitlang/core)；二者为 Apache-2.0 依赖，保留其原许可证，不改成 MIT。

本项目原创代码使用 [MIT](LICENSE)。算法概念参考 [The Debugging Book](https://www.debuggingbook.org/html/DeltaDebugger.html)；核心按本项目契约独立实现，没有复制其 Python 代码。测试 oracle 是人工编写的夹具，不是新发现的生产 bug。来源和赛事公开信息见 STATUS。
