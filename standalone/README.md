# WorkThread RC7 → RC9 独立升级工具 1.0.0

仅用于官方 RC7（a74eec51…）保留本机数据升级到官方 RC9（49381b86…）。随包提供的 RC9 是原发布包，未改名替换其内容。无需 Git、Python、管理员权限或网络；不能绕过文件访问权限。

本工具不证明此前空快照的唯一根因已经查明。它使用系统 robocopy、正常化外部程序 DLL 环境、显式标准输入输出句柄、详细日志和三方清单比对。复制仍保留 DATS 参数（包含 ACL）；权限失败不会降级为忽略权限或强行切换。

## 操作

1. 从官方地址下载工具 ZIP，先核对 ZIP 的 SHA-256。完整解压到原安装目录以外、非 OneDrive 的本地文件夹，例如 `G:\WorkThread-Upgrade-Tool`。不能把内容覆盖到 `G:\WorkThread`。
2. 可先只读核验（下面以实际安装目录 `G:\WorkThread` 为例）：

   `tool\WorkThreadUpgrade.exe --install-root "G:\WorkThread" --release-dir "release" --inspect`

   相对 release 路径以当前工具目录为准。此操作检查原 EXE 指纹、两个空间 schema、RC9 签名和 ZIP；仅在工具 logs 目录写诊断记录。
3. 双击 `Upgrade.cmd`。输入实际安装根目录，例如 `G:\WorkThread`。窗口完成核验并停在 `Type UPDATE`。
4. 停止邮件拉取和值守；关闭 WorkThread 服务和 WorkBuddy。仅关闭浏览器不等于服务停止。正常退出服务窗口；无法确认停止时不要杀不明进程，工具会在停写检查时阻止升级。
5. 在独立窗口本人输入 `UPDATE`。先进行同盘合成复制自检，再备份、试运行副本和切换。每 10 秒显示存活提示；不要关闭窗口或手动启动旧程序。
6. 只有看到 `SUCCESS`、退出码 `0`，才从原安装目录运行 `Start.cmd`。核对网页 RC9、原邮件/To Do/知识/草稿和两套工作空间。升级工具本身不自动启动服务，避免未确认就开始收信。

## 出错与中断

- `FAILED` 或非零退出码：保留窗口、工具 `logs`、安装目录的 `.workthread-updates` 和合成探测目录。不要删除锁文件、快照、版本指针，不覆盖安装，也不要盲目再点网页升级。
- 日志包含本机路径、哈希、文件清单、复制错误；不记录邮件正文或密码。日志可能暴露文件名，仅向维护者提供必要的脱敏摘要。
- 复制自检目录为安装根目录旁的 `WorkThread-Upgrade-Probe-随机编号`，只含合成数据，工具不会自动删除。
- 真正断电或窗口被关闭时，先确认原服务和升级进程均已退出，再在工具目录运行：

  `tool\WorkThreadUpgrade.exe --install-root "G:\WorkThread" --release-dir "release" --recover`

  它要求输入 `RECOVER` 并按原事务记录恢复。已经提交的升级不会回退；如果切换后已有新业务写入，它会停止并保留两份数据，必须人工处理。不得伪造或手改事务记录。
- `--confirmed` 是自动化验收入口，不应由 WorkBuddy 在用户未同意停写的情况下使用。

## 验收边界

Windows Actions 使用 Windows Server 2022 x64。测试包括原始 RC7 包 + 原始 RC9 签名包、两套合成空间、窗口/无控制台执行、文件/数据库/AI 交换/自定义文件/旧备份保留、损坏包与签名拒绝、既有失败升级残留、故障注入和中断恢复。成功后网页显示本次升级结果，旧错误另存于工具日志。具体结果见随包 WINDOWS_REPORT.json 和 TEST_REPORT.md。

Windows 10 19045 用户环境尚未验收。本机若仍出现 ACL 或其他复制错误，工具应安全停止并留下证据，不能宣称成功。此工具不是网页自动更新的新版本，不修改已发布 RC7/RC9 资产。
