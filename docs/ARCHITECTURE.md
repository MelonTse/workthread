# 架构与数据说明

## 边界

Flask/Waitress 仅监听 127.0.0.1。原生页面通过同源 /api/v1 操作；写请求带 CSRF 和版本信息。Python 负责唯一业务写入，WorkBuddy 只读任务并输出标准操作。没有模型 API 或邮件发送接口。

模块：core.py（SQLite 领域服务、版本 1 迁移）、ai.py（JSON Schema、文件交换、对账）、mail.py（IMAP 正文分段与归档日志）、operations.py（加密备份、恢复、知识导入）、server.py（HTTP）、cli.py（本地命令与后台）、demo.py（合成适配器）。

## 数据库

schema_migrations 保存迁移版本，当前 v2 的 DDL 与迁移位于 core.py（v2 增加 no_due_date 标志）。更高版本数据库拒绝启动。外键、WAL、FULL synchronous；每个领域操作独立事务。跨平台 FileLock 对工作空间的全部数据库读写与备份、恢复加锁，支持同机 CLI 与服务协调；SQLite 事务负责提交。正式升级应先停止应用。

To Do 的 due_date 与显式 no_due_date（无限期）互斥，原始捕获可待完善，人工详情保存须明确其一。持久保存需求中全部字段，另含 raw_input、input_at、input_timezone、revision、protected_fields、completion_policy 和 merged_into_id。三入口统一调用 create_todo；人工编辑保护实际变更字段。原始录入不可编辑。相对日期解释锚定原始录入时区，歧义进入审核。

progress_logs 与 status_events 分离。日志可为零或多条，追加或更正，不覆盖。合并保留原事项 tombstone 和 origin_todo_id。简单 reply_sent 完成规则要求绑定原 Message-ID、已发送文件夹、发件账号身份和明确引用；其他业务完成须人工确认。

知识分 personal/customer/case，confirmed 与 revision 独立。候选不进入已确认知识上下文。人工反馈持久保存并加入后续任务。

## 邮件

BODY.PEEK[HEADER]＋BODYSTRUCTURE→仅允许正文 section。跳过附件、内嵌二进制、附带 message/rfc822 和带 name/filename 属性的文本。不抓 RFC822／BODY[]，不解析附件内容。原始邮件证据不包含附件 MIME 镜像。HTML 禁脚本、远程资源并清洗。

meta/YYYY-MM.jsonl 和 body/YYYY-MM.jsonl 为 UTF-8 每行 JSON；schema_version、message_id、archive_tx_id 连接。完整头、收发件显示名、回复链、来源、UID、附件元数据在 meta，正文部件与文本／HTML 在 body。月份按 INTERNALDATE UTC。重复内容新增来源事件，不复制正文。

SQLite archive_commits 先记录 prepared，再 fsync 两类文件，最后索引提交为 committed。重启补全 prepared，保留损坏尾部后修复完整前缀。月度事务 ID 扫描按文件大小和修改时间缓存，避免全量同步时每封邮件重新扫描整月文件；外部写入或恢复后重新校验。索引可从结构化归档重建；当前程序日常检索使用 SQLite 索引。UID 重置重新枚举，内容指纹识别重复；普通增量不会重抓已归档正文。

全文检索 FTS5 trigram，短词使用参数化 LIKE 回退。回复链通过 References/In-Reply-To，不以相似主题冒充确定会话。

## AI 文件

Schema 在 src/workthread/schemas，初始化复制到 agent-workspace/schemas。inputs/outputs/receipts/intake/quarantine 是正式交换目录。

任务按 20 个事项／邮件分页覆盖全部未关闭事项，优先最近 90 天尚未分析的新邮件，附相关原文、会话、日志、确认记录和已确认知识。历史批次新增待办先审核。完整覆盖清单通过后提交；错误操作整体回滚。结果哈希、操作 ID、revision 和 workspace_epoch 防重复与旧结果污染。语义与证据理解仍需真实模型验收，结构校验不能保证理解正确。

API 路由可查 server.py：To Do、日志、合并建议、邮件检索与会话、AI 排队与导入、审核、知识、草稿、反馈、账号、备份恢复和旧规则导入。所有查询参数绑定，AI 不提供 SQL。

## 一致性备份

py7zr AES 加密内容与文件头。full 包使用 sqlite3.Connection.backup，配合归档锁与副本生成同一已提交状态。待执行任务以 ai_jobs 为准，恢复重建队列并更换 epoch，旧任务不能写入。To Do 包包含来源、状态、日志及引用摘要，相同 ID 不同内容整个导入拒绝；用户可恢复至新空间后确认合并。

SQLite 在线备份与跨进程工作空间锁共同协调快照。备份暂存期间其他写入等待；大归档可能延长等待时间。加密在复制完成后进行。恢复保留原目录作为回退。
