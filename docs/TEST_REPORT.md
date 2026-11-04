# 测试报告 · 1.0.0rc1

执行日期：2026-11-04（Asia/Shanghai）。数据全部合成。当前自动测试清单以 tests/ 和 artifacts/tests.xml 为准。

## 自动测试

初次候选版结果：**34 passed**，JUnit 记录在 artifacts/tests.xml。

运行：`.venv/bin/python -m pytest -q --junitxml=artifacts/tests.xml`。

覆盖：契约往返、错误 JSON 隔离；三入口、原文即时保存、原始时间日期解释；零／多条日志、状态不变追加、合并追溯；人工保护及旧结果拒绝；增量同步、失败 UID 重试、UID 重置去重、回复链、附件段零抓取；模拟分析和草稿；回复不代表业务完成；简单回复动作自动完成与证据；旧知识导入、撤销与未确认实体隔离；HTTP 离线操作、CSRF／Origin；两种加密备份、错误密码、重复恢复、路径变化；归档双文件半提交和损坏尾部恢复；操作整体回滚、quarantine；任务重启与重排；MIME 实际 IMAPClient 结构、文本附件和附带邮件；损坏备份；跨进程维护锁；未来版本拒绝；文件头加密；源码数据隔离；多邮件关联同一 To Do。

## Goal 的 20 项关键测试映射

| 编号 | 验证证据 |
|---|---|
| 1、2、18 | test_http_offline_capture_status_two_logs；浏览器实际快速录入 |
| 3 | test_three_intakes_and_progress、test_demo_full_bridge |
| 4 | test_contract_roundtrip；操作幂等凭据 |
| 5、6 | test_three_intakes_and_progress；浏览器连续两条日志 |
| 7、14 | test_manual_protection_and_stale_result、test_restart_recreates_pending_input_and_stale_requeues |
| 8 | test_replied_does_not_close_case_and_manual_protection |
| 9 | test_multiple_mail_evidence_links_one_todo、test_incremental_no_attachment_and_thread |
| 10、11 | test_incremental_no_attachment_and_thread、test_real_imapclient_bodydata_shape_and_bad_charset |
| 12 | test_bad_contract_is_atomic、test_operation_rollback_and_quarantine |
| 13 | test_restart_recreates_pending_input_and_stale_requeues、test_archive_power_loss_recovery_and_tail_repair |
| 15 | test_runtime_and_credential_paths_are_ignored、scripts/check_source.py；未接收真实业务数据 |
| 16 | test_backup_restore_both_different_paths_and_bad_password；浏览器完整备份与恢复 |
| 17 | 中文及空格目录恢复测试、原生包独立临时目录测试；真实 Windows 换盘符待验收 |
| 19 | test_http_ai_result_and_draft；浏览器点击模拟导入后显示建议与草稿 |
| 20 | windows.yml、workthread.spec、smoke_frozen.py、WINDOWS_ACCEPTANCE.md；Windows runner 未执行 |

## 实际浏览器交互（Mac／Codex 内置浏览器）

使用真实页面与浏览器 Playwright locator 接口执行，不是 HTML 源码静态判断：

1. 打开工作总览，确认合成邮件、项目、To Do、分析建议显示。
2. 输入“浏览器验收：明天确认合成项目进度”，提交后立即出现，截止日期为录入日次日。
3. 打开详情，将状态从待整理改为进行中并保存。
4. 连续追加“第一次进展：已核对合成资料”和“第二次进展：等待合成客户确认，保持进行中”，界面显示 2 条，状态仍进行中。
5. 设置页点击“导入模拟 AI 结果并生成草稿”，邮件页出现分析与英文草稿。
6. 搜索 inspection，显示相关邮件；编辑英文草稿并保存，出现成功提示。
7. 完整备份下载为加密 7z；通过文件选择器上传同一合成备份，预览校验通过，实际恢复成功，健康检查通过。
8. 恢复后搜索原事项仍可查询；客户和知识保留；追加个人知识成功。
9. 五个一级页面均已打开并检查，窄视口可用。截图：artifacts/workthread-mac.png。

这些为本轮交互验收记录，不是已部署的持续浏览器 CI。复制正文、所有异常路径及所有浏览器版本不在本轮实际浏览器验收范围内；核心异常路径另有自动测试。

## 原生冻结包

使用 Mac arm64 的 PyInstaller onedir 构建，再通过 scripts/smoke_frozen.py 启动二进制，校验网页、静态资源、Schema、SQLite、加密备份和恢复。最终命令输出保存在 artifacts/mac-smoke.log。这只证明 Mac 原生包，不证明 Windows EXE。

## 外部待验收

Windows CI、Windows 真机、Credential Manager、真实 IMAP 服务器、真实 WorkBuddy 规则加载和 JSON 输出、无人值守权限、每日任务及休眠补跑、新电脑离线于旧机的恢复、真实 11/32 分类迁入，均未标记通过。


## 邮件与回复布局修订 · 2026-11-04

本次完整自动测试 **37 passed**，记录为 artifacts/mail-layout-tests.xml。新增 test_mail_replies.py，验证相同主题的不同邮件按稳定 ID 隔离草稿／反馈、未知草稿拒绝写入、长主题保存，以及 AI 上下文携带反馈的草稿与邮件关联。

实际浏览器已验证：选择邮件只显示该邮件草稿；同邮件两份草稿切换时反馈分别显示；保存反馈并重新选择邮件后仍可读取；切换草稿保留未保存编辑；长主题换行且无横向溢出；搜索 inspection 后清空，邮件列表由 1 封恢复为 3 封。按问题截图宽度 1798 和正常窄视口检查，并恢复默认视口。效果截图为 artifacts/mail-reply-layout.png。

反馈使用既有 target_id 绑定 draft_id；没有数据库迁移。旧通用反馈不自动归属到某封邮件或某份草稿。


## 首屏与信息密度修订 · 2026-11-04

邮件宽屏改为原文与草稿并排，窄屏优先草稿；下拉选择改为草稿标签，支持单击及左右方向键。保存／复制位于草稿顶部，反馈默认折叠。总览指标压缩至约 60px，并移除页面标语、指标辅助语和重复提示。

实际浏览器在 1366×768 与正常窄视口验证：宽屏原文、回复区顶部均约 186px，草稿正文约 396–684px，保存按钮约 204px；无页面横向溢出。窄屏草稿优先可见。切换草稿保留未保存内容，顶部保存成功，反馈仍逐稿对应。宽屏指标高度约 64px、窄屏约 59px。

完整自动测试 37 项，结果 artifacts/compact-ui-tests.xml；截图 artifacts/mail-compact.png、artifacts/overview-compact.png。仅修改 UI，邮件／草稿／反馈数据契约保持原样。


## 全站操作流程统一及截止设置 · 2026-11-04

最终自动测试 **43 passed**（artifacts/workspace-ui-tests.xml）。新增截止日期／无限期互斥、必填校验、AI 人工保护、v1 数据库升级及旧备份兼容、人工日志默认时间等测试。

本轮实际浏览器已验证：To Do 搜索和清空、状态标签、详情默认页、原文即时保存后进入详情、截止空值拦截、具体日期及无限期保存、再次进入仍为详情；进展自动带入当前工作时区时间并正确写入，旧未知时间日志保持原样；小录入按钮约 76×36px，保存自动收起。知识按对象查询、清空、新增、编辑并保持候选／确认状态；设置分组保留未提交字段，健康检查、计划保存、备份下载及恢复校验正常。整体原则见 UI_GUIDELINES.md。

手动补记进展也已验证：将发生时间修改为前一天 09:30，输入内容后保留所选时间；写入时间仍为实际登记时间。最终 Mac 冻结包重新构建，启动、网页资源、Schema、SQLite、加密完整备份与恢复冒烟通过（artifacts/mac-smoke.log）。本轮截图为 artifacts/mail-ui.png、artifacts/todo-deadline-required.png、artifacts/knowledge-ui.png 和 artifacts/settings-ui.png。

全仓 Ruff 检查尚有 47 项提示，涉及导入排序、异常捕获和既有测试写法等（artifacts/ui-ruff.log），未标记静态检查全部通过。本次新增的两个测试文件检查通过；不扩展本轮 UI 范围进行全仓风格重构。

开发演示数据库升级前保留一致性快照于被忽略的 .runtime/migration-backups；未读取或修改旧版项目、真实邮箱或真实业务资料。Windows 实际运行仍待原验收清单。

## To Do 单步表单及紧凑详情 · 2026-11-04

完整功能测试 **45 passed**（artifacts/todo-form-tests.xml）。新增两种显式截止选择的测试：HTML 完整表单中的具体日期或无限期优先于标题内相对日期词，且人工选择受 AI 修改保护；原文捕获入口保持原有行为。

实际浏览器验证：右下角和列表顶部两个新增入口均直接打开完整表单；标题处于首行；标题、截止设置为空会拦截保存。具体日期、无限期均可一次保存入库并自动关闭窗口；已有事项编辑标题与状态后同样关闭。详情与进展间切换保留未保存字段，进展发生时间仍默认当前工作时区。

窄视口与 1366×900 宽屏检查均无详情横向溢出。截止设置为约 53px 高的紧凑横行，保留待填写提示；状态、优先级与负责人同排，宽屏客户与项目同排，保存按钮在填写内容后的右下方。截图：artifacts/todo-single-form.png、artifacts/todo-form-wide.png。浏览器未记录控制台错误或警告；已恢复默认视口。本轮未重新生成 Windows 或 Mac 发布包。

## RC 最终核验进行中 · 2026-11-04

本轮重新运行全部自动测试：45 passed in 2.99s，artifacts/rc-validation-tests.xml、rc-tests.log。独立合成空间 rc-workbuddy 的最新浏览器已完成新增、具体截止日期保存、改为无限期和进行中、连续两条 Progress Log；页面正确显示两条日志，默认工作时区当前时间。其余邮件／知识／模拟／备份恢复网页回归仍待本轮执行，不沿用旧记录冒充通过。真实 WorkBuddy 5.9.3 已启动独立合成任务并读取输入，尚待完成结果与回执。

RC 本轮补充：完整测试更新为 **49 passed in 3.22s**（包含 4 个发布隔离负例）；最终强化冻结包冒烟通过，实际执行新增、状态修改、两条进展、完整加密备份和恢复后数据检查。

最新浏览器已完成其余核心回归：邮件英文草稿编辑保存、反馈按草稿关联并显示；客户 Example 查询后添加候选知识，范围保持客户；真实 WorkBuddy 产生的草稿也已在对应邮件显示（语义问题单列，不自动判为内容正确）。另建 rc-ui 空间在 8767 执行模拟分析，出现已导入与生成草稿提示；从页面下载完整加密备份后通过文件选择器上传，校验 11 个文件，实际确认恢复成功、健康检查通过。没有用这个模拟空间冒充真实 WorkBuddy；恢复不影响 8766 的真实测试。截图 artifacts/rc-real-draft-ui.png、rc-browser-restored.png。

## RC 最终结论 · 2026-11-04

本轮核验完成，当前以 49 项自动测试、最新冻结包强化冒烟和本轮浏览器记录为准。真实第一结果 completed，重复重放计数不变；全新第二会话产生合法旧快照结果，受控人工 revision 2→3 后发布，Python 回执 superseded/stale todo snapshot，七个操作零入库，网页刷新显示已过期（artifacts/rc-real-receipts-ui.png）。第一草稿虚构附件措辞的问题及规则补强、第二真实草稿复查结果单列于 WORKBUDDY_INTEGRATION_TEST.md，不以 Schema 成功掩盖内容问题。

本地源码暂存快照与逐文件指纹见 artifacts/rc-source-manifest.json，发布准备结论见 RC_RELEASE_READINESS.md。没有 Git 提交／远程／推送／Release，未运行 Windows Actions 或真机验收，未接真实邮箱。
