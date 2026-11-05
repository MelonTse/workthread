---
name: workthread-knowledge
description: Maintain scoped knowledge proposals and draft English replies from confirmed evidence.
---
使用 workthread-analysis 的输入输出流程。长期个人写作习惯、客户长期要求、项目订单一次性要求分别维护。只引用已确认知识；未经确认推断不得升级成事实。
发现新事实使用 propose_knowledge 并提供证据。产生英文草稿使用 create_draft；依据已确认风格和人工反馈，保留重要业务条件。不得直接改知识表或发送邮件。


rc2 接口补充：遵守 CODEBUDDY.md 中统一截止日期规则。缺少明确日期时先确认，不提交 due_date=null 且 no_due_date=false 的新事项；不得默认无限期。intake 和 AI create_todo / normalize_todo 均支持 due_date 与 no_due_date。已有业务职责、证据和回执规则继续适用。
