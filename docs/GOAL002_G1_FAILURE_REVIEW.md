# Goal002 G1：冻结修改及 14 项失败审阅

结论：PASS。遵循 WORKTHREAD-GOAL-002-G1-APPROVAL-001，先冻结并审阅已有修改，未 reset、丢弃或覆盖原始基线。G0 的 24 个未完成文件指纹在 G1 入口全部相同；入口再次保存于 `.runtime/goal002-g1/entry-files.tar`、`entry-diff.patch`。原 HEAD 及 62 文件隔离源码仍完整。

入口原样复测：**35 passed / 14 failed**（1.60s），日志 `entry-tests.log`，JUnit `entry-tests.xml`。下表按失败测试逐项说明，后续没有通过删除保护断言制造通过。

| 原失败测试 | 分类及原因 | 处理与保留的验证 |
|---|---|---|
| test_capture_can_be_incomplete_but_human_edit_requires_deadline | 旧业务预期冲突：要求新建保存 null/false | 改为拒绝且 todos/sources/status_events 均零写入；新增全入口矩阵 |
| test_indefinite_is_explicit_exclusive_and_human_protected | 夹具冲突：先创建无日期事项才编辑无限期 | 夹具明确选择无限期；互斥、人工保护、protected_change 断言保留 |
| test_v1_migration_does_not_turn_unknown_deadline_into_indefinite | 夹具错误：迁移之后新建无日期不能证明旧记录迁移 | 在临时库构造真正已有的 v1 记录再迁移，确认原文/版本/空日期保留，非法编辑零写入，补齐后可编辑 |
| test_manual_progress_defaults_to_recording_time_but_unknown_ai_time_stays_unknown | 夹具冲突：无日期新建阻止进入日志断言 | 明确无限期；人工发生时间默认及 AI 未知时间断言原样保留 |
| test_v1_todo_backup_restores_as_pending_deadline | 旧格式能力已按需求取消；py7zr 已移除 | 新版明确拒绝 7z、原文件及目标不变；另增两类 ZIP 的历史空日期原样恢复测试 |
| test_three_intakes_and_progress | 旧 intake 夹具未提供截止日期 | 明确日期/false；原文、时区、来源、saved 回执及多日志保留，另测无效 intake 拒绝/隔离 |
| test_merge_preserves_log_and_source | 两个待合并夹具无日期 | 明确无限期；来源和日志合并追溯断言保留 |
| test_backup_restore_both_different_paths_and_bad_password | API/格式需求变化，密码参数已移除 | 两类 ZIP 在不同新路径无密码预览/恢复；预览零修改、数据及健康检查保留；损坏/哈希/manifest 负例另测 |
| test_todo_backup_reimport_is_idempotent | 同上：旧 7z 和密码调用 | 新 ZIP 无密码重复恢复，原稳定 ID 与数据计数断言保留 |
| test_cli_health_and_resources | 旧 Skill 安装目录预期 | 改查 .workbuddy/skills；新增三个文件、双空间、版本、幂等、自定义保护、真实退出码测试 |
| test_automatic_simple_reply_and_status_evidence | 邮件 To Do 夹具无日期 | 增加明确测试日期，原完成策略及已发送证据断言保留 |
| test_backup_tamper_leaves_destination_untouched | 旧密码 API；目标事项夹具也无日期 | 改 ZIP/明确无限期，保留损坏拒绝与原目标保留；新增逐文件指纹检查 |
| test_ambiguous_dates_remain_review | 旧规则允许不明确日期直接入库 | 继续断言 relative_date 返回 ambiguous，新增业务写入拒绝且不猜日期；AI 模糊规范化的非法组合另有负例 |
| test_backup_headers_are_encrypted | 旧加密能力与产品决策冲突 | 实际用 zipfile 无密码读文件头、manifest、todos.json，确认标准 ZIP 和非加密标志 |

## 真正的程序缺陷及回归诊断

不能因为上述失败主要由契约与夹具变化引起，就忽略程序安全问题。审阅及新增测试另发现/处理：

1. **rc1 恢复异常误删原目录**：在原始隔离代码和全新临时目录实际复现；数据复制失败后 config 和 agent 标记均丢失。修正仅回滚实际处理目录；9 个故障点验证原始三类目录逐文件 SHA-256、业务数据、原 ZIP 均不变。
2. **未完成 ZIP 实现的文件/目录祖先碰撞**：新增 `manifest.json/child` 与 `manifest.json` 同时入包负例最初失败（抛文件系统错误）；增加解压前碰撞检查后明确拒绝，目标零修改。
3. **规范化可能先移除 due_date 从而掩盖非法组合**：在模糊日期处理之前对显式最终组合使用公共校验；模糊建议按日期/无限期整体处理，不清掉一半设置。
4. **演示适配器任意填写固定截止日期**：撤回先前未完成实现中的编造日期，未明确日期的合成邮件仅产生待确认文字建议；模拟分析、草稿及原有人工 To Do 仍正常。新增测试防止伪造日期。
5. **Windows 重定向编码**：在 Mac 用 cp1252 重定向环境运行原始 rc1 CLI，中文路径实际触发 UnicodeEncodeError；当前 CLI 输出显式 UTF-8，新增回归通过。此模拟不是 Windows 真机验收。
6. **完整备份的项目配置覆盖不全**：备份整个 agent-workspace 配置（排除运行队列 exchange），包含自定义文件和部署登记；恢复后重建队列，保留自定义规则。
7. **初始化写入中断及冲突可见性**：模板/登记采用临时文件关闭后替换；不重写 current 文件；自定义文件保留并提供候选，init 退出 2。临时句柄关闭后再替换，避免 Windows 打开文件重命名差异。

最初恢复故障测试中，copy-agent-workspace 注入点未到达，原因是夹具的 agent 根文件未被原选择式备份收录；未删除此注入点，修正完整配置备份后到达并通过。每个故障点都断言确实触发，避免“未运行故障即算成功”。

最终完整回归：**129 passed，0 failed，0 errors，0 skipped**；包含原有合并、人工保护、重复/过期结果、草稿、知识、归档及事务保护。G1 仅本地源码测试，不延伸到 G2 独立程序或 Windows 验收。
