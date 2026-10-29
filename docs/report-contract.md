# JSON 报告契约与离线验证

[report.schema.json](report.schema.json) 描述实际 schema_version=1 的全部字段、类型、枚举和停止状态组合；[validate_report.py](../scripts/validate_report.py) 再检查跨字段算术、位置顺序、保存状态与最小性进度。两者只验证已写出的报告，未改变 SPEC、字段含义或 CLI 运行依赖。

开发验证复用本环境已有的 jsonschema 4.19.2（JSON Schema Draft 2020-12）；不是 MoonReduce 运行要求。其他开发环境缺失时，可自行在虚拟环境安装固定的 `jsonschema==4.19.2`。工具离线读取仓库内 schema，不解析远程引用、不安装或修改环境。

```sh
python3 scripts/validate_report.py docs/report.example.json
python3 scripts/validate_report.py /absolute/path/to/your-report.json
python3 scripts/check_report_contract.py
```

验证器返回 0 表示全部报告通过当前结构及可推导的必要一致性检查，1 表示报告不符合这些约束／无法读取，2 表示用法错误或缺少开发依赖。它不能证明 oracle 确实执行、报告未被伪造，或历史文件仍存在、inode 不同、oracle 稳定、故障仍能复现；目标行为必须实际运行 oracle。诊断长度以解码后的字符作保守上界；运行时仍按每流最多 4096 原始字节读取。

## 必须同时满足的关系

- `tests_started` 等于四阶段计数之和，也等于 interesting、not_interesting、unresolved、oracle_errors、interrupted_tests 之和；不超过 max_tests。launch_attempts 等于 tests_started 加 launch_failures。计数单位仍是 controlled_launcher_start，不能把辅助 kill 当一次判断。
- initial_check／final_revalidation 的明确 I、NI、U 各需对应阶段一次实际启动，并分别累加到该判定类别的计数下界；两次 I 不能共用一次 interesting。not_run 对应阶段零启动。error／interrupted 不强制某个判定分类：可能启动前失败，也可能已计入判定后才发生诊断 IO 错误或中断。
- timeouts 不大于 unresolved；had_unresolved 与 unresolved 是否非零一致。正常退出状态与信号不能同时记录。cache_enabled 恒 false、cache_hits 恒 0。
- 保存结果的位置严格递增、唯一且在原序列内；位置数等于 best_segments，字节／段数不超过原始输入，空序列对应零字节。未保存时 output 与 best 元数据为空。
- output_saved 需初始 I；若 best_segments 小于 original_segments，还至少有一次不同于初始及最终复验的 I 改进调用。
- 完整单删检查需 checked=required=best_segments；verified 的理由是 all_single_deletions_not_interesting 或空结果的 empty_result。blocked_by_unresolved 还需实际 U 计数与相应理由。
- 当前 minimality_checked 不超过累计 tests_by_phase.minimality；not_checked 对应零进度及零单删阶段调用。verified 的当前进度全是 NI；blocked_by_unresolved 当前进度大于零且至少含一个 U；未完成／含 U 的当前进度是 NI 与 U 的组合。它们与初始／最终复验属于不同调用，类别计数必须相加预留，不能重复用作证明。
- result_status 和 only_previously_observed_interesting 由保存状态与 final_revalidation 决定。completed/0 必须最终 I 且最小性 verified；预算耗尽／最小性 U 为 1 且最终 I；最终 NI/U 为 4；中断为 130；执行错误为 4，可能覆盖其他停止原因。

这些下界来自实际实现：Native 每个请求调用一次 invoke，没有缓存；核心在 Singles 只对 NI/U 增加 checked，I 会更新最佳并清零当前轮进度，不能复用搜索或旧轮次结果。[核心状态机](../src/core/reducer.mbt)、[驱动](../src/native/driver.mbt)与[启动分类](../src/native/oracle.mbt)是语义依据。累计单删调用还含旧轮次、I 改进及失败／中断调用，所以不能要求它等于当前轮进度。

初始空输入或搜索得到空最佳可以在零单删调用下 verified；单元素删除到空则可能已有一次单删 I，当前进度仍为零。预算不足／中断保留实际进度，不凭空增加证明。报告没有每次调用的逐项轨迹，校验器不能从这些汇总字段重建或证明真实执行过程；通过必要下界不代表计数来源可信。

最小性描述之前的删除检查，最终复验描述输出当前的目标行为，必须分开读取：最终 NI/U 的报告可以保留此前取得的 minimality=verified，同时 result_status=previously_interesting、exit_code=4。历史 U 不自动否定后来完整的明确单删证据。中断或 IO 错误可以发生在某次检查已完成之后，不能把所有异常都硬改成未观察过结果。

## 真实报告与反例验证

check_report_contract.py 复用阶段 3 的 Case、实际启动计数和超时／中断 fixture，实时生成所有停止原因的报告：正常、三种空结果来源、预算不足／部分单删、历史 U 后完成、全部删除候选 U、初始 NI/U、最终 NI/U、异常退出、启动前失败、取得判定后的 IO 错误、单删改进重启、各阶段超时／SIGINT（含忽略 TERM 的子进程和辅助失败）。同时校验[算法实录](report.example.json)。临时报告不纳入仓库，不伪造运行样本；PID 回收仍由原可靠性断言验证。

负例从实录／即时报告复制后注入矛盾，检查错误退出码、漏计调用、预算超额、虚假最小性、错误位置、丢失最终复验状态等被拒绝。判定／阶段／证明关联变异保持 Schema 与计数总和合法，逐项断言具体字段诊断及 CLI 返回 1，包括原自审的零 I 和零单删调用副本、复验判定被重复用作删除证据等。JSON 中 NaN／Infinity 也拒绝。此验证只补足机器消费契约，不替代原阶段 3 的完整故障矩阵，也不把静态字段关系冒充独立 oracle 复验。

schema_version=1 使用明确字段集合；以后增删字段或状态时应同时审查 schema 和跨字段验证，保持报告使用者可辨识变化。用法／路径预检失败和初始读取错误可能没有报告，报告 IO 失败也只能由 stderr 与工具退出码表明，不要求凭空产生一份 JSON。完整语义见 [SPEC](SPEC.md)。

## 终态必要约束矩阵

以下由 driver.execute／record_error、invoke 的分类及核心快照推导，不从字段名称猜测。Schema 维持版本 1；此处关系由 Python 校验。I/NI/U 指明确判定；C 表示 search_stop_reason=completed，B 表示 budget_exhausted。

| stop_reason／退出码 | 初始判定与允许的后续阶段 | 最终复验 | 错误／最后状态 | 计数与证明 |
| --- | --- | --- | --- | --- |
| completed／0 | 初始 I 且已保存；搜索／单删可为零（空结果），C | I，一次实际 final | error=null，无未处理错误／中断；last_exit_code=0、signal=null | verified；空结果 0/0 合法 |
| budget_exhausted／1 | 初始 I 且已保存，B，最后一次调用预留给 final | I，一次实际 final | 同上，last_exit_code=0 | 当前证明 not_checked/incomplete，理由 budget_exhausted；总启动数等于 max_tests |
| unresolved／1 | 初始 I 且已保存，C | I，一次实际 final | 同上，last_exit_code=0；历史 U 不是执行错误 | blocked_by_unresolved；本轮至少一个 U |
| initial_not_interesting／3 | 初始 NI；只有初始的一次启动，无输出，无搜索／单删／final | not_run | error=null、last_exit_code=1、signal=null | not_checked，进度与应检查数均 0 |
| initial_unresolved／3 | 初始 U；同上 | not_run | error=null，正常 2 或工具超时的 null，signal=null | 同上；超时计数支持 null 状态 |
| final_not_interesting／4 | 初始 I 且已保存；C 或 B | NI，一次实际 final | error=null、last_exit_code=1、signal=null；不是 execution_error | 保留 C 的 verified/blocked 或 B 的未完成证明，不能当当前目标成功 |
| final_unresolved／4 | 初始 I 且已保存；C 或 B | U，一次实际 final | error=null，正常 2 或超时 null，signal=null | 同上；零段证明也可以保留 verified(0/0) |
| execution_error／4 | 可在初始前／后、已保存后、复验后失败；初始非 I 或未保存均不允许后续阶段启动 | not_run/error/interrupted，或此前已取得的 I/NI/U；final 启动可为 0 | error 必须非空；可保留正常、异常或无状态；若有中断须如实标记 | 保留已有计数和证明；不要求 oracle_errors 必须大于零（IO／启动前失败也会到这里） |
| interrupted／130 | interrupted=true；初始非 I 时无后续；已保存的最佳结果保留 | not_run/interrupted，或中断前已取得的判定 | error=null；不根据最后状态强推调用分类 | 保留已取得的证明；interrupted_tests 可以为零（如已观察 I 后保存时中断） |

共通约束及优先级：

- oracle_errors>0 和 launch_failures>0 都要求 execution_error。前者仅是已启动、未得到可用判定的执行错误，后者仅是受控启动器失败；没有忽略后重试的路径。反向不成立：诊断、保存、摘要 IO 错误不一定增加 oracle_errors。
- 已取得明确 final I/NI/U 时，oracle_errors、launch_failures、interrupted_tests 必须均为零；此前发生任何一次此类失败都会停止，不能再得到 final 判定。此后仍可有摘要／报告 IO 错误或取消，保留已有判定并提升工具终态。初始已确认 NI/U 也不能再有受控启动失败尝试。
- interrupted_tests>0 必须有 interrupted=true；中断标记／阶段和该计数只能与 interrupted 或更高优先级 execution_error 终态共存。initial_check/final_revalidation=error 或 search_stop_reason=execution_error 必须对应 execution_error。
- 初始非 I 时 search/minimality/final 计数均为零，未保存、未复验、未开始证明。初始 NI/U 后若发生报告 IO 错误或取消，终态可提升为 execution_error/interrupted，但仍不能多出后续判断。初始 I 的首次保存失败也不能继续搜索；未保存时最终状态 not_run、证明 not_checked。
- search_stop_reason=C 表明核心已有完整单删结论（verified 或 blocked_by_unresolved）；B 表明证明未完成，理由仍是 budget_exhausted。B 时搜索／单删停在 max_tests−1 次，故 tests_started=max_tests−1+tests_by_phase.final；若 final 准备／启动失败，没有那一次实际启动，允许只用 max_tests−1 次。
- 当前证明、初始／最终判定仍分别满足上一节的独立调用及分类下界；新增终态关系不替代这些计数检查。早期 U／超时后取得完整明确证据仍可 completed。

last_exit_code／last_signal 不是工具自身退出或 kill 辅助命令的状态。invoke 开始就清空两者，随后记录其自身 process.wait 结果；若新调用准备／启动失败，两者可均为 null，即使此前有 I。超时分支丢弃等待结果并返回 None，之后的 TERM/KILL 清理信号不写入 last_signal。明确最终 I/NI 必须分别对应 0/1；明确 U 对应 2 或有 timeouts 计数支持的 null。初始 NI/U 后没有后续调用，也遵守该映射。

异常正常退出码或非空 last_signal 排除普通完成、预算、U、初始拒绝及最终 NI/U 终态。错误／中断仍需保守处理：进程状态赋值之后还有候选读取、诊断和分类步骤，取消可能发生在这些步骤之间；不能把错误／中断名称反推为某个唯一调用分类，也不能把所有保留信号强制改成 oracle_errors。已确认的最终判定仍约束其最后状态。

回归使用真实生成器报告覆盖九种终态，额外覆盖四阶段信号、正常退出 137（区别于信号）、空结果最终 U／超时、已保存后 final 启动失败、已最终 I 后摘要失败、已观察 I 后保存中断。终态变异维持 Schema、分类／阶段总和与先前证明约束合法，确保具体诊断来自新的终态关系。校验只拒绝可推导的矛盾，不能证明来源、完整执行轨迹或 oracle 真实性。
