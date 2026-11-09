# 邮件草稿双模式 · 第一阶段本地验收

本地分支为 `feature/rc4-mail-draft-ai`，基线为已发布的 `v1.0.0rc4`（`b8d08dbb73c25dba347e323bfe0db420da20ac06`）。本轮沿用 rc4 数据库结构，复用草稿、反馈、任务和回执。产品代码仅扩展邮件草稿与相应设置。

## 网页怎么操作

1. 打开「设置与运行状态 → 运行与 AI → 邮件草稿」。默认选用 WorkBuddy。在邮件页点击“加入草稿生成队列”或“加入 AI 重写队列”，可查看排队状态、刷新结果或撤回等待中的任务。
2. 选择“模型 API”后，选服务商，填写该账户有权使用的模型 ID 和 API Key。保存后可点击“用合成邮件测试连接”。正式使用时密钥通过操作系统凭据库按工作空间和服务商保存。
3. 打开「邮件与业务处理」并选一封邮件，点“生成回复草稿”。生成的英文主题和正文与原文并排。展开“给这份草稿提供反馈”，保存意见后点“按反馈重写”。新稿和原稿分别保留，可通过标签切换。草稿不会自动发送。

## 实际执行

| 项目 | 环境与结果 |
|---|---|
| Python 全套 | Mac、Python 3.13，193 项通过。其中 17 项新增参数化用例，覆盖六家服务商、故障、跨模式、进程中断、重放和人工修改。 |
| rc4 网页回归 | 本机 Chrome、Playwright、临时合成工作空间，106 项检查通过。 |
| 专项网页操作 | Chrome 实际点击 WorkBuddy 入队和撤回、切换 API、保存配置、合成连接测试、生成、保存反馈、重写、切回原稿，全部通过。1440 × 900 截图四张，另检查 390 像素宽度无横向溢出。 |
| 六家 API 合约 | 每家分别通过合成连接、生成和重写。真实应用组装 HTTPS 请求，在发出前用本机固定响应替代网络。检查目的端点、请求格式、规则、发送材料、返回解析、Python 入库和回执。浏览器专项用小米 MiMo 配置，截图中的模型 ID 是测试代号。 |
| WorkBuddy 文件交换 | 实际生成任务 JSON，写入合成结果文件，使用 Python 消费并验证回执。相同结果重复导入只增加一份草稿。错误目标、额外操作、执行方不匹配和撤回后的迟到结果均被拒绝。 |
| 数据与错误处理 | 单封草稿任务排除无关客户邮件和知识、未确认知识；服务返回 401、限流、超时、拒答、截断或格式不合格时保留原数据。重写期间人工编辑会使旧结果失效。重复重写不会重复调用同一任务。API 请求中断后不会自动外发重试。 |

**证据样例**　合成邮件提供样品价格 USD 42，询问尚未确定的发运日期。浏览器保存“缩短回复，保留 USD 42。”后，新稿保留 USD 42 并写明发运日期待确认。切回原稿可见较长的初稿。这项测试验证反馈传递、版本选择和本地存储；真实模型能否持续正确理解业务约束，留待实际模型验收。

本地截图与原始测试输出位于工作树的 `artifacts/draft-stage1/`。可用 `python -m pytest -q` 重跑 Python 测试。专项浏览器脚本为 `scripts/check_draft_browser.py`，使用 `--node`、`--playwright`、`--browser`、`--output` 指定本机环境及截图目录；通用回归使用 `scripts/check_ui.py`。均在临时目录生成合成邮件。

## 接口范围与待验证项

| 设置中的服务商 | 本轮适配 | 官方参考 |
|---|---|---|
| OpenAI | Chat Completions，选择支持 JSON Schema 的模型 | [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs) |
| DeepSeek | JSON Output + 本地字段校验 | [JSON Output](https://api-docs.deepseek.com/guides/json_mode/) |
| xAI · Grok | Chat Completions，选择支持 JSON Schema 的模型 | [Structured Outputs](https://docs.x.ai/developers/model-capabilities/text/structured-outputs) |
| 智谱 · GLM | 智谱开放平台，JSON 对象 + 本地字段校验 | [结构化输出](https://docs.bigmodel.cn/cn/guide/capabilities/struct-output) |
| 腾讯混元 · HY | 混元 OpenAI 兼容端点，提示返回 JSON + 本地字段校验 | [腾讯云混元调用说明](https://cloud.tencent.com/document/product/1729/111007) |
| 小米 · MiMo | MiMo 按量 API 端点，提示返回 JSON + 本地字段校验；订阅 Token Plan 使用单独端点，本轮适配按量接口 | [小米 MiMo API 接入](https://mimo.mi.com/docs/zh-CN/quick-start/faq/api-integration) |

**待验证**　依用户选择，真实六家 API 的鉴权、具体型号的可用性、实际费用和生成质量留待配置后验证。真实 WorkBuddy 客户端 Skill 调用、Windows 端系统凭据库存取及 Windows 打包也未在本轮执行。当前代码仅提交到本地功能分支。
