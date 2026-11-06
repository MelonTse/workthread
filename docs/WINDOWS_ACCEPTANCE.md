# Windows 10 rc3 全新安装验收（rc3 R0 待构建）

只有 R2 交付及另行真机/传输授权获批后，才由目标 Windows 电脑上的 WorkBuddy 执行 G5。rc2 Windows 真机路径根因由用户提供；rc3 尚未构建，当前不具备 rc3 Windows PASS 结论。不得以 rc1 原地升级、Windows runner 或 Mac 包替代真机验收。

## 环境与隔离

- [ ] Windows 10 Professional 22H2 / 19045 / x64；记录 WorkBuddy 实际版本 5.9.3、时区、可写空间、端口。
- [ ] 离线资料 `F:\WorkThread-Offline-Deploy-V2`；程序新目录 `F:\WorkThread`，已有同名内容时停止，不覆盖或删除。
- [ ] 以实际 R1 报告核对候选版本 1.0.0rc3、Commit、ZIP SHA-256、包内文件和规则资源。
- [ ] 无系统 Python、无管理员权限可初始化、启动；中文空格路径及新盘符检查。
- [ ] Install.cmd 自动初始化 `F:\WorkThread\workspace` 与 `F:\WorkThread\acceptance`。正式空间无账号、邮件、合成 To Do；两者 ID/数据隔离。

## 日期及核心业务

- [ ] API POST 和 PATCH 分别验证：日期/false 允许；null/true 允许；null/false 拒绝；日期/true 拒绝。错误含字段和原因，失败零写入。
- [ ] HTML 新建、编辑；聊天 intake、AI create_todo、normalize_todo 规则一致；人工保护及原始时点相对日期不变。
- [ ] 同状态连续两条 Progress Log；草稿与反馈对应邮件；知识保持作用域和确认状态。

## WorkBuddy（逐项独立证据）

- [ ] GUI Open Folder 选 `F:\WorkThread\acceptance\agent-workspace`，确认信任。不能选资料或 data 上级。
- [ ] 根 CODEBUDDY.md 与 .codebuddy/rules/workthread.md 实际加载，保留规则证据。
- [ ] .codebuddy/skills 内三个 Skills 出现在客户端实际可用列表，保留注册表/列表证据。
- [ ] 按自然语言业务请求分别真实调用 workthread-analysis、workthread-intake、workthread-knowledge，保留工具记录。
- [ ] 全新独立会话仍能发现及自动选择三个 Skill。读取文件或模型自报不能算 PASS。
- [ ] 真实 AI 输出入库，Python completed/saved 回执与网页一致；重复结果无重复数据，过期结果不覆盖人工版本。
- [ ] 缺失时如实报不可用，检查工作空间、信任、启用状态；不修改客户端程序、缓存或用户级 Skills。

## ZIP 与重启

- [ ] To Do、Full 都是普通 ZIP，可由文件管理器识别、列出和解压，不出现密码框或终端密码输入。
- [ ] SHA-256、manifest v2、数量/大小统计一致。ZIP 损坏、错误 manifest、路径穿越明确拒绝，目标数据不受损。
- [ ] 两类备份先预览后分别恢复到新目录；原备份、当前数据和历史 7z 保留。
- [ ] 完整恢复的保护目录可查；人为失败测试仅用独立合成副本，不对正式工作空间注入。
- [ ] 新目标与重启后 To Do、状态、日期、来源、两条进展完整；Full 邮件/草稿/知识保留，计划与邮箱仍禁用。

## 闸门结果

逐项 PASS/FAIL/未测/BLOCKED，记录命令退出码、路径、版本和证据。失败停止对应验收，不修改源码或验收标准制造通过。报告不得含凭证，不上传真实资料。

只有 G5 关键项有真机证据且最终闸门获批，才讨论真实 IMAP；当前无真实邮箱、调度、旧知识导入或传输授权。

- [ ] rc3 原始包全新初始化，无人工复制 Skills；增加不提前透露 Skill 名称的自然语言自动选择任务，并在新会话取证。
