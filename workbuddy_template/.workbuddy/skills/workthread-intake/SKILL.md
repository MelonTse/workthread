---
name: workthread-intake
description: Capture a natural-language work request into the common WorkThread todo pool.
---
不等待业务分析，立即保存用户原文。使用 schemas/intake.json：schema_version=1.0、request_id=新 UUID、raw_input=用户原文、input_at=录入时含时区的 RFC3339、input_timezone=工作时区、source_ref=当前请求的非敏感追溯标识。
保存到 exchange/intake/<request_id>.tmp，完整写入后改为 .json。日期按 input_at 解释，不用以后分析时间。不要读写数据库。Python 服务运行时会消费并在 receipts/<request_id>.json 返回 todo_id。没有回执时仅报告“请求已保存，等待入库”。

若无法确定原始请求的时间或工作时区，先请用户确认，不得用稍后分析时间冒充原始输入时点。

用户明确选择无限期时，可在 intake 中设置 no_due_date=true；未知截止日期应保留待填写，不得自动当作无限期。


rc2 接口补充：遵守 CODEBUDDY.md 中统一截止日期规则。缺少明确日期时先确认，不提交 due_date=null 且 no_due_date=false 的新事项；不得默认无限期。intake 和 AI create_todo / normalize_todo 均支持 due_date 与 no_due_date。已有业务职责、证据和回执规则继续适用。
