# Windows 10 rc2 全新安装速查（G1 草稿）

本页准备供后续批准阶段使用。当前没有 rc2 Windows 构建 SHA 或正式安装授权，不能用 rc1 包代替。

1. G4 批准后，资料放 `F:\WorkThread-Offline-Deploy-V2`。依据 G3 实际构建报告及 .zip.sha256，用 PowerShell `Get-FileHash -Algorithm SHA256` 核对程序 ZIP；按 SHA256SUMS.json 检查包内文件，JSON 使用 UTF-8。
2. 目标环境为 Windows 10 Professional 22H2 build 19045 x64、WorkBuddy 5.9.3。完整解压到新的 `F:\WorkThread`，无需安装 Python。若此目录已有内容，停止并选择新目录，不覆盖 rc1。
3. 双击 `Install.cmd`（无需 PowerShell 执行策略调整）或运行 `tools\install.ps1`，检查退出码及两个部署报告；两个空间都自动安装规则、三个 Skills、Schema、交换目录。自定义文件冲突须人工处理，不能静默覆盖。
4. 双击 Health.cmd、Start.cmd，正式空间 `F:\WorkThread\workspace` 保持空白。合成验收另启动 `app\WorkThread.exe --workspace F:\WorkThread\acceptance demo --port 8766 --open`。
5. 通过 **WorkBuddy GUI Open Folder** 选择 `F:\WorkThread\acceptance\agent-workspace` 并确认信任。不得选择资料目录。正式使用选择 `F:\WorkThread\workspace\agent-workspace`。
6. 按 WINDOWS_ACCEPTANCE.md 分别验证规则加载、Skill 可用列表、三个真实调用、全新会话和 Python 回执。读取 SKILL.md 不算调用。
7. 验证四种日期组合、两条进展、普通 ZIP 无密码备份/预览/新目录恢复和重启。保留历史 7z 文件，不使用它们恢复 rc2。

完整操作见 WORKBUDDY_SETUP.md 及 WINDOWS_WORKBUDDY_DEPLOY_PROMPT.md。系统策略或 Defender 拦截时保留证据，不绕过保护。当前不接真实邮箱，不启用正式计划，不导入旧知识，不自动传输资料到另一台电脑。
