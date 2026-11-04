# WORKTHREAD-GOAL-001 执行报告

交付版本：**WorkThread／事脉 AI 工作台 1.0.0rc1**。日期：2026-11-04。

## 实际交付与验收边界

| 里程碑 | 已开发和本机证据 | 尚待外部验证 |
|---|---|---|
| M0 | Python 3.13.18 项目环境、uv.lock、SQLite v1 迁移、Schema、正式交换目录、契约测试 | WorkBuddy 真实输出 |
| M1 | 三入口统一入池、原文立即保存、全部核心字段、状态与日志、更正、合并、人工保护；自动测试和浏览器通过 | Windows 页面回归 |
| M2 | TLS IMAP、文件夹选择、MIME 正文抓取、Meta/Body、索引、增量与故障恢复；模拟 IMAP 与实际解析器形状测试通过 | 真实服务器与授权 |
| M3 | 规则和三个 Skills、分析与草稿操作、对账、三类知识、关系／项目审核、反馈、脱敏导入与撤销；模拟结果测试通过 | 真实模型理解质量、准确旧分类 |
| M4 | 五个界面、两类加密备份、预览与恢复、路径迁移、自检；自动测试与实际浏览器通过 | Windows 凭证库及跨电脑演练 |
| M5 | Windows Actions、onedir 配置、安装升级和操作入口、版本／许可／哈希清单生成器；Mac 原生包验证 | Windows runner、EXE、真机、正式发布 |

这是一份可运行、可测试的候选源码交付。**没有生成或验证 Windows EXE，也没有声称真实 WorkBuddy、真实 IMAP 或无人值守执行通过。** 官方支持的项目规则／Skills 路径已按 Plan 核对；本轮使用模拟适配器，没有操作现有 WorkBuddy 业务项目或读取其资料。

## 重要补充要求

- AI 正式默认每日一次，时间可配置；正式任务禁用。网页请求仅排队，错过任务保留 pending，手动补跑可继续。
- IMAP 周期独立，默认 15 分钟，账号默认禁用。未连接任何真实邮箱。
- 原文、原始 input_at、input_timezone、来源持久保存；相对日期锚定原始时点，歧义进入审核。邮件派生事项锚定源邮件时间。
- 人工修改受保护，AI 旧结果拒绝并产生 superseded 回执；复杂事项不会因一次回复自动完成。
- 进展日志只追加，更正保留原记录；多个邮件证据可以追溯到同一事项。
- 数据、凭证、依赖、构建及备份与 Git 隔离。已初始化本地 Git，并只暂存源码；无 remote、无推送或发布。

## 目录与文件清单

- src/workthread/core.py：版本化初始 SQLite DDL、领域服务、跨进程锁。
- src/workthread/mail.py：IMAP、MIME、JSONL、事务恢复与全文检索。
- src/workthread/ai.py、schemas/：任务、结果、intake、幂等、证据和版本校验。
- src/workthread/server.py、web/：Flask API 与五个原生网页界面。
- src/workthread/operations.py：加密备份、恢复、导入与撤销。
- src/workthread/cli.py、deployment.py、demo.py：命令行、后台、部署配置补全与合成演示。
- workbuddy_template/：CODEBUDDY.md、规则、三个项目 Skills。
- scripts/、packaging/、.github/workflows/windows.yml：本地启动、检查、打包和升级。
- README.md、WORKBUDDY_SETUP.md、docs/：开发、架构、使用、导入、测试和 Windows 验收。
- tests/：自动测试；artifacts/：本轮测试 XML、截图和本机冻结包日志（不提交）。

## 测试与已修复问题

最终自动测试：**34 passed**，见 docs/TEST_REPORT.md 和 artifacts/tests.xml。实际浏览器验证了快速录入、状态变更、两条日志、模拟 AI、草稿编辑、邮件检索、知识保存、完整备份下载与恢复。

故障测试发现并修复归档 JSON 字段顺序导致的恢复插入错误；补充跨进程备份协调、旧任务重新排队、重复 To Do 恢复的主键判定、Windows 时区数据与未确认旧实体隔离。原生包恢复试验还发现并修复了恢复后缺少 WorkBuddy Schema 副本的问题。没有把未执行测试写成成功。

## Mac 启动

```sh
cd /Users/nova/AI/Codex/workthread
./scripts/demo.command
```

当前依赖已准备。新源码环境先执行 `./scripts/bootstrap.sh`。演示地址 `http://127.0.0.1:8765`，演示目录 `.runtime/demo`，仅合成数据。正式空白源码工作空间默认位于 `~/WorkThread/workspace`，可用 --workspace 改变。

演示流程：快速录入→打开事项修改状态→两次追加日志→设置页导入模拟 AI→邮件页编辑草稿→设置页备份并预览恢复。页面不调用模型 API，不发送邮件。

## Windows 打包与后续验收

用户另行授权私有仓库后执行 Windows Actions。锁定依赖，Windows 原生构建，启动冻结程序完成 HTTP 与备份恢复冒烟，再产出 ZIP、版本、许可和哈希清单。本轮没有远程构建权限需求，也没有创建仓库。

在 Windows 11 x64 安装 WorkBuddy，解压候选包，运行安装／健康检查，加载 agent-workspace 项目配置，先以合成数据完成真实 WorkBuddy 文件交换，按 docs/WINDOWS_ACCEPTANCE.md 验收。正式每日任务最后启用。

## 未完成与待验证事项

1. Windows runner 与真机、真实跨盘符／新电脑迁移、签名与系统防护行为。
2. 真实 IMAP、系统凭证库端到端、各服务商 MIME／文件夹差异。
3. 真实 WorkBuddy 文件交换、权限、全新会话规则重载及无人值守每日任务。
4. 经授权提供的真实 11／32 分类、旧风格及知识迁入。当前只有可复用接口和合成验证。
5. GitHub 私有仓库、实际 Actions 与正式 Release，依照指令未执行。

以上是候选版明确保留的外部验收边界。没有剩余已知且被隐瞒的本机开发阻塞；后续发现失败应继续修复，不能用候选版标签替代验收。
