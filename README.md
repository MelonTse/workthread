# WorkThread · 事脉 AI 工作台

## Windows 安装

把这句话交给已安装的 WorkBuddy：

> 请按照 https://github.com/MelonTse/workthread 首页的 Windows 安装说明，在这台电脑上安装并配置 WorkThread。完成后打开工作台，并告诉我如何检查更新。

[Windows 安装说明与推荐版本 v1.0.0rc5](docs/windows/FIRST_INSTALL.md) · Windows 10 22H2 / Windows 11 x64

轻量、单用户、本机运行的 AI 工作事项工作台。Python 负责持久化、IMAP 与校验；WorkBuddy 负责分析。网页无需模型 API，可独立维护 To Do 和进展日志。

Windows x64 发布候选版 **1.0.0rc5** 修复已发送文件夹识别，支持为已有邮箱选择文件夹或移除邮箱配置。官方 rc4 用户可从「设置与运行状态 → 软件更新」保留本机数据升级。程序 ZIP 的 SHA-256 见 [v1.0.0rc5 发布页](https://github.com/MelonTse/workthread/releases/tag/v1.0.0rc5)。

Windows Server 2022 上已自动验证两个历史 rc3 的升级和全新 rc4 的首次网页更新。Windows 10 19045、Windows 11 与 WorkBuddy 客户端的安装、Skills 发现及实际调用仍待桌面验收。

## v3 UI 源码更新

已按确认的 v3 样板落实五页 UI，包含可折叠导航、统计筛选、连续切换 To Do 详情和宽屏邮件并排。按钮“加入 AI 分析队列 / 加入 AI 重写队列”只写入待处理文件，仍由 WorkBuddy 执行。未保存草稿须先保存再入队。

这次更新位于 `codex/workthread-ui-v3`，基于已构建的 rc3 源码；此前 rc3 安装包及离线资料不因源码更新自动变化。实施和验证见 [UI v3 报告](docs/UI_V3_IMPLEMENTATION_REPORT.md)，界面规范见 [UI Guidelines](docs/UI_GUIDELINES.md)。

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
- 在“设置与运行状态 → 邮箱”查看每个文件夹的已归档、待拉取和异常数量。断线后本轮最多自动重连三次；仍未连通时，可在网络恢复后点击“继续拉取（断点续传）”。刷新网页后仍可继续，已归档邮件跳过正文下载。服务器文件夹的 UIDVALIDITY 变化时会停用旧断点。
- 邮件页搜索历史与相关会话、查看分析建议、编辑和复制英文草稿、保存人工反馈。
- 知识页按个人、客户、项目切换，并按对象查看与编辑。候选知识须确认；人工版本保留历史。
- “请求 AI 分析”只生成任务。WorkBuddy 分析后，Python 导入结果。设置页的“导入模拟 AI 结果”仅适用于演示空间。
- 设置页提供 To Do 独立备份、完整普通 ZIP 备份和恢复前文件预览；全程无需密码。恢复全量数据会保留回退目录，禁用邮箱与正式 AI 计划，要求重新授权。

## 本地测试与后续构建（需分别获阶段批准）

```sh
.venv/bin/python -m pytest -q
.venv/bin/python -m PyInstaller --noconfirm --workpath .runtime/rc3-r0/build --distpath .runtime/rc3-r0/dist packaging/workthread.spec
.venv/bin/python scripts/smoke_frozen.py .runtime/rc3-r0/dist/WorkThread/WorkThread
```

上方 Mac 构建命令使用独立输出目录，保留既有 rc1 产物；R0 仅使用独立临时输出做 Mac 资源核验，不代表 Windows 构建。最后一条是 Mac 原生包测试。Windows 在 `.github/workflows/windows.yml` 的 Windows runner 构建，不能把 Mac 包改后缀当作 Windows 包。完整步骤见 `docs/WINDOWS_ACCEPTANCE.md`。

## 数据与凭证

数据库、JSONL、队列、备份与本地依赖均被忽略。真实工作空间应放源码目录以外；开发测试仅用合成数据。IMAP 凭证写系统凭证库，不写配置或备份。没有明文凭证回退。

默认不连接邮箱、不启动正式定时任务、不发邮件、不上传业务资料。设置邮箱后，只有明确手动同步或启用账号后台轮询才会连接。备份使用普通 ZIP，保留 manifest、SHA-256、快照及恢复保护；历史 7z 不删除、不转换，新版不恢复旧加密格式。

当前部署与架构资料：`WORKBUDDY_SETUP.md`、`docs/ARCHITECTURE.md`。`docs/TEST_REPORT.md`、`RC_RELEASE_READINESS.md`、`GOAL_EXECUTION_REPORT.md` 和 `WORKBUDDY_INTEGRATION_TEST.md` 保留 rc1 历史记录，不作为 rc2 验收结论；`docs/LEGACY_IMPORT.md` 描述通用接口，本轮不执行旧项目导入。

界面维护规则见 `docs/UI_GUIDELINES.md`。
