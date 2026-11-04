# WorkBuddy 真实集成测试结果

日期：2026-11-04（Asia/Shanghai）。客户端：Mac WorkBuddy 5.9.3 / Hy3。工作空间：`.runtime/rc-workbuddy/agent-workspace`，完全合成数据；Python 回环服务 8766。未改旧版项目、未接真实邮箱、未启用定时任务。

## 实际结果

| 验证项 | 证据与结论 |
|---|---|
| 新会话规则与 Skill | UI 打开并信任独立目录；两个不同任务分别读取 CODEBUDDY.md、规则、Schema，并发现／加载 workthread-analysis。第二会话工具过程显示查找 Skill，完成报告记录 Skill 调用。主动重载流程通过；不把模型关于“自动注入”的自报等同于客户端内部调试证明。 |
| Python 输入 → 真实模型 | 第一任务 8f5e35cc-a910-481e-8516-263fb2135a49，Python 创建快照，真实 WorkBuddy 读取、分析并原子发布输出；未运行 simulate。 |
| 标准结果 → Python | 第一结果包含 4 个操作；Python Schema、证据及版本校验通过，回执 completed。原始真实结果：artifacts/rc-real-workbuddy-result.json；数据库 ai_jobs.result_json 与原始结果一致。 |
| 网页显示 | 对应检查清单邮件显示真实生成的长主题与英文草稿；设置刷新显示已完成。截图 rc-real-draft-ui.png、rc-real-receipts-ui.png。 |
| 重复安全 | 重放同一真实结果返回 duplicate=true；todos、progress_logs、drafts、analyses、ai_operations 数量均不变。artifacts/rc-real-duplicate.json。 |
| 全新会话继续 | 离开第一聊天，新建第二任务并重新选择同一空间，不读取旧聊天；独立处理 ff7e80a1-5710-4eaf-8b19-ccde1df96c4b，覆盖三个待办，输出 7 个合法操作。新会话重载能力通过；未测试杀死／重启整个 WorkBuddy 进程。 |
| 真实过期结果拒绝 | 第二会话按验收指令只写 .json.pending 并停止。外部 Python 随后用 Store.edit_todo 将合成事项 revision 2→3，再原子发布这份真实旧快照；后台拒绝，回执 superseded / stale todo snapshot，7 个操作全部未写入，五类业务计数不变。原始第二结果与前后计数：rc-real-second-result.json、rc-real-stale.json。网页刷新显示已过期。 |

## 实际发现与修正

分析 Skill 的规则路径原写 rules/workthread.md，与实际 .codebuddy/rules/workthread.md 不符，已修正模板。两个测试任务均显式指定正确路径；当前冻结包资源逐字节校验包含修正。

第一份草稿在无材料证据时使用“attached/linked”及占位链接，内容质量不通过，虽 Schema／技术消费成功也不算内容正确。已补充规则：禁止虚构已有附件、已完成动作或确定日期。第二份真实草稿写“checklist is being prepared”，未再虚构附件／链接；本次特定问题复验通过，仍需人工审核承诺、时点和事实，不保证模型永不出错。第二结果故意以过期快照拒绝，未将它冒充成功入库。

输入压缩 JSON 被客户端 Read 工具截断，两会话通过本空间只读 Python 解析获得完整上下文。用时约 4m56s 与 6m47s；该客户端与模型速度不代表未来任务耗时。未增加额外服务或改变文件交换契约。

## 仍须外部验收

Windows WorkBuddy 的项目加载、权限、路径、无人值守、睡眠与补跑；正式每天任务默认禁用。本次只证明 Mac 手动触发的两个真实合成会话。CODEBUDDY.md 规定的目录边界是项目规则，不能等同 OS 级沙箱：UI 当前允许完全访问，模型按指令限制访问，未证明客户端可实施强制文件隔离。

最短复验：新会话选择 agent-workspace → 加载 workthread-analysis → 处理 Python 准备的 pending 输入 → 等 receipts/completed → 网页核对草稿、证据及人工保护。不要复制旧聊天或客户端内部调度数据库；错误结果须看 quarantine 与回执，重新 prepare，不改旧快照版本。
