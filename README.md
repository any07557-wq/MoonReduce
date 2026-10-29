# MoonReduce

给一份失败文件和识别同一问题的外部判断程序，自动删除输入行，输出经过再次验证的较小反例；同时提供纯 MoonBit 可复用缩减核心。

**当前为阶段 2 开发版**：Native CLI 已打通输入、缩减、保存、输出路径实际复验和摘要／JSON。纯核心仍可通过[同步序列 API](src/core/README.mbt.md)独立使用。阶段 3 的完整执行边界和报告验证尚未完成，当前不宣称可以最终发布。

```sh
moonreduce failing.txt --output reduced.txt --report report.json \
  --timeout-ms 2000 --max-tests 1000 -- ./oracle.py 'fixed argument'
```

INPUT、--output、--report 和 -- 后的命令必填。判断程序收到其固定参数加上**最后一个参数：候选文件的绝对路径**，工作目录保持不变，stdin 为 /dev/null。通过参数数组启动，不隐式运行 shell。oracle 正常退出 0/1/2 分别代表 Interesting / NotInteresting / Unresolved；超时也为 Unresolved，其他退出码、oracle 自身崩溃或启动失败属于执行错误。判断程序须只读候选，用错误签名等定义“同一个问题”。

被测程序的崩溃应由判断脚本识别特定签名后转换成相应判定；不能将任意非零退出或判断程序自身的崩溃当作成功复现。

文件按 LF 字节切分，保留 CRLF、空白、编码字节和末尾换行原状。原始输入不修改，已有输出／报告一律拒绝覆盖，也会拒绝符号链接、硬链接和同一路径别名。每次改进原子保存；最终直接对输出路径再次实际调用 oracle。

--timeout-ms 默认 2000，范围 1–2147483647；--max-tests 默认 1000，范围 2–2147483647，包含初始检查、搜索、单删检查和最终复验，并预留最后一次调用。没有缓存。

| 工具退出码 | 含义（与 oracle 退出码分开） |
| --- | --- |
| 0 | 输出复验 Interesting 且行粒度 1-minimal 已验证 |
| 1 | 输出复验 Interesting，但预算或 Unresolved 阻止完整最小性证明 |
| 2 | 参数或输出冲突等用法错误 |
| 3 | 初始输入不满足条件或无法判断，未生成反例输出 |
| 4 | 执行错误或输出复验失败／无法判断 |
| 130 | 中断；保留已知结果，报告未完成的验证 |

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
```

首次 check/build 自动获取固定依赖；不需要 `moon upgrade`。核心测试独立重建子序列、重新判断结果并逐个删除元素复查，枚举小规模布尔/三态谓词；Debug 和 Release 使用同一套检查。也可执行 `moon test src/core --target wasm-gc --deny-warn`。

阶段 0 探针脚本核对工具链与 async 版本，执行 Native 字节/进程探针、纯核心 Wasm 检查、超时树清理、外部 SIGINT 和格式检查。成功末行是 `Stage 0 acceptance probes passed...`；临时候选和日志在结束时删除。也可单独运行 `moon run src/probe --target native`，但它不包含外部 SIGINT 验收。

## 已实跑的构建和缩减示例

下面用人工 BUG 标记验证 CLI 管道，不是新发现的生产 bug。构建后运行的 Native 文件名由 MoonBit 生成为 moonreduce.exe：

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

每次 oracle 的候选和日志在私有临时目录中，stdout/stderr 直接写文件，诊断每流最多读 4096 原始字节并以 UTF-8 容错显示，完成后删除完整临时日志；不设日志磁盘配额。Ctrl-C 的已知最佳保存、普通进程树清理及嵌套超时已有代表性回归。若参数／路径预检阶段尚未安全预留报告目标，错误仅写 stderr，不创建 JSON；完整故障注入和报告矩阵留待阶段 3。

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
