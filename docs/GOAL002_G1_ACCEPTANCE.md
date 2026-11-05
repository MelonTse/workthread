# WORKTHREAD-GOAL-002：G1 本地修改与验收报告

记录时间：2026-11-05 16:57:06 CST。

**阶段 G1：PASS（仅 Mac 源码、浏览器、独立合成目录及 Windows 10 静态范围）。已达到本地闸门条件，等待用户审核。**

授权：WORKTHREAD-GOAL-002-G1-APPROVAL-001，仅 G1。没有执行 G2 独立构建或发布审核，没有新提交、GitHub 推送、Windows Actions、离线包制作/传输、真实邮箱或定时任务。

## 1. 主要结果

| 必要条件 | 结论及证据 |
|---|---|
| To Do 四种日期组合 | PASS：7 类写入入口 × 4 组合，另有错误日期、事务回滚、时区、模糊及人工保护回归 |
| 新建/编辑/AI 一致 | PASS：core.validate_deadline 公共规则；HTML 使用同一 POST/PATCH 服务端；AI create/normalize、intake 与人工接受历史建议覆盖 |
| 普通 ZIP 无密码创建/预览/恢复 | PASS：HTTP/CLI/浏览器两种 scope；标准 ZIP、SHA、CRC、清单、系统 unzip 均验证 |
| 损坏及错误备份不破坏原数据 | PASS：负例及 9 个恢复故障点，目标逐文件指纹/原备份保持；优先完成此安全检查后才执行其他恢复 |
| 三 Skills 目录与初始化 | PASS：.workbuddy/skills，保留原正文，双空间及自定义保护；不等同于客户端发现/调用 |
| 原有核心功能 | PASS：最终 129 项完整测试，包括合并、状态/日志、草稿、知识、归档、人工保护、重复/过期结果 |
| Windows 10 适配 | PASS（静态）：中文重定向 UTF-8、PS5.1/cmd 路径、双空间脚本、ZIP 路径安全及全新安装保护；真机未测 |
| 已确认 UI | CSS/HTML 模板均无改动；仅移除备份密码字段及调整 ZIP 文案、下载名和预览清单 |

## 2. 原始基线与已有修改保护

- 当前分支：codex/workthread-1.0.0rc2；HEAD：2c3838a1769ca1af9e99520ce380b1ec707b46d6，未改变。
- 原始 rc1 49 项测试基线、原始 HEAD、G0 报告及隔离快照保留。重新检查原始 62 个跟踪文件指纹全部一致。
- G1 开始验证 G0 冻结的 24 个未完成文件指纹一致，另保存 entry-files.tar/entry-diff.patch；没有 reset、丢弃或以覆盖方式绕开审阅。
- 当前源码版本统一为 1.0.0rc2；数据库 DDL 与原始基线完全相同，仍为 v2，AI 契约仍 1.0。无数据库结构变更，无新增迁移或批量历史数据改写。
- 本地 HEAD 与用户提供的已验收 Windows Commit 064972b 不同，后者不在本地对象库；未 fetch 核对。该来源问题保留给后续获批的发布审核，不混用两者证据。

## 3. 14 项失败逐项处理

入口原样重跑：35 passed、14 failed。详见 [逐项失败及缺陷审阅](GOAL002_G1_FAILURE_REVIEW.md)。

分类：旧业务规则/格式冲突、夹具未提供新规则要求的日期、旧目录/API 预期。逐项保留原核心保护断言，增加公共规则、事务、损坏和原始数据指纹负例。没有仅把期待状态改成成功或移除关键检查。

额外真实缺陷已单列：rc1 恢复清理误删、ZIP 文件/目录祖先碰撞、模糊规范化掩盖非法日期对、模拟适配器编造日期、重定向编码问题和完整项目配置漏备份。不能以“旧测试不适用”掩盖这些缺陷。

## 4. 截止日期最终规则

| due_date | no_due_date | 结果 |
|---|---|---|
| 有效 YYYY-MM-DD | false | 允许 |
| null | true | 允许 |
| null | false | 拒绝，字段/原因明确 |
| 有效 YYYY-MM-DD | true | 拒绝，字段/原因明确 |

规则在最终字段组合上生效，PATCH 合并现有值后验证。非法请求在数据库事务内失败，不写入部分来源/状态/日志。HTML 不依赖前端作为唯一校验；API 错误含 due_date/no_due_date 字段。

七类入口矩阵：HTML/API POST、HTML/API PATCH、文件 intake、CLI intake、AI create_todo、AI normalize_todo、人工接受 historical_todo。保护字段及原始 input_at/input_timezone 相对日期逻辑继续测试。模糊期限先确认，不猜无限期；模拟邮件无明确日期时仅给待确认建议，不编造测试日期写入。

历史未知日期保持原状，新开应用不批量改写，使用新版 ZIP 备份恢复也保留原记录；人工修改其事项时需补齐截止设置。这是保留历史数据，不是允许新业务输入写无效记录。

## 5. 备份安全及实际恢复

详见 [ZIP 与恢复安全报告](GOAL002_G1_BACKUP_REPORT.md)。最高优先级的异常误删问题已在原始隔离代码复现，再以 9 个实际到达的故障点核验当前实现，不接触用户原工作空间。

普通 ZIP 不需密码；保留 SQLite Backup API、JSONL 一致性、manifest v2、文件数/大小、SHA-256、CRC、路径检查、预览及回滚保护。已有目标拒绝覆盖；历史 7z 不处理。

除自动临时目录测试，还将浏览器真实下载的 Full/Todos ZIP 分别恢复到 `.runtime/goal002-g1/independent-restored/full` 与 `todos`，先预览再 apply，再 doctor；两个新位置均正常，日期事项保留 2 条进展。最新源码服务在原合成空间重启后版本 rc2、健康正常、3 条事项与 2 条目标日志保留，正式计划禁用。相关测试服务已停止。

## 6. Skills 与部署文档

详见 [Skills 模板与初始化报告](GOAL002_G1_SKILLS_REPORT.md)及 [Windows 10 静态报告](GOAL002_G1_WINDOWS10_STATIC.md)。

两个独立空间实际初始化均 ready=true，部署 8 个业务文件及必要目录；正式/验收空间的 To Do、邮件、账号均 0、workspace_id 不同、正式计划禁用。自定义规则/Skill/Schema 原样保留，新模板另存候选；init 冲突退出 2。三个 Skill 原业务正文指纹保留，不合并重写。

文档已统一以下路径与职责：F:\WorkThread-Offline-Deploy-V2 为资料；F:\WorkThread 为新程序；F:\WorkThread\workspace\agent-workspace 为正式项目；F:\WorkThread\acceptance\agent-workspace 为合成项目。要求通过 WorkBuddy GUI Open Folder 选择项目并确认信任；分别提供规则加载、可用列表、三个真实调用、新会话和入库回执。缺失报告不可用，读取 SKILL.md 不算成功。

当前部署提示词版本：WORKTHREAD-WINDOWS-DEPLOY-ACCEPT-002-G1-DRAFT，尚未填造任何 rc2 Windows Commit、Actions、安装包哈希或交付状态。

## 7. 自动测试、浏览器与静态检查

完整测试命令：

```sh
.venv/bin/python -m pytest -q --junitxml=.runtime/goal002-g1/all-tests.xml
```

实际结果：**129 passed in 4.03s；0 failures、0 errors、0 skipped**。

| 测试模块 | 项数 |
|---|---:|
| tests.test_deadline_entries | 37 |
| tests.test_deadlines | 8 |
| tests.test_deployment | 5 |
| tests.test_m0 | 2 |
| tests.test_m1 | 3 |
| tests.test_m2 | 6 |
| tests.test_m3 | 6 |
| tests.test_m4 | 4 |
| tests.test_m5 | 3 |
| tests.test_mail_replies | 3 |
| tests.test_resilience | 10 |
| tests.test_restore_safety | 9 |
| tests.test_source_safety | 4 |
| tests.test_zip_backups | 29 |

其他已实际执行：Ruff E9/F 全部通过；uv lock --check 通过；git diff --check 通过。没有声称全仓所有 Ruff 风格规则通过，也没有开展无关格式重构。

浏览器（本机源码服务 127.0.0.1:18766，独立合成目录）：

- 新建未填日期保持表单、未保存；填具体日期保存并关闭；明确无限期新建成功。
- 编辑标题/状态成功；状态不变连续两条 Progress Log；Full 恢复后两条日志完整。
- 备份/恢复页无密码字段；两类 ZIP 下载、上传预览和实际恢复成功；预览显示文件名/大小及确认按钮。
- 邮件草稿实际保存，客户知识作用域及原有五页导航正常。浏览器未记录 error/warn。
- 系统 unzip -t 实际检查两份下载文件均返回 0；Windows Explorer 仍未测。

截图证据：

- [普通 ZIP 预览](../.runtime/goal002-g1/browser/zip-preview.jpg)
- [恢复后两条进展](../.runtime/goal002-g1/browser/restored-logs.jpg)
- [普通 ZIP 恢复完成](../.runtime/goal002-g1/browser/zip-restored.jpg)

## 8. 文件变更清单

下表为当前待审文件（包括 G0 报告及本报告）。Git D/?? 的 Skills 对应目录迁移，原始业务正文及历史基线均保留。所有改动尚未暂存/提交。当前修改只准备供人工 G1 审核，不构成提交集合批准。

| 状态 | 路径 |
|---|---|
| ` M` | `.gitignore` |
| ` M` | `README.md` |
| ` M` | `WORKBUDDY_SETUP.md` |
| ` M` | `docs/ARCHITECTURE.md` |
| ` M` | `docs/UI_GUIDELINES.md` |
| ` M` | `docs/WINDOWS_ACCEPTANCE.md` |
| ` M` | `docs/WINDOWS_QUICK_START.md` |
| ` M` | `docs/WINDOWS_WORKBUDDY_DEPLOY_PROMPT.md` |
| ` M` | `pyproject.toml` |
| ` M` | `scripts/check_source.py` |
| ` M` | `scripts/create_schemas.py` |
| ` M` | `scripts/install.ps1` |
| ` M` | `scripts/package_release.py` |
| ` M` | `scripts/portable-backup.cmd` |
| ` M` | `scripts/portable-health.cmd` |
| ` M` | `scripts/portable-restore.cmd` |
| ` M` | `scripts/portable-start.cmd` |
| ` M` | `scripts/smoke_frozen.py` |
| ` M` | `scripts/upgrade.ps1` |
| ` M` | `src/workthread/__init__.py` |
| ` M` | `src/workthread/ai.py` |
| ` M` | `src/workthread/cli.py` |
| ` M` | `src/workthread/core.py` |
| ` M` | `src/workthread/demo.py` |
| ` M` | `src/workthread/deployment.py` |
| ` M` | `src/workthread/operations.py` |
| ` M` | `src/workthread/schemas/ai-output.json` |
| ` M` | `src/workthread/schemas/intake.json` |
| ` M` | `src/workthread/server.py` |
| ` M` | `src/workthread/web/static/app.js` |
| ` M` | `tests/test_deadlines.py` |
| ` M` | `tests/test_m1.py` |
| ` M` | `tests/test_m4.py` |
| ` M` | `tests/test_m5.py` |
| ` M` | `tests/test_resilience.py` |
| ` M` | `uv.lock` |
| ` M` | `workbuddy_template/.codebuddy/rules/workthread.md` |
| ` D` | `workbuddy_template/.codebuddy/skills/workthread-analysis/SKILL.md` |
| ` D` | `workbuddy_template/.codebuddy/skills/workthread-intake/SKILL.md` |
| ` D` | `workbuddy_template/.codebuddy/skills/workthread-knowledge/SKILL.md` |
| ` M` | `workbuddy_template/CODEBUDDY.md` |
| `??` | `docs/GOAL002_BASELINE.md` |
| `??` | `docs/GOAL002_G1_BACKUP_REPORT.md` |
| `??` | `docs/GOAL002_G1_FAILURE_REVIEW.md` |
| `??` | `docs/GOAL002_G1_SKILLS_REPORT.md` |
| `??` | `docs/GOAL002_G1_WINDOWS10_STATIC.md` |
| `??` | `scripts/portable-install.cmd` |
| `??` | `tests/fixtures/rc1-project-files.json` |
| `??` | `tests/test_deadline_entries.py` |
| `??` | `tests/test_deployment.py` |
| `??` | `tests/test_restore_safety.py` |
| `??` | `tests/test_zip_backups.py` |
| `??` | `workbuddy_template/.workbuddy/skills/workthread-analysis/SKILL.md` |
| `??` | `workbuddy_template/.workbuddy/skills/workthread-intake/SKILL.md` |
| `??` | `workbuddy_template/.workbuddy/skills/workthread-knowledge/SKILL.md` |
| `??` | `workbuddy_template/.workthread-template.json` |
| `??` | `docs/GOAL002_G1_ACCEPTANCE.md` |

本地逐文件指纹与 diff 保存在 `.runtime/goal002-g1/g1-changes.json`、`g1-current-status.txt` 及相关快照；G2 获批后才对最终准备提交集合做正式敏感信息扫描和发布审阅。G1 的源码隔离用例是临时测试仓库中的门禁回归，不冒充 G2 提交审核。

## 9. 尚未验证与数据风险

- G2 未执行：最新 Mac 冻结程序、独立分发包运行、最终提交集合及发布审核。
- G3 未执行：GitHub Commit/推送、Windows runner、x64 原生 EXE、包内资源和 DLL 导入检查、候选 ZIP/SHA。
- G4 未执行：完整离线资料包制作及向 Windows 电脑传输。
- G5 未执行：Windows 10 19045、PS5.1/cmd/Explorer、Credential Manager、实际客户端规则加载、三个 Skills 列表/真实调用及新会话、真实 WorkBuddy 文件交换。
- 未测试真实 IMAP、正式定时任务、旧项目知识导入；这些也未获授权。

G1 未触碰真实业务数据，旧版 Shelley 项目未读取，用户历史 7z 未修改。已验证范围内无未修复的数据安全阻断项；真实 Windows 文件占用/权限、磁盘物理故障、断电或回滚自身二次系统失败仍无验证证据，不能泛化为零风险。

## 10. 阶段闸门审批记录

阶段：G1 — Mac 本地核心修改。

完成情况：**PASS**；本地修改、完整自动测试、浏览器、独立目录备份/恢复、Skills 初始化与 Windows 静态检查及部署文档完成。

通过项目：日期四组合及全部写入入口；两类普通 ZIP；损坏/恶意路径/事务及 9 点故障回滚；双空间与自定义保护；129 项自动测试、必要浏览器回归和最新源码重启。

失败项目：最终无失败。历史入口 14 个失败及中途定位问题已如实保留，详见审阅报告。

尚未验证项目：Mac 独立构建/发布审核、Windows 构建与真机、WorkBuddy 实际发现及调用；不将模板存在计为客户端成功。

是否存在数据风险：未触碰真实数据；恢复误删问题已复现并通过故障回归；保留真实 Windows 及系统故障的未验证边界。

下一阶段准备执行的操作：仅在明确获批后进入 G2，重新构建 Mac 程序，在全新目录运行合成业务/AI/ZIP、检查文档及准备提交内容，生成 GOAL002_MAC_ACCEPTANCE.md 和 GOAL002_RELEASE_AUDIT.md 后再次停止。G2 批准不等同于 GitHub 推送授权。

需要用户授权的事项：审核本报告和本地修改，明确批准进入 G2；当前不继续任何后续阶段。

**停止于 G1 闸门，等待用户明确回复。**
