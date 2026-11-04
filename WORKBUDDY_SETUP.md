# 新电脑 WorkBuddy 部署与恢复

此文档是项目部署入口，不依赖旧电脑、旧会话、固定盘符或账号姓名。

## 1. 环境检查与初始化

Windows 11 x64，当前用户可写目录，可用端口 8765、足够归档及备份空间。安装并登录官方 WorkBuddy。下载经授权的私有 Release，核对 SHA256SUMS.json，解压到可写目录。

运行 `tools/install.ps1` 或 `app/WorkThread.exe --workspace workspace init`，再运行 `Health.cmd`。不要使用管理员权限，不在 Program Files 中保存工作数据。程序自带 Python；不需要安装 pip。

已有完整备份时使用 Restore.cmd 或网页恢复，先预览后应用；保留回退目录。重新授权 IMAP，运行健康检查。先保持账号同步禁用。

## 2. 选择工作空间并加载配置

在 WorkBuddy 新建独立本地任务，选择 `<工作台>/workspace/agent-workspace`，不要选含核心 data 目录的上级。检查当前版本支持的项目配置路径。

依据当前官方项目文档，使用 `.codebuddy/rules/`、`.codebuddy/skills/<技能名>/SKILL.md` 和根 `CODEBUDDY.md`。初始化会复制规则、三个 Skills 与 JSON Schema。官方资料：https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Project

项目级配置需按客户端提示信任后加载。只允许访问指定交换目录和执行下文列出的 WorkThread 受控命令。不要为业务分析授予全磁盘访问；不要打开其他项目。如果当前客户端不能限制权限，先用合成空间验证并保留人工确认，不直接启用无人值守。

模板升级不会覆盖已存在规则。升级时比较新版本模板，备份自定义规则后人工合并，更新 rules_version；重新执行合成自检。

## 3. 一次合成自检

1. 用独立工作空间运行 `WorkThread.exe --workspace <合成空间> demo`。Mac 用 `.venv/bin/workthread --workspace .runtime/probe demo`。
2. 点击“＋ To Do”直接打开完整表单，填写“联系示例客户”与截止日期或无限期；点击右下方“保存”，确认入库且窗口关闭。
3. 网页请求分析，确认 exchange/inputs 出现完整 JSON。
4. WorkBuddy 新会话加载 workthread-analysis Skill，按本项目规则处理一个输入文件，输出临时文件，完成后原子改名为 outputs/<job_id>.json。
5. Python 服务自动消费结果；也可运行 `WorkThread.exe --workspace <合成空间> ai-consume`。
6. 核对 receipts 回执、网页新增结果、日志及草稿。再次写入同一结果，确认无重复任务或日志。
7. 人工修改 To Do 后导入旧结果，确认拒绝并标记 superseded。重新请求分析产生新任务。
8. 全新聊天再次执行，确认无需旧会话上下文。保留客户端版本、权限、日志和截图作为证据。

模拟适配器：设置页“模拟分析”，或 CLI `simulate`。**模拟通过不等于第 4、8 步真实 WorkBuddy 通过。** 2026-11-04 已在 Mac WorkBuddy 5.9.3 用独立合成空间验证真实输出、消费、重复安全、全新会话与过期拒绝，详见 WORKBUDDY_INTEGRATION_TEST.md；Windows 与正式无人值守仍须另行验收。草稿必须人工核对事实、附件是否存在及时间承诺。

## 4. 正式每日任务（默认禁用）

Windows 验收后，在 WorkBuddy 创建**本地**定时任务，工作空间指定 agent-workspace。频率每日一次，默认 09:00，可修改，时区与网页一致。不要创建云端任务，云端不能访问本机交换文件。

任务提示词建议：

> 加载 CODEBUDDY.md、workthread-analysis Skill 和 JSON Schema。先使用 WorkThread 的 ai-prepare 受控命令准备或取得 pending 任务，再处理 exchange/inputs 中未完成的任务；先检查 receipts，跳过已完成及过期实例。逐个输出标准 JSON，完整覆盖待办列表，等待 Python 导入回执。未完成队列下次继续，失败不标完成。不连接邮箱、不发送邮件、不修改核心数据库。

命令使用当前包相对位置：从 agent-workspace 运行 `../../app/WorkThread.exe --workspace .. ai-prepare`；初始化或目录结构变化后先手动验证该命令。源码开发使用项目虚拟环境的 CLI 和显式 workspace。

电脑需开机，WorkBuddy 需登录且运行，Python 网页服务需运行才能自动导入。错过执行不会清除 pending 文件。可以在 WorkBuddy 点击“立即运行”手工补跑。网页按钮仅入队，不声称能唤醒客户端。

不要复制客户端内部调度数据库。新电脑按上述步骤重建任务，正式启用前再次验收。Python 的 ai_schedule 配置只保存计划参数，不是 WorkBuddy 调度器。

## 5. 邮箱与 Python 后台

通用 IMAP over TLS，默认 993，使用邮箱授权码。设置账号保持默认禁用，凭证只存当前电脑系统凭证库。自动发现收件箱、已发送文件夹失败时，填写服务器实际文件夹名；其他文件夹按需添加。

手动同步验收后可在设置页点击“启用后台同步”开启后台轮询。间隔默认 15 分钟，与每日 AI 分析独立。后台跟随应用进程运行；关闭应用后停止。启动采用 Start.cmd，按需由用户配置登录时启动；本候选版不注册正式任务。

## 6. 故障排查

| 现象 | 检查与处理 |
|---|---|
| 页面无法打开 | Health.cmd；8765 端口占用；可使用 serve --port 更换端口 |
| 邮箱授权失败 | 重新授权码，检查主机、TLS、凭证库；不要把密码写到规则或日志 |
| 找不到已发送文件夹 | 网页填写准确名称，先手动同步 |
| 邮件部分失败 | sync_failures 保留失败 UID，下次重试；异常 MIME 不回退整封抓取 |
| 结果被拒绝 | quarantine 中错误摘要；核对 Schema、邮件证据、revision、workspace_epoch |
| superseded | 原任务已过期，重新请求分析，不篡改旧任务版本 |
| 长时间 pending | 客户端登录、工作空间、规则加载、权限等待、正式计划是否启用 |
| 恢复后不能同步 | 正常：重新授权，并明确启用账号 |
| 磁盘不足 | 清理独立备份副本或扩容后重试；不要手工删除数据库 WAL 或归档日志 |
| 升级失败 | 保留 app 回退目录，使用匹配版本与升级前加密备份恢复 |

## 7. 完整迁移验收

旧电脑离线。新电脑安装 WorkBuddy→解压程序→恢复备份→重新授权→加载规则和 Skills→重建每日任务→健康检查→合成闭环→真实邮箱小范围验收。全部通过后才开启日常运行。
