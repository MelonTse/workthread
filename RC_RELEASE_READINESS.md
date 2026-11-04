# WorkThread RC 发布准备核验

核验 ID：WORKTHREAD-RC-VALIDATE-001，2026-11-04。版本保留 **1.0.0rc1**，本次验证包标识 macos-arm64-20261104；没有创建正式 Release。数据库 v2，AI 契约 1.0。此次不再更改已确认 UI。

## A–E 结论

| 问题 | 结论 |
|---|---|
| A 最新源码是否冻结并通过测试 | 已整理为本地暂存快照，最新完整测试 **49 passed**；Mac 构建、强化冒烟和核心浏览器回归通过。最终文件指纹与暂存树保存在 artifacts/rc-source-manifest.json。没有创建提交；后续任何源码变化均须重新核验，不能把暂存快照称为 Git 标签发布。 |
| B 真实 WorkBuddy 是否打通 | **Mac 手动合成链路已打通**。第一真实结果 completed，重复重放无增量；第二全新会话独立生成合法结果，实际版本变化后旧快照被 superseded，业务操作零写入。规则主动加载与 Skill 调用已观察；自动注入仅模型自报的部分、OS 级隔离及 Windows 调度不能泛化为通过。详见 WORKBUDDY_INTEGRATION_TEST.md。 |
| C 是否可安全推送私有仓库 | 当前审阅并暂存的源码范围通过路径、常见密钥模式、保留域名邮箱与忽略规则检查；可作为下一轮另行授权的私有仓库提交候选。仅推送该源码快照，不包含 .runtime、artifacts、dist、数据库、备份、邮件或凭证。模式扫描不能保证任意未来文件无敏感信息。当前没有远程，也未推送。 |
| D Windows Actions 条件 | windows-2022、uv frozen Python 3.13、完整测试、源隔离门禁、原生 onedir、强化 smoke 与 ZIP artifact 流程齐备。**尚无 Windows runner 执行证据**；需在下一轮授权创建私有仓库后实际执行，不能以 Mac 通过替代。 |
| E 真机必须验证 | 无 Python 安装运行、中文／空格／换盘符路径、PowerShell 安装升级回滚、Credential Manager、Defender／SmartScreen、Windows WorkBuddy 规则与 Skills、权限与登录、休眠补跑、第二台机器恢复。真实 IMAP 另行授权后小范围验收，正式任务保持禁用。详见 docs/WINDOWS_ACCEPTANCE.md。 |

## 当前证据

- 自动测试：artifacts/rc-validation-tests.xml、rc-tests.log，49 passed in 3.22s。新增 4 个发布门禁负例，不复用旧 45 项报告冒充最新结果。
- 浏览器：最新源码在独立 rc-workbuddy 空间完成新增、日期／无限期、状态、连续两条进展、邮件与关联草稿、草稿保存及反馈、客户知识查询新增；另在 rc-ui 空间完成模拟导入、完整加密备份下载／上传校验／实际恢复及健康检查。两空间隔离，模拟不计入真实模型证据。截图与详细步骤见 docs/TEST_REPORT.md。
- Mac：artifacts/rc-mac-build.log、rc-mac-smoke.log。冻结包在独立中文临时目录启动，实际新增、修改状态、追加两条日志、加密完整备份及恢复后数据检查均通过；11 个网页／Schema／规则资源与当前源码逐字节相同，rc-bundle-resource-check.json。
- 包：artifacts/WorkThread-1.0.0rc1-macos-arm64-20261104.zip，SHA256 见 rc-mac-package.json；不将 Mac 包当作 Windows EXE。
- Ruff：本轮 46 项提示，未声称全仓 lint 通过。异常捕获、退出清理及错误语义逐类审阅见 docs/RC_RUFF_REVIEW.md；不做纯风格重构。
- Git：源隔离脚本同时扫描暂存与工作副本常见密钥；拒绝私钥、日志、运行目录及备份。最终门禁输出和快照清单位于 artifacts；这些本地证据被 .gitignore 排除。

## 修正与限制

修正分析 Skill 的规则路径；补强草稿禁止无证据附件／动作断言，并在第二份真实输出中复查具体问题；增强发布门禁、冻结包写读及恢复检查。未创建新架构、服务框架或全局依赖。没有读取旧版真实邮件、授权真实 IMAP、修改旧版项目、启用正式计划、创建远程仓库、推送或发布。

本轮验收结论是 **Mac RC 与提交 Windows 构建的准备核验完成**，正式 Windows 发布与生产邮箱接入仍须下一阶段授权及真机证据。
