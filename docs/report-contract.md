# JSON 报告契约与离线验证

[report.schema.json](report.schema.json) 描述实际 schema_version=1 的全部字段、类型、枚举和停止状态组合；[validate_report.py](../scripts/validate_report.py) 再检查跨字段算术、位置顺序、保存状态与最小性进度。两者只验证已写出的报告，未改变 SPEC、字段含义或 CLI 运行依赖。

开发验证复用本环境已有的 jsonschema 4.19.2（JSON Schema Draft 2020-12）；不是 MoonReduce 运行要求。其他开发环境缺失时，可自行在虚拟环境安装固定的 `jsonschema==4.19.2`。工具离线读取仓库内 schema，不解析远程引用、不安装或修改环境。

```sh
python3 scripts/validate_report.py docs/report.example.json
python3 scripts/validate_report.py /absolute/path/to/your-report.json
python3 scripts/check_report_contract.py
```

验证器返回 0 表示全部报告通过，1 表示报告不符合契约／无法读取，2 表示用法错误或缺少开发依赖。验证成功表示字段自洽，不证明历史文件仍存在、inode 不同、oracle 稳定或故障仍能复现；目标行为必须实际运行 oracle。诊断长度以解码后的字符作保守上界；运行时仍按每流最多 4096 原始字节读取。

## 必须同时满足的关系

- `tests_started` 等于四阶段计数之和，也等于 interesting、not_interesting、unresolved、oracle_errors、interrupted_tests 之和；不超过 max_tests。launch_attempts 等于 tests_started 加 launch_failures。计数单位仍是 controlled_launcher_start，不能把辅助 kill 当一次判断。
- timeouts 不大于 unresolved；had_unresolved 与 unresolved 是否非零一致。正常退出状态与信号不能同时记录。cache_enabled 恒 false、cache_hits 恒 0。
- 保存结果的位置严格递增、唯一且在原序列内；位置数等于 best_segments，字节／段数不超过原始输入，空序列对应零字节。未保存时 output 与 best 元数据为空。
- 完整单删检查需 checked=required=best_segments；verified 的理由是 all_single_deletions_not_interesting 或空结果的 empty_result。blocked_by_unresolved 还需实际 U 计数与相应理由。
- result_status 和 only_previously_observed_interesting 由保存状态与 final_revalidation 决定。completed/0 必须最终 I 且最小性 verified；预算耗尽／最小性 U 为 1 且最终 I；最终 NI/U 为 4；中断为 130；执行错误为 4，可能覆盖其他停止原因。

最小性描述之前的删除检查，最终复验描述输出当前的目标行为，必须分开读取：最终 NI/U 的报告可以保留此前取得的 minimality=verified，同时 result_status=previously_interesting、exit_code=4。历史 U 不自动否定后来完整的明确单删证据。中断或 IO 错误可以发生在某次检查已完成之后，不能把所有异常都硬改成未观察过结果。

## 真实报告与反例验证

check_report_contract.py 复用阶段 3 的 Case、实际启动计数和超时／中断 fixture，实时生成所有停止原因的报告：正常、空结果、预算不足、历史 U 后完成、全部删除候选 U、初始 NI/U、最终 NI/U、异常退出、各阶段超时／SIGINT（含忽略 TERM 的子进程和辅助失败）。同时校验[算法实录](report.example.json)。临时报告不纳入仓库，不伪造运行样本；PID 回收仍由原可靠性断言验证。

负例从实录复制后注入矛盾，检查错误退出码、漏计调用、预算超额、虚假最小性、错误位置、丢失最终复验状态等均被拒绝，且校验器失败时非零退出。JSON 中 NaN／Infinity 也拒绝。此验证只补足机器消费契约，不替代原阶段 3 的完整故障矩阵，也不把静态字段关系冒充独立 oracle 复验。

schema_version=1 使用明确字段集合；以后增删字段或状态时应同时审查 schema 和跨字段验证，保持报告使用者可辨识变化。用法／路径预检失败和初始读取错误可能没有报告，报告 IO 失败也只能由 stderr 与工具退出码表明，不要求凭空产生一份 JSON。完整语义见 [SPEC](SPEC.md)。
