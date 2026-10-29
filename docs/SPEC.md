# MoonReduce v0.1 行为规格

本文件是 v0.1 本地交付契约，不是对外发布或赛事批准声明。阶段 0–5 的源码、固定工具链、可靠性、案例和消费工程验收记录见 [STATUS.md](STATUS.md)；结论为 Ready for local v0.1 review。全新 SDK／空注册表与干净 Git 源码由实现者在同一台主机复现，没有外部用户试用或独立机器验证。

## 范围与采用理由

用户已有一份失败输入和能够识别同一问题的判断程序。工具自动删除片段、保存已知反例、实际复验输出并报告证据，减少人工删文件和重复运行判断程序的工作。提供可供独立 MoonBit 工程使用的纯核心。

阶段 4 对采用理由的证据见 [examples](../examples/README.md)：人工算法缺陷以整数段适配 n/数组，实际 96 段缩至 3 段，完成输出复验和独立单删检查；独立账本工程直接复用业务类型及三态回调，8 个操作缩至 2 个，并通过迁出目录的新产物构建。它们支持技术闭环与集成可行性，不证明相对人工的用时优势、真实外部采用或参赛必然获准。解析器等其他实际场景仍待验证。

v0.1 限定单文件、LF 行粒度、有序序列、串行、删除型 ddmin。已验证支持环境仅为 WSL2 Ubuntu 26.04、Linux x86_64 Native；普通非 WSL Linux、其他发行版和架构、macOS／Windows 原生未验证。原始失败文件保持不变。没有 AST、完整语法解析、格式修复、并行缩减、GUI、云服务、沙箱、自动发现 bug、多平台发布或 fuzz 框架；不承诺 Picire 接口兼容或语言/格式标准的完整实现。

## 命令行契约

目标命令形式：

```sh
moonreduce failing.txt --output reduced.txt --report report.json \
  --timeout-ms 2000 --max-tests 1000 -- /absolute/path/to/oracle fixed-arg
```

- `INPUT` 位置参数、`--output`、`--report` 及 `--` 后的非空命令必填；按阶段 2 prompt 采用位置输入，不再提供早期规格的 --input 形式。`--timeout-ms` 默认 2000，范围 1–2147483647；`--max-tests` 默认 1000，范围 2–2147483647。均为十进制整数，超出范围拒绝，不静默截断。`--help`、`--version` 返回 0，不执行 oracle。
- `--` 之前复用 core/argparse 解析工具选项；之后所有参数逐个原样传入，不再解释为工具选项。
- 每次通过参数数组执行 `[command, fixed_args..., absolute_candidate_path]`。候选路径**追加为最后一个参数**；不替换占位符，不拼接 shell 命令，不隐式运行 shell。
- 保持启动 MoonReduce 时的工作目录与环境，stdin 为 `/dev/null`。隔离的是候选文件及其日志目录，不改变 oracle 的 cwd；临时目录不是沙箱。
- 命令含 `/` 时按启动目录解析；不含 `/` 时允许 PATH 搜索。参数不能含 NUL；不承诺表示非 UTF-8 文件名。文件内容始终使用字节。
- 输出、报告路径必须互异且不能指向输入路径；已有目标拒绝。v0.1 不提供覆盖已有文件的选项。先检查路径，首次发布完整输出／报告时使用不覆盖目标的原子 rename，避免检查后被其他进程创建文件的竞争；只替换本次已经发布的输出或报告。不提前创建空占位文件。
- 输入以 realpath 解析；输出/报告的父目录规范化，以 /usr/bin/test 的 -ef（设备和 inode）比较已有文件身份，覆盖硬链接与符号链接；不跟随最终符号链接的存在性检查也会拒绝悬空符号链接。输入本身可以是指向普通文件的符号链接。
- 无已知 Interesting 输入时不创建反例输出；首次保存失败也不留下空占位输出。报告可在没有输出的情况下存在。无权写报告时打印 stderr 并以执行错误退出，不伪称报告已保存。
- 参数／路径预检或初始读文件阶段尚未建立运行上下文，仅向 stderr 报错，不创建 JSON。运行阶段的初始拒绝、oracle 错误、预算停止、最终复验和中断会尝试写报告；已有文件冲突绝不以报告写入为由覆盖目标。并发创建目标导致发布失败为运行执行错误（4），与启动前发现已有目标的用法错误（2）区分。

## Oracle 结果与执行错误

oracle 的退出码与 MoonReduce 自身退出码是两个独立接口。

| oracle 结果 | 判定 / 处理 |
| --- | --- |
| 正常退出 0 | `Interesting`，仍然触发用户定义的目标行为 |
| 正常退出 1 | `NotInteresting` |
| 正常退出 2 | `Unresolved`，无效或暂时无法判断 |
| 本次调用超时 | `Unresolved`，另增 `timeouts`；不是执行错误或 bug 证据 |
| 其他正常退出码，包括 124、137 | 执行错误，停止 |
| oracle 被信号杀死 | 执行错误，记录信号；不能与正常退出 137 混同 |
| 命令无法启动、辅助进程管理失败、工具必要文件读写失败 | 执行错误，停止 |

只有工具自身定时器到期才记超时；不根据 oracle 的 124/137 推断超时。判断程序应将被测程序的崩溃、特定断言、错误签名或输出差异转换为上述三态；判断程序自己的崩溃不能成为 Interesting。用户负责定义“同一个问题”，不能把任意非零退出当作复现。

v0.1 面向确定、可重复的 oracle。目标行为会改变或随机出现的故障超出承诺范围；一次最终复验或少量重复调用不能证明绝对稳定。

判断程序应只读候选文件。驱动在判定后核对原始候选字节，检测到候选内容被修改时作为执行错误，避免把不同内容的结果当作删除候选的证据。若复验中的输出被改写，尽可能原子恢复此前保存的最佳字节，再报执行错误；恢复不是复验，不宣称恢复后的目标行为已通过本次检查。

## 行与字节

按 LF 字节 `0x0a` 分段，LF 留在所属段中；CRLF 的 CR 不删除。空文件为零段；末尾 LF 不生成额外空段。例：`b"a\r\nb\n"` 为 `[b"a\r\n", b"b\n"]`；`b"\n"` 为一段；`b"a"` 为一段。不解码/重编码、不 trim、不补末尾换行、不统一换行。

元素以原始位置身份识别，重复内容仍是不同位置。候选是严格递增的位置索引序列，按其顺序拼接原始字节段。选中所有段必须逐字节等于原输入；选中零段产生真正的零字节文件。

## 核心与缩减语义

核心不导入文件、时钟或进程库。采用同步候选请求/反馈边界：核心给出候选 ID 与位置；Native 驱动物化文件、await 进程判定，再把同一 ID 的判定送回核心。执行错误和中断由驱动停止流程，不伪装成三态结果。不需要同步回调内部嵌套事件循环；库用户可直接使用下述同步包装。

初始输入必须经过一次真实 Interesting 检查后才进入搜索并保存初始最佳结果。只有严格更小且为 Interesting 的候选可以替换最佳结果；NotInteresting 和 Unresolved 均不能替换。不假定单调性；不根据某一候选的结果推导其他候选。任何真正改进后使旧的最小性证据失效。

初始 Interesting 后，非空序列必须明确请求删除所有元素的空候选。长度大于 1 时记为 Search，空候选 Interesting 即得到空最佳；NotInteresting/Unresolved 才继续分块。长度为 1 时这次调用就是 MinimalityCheck，不重复另做空探测。初始零长度不重复调用自己；其初始确认后的零次删除检查为空真。实际调用仍受驱动预算限制，提前停止不能伪称已经测试空候选。

ddmin 的分块及候选顺序固定、可重复：当前有序序列分为连续、长度相差不超过一的块，余数从前向后分配；从左到右遍历子集，再从左到右遍历补集，接受首个 Interesting 改进后重新分块。初始分块数为 `min(2, length)`，子集成功重置为 2，补集成功减一但不低于 2（均限制为当前长度），无改进时加倍至元素个数；长度不足 2 进入最终删除检查。与当前最佳相同或非更小的候选不请求；不同步骤可能请求相同位置序列，不实现跨步骤缓存或以历史 Unresolved 推导新判定。不宣称得到全局最短输入。

搜索结束后，针对当前最佳结果从左到右检查每个单元素删除候选。单元素到空输入必须执行；零元素时没有单元素可删，最小性条件为空真。

- 任一删除得到 Interesting：保存新最佳结果，重新开始最终删除检查，直到没有进一步 Interesting 改进；不得在发现改进后直接结束。
- 一次完整检查中所有删除都明确为 NotInteresting：`minimality=verified`。
- 一次完整检查无改进但存在 Unresolved：`minimality=blocked_by_unresolved`，不得称为 1-minimal。
- 预算/错误/中断使检查未完成：`minimality=incomplete` 或尚未开始时 `not_checked`，不标 verified。报告保留当前检查进度。

“1-minimal”仅指相对于确定 oracle 与当前行粒度，删除任意一个元素都明确得到 NotInteresting；不是最少字节、全局最短或格式最简。每次完整单元素检查只对其当前最佳序列有效；此前其他序列上的 Unresolved 不会自动否定后来完整、明确的证据，但仍须报告历史计数。

### 已实现的核心 API

`moonreduce/moonreduce/core` 仅导入标准库 debug，测试另用标准 test，不导入 async、文件或进程包。用法及可执行示例见 [核心 README](../src/core/README.mbt.md)。

- `Reducer::new(length)` 创建待初始确认会话；原始身份为 `0..length-1`，负长度抛 InvalidLength。
- `next()` 返回待反馈的 CandidateRequest（会话内递增 Int64 ID、Initial/Search/MinimalityCheck、不可变位置数组）；重复读取返回同一请求，不触发调用。
- `submit(id, verdict)` 只接受当前请求，返回是否首次建立/改进最佳结果。错序、重复和停止后的反馈抛 UnexpectedFeedback，状态不变。
- `snapshot()` 暴露不可变原始/最佳位置、初始判定、停止原因、最小性及当前最终检查进度、已接受反馈数与历史 Unresolved 数；无已知 Interesting 时最佳为 None，有效空最佳为 Some([])。
- `stop(cause)` 丢弃待反馈请求并保留最佳，快照停止原因为 Stopped(BudgetExhausted/ExecutionError/Interrupted/UserStopped)；已结束会话不被覆盖，不支持恢复。
- `reduce(input, oracle)` 是同步便利包装，返回快照及最佳元素。序列结构做快照，引用元素不深拷贝，调用期间须稳定；回调异常直接传播，需保留中途最佳时使用 Reducer。

核心的 Completed 仅表示单元素删除证据完整；最终输出路径复验与实际进程调用预算仍由驱动完成。核心反馈数不是实际进程启动数；核心不提供 CLI 的最终成功状态或隐藏复验。

## 调用预算与最终复验

`--max-tests N` 包含初始检查、搜索、单元素检查及最终复验，N 至少为 2。每次判断调用的受控启动成功后计入 `tests_started`；Linux 路径中是启动将 exec oracle 的 setsid 进程，exec 失败仍记录为该次启动并作为执行错误停止。辅助的 kill 进程不算判断次数。另记 `launch_attempts` 与 `launch_failures`，不把无法启动辅助启动器的尝试伪称为已实际运行的 oracle。计数的对象与启动失败阶段必须写入报告。

报告固定 tests_counting_unit=controlled_launcher_start。tests_by_phase 总是包含 initial/search/minimality/final 四个整数（包括零）。每次受控启动恰有一个终结分类，满足：

```text
tests_started = interesting + not_interesting + unresolved + oracle_errors + interrupted_tests
tests_started = initial + search + minimality + final
launch_attempts = tests_started + launch_failures
timeouts <= unresolved
```

oracle_errors 统计已启动、但因异常退出、信号、候选内容错误或执行／清理失败而没有可用判定的调用；interrupted_tests 统计未取得判定就被取消的调用。启动前失败不混入这两个计数。计时器到期即记 Unresolved 和 timeout；后续清理失败仍使工具整体报执行错误，不重复计算该次启动。判定后保存或诊断读取错误也可以使整体执行错误，而不撤销已观察到的判定计数。

初始检查可占用第 1 次；其后只有 `tests_started < N - 1` 时才启动搜索或单元素检查。最后 1 次始终预留给**输出文件的最终实际复验**，不能被隐藏复验占用或超预算。

- N=2，非空初始输入 Interesting：直接交付初始最佳文件并实际复验，`budget_exhausted`，不能称已验证最小性。
- N=2，空初始输入 Interesting：没有单元素可删，复验 Interesting 后可以完整验证。
- 初始结果 1/2：分别报告初始不满足/无法判断，不进入缩减，无反例输出，不消耗预留的最终调用。
- 正常搜索结束、检查受 Unresolved 阻碍或预算耗尽：原子保存最佳输出后，以**输出路径**再次实际调用 oracle；不是只测试之前的候选路径。复验 Interesting 后不再改写输出；检测到 oracle 改写输出的错误恢复遵守前述契约。
- 最终 1/2、超时或执行错误：不发成功结论。文件仅为此前已知 Interesting 的候选，报告本次复验失败/不确定。
- 执行错误后停止启动判断调用；中断后优先保存已知结果与清理进程。此时可不执行最终复验，必须明确 `not_run`/`interrupted`。预留调用不是在错误或中断后继续运行的授权。

v0.1 首先不实现缓存；报告 `cache_enabled=false`、`cache_hits=0`。如有余力加入缓存，键必须精确比较候选的完整位置序列/字节，不能只凭可能碰撞的哈希判等；Unresolved 不缓存为稳定结果。最终复验永远绕过缓存，最小性只能由适用当前序列的明确证据支持。

## 进程、文件及中断

每次判断在新建的权限 0700 临时目录中写入候选和权限 0600 的 stdout/stderr 日志。输出流直接重定向到文件，不用无限内存收集，也不串行等待两个管道。诊断每个流最多读取 4096 字节，记录是否截断。默认在调用清理后删除目录和完整日志；最终报告只保留有界诊断，不提供日志保留选项。日志不设磁盘配额；工具可观察到的必要文件操作失败作为执行错误。

Native 驱动使用已验证的 `moonbitlang/async@0.22.4` 进程与文件 API；Linux 依赖 `/usr/bin/setsid`（util-linux）建立独立会话/进程组、`/usr/bin/kill`（procps-ng）发送组信号，另用 `/usr/bin/test -ef` 比较文件身份。固定使用已验证的 `with_timeout`，只捕获其 TimeoutError；不使用 `with_timeout_opt` 的旧嵌套等待路径，也不使用系统 timeout 的保留退出码判断超时。

单次计时从受控进程启动返回后开始，到进程结束为止；超时后先对进程组发送 TERM，100ms 宽限后发送 KILL，等待并回收直接判断进程。清理处于不可取消区，组长提前退出也不能取消剩余组清理；正常结束也清理遗留组成员。组已消失可立即结束清理。启动与 setsid 建组间的取消竞争有直接 PID 终止后备。kill 使用实测可处理较小负组 ID 的短信号形式（-TERM/-KILL），固定 LC_ALL=C 并仅把明确 No such process 视为已消失；其他失败报执行错误。所有组清理路径（包括组长正常退出后）在辅助程序失败时，都尝试现有 async 硬取消原语对组与直接 PID 作 Linux 后备，然后保留该执行错误；已用真实启动失败注入验证。

验收外部检查真实父、子、孙进程的 PID 消失，并检查普通父进程 wait 子进程的证据；另验证忽略 TERM 的判断程序及其子进程需要 KILL。强制终止的父进程不能再 wait；这种情况下后代由实测环境的 init/reaper 回收，测试同样要求 /proc 中 PID 消失。MoonReduce 自己等待直接判断进程，不实现 Linux subreaper。不能用 mock、仅检查主进程退出或仅检查 kill 返回成功代替。普通子进程继承进程组；不承诺恶意脱离进程组的程序、内核不可中断状态或 SIGKILL 下的友好退出/用户态清理，也不提供沙箱。

每次 Interesting 改进后先保存最佳结果，再继续调用。输出和 JSON 报告各自采用目标同目录的独占临时文件写完、关闭后原子发布；首次发布不覆盖目标，后续最佳改进才替换本次输出。写入中途出错或 rename 失败均清理临时文件，保留上一个已成功保存的最佳文件；原输入不作为临时文件或替换目标。两份文件并非跨文件事务，不承诺 fsync 或断电持久化；报告写入失败不能撤销已保存的最佳文件。

Ctrl-C 保护正在进行的保存及进程清理，尽可能发布已确认的完整候选；初始、搜索、单删和最终复验中的取消分别记录已有证据。最终复验未完成时明确 not_run/interrupted，不能因为预留了调用就继续启动。全部判断已结束后，最终报告／摘要的受保护收尾可能正常完成；不承诺捕获 SIGKILL、断电或每个指令边界的中断。清理本身因文件系统拒绝操作而失败时，保留错误，不宣称资源已清除。

## 报告与工具自身退出码

同时输出人可读摘要与独立 JSON。不使用一个 `success` 字段掩盖不同证据。JSON 至少包含：

| 字段 | 约定 |
| --- | --- |
| `schema_version`、`tool_version` | 首版 schema 版本 1；工具版本 |
| `input`、`requested_output`、`output`、`report`、`oracle_argv` | 绝对路径；output 在无已保存结果时为 null，requested_output 始终标明请求目标；原命令参数数组 |
| `original_bytes/segments`、`best_bytes/segments` | 精确字节和段数；无最佳为 null |
| `stop_reason`、`exit_code` | 见下表；与 CLI 实际退出码一致，不是目标行为/最小性的别名 |
| `search_stop_reason` | not_started / completed / budget_exhausted / execution_error / interrupted；保留复验前的停止原因 |
| `initial_check` | interesting / not_interesting / unresolved / error / interrupted / not_run |
| `final_revalidation` | interesting / not_interesting / unresolved / error / interrupted / not_run |
| `minimality` | verified / blocked_by_unresolved / incomplete / not_checked |
| `minimality_reason` | empty_result / all_single_deletions_not_interesting / unresolved_single_deletions / budget_exhausted / interrupted / execution_error / no_saved_interesting_result / not_completed |
| `minimality_checked/required` | 最终当前序列一轮单元素检查的实际完成数与应检查数；不是历史各轮累加 |
| `tests_started`、`tests_counting_unit`、`launch_attempts/failures` | 如预算节定义；tests_by_phase 的四个分项相加等于 tests_started |
| `interesting/not_interesting/unresolved`、`timeouts` | 判定总数；timeout 是 unresolved 的子集，不重复计入总启动数 |
| `oracle_errors`、`interrupted_tests`、`error` | 调用终结分类与整体执行错误分开；last_exit_code 仅为正常退出码，last_signal 为信号编号，没有结果则为 null；不能与工具 exit_code 混淆 |
| `max_tests`、`timeout_ms`、`elapsed_ms` | 生效参数和实际用时（使用单调时钟计时） |
| `had_unresolved`、`interrupted` | 历史标志，不能因最终通过而隐去 |
| `cache_enabled`、`cache_hits` | 首先固定 false / 0 |
| `diagnostics`、`output_saved` | 有界错误诊断、截断标记及实际保存状态 |
| `result_status` | no_saved_result / revalidated_interesting / previously_interesting，最后一项仅代表曾观察为 Interesting |
| `only_previously_observed_interesting` | 已保存且本次最终复验不是 Interesting 时为 true，包括未运行、失败、无法判断及中断 |

摘要必须同时说明停止原因、最终复验状态、最小性状态、启动/超时次数和实际文件路径；初始检查结果不能代替最终复验。若不同运行对同一字节但不同路径有不同判定，以最终输出路径的实际结果为准，不宣称已解决路径敏感或随机 oracle。

minimality 描述此前对当前字节序列的单删证据，不能代替最终目标行为复验。复验失败或未执行时，即使该字段仍为 verified，摘要也明确说明只是此前检查的证据。最终 NI/U 或错误会保留已保存字节与有界诊断，返回 4。关闭摘要输出管道导致写入失败时，工具改为执行错误并原子更新本次已发布的 JSON；不追加 oracle 调用。报告自身无法写入／更新时返回 4、打印 stderr，尽可能移除失效报告，不声称报告已保存。

| `stop_reason` | MoonReduce 退出码 | 含义 |
| --- | --- | --- |
| `completed` | 0 | 最终复验 Interesting 且最小性 verified |
| `budget_exhausted` | 1 | 最终复验 Interesting，但预算阻止完整最小性检查 |
| `unresolved` | 1 | 最终复验 Interesting，最终单删检查有 Unresolved，最小性未证实 |
| `initial_not_interesting` | 3 | 初始实际结果 1，无反例输出 |
| `initial_unresolved` | 3 | 初始实际结果 2 或超时，无反例输出；与前项靠报告区分 |
| `final_not_interesting` | 4 | 输出实际复验结果 1，不能作为成功反例交付 |
| `final_unresolved` | 4 | 输出实际复验结果 2 或超时 |
| `execution_error` | 4 | oracle 异常退出/信号/启动错误，或必要读写、清理错误 |
| `interrupted` | 130 | 用户中断；保留已知最佳与已取得的证据，未完成的复验明确标注 |

用法错误（含 N<2、缺少 `--`/命令、非法参数、已有输出）为工具退出码 2，不是 oracle 的 Unresolved；尽量在启动 oracle 前拒绝。帮助/版本返回 0 只表示信息命令成功。

状态组合优先级：可观察执行/保存/清理错误 > 中断 > 初始拒绝 > 最终复验失败/不确定 > 预算 > 最终最小性 Unresolved > completed。中断后的清理若失败，最终码 4、`interrupted=true`；复验失败仍保留 `search_stop_reason` 与已有最小性字段，摘要必须指出这些只是在此前判定下的证据。若预算恰好在完整证明后到零，不称“预算阻止验证”，仍可 completed；只在缺少必要检查时标预算耗尽。
