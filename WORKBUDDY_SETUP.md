# WorkBuddy 项目部署（1.0.0rc3，本地修改候选）

当前只执行 rc3 R0 本地修复。rc3 Windows 构建、离线交付须分别获 R1/R2 闸门批准，真机安装另行批准。本文不构成安装、接入真实邮箱或启用定时任务的授权。

## 1. 环境与工作空间

目标环境：Windows 10 Professional 22H2、build 19045、x64，WorkBuddy 5.9.3。程序包内带 Python，无需系统 Python、pip、Docker 或管理员权限。Windows 11 不作为唯一适用系统。当前 Mac 检查不能替代 Windows 真机结果。

统一部署路径：

| 用途 | 路径 |
|---|---|
| 离线资料（不能作为 WorkBuddy 项目） | `F:\WorkThread-Offline-Deploy-V2` |
| 新程序根目录 | `F:\WorkThread` |
| 正式数据 | `F:\WorkThread\workspace` |
| 正式 WorkBuddy 项目 | `F:\WorkThread\workspace\agent-workspace` |
| 合成数据 | `F:\WorkThread\acceptance` |
| 合成验收 WorkBuddy 项目 | `F:\WorkThread\acceptance\agent-workspace` |

如果目标位置已有 rc1 程序或数据，停止并选择新的空目录；不解压覆盖，不自动迁移、删除或导入旧内容。`upgrade.ps1` 在 rc3 明确停止原地升级，不更改原程序和数据。

## 2. 自动初始化两个空间

取得经批准的 rc3 候选包并校验实际 SHA-256 后，在新目录完整解压，保留整个 app 目录。运行 `Install.cmd`，或在系统策略允许时运行 `tools\install.ps1`（PowerShell 5.1）；不降低执行策略。两个入口均对 workspace 和 acceptance 执行 init 与 doctor，不播种任何演示数据。

单空间等价命令（显式路径，不依赖当前目录）：

```powershell
$WT_EXE = 'F:\WorkThread\app\WorkThread.exe'
& $WT_EXE --workspace 'F:\WorkThread\workspace' init
& $WT_EXE --workspace 'F:\WorkThread\acceptance' init
```

每个 agent-workspace 自动获得：

```text
CODEBUDDY.md
.codebuddy/rules/workthread.md
.codebuddy/skills/workthread-analysis/SKILL.md
.codebuddy/skills/workthread-intake/SKILL.md
.codebuddy/skills/workthread-knowledge/SKILL.md
schemas/ai-input.json
schemas/ai-output.json
schemas/intake.json
exchange/{inputs,outputs,intake,receipts,quarantine}/
.workthread-deployment.json
```

部署报告包含模板版本、逐文件 installed/current/updated/custom_preserved、SHA-256 和冲突位置。已知原版 rc1 文件可更新；自定义规则、Skills 或 Schema 原样保留，新模板放在 `.workthread-updates/1.0.0rc3/` 供人工比较。init 遇冲突返回退出码 2，先人工合并后重试，不把有冲突的安装视为完成。旧 rc2 `.workbuddy/skills` 文件不删除、不搬动；旧 managed_files 对应文件以 legacy_files 记录 preserved/custom_preserved，新 managed_files 仅登记有效路径。旧自定义内容不自动复制到新路径；需用户人工合并。正式 `.codebuddy/skills` 的自定义内容报冲突并使 ready=false。

## 3. 在 GUI 中打开正确项目并确认信任

合成验收时，在 **WorkBuddy GUI 的 Open Folder／打开文件夹** 选择 `F:\WorkThread\acceptance\agent-workspace`，按客户端提示确认对该目录的信任。不要选择离线资料目录或包含核心数据库的上级目录。未来正式使用选择 `F:\WorkThread\workspace\agent-workspace`。

打开新会话，分别核查：

1. 项目规则实际加载，能指出当前项目及 rc3 规则版本、文件交换限制和人工保护。
2. 客户端实际可用 Skill 列表分别包含三个名称，保留列表/注册表证据。
3. 按业务语义分别实际调用三个 Skill，保留真实工具调用记录。
4. 新开独立会话，重新验证发现和自动选择；不依赖旧聊天。
5. 检查 Python completed 或 intake saved 回执，以及网页数据。

**文件存在、读取 SKILL.md、模型自报成功均不能替代第 2、3 步。** 缺失时报告“Skill 不可用”，检查工作空间、信任、启用状态及目录。不得改 app.asar、客户端缓存或全局 Skills 作为替代。

职责映射已写入 CODEBUDDY.md：邮件分析/分类/关联/英文草稿/To Do 对账调用 workthread-analysis；对话新增 To Do 调用 workthread-intake；个人习惯/客户要求/项目知识维护调用 workthread-knowledge。用户正常提问无需每次指定 Skill 名称。

目录依据：用户提供的 Windows 10 19045 / WorkBuddy 5.9.3 真机结论：rc2 的 .workbuddy/skills 无法发现，原文复制到 .codebuddy/skills 后三个 Skill 可发现、可调用且多个新会话持续可用。rc3 采用此已实测路径；未经人工修复的 rc3 原始安装包仍须另行真机验收。

## 4. 合成业务与 AI 文件交换

仅在获相应阶段授权后启动合成空间：

```powershell
& $WT_EXE --workspace 'F:\WorkThread\acceptance' demo --port 8766 --open
```

`Start.cmd` 使用正式 workspace 和端口 8765；合成 demo 服务独立使用 acceptance/8766。正式空间保持空白。演示生成的分析明确标记 SIMULATED，不算真实 WorkBuddy 证据。

网页请求分析只排队，不保证唤醒客户端。WorkBuddy 使用输入 JSON、项目规则、Schema 和对应 Skill；完整输出先写临时文件，再原子改名为 `exchange/outputs/<job_id>.json`。Python 服务消费并写 receipts；没有回执只报告等待入库。

原文、input_at、input_timezone 保留。新事项必须具有有效 due_date 且 no_due_date=false，或用户明确选 null/true；null/false 和日期/true 均拒绝。缺日期先确认，不虚构日期、不默认无限期；不明邮件建议保留为待确认文字。旧记录保留原状，人工编辑时补齐截止设置。AI 不得覆盖人工字段，不得把回复动作当作业务完结。

源包中的受控命令可使用已核对的绝对 EXE 路径：ai-prepare、ai-consume、doctor。分析工作空间只读输入/规则/Schema，向 outputs/intake 写 JSON；不直接读写数据库或其他项目。凭证不写规则，不发送邮件。

## 5. 普通 ZIP 备份与新目录恢复

两类文件默认命名 `WorkThread-Todos-日期.zip`、`WorkThread-Full-日期.zip`。网页、API、CLI 的备份、预览、恢复均无密码。`Backup.cmd` 默认创建完整 ZIP 到 workspace/backups。指定合成空间示例：

```powershell
& $WT_EXE --workspace 'F:\WorkThread\acceptance' backup 'F:\WorkThread\backups\WorkThread-Todos-test.zip' --scope todos
& $WT_EXE --workspace 'F:\WorkThread\acceptance' backup 'F:\WorkThread\backups\WorkThread-Full-test.zip' --scope full
& $WT_EXE --workspace 'F:\WorkThread\restored-full' restore 'F:\WorkThread\backups\WorkThread-Full-test.zip'
# 预览通过、核对新恢复位置后：
& $WT_EXE --workspace 'F:\WorkThread\restored-full' restore 'F:\WorkThread\backups\WorkThread-Full-test.zip' --apply
```

可用普通 ZIP 工具查看；完整备份使用 SQLite Backup API、归档锁及 JSONL 一致性检查。manifest v2 包含 SHA-256、大小、文件数；恢复先检查 ZIP、路径、manifest、哈希和数据库。完整恢复保留原目录保护副本，失败按实际处理目录回滚。邮箱与正式 AI 计划恢复后禁用，epoch 更新，旧结果失效。

优先恢复到新的空目录。`Restore.cmd` 明确要求新目标并先预览；网页恢复当前选中的空间会保留保护副本，仅在明确核对目标后操作。To Do 恢复遇不同内容同 ID 会整笔回滚。不要覆盖原备份或复制正在写入的 SQLite 文件。历史 todos.7z/full.7z 不删除、不转换、不猜密码；rc3 仅恢复新版普通 ZIP。

## 6. 阶段边界

R0 仅本地检查、路径/文档修复与测试；R1 明确批准后才能提交、推送和 Windows 构建；R2 明确批准后才能制作新 rc3 离线包。随后真机安装另行批准，必须验证未经人工复制目录的原始包、独立新会话和不透露 Skill 名称的自然语言自动选择。本轮不连接真实 IMAP、不创建正式任务、不读取旧项目，不改现有 rc2 Windows 空间。
