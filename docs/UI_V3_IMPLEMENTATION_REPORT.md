# WorkThread v3 UI 实施报告

日期：2026-11-06。用户已确认 v3 样板并授权落实到正式项目及同步 GitHub。本轮为源码 UI 更新，不替换此前通过验收的 rc3 Windows 安装包。

## 实施范围

- 五个正式页面采用已确认的深蓝导航、白色工作面、玫红强调、浅色邮件与知识对象列表及有方向性的右侧抽屉。移除账户头像、个人工作空间标识和宣传性说明。
- 总览数字使用紧凑布局，可点击进入与数字口径一致的事项筛选；合并记录、已取消事项不会被误计为待推进或优先处理。
- To Do 非模态详情支持直接切换左侧事项，按事项 ID 保留当前会话内未保存输入；异步响应不能覆盖较新的选择，保存仍使用原 revision 校验。刷新页面会丢弃未保存的输入。
- 宽屏邮件列表、原文与回复草稿并排，阅读区独立滚动；窄屏纵向排列。保留多份草稿、复制正文、全文检索、相关会话、确认建议等既有业务能力。
- 草稿反馈入口增加点按面积；草稿与修改意见使用内侧焦点边框。邮件、To Do、知识搜索均取消焦点高亮，保留光标。导航折叠只淡出文字，图标位置固定，支持减少动效设置。
- 所有保存操作接回原 Python API、CSRF、SQLite 与并发校验，不携带样板模拟数据或模拟成功逻辑。

## AI 队列的真实含义

“加入 AI 分析队列”只写入待处理 JSON，仍需 WorkBuddy 执行及 Python 导入回执。

新增 `POST /api/v1/drafts/<draft_id>/queue`，只为所选已保存草稿创建待处理任务。输入中的 `context.draft_rewrite` 包含精确草稿 ID、原邮件、草稿 revision、正文及该草稿反馈；已分析或较早的邮件也可重新入队。相同保存版本及反馈的 pending 任务复用，新增反馈或保存新版本产生新的快照。普通分析队列和专门重写队列不会相互替代。未保存的草稿或修改意见须先保存，界面不会暗中提交。

无模型调用、自动发信或新增定时任务。没有数据库结构或 Schema 版本变化；新增上下文字段符合现有开放式 context 定义。三个 WorkBuddy Skills 与部署机制保持原样。真实客户端是否处理该新增上下文仍需实际 WorkBuddy 验证，本轮不将合成结果导入称为真实 AI 验收。

## 验证

| 项目 | 结果 |
|---|---|
| Python 自动测试 | 146 通过，含原有 142 项及 4 项重写队列回归 |
| Chromium 浏览器检查 | 106 项通过，使用真实 Flask API 与可销毁的合成空间 |
| 屏宽 | 1920、1440、1024、800、390；五页无横向溢出 |
| To Do | 统计筛选、日期必填/无限期、新建保存、连续切换、输入保留、响应乱序、revision 冲突、Progress Log、键盘操作 |
| 邮件和知识 | 保存草稿、反馈绑定、真实 pending JSON、未保存内容保护、全文检索、知识保存及三个作用域 |
| ZIP | 合成空间下载、预览、恢复、网页重载数据一致；损坏 ZIP 拒绝且数据不变 |
| 焦点与动效 | 所有搜索无高亮；两个邮件文本区内侧边框；五种宽度逐帧检查导航图标无位移 |
| 静态检查 | JavaScript 语法、Git diff 空白检查、新增 Python 工具及测试 lint 通过 |

浏览器可复现命令：`python scripts/check_ui.py --node <node> --playwright <playwright-module> --browser <chromium-executable> --output <evidence-directory>`。该脚本自行创建临时合成工作空间和 loopback Flask 服务，结束后关闭并移除；不接受现有业务空间作为测试目标。Node/Playwright 仅是开发测试依赖，不引入应用运行依赖。

本轮本地证据：`.runtime/ui-v3-implementation/tests.xml`、`browser/results.json`、五页桌面/窄屏截图和 To Do 抽屉截图。临时 ZIP、日志、数据库和截图均不上传。

## Git 提交边界

以远端 rc3 `66fea8f746963561268382b6ab3735eefdc0704f` 为基线，新建 `codex/workthread-ui-v3` 分支。提交前重新检查远端基线未变化，以 base tree 保留远端额外文件；只应用下列 11 个文件，不推送根目录旧的本地历史，不修改 main 或既有 rc3 分支。

1. `src/workthread/web/templates/index.html`
2. `src/workthread/web/static/app.css`
3. `src/workthread/web/static/app.js`
4. `src/workthread/ai.py`
5. `src/workthread/server.py`
6. `scripts/check_ui.py`
7. `scripts/check_ui.cjs`
8. `tests/test_ui_queue.py`
9. `docs/UI_GUIDELINES.md`
10. `docs/UI_V3_IMPLEMENTATION_REPORT.md`
11. `README.md`

根工作区原始 HEAD、索引及其他未完成修改保留；本轮修改前副本位于 `.runtime/ui-v3-implementation/baseline/`。最终提交 SHA 与远端核验结果记录在本地 `publication.json` 并在交付消息提供，避免在提交内部自引用 SHA。

## 限制和后续边界

本轮未运行 Windows 真机或真实 WorkBuddy；未读取旧版 Shelley 项目、连接真实邮箱、创建正式计划、修改真实业务数据或发布 Release。现有 push 工作流会在新分支触发 Windows 候选 CI，其结果属于该提交的构建验证，不代表真机安装验收。已交付 rc3 离线安装包仍是原始构建，不自动替换成新 UI 版本。
