---
description: WorkThread JSON exchange, evidence and human protection rules
alwaysApply: true
---

# 工作流

1. 读取 CODEBUDDY.md 与 schemas/ai-input.json、schemas/ai-output.json。
2. 对每个待处理输入核对 schema_version、workspace_epoch、job_id、input_sha256 原样回传。
3. context.messages、todos、human_decisions 是本轮唯一允许的业务上下文。需要更多证据时提出待确认，不自行扫描其他目录。
4. 覆盖 scope.todo_ids 所有事项，包括无变化的事项；reviewed_todo_ids 必须完整。大批任务逐文件处理。
5. 输出 outcome=completed；只使用 Schema 列出的操作。使用唯一 operation_id。todo 操作带原始 expected_revision。
6. 先写临时结果文件；完成后改名为 exchange/outputs/<job_id>.json，不包 Markdown，不写说明前后缀。由 Python 导入，读取 exchange/receipts/<job_id>.json。若无法原子改名，保留临时文件并报告，不暴露半成品。
7. 重跑读取已有回执；失败结果修订时保留任务 ID，避免重用不同内容的 operation_id。过期任务须重新生成。

# 推理规则

- 识别工作类型、业务阶段、历史沟通摘要、处理建议；客户、联系人、项目与订单关系形成建议。
- create_todo 必须有邮件证据；action_key 为同一邮件同一动作的稳定英文键。重复已有事项优先追加日志或建议关联。
- append_progress 精炼记录实际动作、等待或变化；实际发生时间不明时留空。不得改写原日志；纠错使用 corrects_log_id。
- propose_status：已回复仅证明回复动作。复杂事项未达到全部完成条件不得建议 done。cancelled、冲突和不确定情况交人工审核。
- 每条证据必须是当前任务邮件 body_text 的原文摘录，标注 message_id；禁止编造摘录。
- normalize_todo 不得修改 raw_input、input_at、input_timezone。明天、后天等锚定原始录入时间；相对含义不明时不要设置日期，提出待确认。
- suggest_link 只使用已知实体 ID；新客户、人物、企业和项目通过 suggest_relationship / suggest_case 提出，人工确认后创建。
- propose_knowledge：scope=personal/customer/case。客户规则不能扩展到全体客户，订单要求不能提升为客户长期事实。未经人工确认的历史推断保持候选。
- create_draft 输出英文邮件草稿，使用已确认个人写作习惯、客户规则、项目约束。不要声称已发出，也不要使用任何邮件发送工具。
- 回复草稿不得虚构已完成动作、已有附件、已提供清单或确定的日期。没有输入证据证明材料已准备并可提供时，使用“正在准备／待确认”等措辞；不得用占位链接搭配“please find attached/linked”伪装材料已经存在。草稿标注未发送也不能抵消正文中的无证据事实。
- 本地网页的排队按钮只生成任务。默认计划每日一次，具体时间由用户配置。正式计划默认禁用，Windows 验收后配置。错过执行后处理剩余任务，不丢弃队列。

- 反馈含 target_id 时，只针对该 draft_id 及其 message_id 的具体回复理解；参考随输入提供的 draft_subject、draft_body。不得把单份草稿的修改意见自动提升为所有客户或个人通用规则。

- 截止设置包含具体 due_date 或用户明确选择的 no_due_date=true（无限期）。未知日期先提出待确认建议，不写入无效 To Do；不得擅自推断为无限期。人工确认的截止设置作为一个整体保护。

- 按 CODEBUDDY.md 的职责映射自动调用三个独立 Skills。项目 Skills 位于 .codebuddy/skills；缺失时明确报告不可用，检查工作空间、信任、启用状态和目录。规则已加载不代表 Skills 已发现，读取文件不代表真实调用。
