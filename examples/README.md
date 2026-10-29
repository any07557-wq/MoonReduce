# 使用价值与证据

两个示例均为原创、MIT 许可的人工缺陷，没有借用真实竞赛数据、未授权材料或生产 bug 经历。现有 BUG 加 LF 示例保留为基础 CLI 回归。

| 具体使用者与原流程 | 接入后的流程 | 已有运行证据 |
| --- | --- | --- |
| 算法对拍开发者：删数组元素、手改 n、运行两实现并检查相同差异 | [整数段 oracle](algorithm/README.md) 自动重建目标输入；CLI 缩减、保存、复验；外部审计逐删复查 | 96 段／310 字节 → 3 段／9 字节，98 次 CLI 判断；目标值 33/19，3 次独立单删均相等 |
| MoonBit 序列处理库开发者：已有失败操作序列、类型及错误分类，需要自动删除操作定位问题 | [独立消费工程](moonbit-consumer/README.md) 本地依赖公开核心，直接传 Entry 序列及业务回调 | 8 个账本操作 → 2 个，23 次回调；Debug／Release 与迁出目录的新产物构建、独立后置条件检查通过 |
| 解析器／任意命令行开发者 | 自行定义合法候选与同一错误签名的 oracle | 本阶段没有实际解析器案例或外部用户，场景价值待验证；不自动修复输入格式 |

这回填了阶段 0 的两个采用理由：失败文件可走完自动删除到实际复验的闭环，MoonBit 项目可直接复用有序序列核心。没有测量相对人工的效率、学习成本或迁移偏好；不据此宣称用户应放弃已有工具。

## 与已有能力的任务比较

以下于 2026-10-29 阅读一手文档，未安装第三方工具跑本案例，也未做通用性能测试。

| 工具／能力 | 与所选任务相近之处 | 本项目的接入位置与证据边界 |
| --- | --- | --- |
| [MoonBit core QuickCheck shrinking](https://mooncakes.io/docs/moonbitlang/core/quickcheck) | 已有属性生成、Shrink 候选遍历、失败后贪心收缩、过滤与尝试上限；不应把缩减说成生态空白 | 本例从已经失败的操作序列出发，提供现成的有序删除、位置身份、三态与单删证据。没有比较两者结果质量或耗时 |
| [MoonBit QuickCheck 0.14.0 的 shrinking](https://mooncakes.io/docs/moonbitlang/quickcheck@0.14.0) | 允许自定义 shrinker 和已有起点手动缩减，并非只能从随机生成开始 | 调用者也可在那里实现删除候选；本例无需 Arbitrary/Shrink 不是独有能力。这里的增量是已经实现和检查过的删除策略／证据契约 |
| [Picire](https://github.com/renatahodovan/picire/blob/master/README.rst) | Python 库与 CLI，已有按行／字符的 delta debugging、并行及遍历配置；外部 tester 可接同类数组判定 | MoonReduce 当前串行、LF 删除范围更窄；面向 MoonBit 的直接类型调用和本工具的预算／报告契约有实测。本阶段没有核验 Picire 的完整错误、复验协议或做性能比较 |
| [Lithium](https://github.com/MozillaSecurity/lithium/blob/master/README.md) | 已有 testcase 行缩减及重复单删到 1-minimal；[interestingness 模块接口](https://github.com/MozillaSecurity/lithium/blob/master/src/lithium/docs/creating-tests.md) 接收参数并返回 bool，也能定义差异判定 | 同类外部程序任务已有工具能做；本案例的 oracle 若接入 Lithium 需适配其接口。未比较其完整执行边界，不声称这些流程是 MoonReduce 首创 |

core QuickCheck 同时核对了固定工具链附带的 quickcheck/README.mbt.md、quickcheck/shrink/pkg.generated.mbti；部分 GitHub 原始文件抓取失败，不把在线最新文档等同于已在本机测试的新版本。上表是能力／接口比较，只有 MoonReduce 两个示例有本仓库运行证据。

参赛论证现在有闭环案例和 MoonBit 类型集成证据，但算法与任务本身不新；跨语言同类工具已存在，公开索引还有同名 Ag108/MoonReduce，其功能差异尚未充分核验。产品差异化仍有限，真实采用、性能优势和外部可用性仍待证明，不能把“相同算法改用 MoonBit”或已有工具的用户当作本项目的采用证据。是否获准参赛由审核决定。
