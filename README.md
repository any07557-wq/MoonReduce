# MoonReduce

给一份失败文件和识别同一问题的外部判断程序，自动删除输入行，输出经过再次验证的较小反例；同时提供纯 MoonBit 可复用缩减核心。

**当前为阶段 0 骨架**：已运行文件与进程能力探针；ddmin、正式 CLI、预算/报告和调试示例尚未实现。下列缩减命令是 v0.1 规格，不是当前可用功能：

```sh
moonreduce --input failing.txt --output reduced.txt --report report.json \
  --timeout-ms 2000 --max-tests 1000 -- ./oracle.py 'fixed argument'
```

判断程序收到的参数是其固定参数加上**最后一个参数：候选文件的绝对路径**。通过参数数组启动，不隐式运行 shell。oracle 正常退出 0/1/2 分别代表 Interesting / NotInteresting / Unresolved；其他退出码、oracle 自身崩溃或启动失败属于执行错误。用户必须用错误签名等定义“同一个问题”。原始文件不修改，已有输出拒绝覆盖。

## 实测环境与构建

首个验证环境为 Linux x86_64、WSL2（内核 `6.18.33.2-microsoft-standard-WSL2`）。组合固定为：

- `moon 0.1.20261012 (748b63c)`，`moonc v0.10.15+943464bfa`，随工具链的 core 同版本。
- `moonbitlang/async@0.22.4`，在 [moon.mod](moon.mod) 精确声明；无其他第三方 MoonBit 依赖。
- GCC 15.2.0、glibc 2.43；运行组管理依赖 `/usr/bin/setsid`（util-linux 2.41.3）和 `/usr/bin/kill`（procps-ng 4.0.4）。不依赖 GNU timeout。
- 探针另用 `/usr/bin/python3`（本机 3.14.4）和 `/usr/bin/sleep`。正式 CLI 不计划依赖 Python。

在仓库根目录执行：

```sh
moon version --all
moon check --target native --deny-warn
moon build --target native --deny-warn
moon run src/cmd/moonreduce --target native
python3 scripts/check_stage0.py
```

首次 check/build 自动获取固定依赖；不需要 `moon upgrade`。探针脚本核对实测工具链和实际解析的 async 版本，执行 Native 字节/进程探针、纯核心 Wasm 检查、超时树清理、外部 SIGINT 和格式检查。成功末行是 `Stage 0 acceptance probes passed...`；临时候选和日志在结束时删除。也可单独运行 `moon run src/probe --target native`，但它不包含外部 SIGINT 验收。

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

本项目原创代码使用 [MIT](LICENSE)。阶段 0 未复制第三方缩减算法代码；测试中的 oracle 是人工编写的能力夹具，不是新发现的生产 bug。算法参考及赛事公开信息见 STATUS。
