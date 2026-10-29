# 实际状态与事实记录

记录日期：2026-10-29（Asia/Shanghai）。阶段 0–3 已验收，当前完成 Native CLI 执行限制、可靠保存、进程清理和报告矩阵；不代表最终可发布或比赛审核通过。实际调试案例、独立消费工程和干净环境验收尚未完成。

## 阶段 0 已完成（历史记录）

- 确认 `pwd` 与 Git 根均为 `/home/user/MoonBit_Program/MoonReduce`；开始本阶段时 main 无提交、工作区为空，无适用 AGENTS.md。沿用当前独立仓库，没有操作上级目录或其他项目。
- 建立 MoonBit 模块、纯 `core` 协议类型、仅输出帮助的 CLI 骨架及 Native 探针；加入忽略规则、README、MIT 许可证和三份要求的文档。
- 固定并实测 async 0.22.4；没有升级 MoonBit、编译器或全部依赖。旧缓存 0.20.2 源码的 Linux 退出状态未可靠区分信号，且取消仅发送单 PID 信号，不用于此项目。
- Native 探针通过真实文件/进程 API 验证请求→异步执行→反馈接口方向，无嵌套事件循环。阶段 0 当时仅证明接口，尚未实现 ddmin；阶段 1 已接入真实 Reducer 做回归。
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
| 运行辅助工具 | `/usr/bin/setsid` util-linux `2.41.3`；`/usr/bin/kill` procps-ng `4.0.4`；阶段 2 新增 `/usr/bin/test -ef`（本机 uutils coreutils `0.8.0`） |
| 仅探针依赖 | `/usr/bin/python3` `3.14.4`、`/usr/bin/sleep` |
| 非依赖 | 发现 `timeout (uutils coreutils) 0.8.0`，**未采用其退出码包装** |

锁定依据是本机运行结果，不是声称这些是最新版本。`moon.mod` 指定唯一依赖版本，验收脚本检查实际解析版本以防漂移。包保存在正常 MoonBit 缓存/`.mooncakes`，不提交依赖源码或二进制。

已下载并阅读官方 [Unix 安装脚本](https://cli.moonbitlang.com/install/unix.sh)，确认其接受固定版本参数；脚本 SHA-256 为 `46495f8cdc0050f79b6cb195d66478d101cb3601d68506568fbe377fcdf2a9fe`。已对以下地址执行 HEAD，均返回 HTTP 200：

- `https://cli.moonbitlang.com/binaries/0.10.15%2B943464bfa/moonbit-linux-x86_64.tar.gz`
- `https://cli.moonbitlang.com/cores/core-0.10.15%2B943464bfa.tar.gz`

未执行重新安装。服务响应标明这些归档有 60 天保留策略，本次响应到期日为 2026-12-12；长期复现应保留工具链归档。本仓库不分发工具链。三天内的复现步骤及新机器独立执行仍需最后阶段实际验证。

## 阶段 0 实际执行与结果

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

截至阶段 0，`moon test` 未执行，没有算法单元测试，以可执行能力探针验收。当时正式缩减、预算、报告、最佳保存、最终输出路径复验与 Release 均未实现/未验证。阶段 1 验证见下一节。

## 阶段 1 纯缩减核心

开始阶段 1 时检查了三份项目文档、Git 根/状态/最近提交与 AGENTS.md。仓库位于正确目录、main 干净，前置提交为 `f0853c7 chore: bootstrap MoonReduce and freeze v0.1 scope`。没有真实前置阻塞，没有修改依赖或推进 Native 驱动。

已实现：

- 纯 MoonBit `Reducer`：有序原始位置、唯一待反馈请求、确定次序的子集/补集 ddmin、三态反馈、明确初始拒绝、当前最佳不可变快照。
- 初始 Interesting 后明确测试删除全部元素；单元素到空是一次真实候选请求，初始空序列仍须确认，零次删除证明为空真。
- 独立最终单元素检查：Interesting 继续缩减并重启证明，旧证据失效；当前完整一轮有 Unresolved 就 BlockedByUnresolved。只有全为 NotInteresting 才 Verified，不称全局最短。
- `stop(cause)` 可在任意边界安全停止，保留已知 Interesting；预算、错误和中断不会伪装成完整证明。错序/重复/迟到反馈被拒绝且不修改状态；完成后的 stop 不覆盖已完成结论。
- 同步 `reduce(input, oracle)` 返回最佳元素及原始位置，不依赖文件或进程；回调错误直接传播，没有隐藏复验或预算。`feedback_count` 与实际进程启动数分开。
- 核心 README 提供可执行使用示例；原 Native 探针改为向真实 Reducer 反馈实际进程结果，再安全停止，保持异步边界可接入。

独立验证使用黑盒测试，只依赖公开接口。检查器重建返回位置与原始元素的对应关系、重新调用谓词确认仍 Interesting，并独立重建每个单元素删除候选验证所有最小性声明，不复用核心删除函数或把内部 Verified 当作证明。完整枚举长度 0–4 的布尔谓词、长度 0–3 的三态谓词，覆盖其全部子序列判定表；此外检查重复元素、多元素共同触发、非单调情况下 1-minimal 非全局最短、确定遍历和提前停止。

为覆盖“最终检查得到 Interesting 必须继续”的协议分支，另有人工反馈序列模拟搜索时 Unresolved、验证时可判断；测试最终用独立的确定目标谓词复查结果。此测试不代表对随机 oracle 的稳定性承诺。

阶段 1 补充明确了 SPEC：多元素初始 Interesting 后先发空 Search 候选；单元素直接发空 MinimalityCheck，避免漏掉全部删除。重复步骤可请求相同位置，不实现缓存。算法概念已实际核对原作者 Andreas Zeller 的 [The Debugging Book 一手说明](https://www.debuggingbook.org/html/DeltaDebugger.html)；当前实现独立编写，没有复制 Python 源码。核心只导入标准 debug，测试另用标准 test。

| 阶段 1 实际命令 | 最终结果 |
| --- | --- |
| `moon test src/core --target native --deny-warn` | Debug：20 个测试全部通过，含文档示例和穷举谓词的独立复查 |
| `moon test src/core --target native --release --deny-warn` | Release：同一套 20 个测试全部通过 |
| `moon test src/core --target wasm-gc --deny-warn` | 20 个测试全部通过，核心不依赖 Native 进程层 |
| `python3 scripts/check_stage0.py` | 修复后完整回归通过，含构建约 6.4 秒；文件/退出码/大输出、树清理与两种外部 SIGINT 均通过。真实 Reducer 的 async 反馈与安全停止也通过 |
| `moon fmt --check` | 通过（包含在最终回归脚本中） |
| `git diff --check` | 通过，无空白错误 |

必要前置修复：本阶段回归首次在树清理阶段触发整个探针的 20 秒 TimeoutError。另用 `git archive f0853c7` 在 `/tmp/moonreduce-stage1-baseline` 重建未修改的阶段 0 代码，也在约 20.2 秒复现，证明不是纯核心新增逻辑引起。现场检查可见独立进程组已建立，500ms 等待期限后进程仍存活。本机固定组合下，改用 `with_timeout` 并只将其 TimeoutError 映射为 None 后，原回收及 SIGINT 验收通过；没有改动依赖、延长 20 秒看门狗或取消进程树检查。新增对 500ms/300ms 两个超时调用在 5 秒内完成的检查。上游 `with_timeout_opt` 在此嵌套路径停滞的更深层根因未确认，不声称已修复上游库。后续 Native 驱动应沿用本次实测路径。

本阶段无需下载新依赖。初次编译暴露的类型/运算符优先级问题已修复，没有通过降低警告级别绕过；核心命令均使用 `--deny-warn`。Native 回归构建仍可见阶段 0 记录的上游 C `write` 返回值警告。阶段 1 验收通过：返回值及最小性声明有独立行为检查，提前停止与 Unresolved 不冒充完整证明；Native 接口回归问题也已修复。4 小时阶段预算内完成，下一阶段仍等待用户 prompt。

## 阶段 2 完整 CLI 主流程

开始时读取 SPEC、PLAN、STATUS 和 Git 状态；main 干净，前置提交为 `f7c82ac feat: implement deterministic ddmin reduction core`，未发现新增 AGENTS.md 或无关改动。按本阶段 prompt 的 4 小时预算实现主流程，未开始阶段 3。

已完成：

- CLI 使用 INPUT 位置参数、必填 --output/--report、默认 2000ms/1000 次，数值限制为正 32 位范围（max-tests 至少 2）。帮助、版本和参数错误使用现有 core/argparse；-- 后命令与固定参数保持数组边界，候选绝对路径追加最后。
- 纯字节 LF 分段与原位顺序拼接，覆盖 CRLF、空行、无末尾 LF、NUL/非法 UTF-8、空文件和单行删空；不解码输入。
- 串行接入实际 Reducer 与 async 文件／进程 API，每次调用创建独立候选／日志目录；初始输入实际确认，改进先原子保存再提交核心最佳状态，保证写失败时保留上一份已保存结果。
- 实际启动计数和最终调用预留已接入；没有缓存。最终直接把输出路径交给真实 oracle 复验，复验失败不输出成功结论。摘要和基础 JSON 分开记录复验与最小性。
- 原文件不写入；父目录规范化、test -ef 设备/inode 比较和不跟随最终链接的存在性检查，拒绝同文件、符号链接、硬链接、悬空链接及已有输出／报告。独占预留，目标同目录临时文件写完关闭后再替换。
- 异常退出、信号和启动失败停止；0/1/2 与工具退出码分开。检测到 oracle 改写候选也停止。stderr/stdout 文件重定向，每流诊断最多读取 4096 原始字节，显示时 UTF-8 容错，不转换输入字节。
- 已知最佳保存和清理处于受保护路径；中断不会冒充最终复验，代表性 Ctrl-C 测试保留已保存结果并清理父/子/孙进程。

保持阶段 1 的抛错式 `with_timeout` 路径。`check_stage2.py` 新增真实嵌套回归：外层驱动任务组＋进程任务组内的 500ms 超时必须在 5 秒内返回 Unresolved，检查三个 PID 均从 /proc 消失及父、子 wait 标记；另测忽略 TERM 的直接 oracle 需要 KILL。没有把外层看门狗到期当作本次调用成功超时。

接入时进一步发现本机 procps-ng 4.0.4 的长信号参数形式，在较小负进程组 ID 上会打印 usage 并退出 1；原探针仅接受 0/1 会掩盖这类错误。已实测改用 -TERM/-KILL 短形式，Native runner 固定 LC_ALL=C 并只把明确 No such process 视为组已消失；其他错误停止。原探针也更换相同参数形式。这是此前停滞路径的一个相关风险，不将阶段 1 的现象单独归因为 async 上游 bug。最深层归因和所有异常组合仍未验证。

新增运行依赖 `/usr/bin/test -ef` 已在本机用普通文件、硬链接、符号链接及不存在目标实际验证，返回 0/0/1 符合所需身份判断；本机可执行文件解析到 `/usr/lib/cargo/bin/coreutils/test`，版本沿用 uutils coreutils 0.8.0。未新增或升级 MoonBit 第三方模块。CLI 唯一自有 libc 绑定是退出码所需的 exit；进程／文件操作仍使用现有 async 库及已声明系统工具。

| 阶段 2 实际命令 | 结果 |
| --- | --- |
| `moon check --target native --deny-warn` | 通过 |
| `moon test src/lines --target native --deny-warn` | 字节分段与所有选择拼接检查通过 |
| `moon test --target native --deny-warn` | Debug：21 个测试全部通过 |
| `moon test --target native --release --deny-warn` | Release：同一套 21 个测试全部通过 |
| `moon build --target native --deny-warn` | Debug 构建通过 |
| `moon build --target native --release --deny-warn` | Release 构建通过 |
| `python3 scripts/check_stage0.py` | 阶段 0/1 文件、进程、超时、SIGINT 和真实核心反馈回归通过；包含核心 Wasm check 与格式检查 |
| `python3 scripts/check_stage2.py` | Debug CLI 主流程及基本失败处理通过 |
| `python3 scripts/check_stage2.py _build/native/release/build/cmd/moonreduce/moonreduce.exe` | 同样的真实 CLI 工作流在 Release 通过 |
| README 的 Release 构建＋示例命令 | 实际 21 字节→4 字节 BUG 加 LF；初始、搜索、单删、最终共 7 次启动，复验 Interesting、最小性 verified；再独立运行 oracle 退出 0，原文件字节不变 |

端到端脚本按外部可见行为验收：逐字节检查 LF/CRLF/空行/无末尾换行/空文件/单行/非法 UTF-8 输出和原文件哈希；调用日志证明实际次数及最后一次使用输出绝对路径；命令和参数含空格、引号、换行及 shell 字符保持原样。初始 1/2、缺输入、缺命令、退出 7/124/137、信号 9/15、候选被改写、已有输出和链接别名均得到明确拒绝/错误。预算 2 的案例确为初始＋最终两次，保留原始最佳且不称最小；路径敏感 oracle 的最终失败不被掩盖。双流各 8MiB 不挂住，摘要不包含无限输出，诊断截断明确。

本阶段结论：从文件输入到输出复验的整条 CLI 主流程已闭合，代表性失败处理和嵌套超时回归通过；不是最终发布验收。基础 JSON 已可使用，参数／路径预检尚未安全预留报告时仅写 stderr，不创建 JSON。执行边界与报告的完整故障注入、各种中断时机和资源失败组合留给阶段 3，未验证的路径不视为通过。

## 阶段 3 执行限制、保存和报告

开始时读取 SPEC、STATUS、PLAN、Git 根／状态和适用 AGENTS.md；main 干净，前置提交为 63b97a3（feat: add line-based reducer CLI and oracle runner），没有新增 AGENTS.md、无关改动或真实前置阻塞。本阶段未改变工具链、依赖或运行系统工具，未进入阶段 4。

实际发现并修复：

1. 原 runner 在组长正常退出后遇到 kill 辅助程序启动失败，只报错，没有执行组强制终止后备。测试专用 LD_PRELOAD 将真实 posix_spawn(/usr/bin/kill) 注入 EACCES，独立观察到子进程仍存活；失败后的脚本补救清理不算通过证据。现在所有组清理路径都尝试现有 async 的 hard_cancel 后备，同时保留执行错误。正常退出遗留子进程、超时及 Ctrl-C 同时遇到辅助启动失败的回归均验证 PID 消失；中断加清理错误为退出 4 且 interrupted=true。
2. 真实目录权限拒绝显示，预留的空输出在首次保存失败后可能也无法删除。取消输出／报告的空占位预留：先写完并关闭同目录独占临时文件，首次以不覆盖目标的原子 rename 发布，后续仅替换本次已保存的最佳。无首次保存就无空输出／报告；并发创建的目标原样保留。注入先部分 pwrite 再 ENOSPC，确认旧最佳逐字节不变且临时文件清除；保存过程中外部 SIGINT 仍交付完整已确认候选。
3. stdout 管道提前关闭时，原 CLI 实际退出 4，但 JSON 仍为 completed/0。现在摘要写入失败后原子更新本次报告为 execution_error/4，保留此前取得的目标／最小性证据，不追加 oracle 调用；真实 Broken pipe 回归通过。
4. 调用分类补齐无判定错误和中断，不再把取消当 oracle 异常；该工具链的 errdefer 也在取消时运行，因此用 Result 边界区分实际异常与取消。tests_started 等于三态、oracle_errors、interrupted_tests 之和；启动器失败另列 launch_failures。外部 libc 启动计数器和每次 oracle 的独立日志共同核对实际启动与四阶段分项。保留复验前 search_stop_reason，最终中断不抹去 completed/budget_exhausted。
5. 诊断读取失败也必须清除本轮临时目录。复验 oracle 改写输出时尽可能恢复已保存字节并报错，不把恢复当成复验。报告增加工具 exit_code、计数对象、requested_output、result_status、only_previously_observed_interesting 和 minimality_reason；摘要对“仅曾 Interesting”明确说明最小性只是此前检查的证据。

预算仍为所有实际受控启动（包含初始和最终）合计；无缓存。搜索／单删仅在 tests_started < max_tests - 1 时启动，最后一次预留输出路径复验。通过从预算 2 到正常所需次数再多一次的每个边界：不足时退出 1、最终实际 Interesting、最小性不 verified；恰好完成证据与复验时即使达到上限仍为 completed/0。初始空输入预算 2 可完整验证，单行可删空与不可删空也覆盖。

| 阶段 3 最终实际命令 | 结果 |
| --- | --- |
| moon check --target native --deny-warn | 通过 |
| moon test --target native --deny-warn | Debug：21 个测试通过，包含核心独立黑盒／穷举后置条件检查 |
| moon test --target native --release --deny-warn | Release：同一套 21 个测试通过 |
| moon build --target native --deny-warn | 通过；由阶段 0/2/3 脚本实际执行 |
| moon build --target native --release --deny-warn | 通过 |
| python3 scripts/check_stage0.py | 完整探针通过，含版本、核心 Wasm check、原文件／进程能力、外部 SIGINT 和格式检查 |
| python3 scripts/check_stage2.py | Debug 主流程、字节、路径／参数、失败处理及 500ms 嵌套超时回归通过 |
| python3 scripts/check_stage2.py _build/native/release/build/cmd/moonreduce/moonreduce.exe | 相同矩阵 Release 通过 |
| python3 scripts/check_stage3.py | Debug 可靠性和报告矩阵通过 |
| python3 scripts/check_stage3.py _build/native/release/build/cmd/moonreduce/moonreduce.exe | 相同矩阵 Release 通过 |

阶段 3 黑盒矩阵覆盖：

- 正常完成、零字节结果、预算恰好耗尽／不足、初始 NI/U；实际调用计数、分项、分类、摘要、JSON 与 CLI 退出码相互核对。
- 搜索超时、部分历史 U 后仍能完整证明、全部严格子候选 U、最终 NI/U/超时／异常；最终失败优先于预算，原搜索停止原因保留，已保存输出仅标为此前证据。
- 最终单删得到 Interesting 后继续缩减并重置证明，或随即预算耗尽而交付已保存的改进；人工变化可判断性的 fixture 只用于协议分支验证，不代表对随机 oracle 稳定性的承诺。
- 普通三层树、忽略 TERM 的直接 oracle 与子进程、组长已退出遗留子进程；超时和四阶段 SIGINT 均检查 /proc PID 消失。普通树另检查父、子 wait 标记；被 KILL 的父进程无法再 wait，其孤儿后代由本环境 init/reaper 回收，未冒称 MoonReduce 自己是 subreaper。
- 首次／改进输出权限失败、报告权限失败、候选修改、诊断读取失败、实际启动器失败、oracle exec 失败及组信号辅助程序失败；已保存最佳和原输入安全，不能写报告时 stderr 明示退出 4。
- 每流 32 MiB stdout/stderr 文件重定向，诊断每流实际 4096 字节并标截断，报告保持有界；所有正常／已测故障完成后临时候选、日志和原子写入文件均无泄漏。没有设置日志磁盘配额。
- 测试库只在临时目录构建，用于外部计数和故障注入，不链接 CLI、不新增运行依赖；每次进程调用均设合理看门狗，失败补救清理不计入验收证据。

验收结论：本阶段通过。关键清理与复验语义由真实进程、权限故障及外部计数核实，没有放宽通过条件、以 mock 代替进程或把尚未执行的案例标成通过。SPEC、README 与 PLAN 已同步。阶段 4 的实际开发者调试流程、独立 MoonBit 消费工程及阶段 5 干净环境复现仍未验证。

## 公开事实与相关工作

以下为 2026-10-29 查阅结果，不是报名或资格判断。浏览连接器未返回结果后改用网页工具和官方公开源码；部分动态页面/包文档无法抓取，具体限制如下。

- [2026 MoonBit 软件合成挑战赛说明](https://www.moonbitlang.cn/2026-scc/)：公开页按完成度、工程质量、可解释性和用户体验评价，要求可构建、可运行、可复现。页面提到的代码量是参考，并保留项目审核流程；其中日程为 2–4 月，不能据此推断当前批次或仍开放报名。
- [MoonBit 国产基础软件生态开源大赛官网](https://moonbitlang.github.io/OSC2026/)为动态页面；已实际读取其[官方页面源码](https://github.com/moonbitlang/OSC2026/blob/main/main/main.mbt)。源码说明允许原创库、移植及开发工具，强调边界、文档、可运行测试、维护和许可证；规则以公告/最终章程为准。源码仍列申报截止 7 月 12 日，已早于本记录日期。用户未指定具体赛事/批次，本阶段不推断资格，也未提交报名或联系赛事方。
- [Picire](https://github.com/renatahodovan/picire)：Python 的 Delta Debugging 库与 CLI，已有行/字符粒度、遍历策略和并行能力，BSD-3-Clause。MoonReduce 不声称兼容其所有参数；采用理由应由调试闭环、明确三态/复验报告及 MoonBit 库消费证明，而不是替用户放弃已有工具。
- [C-Reduce](https://github.com/csmith-project/creduce)：已有用于保持特定属性的 C/C++ 程序缩减工具，不是本项目宣称新发明的方向。这里只参考公开定位，没有复制实现。
- 本机 Mooncakes 缓存索引 `~/.moon/registry/index/user/Ag108/MoonReduce.index` 已有 `Ag108/MoonReduce` 0.1.0（2026-09-14）及 0.2.0（2026-09-21），描述为确定性失败用例缩减，依赖 async 0.20.4、许可证 Apache-2.0、repository 字段为空。**这至少是已有同名相近工作的证据**。[在线包文档](https://mooncakes.io/docs/Ag108/MoonReduce/)抓取失败，未下载其源码，未核验在线当前状态、功能完整性、作者归属或与本项目的关系；不将索引记录推断为没有竞争或已经完成差异化。
- 当前安装的 [core](https://github.com/moonbitlang/core) 已有 `quickcheck/shrink` 的 `Shrink` 候选迭代接口，覆盖数组/Bytes 等类型；参数和 JSON 也有现有库。缩减不是 MoonBit 生态从零开始的能力。是否具有与本规格相同的独立外部 oracle 工作流未作全面核验。
- [async](https://github.com/moonbitlang/async) 已有 Native 文件、进程、超时、取消及文件重定向 API。本项目直接复用；0.22.4 安装源可见对信号返回负值的处理，而默认 Unix 取消发送单 PID 信号，因此另用 setsid/kill 清理进程组。
- ddmin 的算法来源参考 Andreas Zeller、Ralf Hildebrandt 的 *Simplifying and Isolating Failure-Inducing Input*（2002，[DOI](https://doi.org/10.1109/32.988498)）及 [Delta Debugging 项目](https://www.st.cs.uni-saarland.de/dd/)。原论文 PDF 抓取未成功；阶段 1 已核对作者的 [Reducing Failure-Inducing Inputs](https://www.debuggingbook.org/html/DeltaDebugger.html) 一手算法说明，没有复制其 Python 源码。

第三方依赖的 Apache-2.0 许可证仍随原包保留；本项目 MIT 不覆盖第三方依赖。没有借用其他项目名义、生产 bug 或测试数量保证赛事通过。

## 验收结论、限制和下一步

阶段 0 的文件／进程能力、阶段 1 的纯核心、阶段 2 的 CLI 主流程及阶段 3 的可靠性和报告矩阵均已通过；完整 v0.1 尚未通过最终发布验收。计划仍为 21 小时并保留约 2 小时缓冲，本阶段在约 4 小时预算内完成，三天预算仍可信。

原历史探针对 kill 0/1 的宽松判断不作为正式 runner 的语义。Native runner 已严格区分 ESRCH 和其他失败，并通过正常、超时、中断三种清理上下文的辅助启动失败注入。强制终止孤儿后代的最终回收依赖实际环境 init/reaper；普通非 WSL Linux 及其他容器 init 行为未验证。不承诺恶意 setsid 脱离、不可中断内核等待、SIGKILL 或断电后的用户态清理。

保存和 JSON 分别原子发布，不是跨文件事务、不承诺断电持久化；日志不设磁盘配额。必要文件无法操作时可能无法写出报告，明确以 stderr 和退出码 4 报错。新装工具链／干净环境、独立消费工程和实际开发者调试流程仍未验证。当前 BUG 标记示例与故障 fixture 都是人工案例，不是新发现的生产 bug；不承诺全局最短或随机 oracle 稳定性。

下一阶段入口：等待用户阶段 4 prompt，完成可复现开发者调试流程与独立 MoonBit 消费工程；本阶段结束后停止，不提前进入下一阶段。
