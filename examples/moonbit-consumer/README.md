# 独立 MoonBit 账本消费工程

这是开发者自行运行的集成验证，没有真实外部用户采用的证据。账本重置错误是明确的人工缺陷，不是实际金融系统问题。

调用者拥有自己的 Operation 枚举（Credit、Debit、Reset）、带 id 的 Entry，以及状态回放与 Signature 分类函数。正确回放遇到 Reset 清零，故意出错的回放忽略 Reset；非法金额或无法执行的扣款为 InvalidTransaction。缩减目标是两次正常回放之间的 ResetKeptBalance 签名。

## 实际依赖接入

本工程有独立 moon.mod 和 src/moon.pkg；通过公开 moonreduce/moonreduce/core 包调用，不复制核心，不访问其私有字段或直接导入源码文件。

当前工具链实测要求现代 manifest；旧 moon.mod.json/path 配置不被接受。因此采用工具链支持的 [moon.work 本地源码解析](https://docs.moonbitlang.com/en/latest/toolchain/moon/module.html#dependency-management)：

```text
// moon.work：本工程目录与 MoonReduce 根目录是两个模块
members = [".", "../.."]
```

moon.mod 声明 moonreduce/moonreduce@0.1.0，moon.work 优先解析到本地库源码；0.1.0 是库仓库已有的源码版本元数据，**不是已经发布的注册表版本**。不要使用 moon add 从注册表安装这个未发布模块。检查实际解析：

```sh
moon -C examples/moonbit-consumer tree
moon -C examples/moonbit-consumer check src --target native --deny-warn
moon -C examples/moonbit-consumer build src --target native --deny-warn
moon -C examples/moonbit-consumer test src --target native --deny-warn
moon -C examples/moonbit-consumer run src --target native --deny-warn
moon -C examples/moonbit-consumer test src --target native --release --deny-warn
moon -C examples/moonbit-consumer run src --target native --release --deny-warn
```

tree 实际显示两个 local workspace member，并解析库的 async@0.22.4 模块依赖。消费源码只导入 core 与标准 debug，不调用文件／进程 API；模块级依赖解析仍含 async，没有宣称已拆分为零第三方依赖的独立发行包。

迁到其他目录时，只把 moon.work 的第二个成员改成库源码根路径，两个模块各自的 manifest 和公开 import 不变。check_stage4.py 实际将消费工程迁出仓库，使用空的 --target-dir 构建并运行；构建计划从库源码编译 core，接口和 core.core 均在新目录生成，没有引用作者的 _build。这是同机集成验证，不是阶段 5 的干净机器／新工具链验收。

## 调用适配

[src/main.mbt](src/main.mbt) 中的 verdict 将调用者已有的业务分类映射成三态；核心调用如下（完整可执行代码以源码为准）：

```mbt
fn verdict(entries : ReadOnlyArray[Entry]) -> @reduce.Verdict {
  match classify(entries) {
    ResetKeptBalance => Interesting
    Same => NotInteresting
    InvalidTransaction => Unresolved
  }
}

let result = @reduce.reduce(input[:], verdict)
```

Entry 不需要实现 Arbitrary 或 Shrink；Eq 仅用于示例的独立身份核对。调用者继续使用其枚举、金额和错误分类，不经过文本编码。测试和 main 复用同一示例，检查原始位置严格递增、值与原输入对应、重放仍是目标签名，以及自行构造每个单删候选都明确为 Same；不是只读内部 verified 标志。

本机 Debug／Release 真实结果：8 个 Entry → 2 个，23 次核心回调，保留原始位置 [1, 3]，对应 id=11 Credit(12)、id=13 Reset。独立回放余额为 reference=0、injected=12，两个单元素删除都 NotInteresting。反馈次数是同步核心回调数，不是 CLI 进程预算，也没有隐藏的文件最终复验。

这一案例证明可直接复用类型和业务判定；没有测量与手写循环、QuickCheck 或跨语言工具的接入时间差，不把开发者验证写成市场采用。
