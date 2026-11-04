# WorkThread：Windows 部署与真机验收提示词

提示词 ID：WORKTHREAD-WINDOWS-DEPLOY-ACCEPT-001

这是可直接交给 Windows WorkBuddy 执行的完整任务。当前阶段只部署候选包并用合成数据验收，不连接真实邮箱、不启用正式定时任务。本页是候选验收入口；通用 WORKBUDDY_SETUP.md 中的真实邮箱、每日任务、正式迁移和未来 Release 章节，本轮不执行。

## 目标与完成标准

请作为本机部署与验收助手，先检查环境，再完成下载校验、安装启动、项目规则与 Skills 加载、合成业务操作、真实 AI 文件交换，以及两类加密备份的独立恢复。根据实际结果继续工作，失败时保留证据；不能运行或缺权限的项目明确标为“未测／受阻”，不得用预置演示数据或模拟适配器冒充真实模型结果。不得为获得 PASS 修改应用源码、数据库或测试标准。

## 固定候选包

- 私有仓库：https://github.com/MelonTse/workthread
- 成功 Windows Actions：https://github.com/MelonTse/workthread/actions/runs/41854817225
- Artifact：https://github.com/MelonTse/workthread/actions/runs/41854817225/artifacts/13337625059
- Artifact 名称：WorkThread-windows-candidate；ID：13337625059。
- 程序包：WorkThread-1.0.0rc1-windows-x64.zip；版本：1.0.0rc1；18,648,190 字节。
- **程序 ZIP SHA-256**：`699503f38372cf20c6c9b855b26f82934d30f7dfae94f19d7eda4e8e634f5c1c`
- 包源码提交：`064972b5622406d38f78c32aeccfd4a15ff3d192`。本文档所在提交可以晚于包源码提交，不能把文档更新当成程序更新。
- Artifact 外层 ZIP SHA-256：`8b652f9bf9c096840bfc8741477739ee13d725dfd8a4e4fd12652fc941f88826`。它与程序 ZIP 是两种文件，不能混用校验值。
- 当前记录的 Artifact 过期时间为 2027-02-02 23:09:35（Asia/Shanghai）。若失效、包缺失或哈希不符，停止安装并请求重新确认候选构建；不要自动换成同名“最新版”。

GitHub Windows Server 2022 x64 runner 已通过 49 项自动测试、原生打包和冻结 EXE 冒烟。这不等于这台 Windows 用户电脑已通过验收。

## 工作边界

1. 只操作用户选择的新部署目录、新合成验收目录、新恢复目录及独立备份位置。已有同名目录含文件时先报告并选择新位置，不覆盖。不得读取旧版 Shelley 项目、历史邮件、业务资料或其他工作空间。
2. 不配置真实 IMAP 账号，不输入邮箱授权码，不同步真实邮箱，不发送邮件，不启用 WorkBuddy 或 Windows 正式定时任务、登录启动或后台同步。不要访问真实客户资料。
3. 只通过应用网页、受控 CLI 和规定 JSON 交换操作业务。不得自行打开、查询或修改 SQLite，不修改核心文件来掩盖失败。不得把数据、备份、日志、账号、Token 或验收截图上传 GitHub。
4. 使用现有正常授权下载；无私有仓库访问权限时，请用户下载上述 Artifact 或提供本地候选 ZIP、校验文件和本文档。Windows WorkBuddy 不会自动继承另一台机器或 Codex 的 GitHub 登录。不要要求把密码／Token 发到聊天，不公开仓库、不扩大其他仓库授权。
5. 不要求管理员权限、安装系统 Python／Docker 或修改全局依赖。若系统策略、Defender／SmartScreen 或权限弹窗阻碍，保留提示，请用户审核必要动作；不绕过安全保护。没有必要暂停时继续完成独立步骤。

## 一、检查、下载与校验

记录 Windows 版本／架构、WorkBuddy 版本、工作时区、端口 8765／8766 是否可用、目录可写性和剩余空间。此包仅针对 Windows x64；不把 ARM 仿真当作已验证的原生 x64 环境。端口占用时不要结束未知进程。

下载指定 Artifact，先解开外层 ZIP，取得程序 ZIP、同名 .zip.sha256 和 windows-tests.xml。若用户已提供本地文件，直接校验这些文件即可，不重复索要 GitHub 权限。

用 PowerShell `Get-FileHash -Algorithm SHA256` 校验**程序 ZIP**，结果须与上方固定值及 .zip.sha256 一致。完整解压到用户可写的新目录，保留 app 整个目录，不单独复制 EXE。不得解压覆盖已有工作台。

读取 BUILD_INFO.json，核对 version、Windows/AMD64 和上述包源码提交；按 SHA256SUMS.json 校验包内文件。JSON 明确按 UTF-8 读取；校验路径限定包内，不接受绝对路径或 `..`。核对网页资源、Schema、规则模板、Start/Health/Backup/Restore.cmd、tools 安装升级脚本、WORKBUDDY_SETUP.md 和 docs 是否齐全。任何校验不符均先停止，不改校验值。

## 二、初始化与启动

以下 PowerShell 命令从实际解压根目录执行；先核对 app\WorkThread.exe 存在。保存真实绝对路径，后续即使切换 WorkBuddy 工作空间，也不得混用相对目录：

```powershell
$WT_ROOT = (Get-Location).Path
$WT_EXE = Join-Path $WT_ROOT 'app\WorkThread.exe'
$WT_WORK = Join-Path $WT_ROOT 'workspace'
$WT_TEST = Join-Path $WT_ROOT 'acceptance'
& $WT_EXE --workspace $WT_WORK init
& $WT_EXE --workspace $WT_WORK doctor
```

每条命令检查退出码，不因看到输出就判成功。也可运行系统策略允许的 tools\install.ps1，不降低脚本执行策略。双击 Health.cmd、Start.cmd，验证空白工作台的本地网页、五个页签与静态资源能打开，仍没有邮箱账号或正式 AI 计划。

合成验收使用独立 `$WT_TEST`。在独立、持续运行的终端或可保留的后台进程中启动：

```powershell
& $WT_EXE --workspace $WT_TEST demo --port 8766 --open
```

记录该进程，后续只停止自己启动的验收进程。8766 被占用时选择其他空闲端口并记录全部实际 URL。Start.cmd 默认使用 workspace／8765，不要误把其中空白空间当作 acceptance。启动不等于创建定时任务，演示服务也不能连接真实 IMAP。

## 三、先完成网页合成操作

1. 新增两条带明显“Windows 合成验收”标记的 To Do：一条具体截止日期，一条明确无限期。确认直接打开完整表单、标题在首行、未填截止设置不能保存，保存后窗口关闭。
2. 打开详情修改标题与状态；在状态不变时连续追加两条不同 Progress Log。发生时间应默认当前工作时区时间，可手动修改。关闭再打开确认两条均保留，默认仍进入详情。
3. 查询合成邮件与相关会话，核对选中邮件只显示其对应草稿；编辑英文草稿、保存，再保存针对该草稿的反馈。检查多份草稿切换、邮件／To Do 搜索及清空。
4. 在客户范围维护一条明确的合成候选知识，搜索并重新打开；不要把候选变成已确认或错误地显示为所有客户／个人规则。
5. 记录演示空间预置的任务与草稿。设置页“模拟分析”可以单独验证 UI，但必须标为模拟；不能将它计为下面真实 WorkBuddy 成功。不要在真实结果待处理时用模拟按钮消费同一任务。

## 四、加载项目能力并验证真实 AI 交换

在 WorkBuddy 中选择 `$WT_TEST\agent-workspace`，不要选择含核心 data 的上层目录。按客户端要求由用户确认信任；不要一并授权其他项目。确认并读取：

- CODEBUDDY.md
- .codebuddy/rules/workthread.md
- .codebuddy/skills/workthread-analysis/SKILL.md
- .codebuddy/skills/workthread-intake/SKILL.md
- .codebuddy/skills/workthread-knowledge/SKILL.md
- schemas/ai-input.json、ai-output.json、intake.json

记录实际发现与调用的 Skill。目录限制首先是项目规则，不能将“模型按要求操作”谎称为操作系统强制沙箱。若客户端无法发现项目 Skill，报告路径与版本，不擅自安装全局 Skill 或挪用其他项目配置。

通过网页请求 AI 分析，或使用 `& $WT_EXE --workspace $WT_TEST ai-prepare` 取得 pending job。完整解析输入；若 Read 工具截断单行 JSON，用客户端可用的只读 JSON 解析方式读取全部内容，不凭截断片段补猜。

真实调用 workthread-analysis：遵循 Schema、覆盖 scope.todo_ids、回传原始 job_id／input_sha256／workspace_epoch，证据只能来自输入正文；人工确认不得覆盖，已回复不等于事项完成。不得虚构已有附件、已提供清单、已完成动作或确定日期；没有材料证据时不写“please find attached/linked”。

写完整临时 JSON，保留一份不以 .json 结尾的真实结果副本（例如 exchange/outputs/<job_id>.replay），再原子发布 outputs/<job_id>.json。保留原始分析结果，不用模拟适配器代替。由运行中的 Python 服务消费；必要时用 `ai-consume` 受控命令。核对 receipts/<job_id>.json 为 completed，再从网页验证对应建议、草稿和进展。无回执不算入库成功。

再验证：

1. 用 workthread-intake 从聊天添加一条合成 To Do，检查 intake 与回执及网页入库，保持原文时点和时区。
2. 用 workthread-knowledge 走同一标准分析契约提出一条有证据的客户知识候选；在网页检查对象范围及候选状态，不直接写知识表。
3. 将同一真实结果原样重放，检查 duplicate=true，To Do、日志和草稿没有重复增长；不修改 job_id 或 operation_id 来“做出”成功。
4. 为另一个新任务先生成 .pending 结果；结果生成后，通过网页人工修改该输入快照内的一个合成 To Do，再发布旧快照结果。期待 superseded／stale todo snapshot，无业务操作部分写入。不改旧版本号绕过拒绝，随后重新 prepare。
5. 离开旧聊天，在同一 agent-workspace 开一个全新会话，重新加载规则与 Skill，处理新的合成任务并核对回执。不依赖旧聊天。若无法自动切换新会话，仅请求用户完成这一 UI 动作，并给出确切继续入口。

## 五、两类加密备份与独立恢复

先在验收空间保留上述 To Do、两条进展、草稿反馈及客户知识。备份位置由用户选择，独立于应用、验收和恢复目录。备份密码至少 10 字符，由用户在本机输入和保管，不写到对话、命令参数、报告或 GitHub。

执行两类备份，可以使用 8766 验收网页；CLI 等价命令如下，输出文件路径替换成实际、尚不存在的备份路径：

```powershell
& $WT_EXE --workspace $WT_TEST backup '<独立备份位置>\todos.7z' --scope todos
& $WT_EXE --workspace $WT_TEST backup '<独立备份位置>\full.7z' --scope full
```

不要直接使用默认 Backup.cmd／Restore.cmd 测 acceptance，因为它们默认指向 workspace。不得手工复制运行中 SQLite 文件作为备份。

分别创建全新的 `$WT_ROOT\restored-todos` 与 `$WT_ROOT\restored-full` 目标，不覆盖验收源或任何已有工作空间。每份备份先使用 `restore <备份路径>` 预览校验；确认目标为空且全部数据合成后，才对**该新目标**执行相同命令并附加 `--apply`。每条命令检查退出码。没有本机密码输入能力时，请用户协助输入，不伪造恢复成功。

```powershell
$WT_TODO_RESTORE = Join-Path $WT_ROOT 'restored-todos'
$WT_FULL_RESTORE = Join-Path $WT_ROOT 'restored-full'
& $WT_EXE --workspace $WT_TODO_RESTORE restore '<独立备份位置>\todos.7z'
& $WT_EXE --workspace $WT_FULL_RESTORE restore '<独立备份位置>\full.7z'
# 仅在上述校验通过、目标为空且已确认全部合成后执行：
& $WT_EXE --workspace $WT_TODO_RESTORE restore '<独立备份位置>\todos.7z' --apply
& $WT_EXE --workspace $WT_FULL_RESTORE restore '<独立备份位置>\full.7z' --apply
```

恢复后通过受控 CLI doctor 与应用网页核对：

- To Do 独立恢复：稳定 ID、标题、具体日期／无限期、状态、两条 Progress Log 与来源／历史保留；不把客户摘要当作完整客户知识恢复。
- 完整恢复：邮件与检索、To Do／日志、草稿与反馈、客户知识候选／确认状态、规则与 Skills 保留；邮箱仍禁用，正式计划仍禁用。恢复后 workspace_epoch 变化和 pending 任务重建属于设计，不能强改旧结果版本。
- 新目标可以在独立空闲端口用 `serve --port <端口> --open` 启动。确认不再依赖原验收进程；原始数据不删除。
- 错误密码校验应失败且不改变目标；再次用正确密码仍可校验和恢复。不要为负例覆盖已有真实工作台。

## 六、重启与交付报告

停止并重启自己启动的合成验收服务，核对 To Do 与日志仍在、恢复目标可独立使用、健康检查通过。最后只保留用户需要的本地服务；停止多余验收进程，不创建常驻任务，不删除数据或备份。

在本机新建验收报告（不上传 GitHub），逐项列 PASS／FAIL／未测／受阻，包含：

- 系统、架构、WorkBuddy 版本、实际路径与端口；包版本、源码提交和 SHA-256。
- 安装、五页打开、To Do／日志、草稿反馈、客户知识、模拟 UI 与真实 AI 的分别结果。
- 三个 Skills 发现／调用、新会话、真实 job_id、completed／duplicate／superseded 回执及计数证据。
- To Do 与完整备份的实际文件位置、新恢复位置、数据核对、错误密码与重启结果；不记录密码、Cookie、CSRF、Token 或任何凭证。
- 最终分别说明“GitHub Windows runner 已通过”和“本机真机哪些项目实际通过”，不能混为一谈。把系统凭证库、真实 IMAP、正式调度及睡眠补跑列为本轮明确未测试，不影响本轮合成范围的如实结论。

若某项失败，只继续做必要、可恢复的诊断，保留错误和已完成证据；不改程序或安全设置强行通过。完成本轮合成部署验收后停止，等待用户下一条指令，不自动接入真实邮箱或启用正式定时任务。
