# WorkThread · 事脉 AI 工作台

## Windows 安装 · WorkThread 1.0.0rc4

将下面的指令交给已安装的 WorkBuddy：

> 请按照 https://github.com/MelonTse/workthread 首页的 Windows 安装说明，在这台电脑上安装并配置 WorkThread。完成后打开工作台，并告诉我如何检查更新。

[Windows 首次安装说明](https://github.com/MelonTse/workthread/blob/v1.0.0rc4/docs/windows/FIRST_INSTALL.md) · [下载 v1.0.0rc4 和核对程序包 SHA-256](https://github.com/MelonTse/workthread/releases/tag/v1.0.0rc4) · [从受支持的 rc3 升级](https://github.com/MelonTse/workthread/blob/v1.0.0rc4/docs/WINDOWS_PRESERVING_UPDATES.md)

目标系统为 Windows 10 22H2 / Windows 11 x64。rc4 已完成 Windows Server 2022 自动化验证，桌面系统与 WorkBuddy 客户端验收待安排。安装后可在「设置与运行状态 → 软件更新」检查兼容版本。

## 早期开发资料

轻量、单用户、本机运行的 AI 工作事项工作台。Python 负责持久化、IMAP 与校验；WorkBuddy 负责分析。网页无需模型 API，可独立维护 To Do 和进展日志。

本分支下方保留 **1.0.0rc1** 开发说明。Windows runner 的 49 项测试及冻结程序冒烟已通过，Mac 真实 WorkBuddy 合成文件交换已验证；Windows 用户电脑、真实 IMAP 与正式无人值守仍待验收。

历史 rc1 Windows 部署资料：[完整部署与真机验收提示词](docs/WINDOWS_WORKBUDDY_DEPLOY_PROMPT.md)。提示词固定候选包、构建提交和 SHA-256，只用合成数据，不启用真实邮箱或正式定时任务。

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
- 设置页提供 To Do 独立备份、完整加密备份和恢复预览。恢复全量数据会保留回退目录，禁用邮箱与正式 AI 计划，要求重新授权。

## 测试与打包

```sh
.venv/bin/python -m pytest -q
.venv/bin/python -m PyInstaller --noconfirm packaging/workthread.spec
.venv/bin/python scripts/smoke_frozen.py dist/WorkThread/WorkThread
```

最后一条是 Mac 原生包测试。Windows 在 `.github/workflows/windows.yml` 的 Windows runner 构建，不能把 Mac 包改后缀当作 Windows 包。完整步骤见 `docs/WINDOWS_ACCEPTANCE.md`。

## 数据与凭证

数据库、JSONL、队列、备份与本地依赖均被忽略。真实工作空间应放源码目录以外；开发测试仅用合成数据。IMAP 凭证写系统凭证库，不写配置或备份。没有明文凭证回退。

默认不连接邮箱、不启动正式定时任务、不发邮件、不上传业务资料。设置邮箱后，只有明确手动同步或启用账号后台轮询才会连接。备份密码由用户保管，程序不保存。

资料：`WORKBUDDY_SETUP.md`、`docs/ARCHITECTURE.md`、`docs/LEGACY_IMPORT.md`、`docs/TEST_REPORT.md`。

界面维护规则见 `docs/UI_GUIDELINES.md`。
