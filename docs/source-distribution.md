# 本地源码交付包

[package_source.py](../scripts/package_source.py) 从已提交 Git 快照读取文件，生成 tar.gz 与 SHA-256 校验文件。默认 HEAD，可显式指定 --ref；不读取暂存区或工作区文件，不执行提交、打标签、上传或发布。包内 SOURCE_COMMIT 记录完整来源 hash，文件名使用其前 12 位。

在仓库根目录，使用已有的固定 SDK 和系统环境：

```sh
moonreduce_source_dist="$(mktemp -d)"
python3 scripts/package_source.py "$moonreduce_source_dist"
(cd "$moonreduce_source_dist" && sha256sum --check ./*.sha256)
tar -xzf "$moonreduce_source_dist"/moonreduce-source-*.tar.gz -C "$moonreduce_source_dist"
cd "$moonreduce_source_dist"/moonreduce-source-*/
cat SOURCE_COMMIT
moon build --target native --release --deny-warn
moonreduce_source_demo="$(mktemp -d)"
printf 'noise\nBUG\nmore noise\n' > "$moonreduce_source_demo/failing.txt"
_build/native/release/build/cmd/moonreduce/moonreduce.exe "$moonreduce_source_demo/failing.txt" --output "$moonreduce_source_demo/reduced.txt" --report "$moonreduce_source_demo/report.json" -- /usr/bin/python3 tests/fixtures/reduce_oracle.py contains BUG
/usr/bin/python3 tests/fixtures/reduce_oracle.py contains BUG "$moonreduce_source_demo/reduced.txt"
cat "$moonreduce_source_demo/reduced.txt"
```

实测为 21 字节到 BUG 加 LF 的 4 字节；最终复验和单删检查通过，原输入不变。它是基础链路回归，人工算法案例仍见 [algorithm](../examples/algorithm/README.md)。输出与校验文件已有时拒绝覆盖；脚本失败返回 1，成功返回 0，源仓库没有改动。解包后的源码不带 .git，不能在该目录重新从 Git 打包；请回原仓库选择来源 ref。

## 内容与可复现边界

包内包含根构建清单、README、MIT LICENSE、MoonBit 源码、示例（含本地依赖消费工程）、测试 fixture、开发脚本及交付文档。显式允许源码目录和扩展名；JSON 仅保留人工审阅的 docs/report.schema.json 与阶段 5 实际报告实录 docs/report.example.json。排除构建目录、下载依赖、缓存、.git、编辑器／凭证目录、日志、运行结果和密钥等非源码类型。未跟踪文件与未提交修改即使位于允许目录也不会进入包；选择旧 ref 时只包含该 ref 已有的功能。

选中文件必须为 Git 普通文件，不跟随符号链接或子模块；保留已提交的可执行位。源码筛选不是秘密扫描器：新增文件类型／目录要先审阅再调整允许集合，不能把凭证写入源码。归档统一 uid/gid、时间戳与 gzip 元数据，相同 commit 在不同输出目录生成的包字节相同。SHA-256 只校验完整性，不充当发布签名或可信来源认证。

新 SDK／空注册表的设置仍按 [README 固定安装和首次 moon update](../README.md#固定工具链的独立安装)。源码包不捆绑 SDK、C 编译器或 async 下载内容；后续 build 根据 moon.mod 获取精确 async@0.22.4，需要可用注册表／缓存。开发用报告校验仍需单独的 jsonschema 4.19.2，CLI 无此依赖。支持范围保持本机已验证的 WSL2 Ubuntu 26.04、Linux x86_64 Native。

## 打包回归

在原仓库根目录运行：

```sh
python3 scripts/check_source_package.py
# 可选：保留两个源码包、解包源码和实际运行结果；指定尚不存在的目录
python3 scripts/check_source_package.py --work-dir /tmp/moonreduce-source-review
```

脚本检查相同 commit 两次打包字节一致、sha256sum 通过、已有输出拒绝且内容不变、无效 ref 失败、排除规则与 Git 对象字节一致。随后在新解包目录以已有固定 SDK／注册表缓存构建 Release，实际缩减、独立复验并单删复查，失败返回非零。不读取作者工程 _build 或未跟踪文件；没有把此次源码包验证写成再次下载全新 SDK，也没有声称第三方或独立机器验收。所有产物只留在本地指定目录，默认临时目录结束时删除。
