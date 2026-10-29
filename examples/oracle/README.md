# 可运行的错误签名 oracle 模板

[signature.py](signature.py) 是通用适配器，只启动目标、读取有界诊断并判定；没有缩减算法。MoonReduce 把候选绝对路径追加到整个命令末尾，适配器通过参数数组执行 -- 后的目标命令，候选仍是其最后一个参数。不要拼接 shell 字符串。

模板选择的同一问题是：**目标正常退出到指定状态，并在 stderr 输出指定完整字面签名行**。未知非零退出或目标崩溃不自动算该问题。适用于断言／错误签名，不承诺自动适配任意程序或识别所有崩溃。

## 从正反例运行

配套 [assertion_target.py](assertion_target.py) 为原创人工缺陷：输入允许 PUSH 整数、POP、NOP；空栈 POP 本应无操作，却输出 MOONREDUCE_EXAMPLE_ASSERT_EMPTY_POP 并正常退出 42。格式无效则退出 2 且输出 MOONREDUCE_INVALID_INPUT。不是生产 bug 发现。

在仓库根目录执行：

```sh
moon build --target native --deny-warn
moonreduce_signature_dir="$(mktemp -d)"
printf 'PUSH 7\nNOP\nPOP\nPOP\nNOP\n' > "$moonreduce_signature_dir/failing.txt"
python3 examples/oracle/signature.py --failure-exit 42 --signature MOONREDUCE_EXAMPLE_ASSERT_EMPTY_POP -- /usr/bin/python3 examples/oracle/assertion_target.py "$moonreduce_signature_dir/failing.txt"
_build/native/debug/build/cmd/moonreduce/moonreduce.exe "$moonreduce_signature_dir/failing.txt" --output "$moonreduce_signature_dir/reduced.txt" --report "$moonreduce_signature_dir/report.json" --timeout-ms 3000 -- python3 examples/oracle/signature.py --failure-exit 42 --signature MOONREDUCE_EXAMPLE_ASSERT_EMPTY_POP -- /usr/bin/python3 examples/oracle/assertion_target.py
python3 examples/oracle/signature.py --failure-exit 42 --signature MOONREDUCE_EXAMPLE_ASSERT_EMPTY_POP -- /usr/bin/python3 examples/oracle/assertion_target.py "$moonreduce_signature_dir/reduced.txt"
cat "$moonreduce_signature_dir/reduced.txt"
```

实测结果为 POP 加 LF，最终复验 Interesting，单删空文件明确 NI。负例可用 NOP 加 LF（oracle 1），格式反例可用未知命令（oracle 2）；自动回归为 `python3 scripts/check_oracle_templates.py`。

## 两套退出码与有效性责任

| 目标或执行情况 | 模板退出／判定 |
| --- | --- |
| 指定 failure-exit + 完整 stderr 签名行 | 0 / Interesting |
| 正常 0；或指定 failure-exit 但明确没有该签名 | 1 / NotInteresting |
| invalid-exit + 独立的 invalid-signature 完整行 | 2 / Unresolved，格式或业务域无效 |
| 目标内部计时器到期；签名未找到且 stderr 被截断 | 2 / Unresolved，没有足够判定证据 |
| 找不到命令／脚本、权限／IO 错误、信号终止、未知退出码、配置错误 | 3 / 执行错误，MoonReduce 以 4 停止 |

只认 invalid-exit 不够：Python 缺失脚本也可能退出 2。模板同时要求有效性签名（默认 MOONREDUCE_INVALID_INPUT，可用 --invalid-signature 指定已有解析器的完整诊断行）；无对应签名的退出 2 是执行错误。不能随意把一切解析／环境异常都映射成 U。目标没有可辨识的有效性协议时，请复用已有验证程序或参考[算法 oracle 的预先校验](../algorithm/oracle.py)，定义清楚后再接入。

stderr 只读前 4096 字节；完整行可以是 LF、CRLF 或已确定 EOF 的末行。截断的末行不会当完整签名，未找到签名时若日志截断则返回 U，避免用不完整读取证明 NI。stdout 不参与目标签名，两流直接写临时文件，退出后清理；不设磁盘配额。

--target-timeout-ms 默认 1000；建议 CLI 外层超时大于它。模板内部超时返回 2，工具记录 unresolved；只有 MoonReduce 自己的计时器到期才增加报告 timeouts。模板不会另建会话，CLI 沿用已验收的进程组清理；独立手工调用模板只回收直接目标，派生子进程的目标应自己等待，不能据此宣称沙箱隔离。

签名和预期状态必须来自实际复现。目标正常退出 137 与被信号 9 杀死不同；模板默认拒绝把信号终止当证据。需要缩减特定崩溃时，应另行识别所需信号与稳定错误签名并归一化，不能只检查任意非零退出。oracle 自身崩溃也不能作为目标 bug。原始输入只读，有效性与同一问题由调用者负责。
