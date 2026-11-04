# Windows 候选版安装与首轮验收

适用：Windows 11 x64 候选测试。GitHub Windows runner 通过与用户电脑真机通过分别记录；runner 成功不能替代本清单。无需安装 Python。

1. 使用有私有仓库权限的 GitHub 账号进入本次成功 Actions 运行，下载 `WorkThread-windows-candidate` Artifact。先解开 Artifact 外层 ZIP，取得 `WorkThread-1.0.0rc1-windows-x64.zip` 与同名 `.zip.sha256`。
2. 在 PowerShell 执行 `Get-FileHash .\WorkThread-1.0.0rc1-windows-x64.zip -Algorithm SHA256`，与 `.sha256` 文件及构建交付报告比较。相同后把候选 ZIP 完整解压到当前用户可写目录，不放在 Program Files；保留整个 app 目录，不单独移动 EXE。
3. 从解压根目录执行 `app\WorkThread.exe --workspace workspace init`，再双击 `Health.cmd`。也可在系统策略允许时运行 `tools\install.ps1`，无需管理员权限；不要为了运行脚本降低系统安全策略。
4. 双击 `Start.cmd`，浏览器应打开本地网页。关闭其终端会停止服务。若端口占用，先检查已有 WorkThread 进程，保留用户数据。
5. 只录入合成事项：新增标题及日期／无限期，保存后窗口关闭；修改状态并连续追加两条进展，重启后核对保留。
6. 按 `WORKBUDDY_SETUP.md` 在新的独立合成空间加载规则和 Skills，完成手动文件交换自检。真实邮箱授权、正式每日任务及生产资料迁入留待下一轮明确指令。
7. 测试备份与恢复、中文／空格路径和不同盘符；升级先关闭程序并保留加密备份。错误密码、损坏备份和回滚按 `docs/WINDOWS_ACCEPTANCE.md` 验证。

如果 Defender／SmartScreen 或组织策略拦截，记录提示与包 SHA，交由用户或管理员审核；本候选包未提供 Authenticode 签名，不绕过系统警告。

数据位于解压根目录的 workspace；完整迁移使用加密备份。不要上传 workspace、邮箱授权码、数据库或业务资料到 GitHub。
