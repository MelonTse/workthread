# Windows 保留本机数据升级

本文适用于官方签名的 Windows x64 发布候选版 1.0.0rc4。仅支持 Windows x64 本地磁盘的便携安装；正式与验收空间须均已初始化，数据库均为 schema 2。

**首次从 rc3 升级。** 使用新版本的独立工具，不能运行旧 rc3 中禁用升级的脚本。将受信任的新包完整解压在旧安装目录之外。首次执行前须通过独立可信渠道核对发布者及包指纹；仅在同一下载目录看到一个 SHA 文件不能建立初次信任。另保留原签名 ZIP、update.json、update.sig，不要解压覆盖已安装程序。

1. 用新版工具执行只读诊断：从新版解压目录运行 `app\WorkThread.exe --maintenance inspect "<原安装目录>"`。报告版本、Commit、两个数据库版本和是否属于支持的来源。早期 rc3 识别为 `66fea8f`、v3 UI rc3 为 `1ce8e08`；发布签名清单还须明确允许该完整源 SHA。无法识别或旧于 rc3 时停止。不要把未知旧数据库交给新程序初始化。
2. 关闭 WorkBuddy、WorkThread 及其他可能编辑这些目录的程序。使用**新包**的 `tools\upgrade.ps1 -InstallRoot "<原安装目录>" -ReleaseDirectory "<三个发布文件所在目录>" -Apply`，阅读诊断后输入 UPDATE。无需管理员权限；如果无法确认停写、无法保留访问权限、缺空间或有冲突，就先处理原因，不关闭安全策略来强行升级。
3. 成功后用原 Start.cmd 或原程序快捷方式打开工作台。正式和验收工作空间、WorkBuddy 的 Open Folder 路径均不变。验收前先使用合成副本；不能用候选程序和真实邮箱试错。

**后续升级。** 从正式空间的「设置与运行状态 → 软件更新」检查已发布版本。此动作之前不访问 GitHub；检查或下载不会停机。确认「备份并重启更新」前关闭 WorkBuddy、暂停外部编辑。工具排空本地服务，检查两个空间并快照，在副本上用新程序验证 SQLite、归档、规则与 UI。只有就绪才切换并在原端口重启。合成验收空间或源码运行模式不能发起安装。未配置发布公钥的开发构建拒绝更新。GitHub Actions 候选 Artifact 不作为在线更新源。

**本地文件与恢复。** 安装根的 `.workthread-updates` 保存安装锁、只读意义上的历史版本、活动版本指针、升级事务和最近结果。每次事务在 `transactions/<id>/snapshot` 保存两个完整工作空间（含 SQLite、历史备份、AI exchange、回执、配置和自定义内容）；成功切换还保留旧目录。它不是普通备份/恢复操作，不重置 workspace_epoch、AI 队列、邮箱设置或操作系统凭证。快照可能很大，包含原业务内容且未加密，只保存在本地，绝不上传。无自动清理或自动倒退。

- 模板预检遇到用户改过的受管文件时，旧文件保留，错误给出冲突路径和副本目录；在副本项目的 `.workthread-updates` 中比较候选内容。首版保守地阻止所有受管文件冲突；额外的用户文件原样保留。
- 升级中断后使用原 Start.cmd。启动器在开放业务写入前处理未完成事务。若发现目标工作空间有快照之后的新写入，保持双方目录、停止启动，人工比较后再决定。已经成功的事务不自动回滚，避免丢失升级之后产生的数据。
- 不要删除事务目录、手改 active.json 或直接运行内部版本目录的 EXE。空间预检会计入两个完整副本、程序并排副本和余量。旧程序直接快捷方式首次切换为小型启动器；原完整运行时仍保留。未批准业务迁移的新数据库版本一律拒绝。

**维护者发布。** 使用新版本号和唯一 tag（例如候选 v1.0.0rc4）。通过 Windows 原生构建和升级验收后才考虑发布。构建时 `WORKTHREAD_BUILD_PUBLIC_KEY` 指向只含 32 字节 Ed25519 公钥十六进制的 `release-public.hex`；正式 Windows 工作流从版本控制的 `packaging/release-public.hex` 嵌入维护者公钥。私钥不进仓库、客户端或普通构建环境。离线签名机的 `WORKTHREAD_SIGNING_KEY_FILE` 指向 32 字节原始私钥，用 `scripts/sign_update.py <程序ZIP> --output <新元数据目录> --source <旧版本>@<完整SHA>` 生成 update.json 和 update.sig，逐一列出验收通过的来源。当前工具不支持自动换根密钥。发布到 MelonTse/workthread 的对应 GitHub Release，附原 ZIP 和两个签名元数据文件。不要替换同版本的发布文件；正式版不接受 rc 候选。

**Windows 原包验收。** `Windows rc3 upgrade qualification` 是候选分支上自动运行且可手动发起的独立工作流：下载两个历史 Actions 产物、对内部 ZIP 核对固定 SHA-256，以一次性测试密钥构建不发布的候选，在临时目录实际运行旧 EXE 和升级工具。Artifact 过期时验收应失败，可使用同哈希的离线存档在 Windows 上运行 `scripts/check_windows_upgrade.py --help` 所列入口。Windows-2022 runner 的成功不能替代 Windows 10 19045 + WorkBuddy 客户端验收。
