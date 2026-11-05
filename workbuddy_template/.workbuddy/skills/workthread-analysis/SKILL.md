---
name: workthread-analysis
description: Analyze WorkThread mail and reconcile all open todos using versioned JSON exchange.
---
先加载 CODEBUDDY.md 和 .codebuddy/rules/workthread.md。逐个读取 exchange/inputs/*.json。读取 schemas/ai-output.json 的全部允许操作。
产生邮件工作类型、业务阶段、相关会话摘要、处理建议、英文草稿、新工作、进展与状态建议。识别客户联系人关系、项目订单关系和三个作用域的知识建议。
每个待办都纳入 reviewed_todo_ids。明确邮件证据才能支持实际动作完成。人工保护字段只能建议。输出临时 JSON，完成后原子改名；由 Python 导入并返回回执。
无新邮件时仍检查未关闭待办，不能重复制造相同任务。历史任务 historical=true 的新增事项交人工激活。


rc2 接口补充：遵守 CODEBUDDY.md 中统一截止日期规则。缺少明确日期时先确认，不提交 due_date=null 且 no_due_date=false 的新事项；不得默认无限期。intake 和 AI create_todo / normalize_todo 均支持 due_date 与 no_due_date。已有业务职责、证据和回执规则继续适用。
