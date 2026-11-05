# Goal002 G1：Skills 模板与初始化验收

**PASS（仅 Mac 文件部署与初始化）**。**Windows WorkBuddy 发现/调用：未验证。** 没有修改客户端程序、缓存或全局 Skills，没有通过人工读取文件模拟调用。

## 模板

项目根 CODEBUDDY.md，规则 .codebuddy/rules/workthread.md，三个独立技能位于：

- .workbuddy/skills/workthread-analysis/SKILL.md
- .workbuddy/skills/workthread-intake/SKILL.md
- .workbuddy/skills/workthread-knowledge/SKILL.md

原三个 Skill 的完整 frontmatter 和业务正文均保留为字节前缀，仅附加 rc2 截止接口说明；原始前缀长度及 SHA-256 记录在 `.workthread-template.json`，自动测试逐一核对。测试使用固定 rc1 合成项目模板 fixture，不依赖未来改变后的 Git HEAD，因此提交后仍可复现。

CODEBUDDY.md 已明确三个职责映射、按内容自动选择、不可用时报告工作空间/信任/启用/目录问题、不冒充调用、两个独立会话验证和 Python 回执要求。缺日期不能默认无限期。

## 初始化

Install.cmd 与 PowerShell 安装脚本分别对 workspace、acceptance 执行 init/doctor；不播种演示数据。单空间 init 只初始化明确指定目录，不擅自触碰其他空间。

每个空间自动部署 8 个业务文件（CODEBUDDY + 项目规则 + 3 Skills + 3 Schema）、5 个 exchange 目录及版本登记。缺失创建、当前跳过、已知未改动版本更新；自定义规则/Skills/Schema 保留，新模板另存候选。报告列每个文件状态、SHA、模板版本、冲突和 ready。冲突 init 返回 2，不静默覆盖。原 .codebuddy/skills 内容不自动删除，可能的同名客户端优先级需真机审核。

5 项专项测试全部通过：双空间/空白/幂等/独立性、自定义保护及人工合并、已知 rc1 更新及旧自定义文件保留、三原 Skill 内容指纹、CLI 部署报告/冲突退出码。

另实际初始化 `.runtime/goal002-g1/init-check/workspace` 和 `acceptance`：均 ready=true、8 文件，To Do/邮件/账号均为 0，AI 正式计划禁用；workspace_id 不同。报告保存在 `init-workspace.json`、`init-acceptance.json`、`local-acceptance.json`。

## 证据边界

截至 2026-11-05，官方[项目配置文档](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Project)仍列 .codebuddy/skills 的代码开发兼容配置。这里按用户给出的 WorkBuddy 5.9.3 Windows 目标优先部署 .workbuddy/skills；官方当前页面不是该历史客户端版本的发现保证。

G5 必须分别提供项目规则加载、客户端实际 Skill 列表/注册记录、每个真实调用、新会话和 Python 入库回执。Mac 文件存在或规则文字不构成这些证据。

部署文档已明确通过 GUI Open Folder 选择合成 `F:\WorkThread\acceptance\agent-workspace` 并确认信任；正式目录为 `F:\WorkThread\workspace\agent-workspace`，不得选 `F:\WorkThread-Offline-Deploy-V2` 资料目录。当前没有创建客户端会话或任务。
