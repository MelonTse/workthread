# WORKTHREAD-GOAL-002：G2 Mac 独立运行验收

记录时间：2026-11-05 17:29:00 CST。

**G2 Mac 独立运行：PASS；等待 G2 人工闸门批准。**

授权：WORKTHREAD-GOAL-002-G2-APPROVAL-001，仅 Mac 独立运行及发布前审核。未推送 GitHub、未运行 Windows Actions、未制作或传输 Windows 安装包。原始 rc1 HEAD/隔离快照、G0 和 G1 报告均保留。

## 1. 构建与产物来源

| 项目 | 实际结果 |
|---|---|
| 源码版本 | 1.0.0rc2 |
| 本地基线 HEAD | 2c3838a1769ca1af9e99520ce380b1ec707b46d6，未改变；rc2 尚未提交 |
| 构建机器 | macOS 27.0.1，arm64 |
| Python / PyInstaller | 3.13.18 / 6.22.3 |
| 原生文件 | Mach-O 64-bit executable arm64，非 Windows EXE |
| 完整源码自动测试 | **129 passed in 4.15s，0 failure / error / skipped** |
| 实际构建输入指纹 | `632dacb1fd23a25173ff5d2c0f72c6b7ae3e1e47b5ec56f7fdb44d9aeb082d7f` |

构建命令：

```sh
.venv/bin/python -m PyInstaller --noconfirm --clean --workpath .runtime/goal002-g2/build --distpath .runtime/goal002-g2/dist packaging/workthread.spec
```

构建退出 0。使用独立 build/dist 目录，没有覆盖原 dist/WorkThread 或 rc1 Mac ZIP。G2 没有修改 src、packaging、Schema、业务模板或依赖；仅修正文档并增加两份 G2 报告，因此该构建对应最终受审程序内容。

源码自动测试与原 G1 不混用证据：本次重新执行，日志 `.runtime/goal002-g2/source-tests.log`、JUnit `source-tests.xml`。G1 的 129 passed 报告仍按原记录保留。

## 2. 真正的独立运行条件

将完整 onedir 产物复制到：

`.runtime/goal002-g2/独立程序 中文路径/WorkThread-1.0.0rc2-macos-arm64/app/`

所有业务操作通过**复制后的原生 WorkThread 可执行文件或它的 loopback API**。运行 cwd 为单独无源码目录；子进程 PATH 仅为 `/usr/bin:/bin:/usr/sbin:/sbin`，移除 PYTHONPATH、PYTHONHOME、VIRTUAL_ENV 和动态库开发路径。CLI stdin=DEVNULL，无密码交互。未从 .venv 导入业务模块替代原生运行。

- 不传 --workspace 的 init 实际落在可执行程序上级的新 workspace，未使用用户 HOME 的真实工作空间。
- 新正式 workspace 为空：无 To Do、邮件、账号，正式 AI 计划禁用。
- 新 acceptance 独立初始化后才显式执行 demo，只有 example.org 合成邮件/账号/知识。
- 两空间的项目规则、三个 .workbuddy/skills、3 个 Schema 和 5 类交换目录均自动部署；正式空间在全部验收后仍为空。

## 3. 原生业务验收

| 原生检查 | 结果 |
|---|---|
| HTML/JS/CSS 服务及合成 seed | PASS，原生 HTTP 返回 200，3 封合成邮件及草稿/分析可见 |
| POST 日期四组合 | PASS，日期/false 与 null/true 成功，另外两种 HTTP 400，失败零写入 |
| PATCH 日期四组合 | PASS，基于当前 revision，非法组合明确拒绝且原事项完全相同 |
| 标题/状态编辑 | PASS，人工改为“G2 原生事项已编辑”与 in_progress |
| 两条 Progress Log | PASS，同状态追加两条，关闭再开及重启保持 |
| 独立正式/合成空间 | PASS，合成流程不污染正式空间 |
| 损坏备份 | PASS，独立目标拒绝截断 ZIP，数据库 SHA 不变 |
| 程序重启 | PASS，日期、状态、两条日志及人工修改完整，版本为 rc2 |

原生验收驱动及详细命令退出码保存在 `.runtime/goal002-g2/frozen_acceptance.py`、`frozen-acceptance.log`、`frozen-acceptance.json`。共 9 组集成检查、19 次受控 CLI 调用；不把它们与 129 个源码测试混加成一个测试数。

浏览器另外打开复制后的原生服务，实际看到 4 条事项、目标事项的 2 条日志、合成空间路径、已完成/过期任务及无密码 ZIP 界面。浏览器 error/warn 为 0。截图：`frozen-progress.jpg`、`frozen-runtime.jpg`、`frozen-zip-ui.jpg`。

## 4. WorkBuddy JSON 交换协议

**PASS：独立程序的文件契约、结果导入及回执。未调用真实 WorkBuddy 客户端或模型。**

本次明确标注 G2 SYNTHETIC CONTRACT FIXTURE，生成符合公开 Schema 的本地合成 JSON。不能据此宣称真实客户端 Skills 发现、调用、模型业务理解或无人值守通过。

| 步骤 | 证据 |
|---|---|
| intake 原文、原始时点与时区 | receipt=saved；todo_id `5f0fd68d-b767-482c-9ec3-ff81572a38bb`；input_at 保持 |
| ai-prepare 输入 | job 含 scope、快照、hash、epoch，读取打包 Schema 完成验证 |
| 结果原子发布、Python 入库 | job `90b582e7-d831-497e-a6f3-9c0a109271f0` → completed，duplicate=false |
| 原样重放 | 同一 job → completed，duplicate=true；To Do/日志无增量 |
| 人工修改后提交旧快照 | job `0db50b8e-8f8f-432a-a628-3d378451fb32` → superseded / stale todo snapshot；人工版本和日志不变 |

完整输入、输出副本/隔离材料与回执仅在全新合成空间；不上传 GitHub。G3/G5 需保留 Windows 原生及真实客户端证据，不能引用本表替代。

## 5. 无密码普通 ZIP 与新目录恢复

两个 scope 均使用独立程序、stdin=DEVNULL，依次创建 → 标准 zipfile 打开/CRC/SHA 清单校验 → 新目录预览 → apply → doctor → 新目标 HTTP 启动及核对 → 停止。

| Scope | ZIP 字节 | manifest 文件数 | ZIP SHA-256 |
|---|---:|---:|---|
| todos | 2560 | 1 | `280fdfcd554b51d945f9f8809209af1a27ad91076fa4ce34477fdfdb481d4d8e` |
| full | 39407 | 12 | `386a6859bdbbc0c0c9f01e00bc4c54c5fd9104208e037f0318066ce73fa56485` |

- 两个恢复目标均为此前不存在的中文/空格路径，保留 4 个事项及其全部来源、状态历史和日志。
- Full 另核对邮件、草稿、客户、项目和知识，计划/账号仍禁用，保护目录保留。
- 恢复后原 ZIP 字节完全不变。没有读取或转换用户历史 7z，也没有以复制活动 SQLite 文件代替快照。
- 截断副本在独立初始化目标实际失败，目标数据库 SHA 不变；G1 的故障注入报告继续保留，不用本次正常恢复替代 9 点安全测试。

另执行仓库现有 `scripts/smoke_frozen.py`，对复制后的原生程序完成 HTTP To Do、状态、两条日志及 Full ZIP 恢复，退出 0，日志 `ci-smoke-mac.log`。这只证明同一冒烟脚本在 Mac 工作，不等于 Windows runner 已执行。

## 6. 打包资源与本地 Mac 审阅 ZIP

网页 3 文件、Schema 3 文件、模板 6 文件（含隐藏目录及版本元数据）共 **12 个资源**与当前源码逐字节一致。包含三个独立 Skills；不是只检查一个 Schema 文件。

PyInstaller 分析有 62 条 missing/excluded 提示，包含 Windows/Linux 平台模块、类型检查属性、可选后端/扩展；已记录具体名称，原生冷启动、Schema、HTTP、文件交换及 ZIP 路径均实际运行。没有声称“零构建告警”，也没有以 Mac 运行推断 Windows DLL 完整性。Mac 系统凭证操作、其他 Mac 版本和分发签名/公证未验收。

本地 Mac ZIP（仅供 G2 审阅，不是 Windows 安装包或正式 Release）：

- 路径：`artifacts/goal002-g2/WorkThread-1.0.0rc2-macos-arm64-G2.zip`
- 大小：14,983,847 字节。
- SHA-256：`8bb6c336501da2ace466ed7621fd3cb116493abf0ba877d854e397364209c46a`。
- 包内：104 文件，SHA256SUMS.json 校验 103 个载荷文件；无数据库、邮件 JSONL、工作空间或测试回执。
- BUILD_INFO.json 区分未改变的基线 HEAD 与实际未提交构建指纹，未伪造 rc2 Commit。

系统 unzip 将该 ZIP 解压到新的 `ZIP 全新解压` 目录；103 载荷哈希全匹配、可执行权限保留。解压后的程序在 `/tmp` cwd 和系统 PATH 下独立 init/doctor 成功，版本 rc2、健康正常。证据 `archive-extraction-check.json`。

## 7. 阶段边界与停止

实际执行：Mac 原生构建、129 源码测试、复制和 ZIP 解压后独立运行、合成业务/协议/恢复/重启、打包资源和包内文件检查、浏览器取证。

仅静态/文档审核：Windows CI、Windows 10 依赖/系统 API、PowerShell/cmd、全新安装文档及 WorkBuddy 目录约定；详见 GOAL002_RELEASE_AUDIT.md。

仍须 Windows 验证：x64 EXE、19045、系统凭证库、Explorer、Defender/文件占用、实际项目规则加载、三个 Skills 列表/调用/新会话和真实 WorkBuddy 入库。

没有读取旧版 Shelley 项目、真实业务工作空间或真实客户邮件；未连接真实 IMAP、创建计划、修改 UI 或上传资料。只使用新建合成目录。测试服务均已停止，原数据及备份留存。

**G2 Mac 验收 PASS；G3 未授权，等待用户明确批准。**
