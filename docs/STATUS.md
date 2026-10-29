# 实际状态与事实记录

记录日期：2026-10-29（Asia/Shanghai）。阶段 0 的实现/探针验收通过；不代表 v0.1 已完成或比赛审核通过。下一阶段尚未开始。

## 已完成

- 确认 `pwd` 与 Git 根均为 `/home/user/MoonBit_Program/MoonReduce`；开始本阶段时 main 无提交、工作区为空，无适用 AGENTS.md。沿用当前独立仓库，没有操作上级目录或其他项目。
- 建立 MoonBit 模块、纯 `core` 协议类型、仅输出帮助的 CLI 骨架及 Native 探针；加入忽略规则、README、MIT 许可证和三份要求的文档。
- 固定并实测 async 0.22.4；没有升级 MoonBit、编译器或全部依赖。旧缓存 0.20.2 源码的 Linux 退出状态未可靠区分信号，且取消仅发送单 PID 信号，不用于此项目。
- Native 探针通过真实文件/进程 API 验证请求→异步执行→反馈接口方向，无嵌套事件循环。这里只是接口证明，**没有实现 ddmin 状态机**。
- 在当前仓库本地设置用户提供的 Git 身份；未配置全局 Git 身份，未 push、发布或打标签。

## 固定的实测组合

| 项目 | 实际值 |
| --- | --- |
| 系统 | WSL2 Linux x86_64，`6.18.33.2-microsoft-standard-WSL2` |
| moon / moonrun | `0.1.20261012 (748b63c 2026-10-12)` |
| moonc / core | `v0.10.15+943464bfa (2026-10-12)`；core manifest `0.10.15+943464bfa` |
| 构建特性 | `rr_moon_mod,rr_moon_pkg` |
| 直接依赖 | `moonbitlang/async@0.22.4`；`moon tree` 仅这一项，无传递第三方模块 |
| async 下载归档 SHA-256 | `2ffdb85cb229cfe9219161a7f2b959215a79a0d75b7e642cb346713f168a1457` |
| Native C / libc | GCC `15.2.0`（Ubuntu 15.2.0-16ubuntu1），glibc `2.43` |
| 运行辅助工具 | `/usr/bin/setsid` util-linux `2.41.3`；`/usr/bin/kill` procps-ng `4.0.4` |
| 仅探针依赖 | `/usr/bin/python3` `3.14.4`、`/usr/bin/sleep` |
| 非依赖 | 发现 `timeout (uutils coreutils) 0.8.0`，**未采用其退出码包装** |

锁定依据是本机运行结果，不是声称这些是最新版本。`moon.mod` 指定唯一依赖版本，验收脚本检查实际解析版本以防漂移。包保存在正常 MoonBit 缓存/`.mooncakes`，不提交依赖源码或二进制。

已下载并阅读官方 [Unix 安装脚本](https://cli.moonbitlang.com/install/unix.sh)，确认其接受固定版本参数；脚本 SHA-256 为 `46495f8cdc0050f79b6cb195d66478d101cb3601d68506568fbe377fcdf2a9fe`。已对以下地址执行 HEAD，均返回 HTTP 200：

- `https://cli.moonbitlang.com/binaries/0.10.15%2B943464bfa/moonbit-linux-x86_64.tar.gz`
- `https://cli.moonbitlang.com/cores/core-0.10.15%2B943464bfa.tar.gz`

未执行重新安装。服务响应标明这些归档有 60 天保留策略，本次响应到期日为 2026-12-12；长期复现应保留工具链归档。本仓库不分发工具链。三天内的复现步骤及新机器独立执行仍需最后阶段实际验证。

## 实际执行与结果

环境检查运行了 `pwd`、`git rev-parse --show-toplevel`、`git status --short --branch`、文件列表与祖先/工作区 AGENTS.md 搜索；无无关改动。`git var GIT_AUTHOR_IDENT` 起初报告缺身份；收到用户提供的信息后仅使用 `git config --local` 设置。沙箱将 `.git` 设为只读，相关 Git 写入经授权的沙箱升级执行。

依赖命令为 `moon add moonbitlang/async@0.22.4 --no-update`（manifest 已声明，提示无需更改），随后 `moon check --target native` 实际下载 0.22.4。后续没有使用猜测的同步 API；直接检查安装的 `pkg.generated.mbti` 和进程实现后编写探针。

| 运行命令 | 实际结果 |
| --- | --- |
| `moon version --all`、`cc --version`、辅助工具版本命令 | 版本如上 |
| `moon tree` | 唯一依赖解析为 async 0.22.4 |
| `sha256sum ~/.moon/registry/cache/moonbitlang/async/0.22.4.zip` | 与上表哈希一致 |
| `moon check --target native --deny-warn` | 通过，MoonBit 零警告/错误 |
| `moon check src/core --target wasm-gc --deny-warn` | 通过，证明当前核心协议不依赖 Native 进程/文件接口；不是 CLI Wasm 支持声明 |
| `moon build --target native --deny-warn` | Native 构建通过；GCC 曾在 async 依赖中提示忽略 `write` 返回值，未隐藏或修改上游源码 |
| `moon run src/cmd/moonreduce --target native` | 输出明确标有阶段 0 的帮助骨架，不执行缩减 |
| `moon run src/probe --target native` | 文件/进程探针通过 |
| `python3 scripts/check_stage0.py` | 完整阶段 0 验收通过，包括外部 SIGINT、版本约束及构建/格式检查 |
| `moon fmt --check` | 通过 |

验收脚本实际验证的可观察行为：

1. 文件含所有 256 种字节、CRLF、NUL、无末尾 LF 和非法 UTF-8 字节，写入/读取/替换逐字节相等；空文件保持零字节。
2. 独占创建及非覆盖 rename 拒绝已有文件且原内容不变；同目录 replace rename 可用。
3. 参数数组执行准确取得正常 0/1/2/7/124/137 与信号 -9/-11/-15；缺失命令抛 ENOENT。通过 setsid 后 0/1/2/124/137 和信号仍保留；缺失命令为 127，保持执行错误语义，不伪装成超时。
4. 可执行文件路径、候选文件路径含空格；参数含空格、引号、换行、分号、`$()` 和 `*`，外部程序看到的 argv 精确相等，没有 shell 展开。
5. stdout/stderr 各写 8 MiB，重定向到文件后正常结束，文件大小精确相符；诊断读取只读 4096 字节，未无限内存收集。
6. 超时调用返回 None，独立进程组 TERM→100ms→KILL，普通父/子/孙进程全部被回收，`/proc/<pid>` 消失且父/子留下 wait 证据；忽略 TERM 的直接 oracle 经 KILL 后也被回收。
7. 外部 Python 对已就绪的 Native 探针发送 SIGINT，最终保留 signal 退出状态，清理完成标记存在，三层进程树全部消失；另验证 SIGINT 中忽略 TERM 的 oracle 也完成 KILL 升级。
8. 正常运行后的候选临时目录和完整日志清除。失败时测试脚本的补救清理不计为通过证据。

`moon test` 未执行：阶段 0 没有算法单元测试，以可执行能力探针验收。正式缩减、预算、报告、最佳保存和最终输出路径复验均**尚未实现/未验证**；Release 构建、普通非 WSL Linux、新装工具链/干净机器、独立消费工程及真实调试流程也**未验证**。

## 公开事实与相关工作

以下为 2026-10-29 查阅结果，不是报名或资格判断。浏览连接器未返回结果后改用网页工具和官方公开源码；部分动态页面/包文档无法抓取，具体限制如下。

- [2026 MoonBit 软件合成挑战赛说明](https://www.moonbitlang.cn/2026-scc/)：公开页按完成度、工程质量、可解释性和用户体验评价，要求可构建、可运行、可复现。页面提到的代码量是参考，并保留项目审核流程；其中日程为 2–4 月，不能据此推断当前批次或仍开放报名。
- [MoonBit 国产基础软件生态开源大赛官网](https://moonbitlang.github.io/OSC2026/)为动态页面；已实际读取其[官方页面源码](https://github.com/moonbitlang/OSC2026/blob/main/main/main.mbt)。源码说明允许原创库、移植及开发工具，强调边界、文档、可运行测试、维护和许可证；规则以公告/最终章程为准。源码仍列申报截止 7 月 12 日，已早于本记录日期。用户未指定具体赛事/批次，本阶段不推断资格，也未提交报名或联系赛事方。
- [Picire](https://github.com/renatahodovan/picire)：Python 的 Delta Debugging 库与 CLI，已有行/字符粒度、遍历策略和并行能力，BSD-3-Clause。MoonReduce 不声称兼容其所有参数；采用理由应由调试闭环、明确三态/复验报告及 MoonBit 库消费证明，而不是替用户放弃已有工具。
- [C-Reduce](https://github.com/csmith-project/creduce)：已有用于保持特定属性的 C/C++ 程序缩减工具，不是本项目宣称新发明的方向。这里只参考公开定位，没有复制实现。
- 本机 Mooncakes 缓存索引 `~/.moon/registry/index/user/Ag108/MoonReduce.index` 已有 `Ag108/MoonReduce` 0.1.0（2026-09-14）及 0.2.0（2026-09-21），描述为确定性失败用例缩减，依赖 async 0.20.4、许可证 Apache-2.0、repository 字段为空。**这至少是已有同名相近工作的证据**。[在线包文档](https://mooncakes.io/docs/Ag108/MoonReduce/)抓取失败，未下载其源码，未核验在线当前状态、功能完整性、作者归属或与本项目的关系；不将索引记录推断为没有竞争或已经完成差异化。
- 当前安装的 [core](https://github.com/moonbitlang/core) 已有 `quickcheck/shrink` 的 `Shrink` 候选迭代接口，覆盖数组/Bytes 等类型；参数和 JSON 也有现有库。缩减不是 MoonBit 生态从零开始的能力。是否具有与本规格相同的独立外部 oracle 工作流未作全面核验。
- [async](https://github.com/moonbitlang/async) 已有 Native 文件、进程、超时、取消及文件重定向 API。本项目直接复用；0.22.4 安装源可见对信号返回负值的处理，而默认 Unix 取消发送单 PID 信号，因此另用 setsid/kill 清理进程组。
- ddmin 的算法来源参考 Andreas Zeller、Ralf Hildebrandt 的 *Simplifying and Isolating Failure-Inducing Input*（2002，[DOI](https://doi.org/10.1109/32.988498)）及 [Delta Debugging 项目](https://www.st.cs.uni-saarland.de/dd/)。本阶段没有移植算法代码；论文 PDF 抓取未成功，算法实现前仍需核对一手算法说明。

第三方依赖的 Apache-2.0 许可证仍随原包保留；本项目 MIT 不覆盖第三方依赖。没有借用其他项目名义、生产 bug 或测试数量保证赛事通过。

## 验收结论、限制和下一步

阶段 0 的文件/进程关键可行性风险已有真实可运行路径，骨架可 check/build，范围与状态契约已固定。23 小时计划仍可信；缓存等优化不在必交付路径。当前不是一个可用缩减器。

进程探针只把 kill 的 0/1 当作成功/通常已消失，未完整区分权限等异常诊断；不能直接复制为生产驱动。下一 Native 阶段须补准确失败诊断及错误注入，保证无法清理时报告执行错误。已验证普通继承进程组的树；不承诺恶意 setsid 脱离、不可中断内核等待或 SIGKILL 后用户态清理。

下一阶段入口：等待用户阶段 1 prompt，在本规格下实现纯 MoonBit ddmin 候选请求/反馈核心及必要行为测试；当前停止，不提前实现。
