# WorkThread Windows 全新部署与验收提示词（rc2 草稿）

提示词 ID：**WORKTHREAD-WINDOWS-DEPLOY-ACCEPT-002-G1-DRAFT**。

状态：G1 形成、经 G2 文档审核的部署草稿；G3 完成后填写实际构建信息，G4 批准并传输后才可执行。没有 rc2 实际包、SHA-256 或阶段授权时停止，不沿用 rc1 哈希、Commit 或历史 Actions 链接。

## 给 Windows WorkBuddy 的任务

只在本机得到 G5 合成验收授权后执行。目标：Windows 10 Professional 22H2、build 19045、x64，WorkBuddy 5.9.3，从 rc2 离线包全新安装，用合成数据验证程序、截止日期、普通 ZIP、项目规则、三个 Skills 与真实 AI 入库回执。逐项保留证据，失败如实记录；不更改应用源码或测试标准来制造 PASS。

### 1. 范围与路径

- 资料：`F:\WorkThread-Offline-Deploy-V2`，其中应包含 rc2 程序 ZIP、SHA-256、WINDOWS_BUILD_REPORT.md、WINDOWS_QUICK_START.md、WINDOWS_ACCEPTANCE.md、WORKBUDDY_SETUP.md、本提示词及 VERSION_INFO.md。
- 新程序：`F:\WorkThread`；正式数据：`F:\WorkThread\workspace`；正式 WorkBuddy 项目：`F:\WorkThread\workspace\agent-workspace`。
- 合成数据：`F:\WorkThread\acceptance`；合成验收必须打开：`F:\WorkThread\acceptance\agent-workspace`。
- 资料目录不是业务项目工作空间；不要把当前对话绑定在 `F:\WorkThread-Offline-Deploy-V2`。
- 不读取旧版 Shelley 项目，不复用 rc1 数据库，不迁移旧知识，不读取真实客户邮件，不连接真实邮箱，不发邮件，不创建正式定时任务。
- 若 F:\WorkThread 已有内容，停止安装并报告，保留所有原程序和数据。不得以覆盖或原地升级代替全新安装；得到新目录指示后统一调整全部路径。

### 2. 校验与初始化

记录系统、架构、WorkBuddy 版本、时区、磁盘空间、8765/8766 端口。不要结束未知进程或绕过系统安全策略。

读取实际 WINDOWS_BUILD_REPORT.md 和 VERSION_INFO.md，核对为获批 rc2。用 `Get-FileHash -Algorithm SHA256` 比较程序 ZIP 和校验文件；完整解压后按 UTF-8 SHA256SUMS.json 校验包内文件及 BUILD_INFO.json 的真实 Commit、Windows/AMD64。哈希不符停止，不改校验值。不索取聊天中的密码/Token，不擅自公开仓库。

在新目录运行 Install.cmd；或系统策略允许时 tools\install.ps1。每步检查退出码，不降低执行策略。两个空间均应自动创建：CODEBUDDY.md、.codebuddy/rules/workthread.md、.workbuddy/skills 下三个独立 Skills、三个 schemas 和 exchange 子目录。检查 .workthread-deployment.json 模板版本和冲突；冲突不能静默覆盖。

运行 Health.cmd、Start.cmd，正式页面只检查空白状态；合成服务另用：

```powershell
$WT_EXE = 'F:\WorkThread\app\WorkThread.exe'
$WT_TEST = 'F:\WorkThread\acceptance'
& $WT_EXE --workspace $WT_TEST demo --port 8766 --open
```

保留自己启动的进程信息。8766 被占用时只选择其他空闲端口并记录。不得用默认 Start.cmd 的正式空间录入合成数据。

### 3. 网页与服务端日期校验

新建具体日期和明确无限期两个合成 To Do；默认完整表单、保存后关闭；编辑标题、状态，保持状态不变连续追加两条进展，检查原始时点和时区。检查草稿保存、反馈绑定及客户知识作用域。

通过受控 API POST 与 PATCH 分别验证四种组合（保留 HTTP 状态、错误字段、保存前后计数）：

| due_date | no_due_date | 期待 |
|---|---|---|
| 有效 YYYY-MM-DD | false | 成功 |
| null | true | 成功 |
| null | false | HTTP 400，零写入 |
| 有效 YYYY-MM-DD | true | HTTP 400，零写入 |

仅看到网页必填提示不算服务端验收。不得直接修改 SQLite 制造测试结果。WorkBuddy intake、create_todo、normalize_todo 还须按相同规则测试；没有明确日期先确认，不自动当作无限期。

### 4. GUI 打开项目、规则与三个真实 Skills

请用户通过 **WorkBuddy GUI 的 Open Folder／打开文件夹** 选择 `F:\WorkThread\acceptance\agent-workspace`，确认对该目录的信任。检查当前绑定路径，必须是该合成项目；选择资料目录时先纠正，不从错误目录继续。

必须分别报告以下独立结果：

1. CODEBUDDY.md 与 .codebuddy/rules/workthread.md 实际加载：给出客户端证据及规则版本。
2. 实际可用 Skill 列表/注册表包含 workthread-analysis、workthread-intake、workthread-knowledge：保留每个名称的发现证据。
3. 根据自然语言任务自动选择并通过 Skill 工具分别真实调用，保留每个调用记录；不能仅指定路径读文件执行。
4. 新建独立会话，仍绑定同一 agent-workspace，重复发现与调用检查，不依赖旧聊天。

职责：邮件分析、分类、关联、英文草稿、To Do 对账调用 analysis；对话新增事项调用 intake；个人习惯、客户/项目知识调用 knowledge。不得合并三个 Skill。

若客户端列表中缺失，明确报告 Skill 不可用并停止对应调用验收，记录版本、绑定路径、信任、启用状态与目录。可继续独立的程序/备份测试。不得改 app.asar、客户端缓存或用户级全局 Skills，不把 .codebuddy/skills 当作唯一方案，不将“读取 SKILL.md 并模仿”记为成功。

### 5. 真实 AI JSON 闭环

通过合成页面请求分析或执行 `& $WT_EXE --workspace $WT_TEST ai-prepare`。读取完整 JSON，不以被截断的一行猜测；真实调用相应 Skill。输出遵循 Schema，原样回传 job_id、workspace_epoch、input_sha256，覆盖所有 reviewed_todo_ids，保留人工保护。

原子发布 outputs/<job_id>.json，保留原始输出副本；等待 Python receipts 为 completed，intake 为 saved，再核对网页数据。没有回执不算入库成功。模拟分析明确标记 SIMULATED，不能代替真实 WorkBuddy。

重复原样发布同一结果，验证 duplicate 且无重复 To Do/日志。另生成旧快照结果，先通过网页人工编辑快照中的合成事项，再发布，期待 superseded/stale 且整批业务写入回滚。不要修改版本绕过拒绝。知识提议保持候选范围；草稿不得虚构已有附件或已完成动作，不发送邮件。

### 6. 两类普通 ZIP、独立恢复和重启

网页下载或 CLI 在合成空间创建：

```powershell
& $WT_EXE --workspace $WT_TEST backup 'F:\WorkThread\backups\WorkThread-Todos-test.zip' --scope todos
& $WT_EXE --workspace $WT_TEST backup 'F:\WorkThread\backups\WorkThread-Full-test.zip' --scope full
```

不应有密码框、密码参数或 getpass 交互；由普通 ZIP 工具列出并解压到新的临时目录，确认 manifest v2、文件数/大小、SHA-256。不直接复制活动数据库。历史 todos.7z/full.7z 原样保留，不转换或猜密码。

先核对 `F:\WorkThread\restored-todos`、`F:\WorkThread\restored-full` 尚不存在，再分别执行受控 CLI `--workspace <新目标> restore <对应ZIP>` 预览，核对文件清单后附 `--apply`。两个目标不可混用；原验收空间和原备份保留。Restore.cmd 也要求新目录并先预览。

验证 To Do ID、状态、日期/无限期、来源、两条进展；Full 还包括邮件/检索、草稿/反馈、客户知识、规则及 Skills。邮箱/计划仍禁用，epoch 更新，旧结果失效。新目标独立 serve/doctor，停止再启动自己创建的测试进程，确认数据保留。

损坏 ZIP、错误 manifest、路径穿越只在备份的独立合成副本测试，期待明确失败且目标指纹/业务数据不变。不得在正式空间注入故障或覆盖原备份。

### 7. 真机报告与停止

生成本机 G5 报告，逐项 PASS/FAIL/未测/BLOCKED，包括系统版本、实际路径、程序版本/真实 Commit/SHA、命令退出码、日期四组合、两类 ZIP 与新恢复位置、重启数据、两个空间隔离、规则加载证据、每个 Skill 的可用列表和真实调用证据、新会话、completed/saved/duplicate/superseded 回执。不要记录凭证或上传业务资料到 GitHub。

区分“CI 构建成功”“Mac 模板存在”“Windows 客户端实际发现”“真实调用”“Python 入库”。失败时停止相应验收，不伪装通过。完成后停止，等待用户最终闸门；不自动接入真实 IMAP、不启用正式调度。
