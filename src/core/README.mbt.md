# MoonReduce core

导入 `moonreduce/moonreduce/core`，无需导入进程、文件或 async 包。

## 同步序列接口

`reduce(input, oracle)` 接受任意元素序列及三态同步回调，返回原始位置和对应元素。元素无需实现 Hash 或 Eq。它复制输入的序列结构，引用类型的元素不会深拷贝，调用期间应保持稳定。回调错误原样传播；它不隐藏最终复验或提供调用预算。

```mbt check
///|
test "library usage without process dependencies" {
  let input = [10, 20, 30, 40]
  let result = @core.reduce(input, candidate => {
    if candidate.contains(20) && candidate.contains(40) {
      Interesting
    } else {
      NotInteresting
    }
  })
  @test.assert_eq(result.best, Some([20, 40]))
  @test.assert_eq(result.snapshot.best_positions, Some([1, 3]))
  @test.assert_eq(result.snapshot.minimality, Verified)
}
```

## 请求／反馈接口

`Reducer::new(length)` 以 `0..length-1` 为元素身份创建会话。负长度抛 `CoreError::InvalidLength`。核心只管理位置，Native 驱动可保留自己的字节段并据位置物化候选。

- `next()` 返回唯一待判定请求，或在停止后返回 None；重复读取不推进状态，也不代表另一次 oracle 调用。
- 请求的 `id: Int64` 在会话中递增，`phase` 为 Initial / Search / MinimalityCheck。`positions` 是不可变的、严格递增的原始位置序列；空候选为零个位置。
- `submit(id, verdict)` 提交该请求结果。返回 true 表示首次建立或改进最佳结果，驱动应在继续调用前保存它。错序、重复及停止后的反馈抛 UnexpectedFeedback，状态不变。
- `snapshot()` 随时取得不可变快照；`best_positions=None` 表示还没有经 Interesting 确认的结果，`Some([])` 是已知 Interesting 的空序列。
- `stop(cause)` 可在任意请求边界停止并保留最佳结果，丢弃待处理请求。原因包括 BudgetExhausted / ExecutionError / Interrupted / UserStopped；已经结束的会话保持原结论，不能恢复。

初始输入也由真实回调/驱动判定，拒绝或无法判断时不进入搜索。非空输入明确请求空候选；单元素时该调用就是单元素删除检查。之后按固定次序检查分块子集及补集。搜索结果始终是原序列的有序子序列，只有 Interesting 可以替换最佳值。

最终单元素检查从左到右执行，发现 Interesting 后保存新最佳并重新检查；旧轮次证据清零。所有删除都为 NotInteresting 才是 Verified；完整一轮含 Unresolved 为 BlockedByUnresolved，提前停止为 NotChecked / Incomplete。空最佳的零次删除检查为空真。

`Snapshot.stop_reason=Completed` 仅表示核心完成相对于确定 oracle、当前元素粒度的 **1-minimal** 检查，不能当作 Native 工具的完整交付成功：实际进程预算、文件保存和输出路径最终复验属于驱动。`feedback_count` 只是已接受反馈数，不是实际启动进程数；`unresolved_count` 包括历史无法判断，不能用其非零直接否定后来完整明确的检查。

## 独立验证

`audit_test.mbt` 使用公开结果重建原始子序列，并重新构造每个单元素删除候选调用谓词，不读取核心内部状态或复用核心删除函数。穷举覆盖长度 0–4 的所有布尔谓词及长度 0–3 的所有三态谓词，包含非单调情况。定向检查还覆盖重复元素、确定次序、提前停止、协议误用和最终检查阶段继续缩减。

运行 `moon test src/core --target native --deny-warn` 和添加 `--release` 的同一命令分别验证 Debug 与 Release；`--target wasm-gc` 可直接运行纯核心测试，不包含 Native CLI 的支持承诺。

算法概念参考 Andreas Zeller 的 [Reducing Failure-Inducing Inputs](https://www.debuggingbook.org/html/DeltaDebugger.html) 及 [2002 年论文](https://doi.org/10.1109/32.988498)。本实现依据本项目规格独立编写请求／反馈状态机，没有复制该书的 Python 源码；分块顺序、严格初始检查、空候选和三态最小性证据以本项目 SPEC 为准。
