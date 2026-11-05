# WorkThread · 事脉 AI 工作台

轻量、单用户、本机运行的 AI 工作事项工作台。Python 负责持久化、IMAP 与校验；WorkBuddy 负责分析。网页无需模型 API，可独立维护 To Do 和进展日志。

当前源码候选版本：**1.0.0rc2**，G1 已验收通过，G2 Mac 独立运行及发布前审核报告已生成，等待用户审核并批准 G3；尚未获得推送及 Windows 构建授权。rc1 的历史构建和真机测试不能替代 rc2 验收。报告见 `docs/GOAL002_MAC_ACCEPTANCE.md`、`docs/GOAL002_RELEASE_AUDIT.md`，G1 报告保留。

Windows 目标：Windows 10 Professional 22H2 build 19045 x64、WorkBuddy 5.9.3。部署入口：[全新部署与真机验收提示词（G1 草稿）](docs/WINDOWS_WORKBUDDY_DEPLOY_PROMPT.md)。只用合成数据，真实邮箱与正式计划保持禁用。

## Mac 开发与合成演示

```sh
./scripts/bootstrap.sh
./scripts/demo.command
```

已有本项目环境时直接执行第二条。浏览器打开 `http://127.0.0.1:8765`。演示仅含 `example.org` 合成邮件、示例项目、待办、日志和模拟 AI 分析。演示数据在被 Git 忽略的 `.runtime/demo/`。双击 `scripts/demo.command` 也可启动。

空白工作台：`./scripts/start.command`，源码运行默认数据在 `~/WorkThread/workspace`，与源码分离。显式指定数据目录：

```sh
.venv/bin/workthread --workspace '/独立位置/工作空间' serve --open
```

源码虚拟环境与本机路径绑定；迁移源码开发环境时重新 bootstrap，不复制 `.venv`。正式 Windows 包内带运行时，无需安装 Python。系统 Python 不会被替换。

## 日常操作

- 右下角“＋ To Do”或列表顶部“新增 To Do”直接打开完整表单；标题位于首行，填写后点击“保存”，窗口自动关闭。保存时保留原始输入、录入时点和工作时区。
- To Do 默认打开详情，截止日期需填写或选择“无限期”；状态、优先级、负责人、关联对象和完成条件均可维护，原始输入保留。
- 进展发生时间默认当前工作时区时间，可手动修改。同一事项可持续追加进展。状态不变不妨碍记录；错误日志通过“追加更正”留痕。
- 邮件页搜索历史与相关会话、查看分析建议、编辑和复制英文草稿、保存人工反馈。
- 知识页按个人、客户、项目切换，并按对象查看与编辑。候选知识须确认；人工版本保留历史。
- “请求 AI 分析”只生成任务。WorkBuddy 分析后，Python 导入结果。设置页的“导入模拟 AI 结果”仅适用于演示空间。
- 设置页提供 To Do 独立备份、完整普通 ZIP 备份和恢复前文件预览；全程无需密码。恢复全量数据会保留回退目录，禁用邮箱与正式 AI 计划，要求重新授权。

## 本地测试与后续构建（需分别获阶段批准）

```sh
.venv/bin/python -m pytest -q
.venv/bin/python -m PyInstaller --noconfirm --workpath .runtime/goal002-g2/build --distpath .runtime/goal002-g2/dist packaging/workthread.spec
.venv/bin/python scripts/smoke_frozen.py .runtime/goal002-g2/dist/WorkThread/WorkThread
```

上方 Mac 构建命令使用独立输出目录，保留既有 rc1 产物；该命令已在获批 G2 中验证。最后一条是 Mac 原生包测试。Windows 在 `.github/workflows/windows.yml` 的 Windows runner 构建，不能把 Mac 包改后缀当作 Windows 包。完整步骤见 `docs/WINDOWS_ACCEPTANCE.md`。

## 数据与凭证

数据库、JSONL、队列、备份与本地依赖均被忽略。真实工作空间应放源码目录以外；开发测试仅用合成数据。IMAP 凭证写系统凭证库，不写配置或备份。没有明文凭证回退。

默认不连接邮箱、不启动正式定时任务、不发邮件、不上传业务资料。设置邮箱后，只有明确手动同步或启用账号后台轮询才会连接。备份使用普通 ZIP，保留 manifest、SHA-256、快照及恢复保护；历史 7z 不删除、不转换，新版不恢复旧加密格式。

当前部署与架构资料：`WORKBUDDY_SETUP.md`、`docs/ARCHITECTURE.md`。`docs/TEST_REPORT.md`、`RC_RELEASE_READINESS.md`、`GOAL_EXECUTION_REPORT.md` 和 `WORKBUDDY_INTEGRATION_TEST.md` 保留 rc1 历史记录，不作为 rc2 验收结论；`docs/LEGACY_IMPORT.md` 描述通用接口，本轮不执行旧项目导入。

界面维护规则见 `docs/UI_GUIDELINES.md`。
