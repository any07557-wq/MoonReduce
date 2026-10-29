# 算法对拍调试流程（人工植入缺陷）

这是本项目原创、MIT 许可的教学回归，不是发现的生产 bug、真实竞赛题或第三方数据。目标使用者是已有失败数组的算法对拍开发者。

任务是允许空区间的最大连续子段和，答案至少为 0。[max_subarray.c](max_subarray.c) 默认使用累积和变负才归零的正确实现；编译 INJECT_BUG=1 时，故意改成遇到任何负数都归零，因此漏掉跨小负数的更优区间。两个版本从同一源文件提前各编译一次，oracle 从不调用编译器。

原流程要反复删数组元素、修正 n，再运行两程序检查差异。这里候选文件每个 LF 段一个整数，oracle 每次根据剩余段重建 n 和数组；MoonReduce 负责删段、保存、预算和复验。这个示例验证流程能够自动完成，没有测量相对人工的时间节省。

## 从初始反例到独立检查

在仓库根目录按顺序运行（原生依赖见主 README，示例另用 Python 3 和 C 编译器）：

```sh
moon build --target native --release --deny-warn
moonreduce_case_dir="$(mktemp -d)"
cc -std=c11 -O2 -Wall -Wextra -Werror -DINJECT_BUG=0 examples/algorithm/max_subarray.c -o "$moonreduce_case_dir/reference"
cc -std=c11 -O2 -Wall -Wextra -Werror -DINJECT_BUG=1 examples/algorithm/max_subarray.c -o "$moonreduce_case_dir/buggy"
python3 examples/algorithm/generate.py "$moonreduce_case_dir/initial.txt"
python3 examples/algorithm/oracle.py --reference "$moonreduce_case_dir/reference" --buggy "$moonreduce_case_dir/buggy" "$moonreduce_case_dir/initial.txt"
_build/native/release/build/cmd/moonreduce/moonreduce.exe "$moonreduce_case_dir/initial.txt" --output "$moonreduce_case_dir/reduced.txt" --report "$moonreduce_case_dir/report.json" --timeout-ms 5000 --max-tests 500 -- python3 examples/algorithm/oracle.py --reference "$moonreduce_case_dir/reference" --buggy "$moonreduce_case_dir/buggy"
python3 examples/algorithm/oracle.py --reference "$moonreduce_case_dir/reference" --buggy "$moonreduce_case_dir/buggy" "$moonreduce_case_dir/reduced.txt"
python3 examples/algorithm/audit.py --reference "$moonreduce_case_dir/reference" --buggy "$moonreduce_case_dir/buggy" "$moonreduce_case_dir/reduced.txt"
cat "$moonreduce_case_dir/reduced.txt"
```

最后两次检查在 MoonReduce 已退出之后执行，不计入它的调用预算。每次使用 mktemp 新目录；生成器也拒绝覆盖已有初始文件。需要批量验收时运行同一组示例代码：

```sh
python3 scripts/check_stage4.py
python3 scripts/check_stage4.py _build/native/release/build/cmd/moonreduce/moonreduce.exe
```

## 判定与安全边界

[oracle.py](oracle.py) 只解析候选、构造目标输入、运行两程序和比较答案，不包含缩减算法。候选绝对路径由 MoonReduce 追加在命令最后。

- 每段须是 -1000..1000 的 ASCII 整数，允许 CRLF 及末段无 LF；最多 4096 段，空候选表示 n=0。空行、非法字节、超范围或超大候选退出 2（Unresolved）。
- 两程序都须正常退出 0，各输出一个规范的非负整数答案；校验答案不超过正数总和。只有 reference > buggy 才退出 0（Interesting）；相等退出 1。
- 相反方向的差异、异常退出、崩溃、空／垃圾／越界输出、缺失命令或读写失败退出 3，MoonReduce 将其作为执行错误 4。不能把任何崩溃或非零退出当对拍成功。
- 每个目标程序另设 1 秒执行保护；本案例要求两者正常完成，所以该保护触发也作为执行错误。CLI 的 5000ms 是整个 oracle 的独立超时，触发时仍遵守库规格记 Unresolved。两层计时的含义不同。
- 目标输出写临时文件后有界读取，单流最多检查 4097 字节；异常 stderr 最多读 1024 字节。示例目标不派生子进程，不提供沙箱或日志磁盘配额。

判定条件有意固定为“两个正常答案之间的指定方向差异”。换成其他问题时，调用者应替换相应的同一问题签名，不能沿用任意输出不等即成功的宽泛规则。

## 本机实测记录

2026-10-29，在主 README 固定工具链／WSL2 环境的 Debug 与 Release CLI 上重复运行得到一致结果：

| 项目 | 实际结果 |
| --- | --- |
| 初始文件 | 96 段，310 字节；生成器 seed=1729 |
| 初始 SHA-256 | 29d8ecde61cb096cc58abb769949891883c696a9293c49dd153affc95fa3a8d8 |
| 缩减文件 | 3 段，9 字节；17、-3、19，各保留 LF |
| CLI 实际判断启动 | 98：初始 1、搜索 93、单删 3、最终复验 1 |
| 最终及独立复验 | Interesting；正确答案 33，错误答案 19 |
| 最小性 | 工具 verified；独立重新执行两程序检查 3 次删除，全部 NotInteresting |
| 原始文件／二进制 | 原始字节不变，两个提前编译的二进制哈希与 mtime 不变 |

独立 [audit.py](audit.py) 不导入 oracle 或核心：枚举所有连续区间核对参考程序，再逐个删除最终元素并重新生成 n、实际运行两程序。真实删除记录为：

| 删除原结果中的元素 | 正确答案 | 错误答案 |
| --- | --- | --- |
| 17 | 19 | 19 |
| -3 | 36 | 36 |
| 19 | 17 | 17 |

这证明该结果在确定判断程序、当前 LF 粒度下是 1-minimal。MoonReduce 不承诺全局最短、按数值缩小元素或解决随机故障。此处 98 次是 CLI 内调用，额外复验／审计次数单独记录，未计作工具隐藏调用。
