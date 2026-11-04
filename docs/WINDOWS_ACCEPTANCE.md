# Windows 发布候选验收

当前 Windows CI 配置已提供，但本轮没有远程仓库或 runner，**尚未运行 Windows 构建**。不得将 Mac PyInstaller 通过描述为 Windows 通过。

## CI 构建

1. 用户另行授权后创建 GitHub 私有仓库；先运行 source isolation 检查，只提交源码与合成测试。
2. 执行 .github/workflows/windows.yml：固定 windows-2022，uv 0.13.7，Python 3.13，frozen lock，pytest、隔离检查、PyInstaller onedir、二进制冒烟、便携 ZIP。
3. 下载 Actions artifact，检查 SHA256SUMS.json。候选包包括 app、Start/Health/Backup/Restore.cmd、tools 安装升级、依赖锁和文档。
4. 候选验收通过后，以 v1.0.0 标签和干净 CI 产物创建私有 Release；不从真实工作空间打包。发布权限由用户提供，本轮不执行。

## 必须在 Windows 真机勾选

- [ ] Windows 11 x64 无 Python 环境，中文及空格路径解压、初始化、启动、重启。
- [ ] 同目录复制到其他盘符运行；源码虚拟环境不可用作便携包。
- [ ] 合成数据录入、状态、两条日志、草稿编辑复制、模拟 AI 导入。
- [ ] Windows Credential Manager 存取 IMAP 授权码，无明文文件或备份凭证。
- [ ] 真实邮箱经授权小范围验收 TLS、文件夹、MIME 与附件段零抓取，再全量归档。
- [ ] UID 重置、网络失败、磁盘满、进程中断后可恢复。
- [ ] WorkBuddy 新会话加载项目规则与三个 Skills，实际输出和回执闭环。
- [ ] 正式每日任务先保持禁用，验证权限、登录、睡眠及错过执行补跑后再启用。
- [ ] 完整备份在第二台电脑恢复，旧电脑离线，重新授权、加载规则、重建任务。
- [ ] To Do 单独恢复、冲突处理、错误密码与损坏备份。
- [ ] upgrade.ps1 成功升级，以及失败后程序和匹配数据备份恢复。
- [ ] Defender/SmartScreen 与未签名程序行为；目前无 Authenticode 签名，不绕过系统警告。
- [ ] 全部通过后才发布正式 Release。保留系统、WorkBuddy 版本和截图／日志证据。

## 本次 RC 准备检查 · 2026-11-04

Mac 当前 49 项测试通过，最新 onedir 构建与强化冒烟通过；这些是 Mac 证据。工作流采用同一 tests、release isolation 和 frozen smoke 脚本。发布隔离门禁现会拒绝运行目录、日志、私钥及常见 token，并检查暂存与工作副本。候选目录只从源码、构建产物与锁文件组装。

尚无远程仓库或 Windows runner 结果，Actions 可执行性仍须实际提交后运行确认。Windows 的 PowerShell 路径、Credential Manager、终端密码输入、Defender／SmartScreen、换盘符、休眠补跑、第二台电脑恢复和 WorkBuddy 权限需按上表验收。Mac 真实 WorkBuddy 成功不代替 Windows 客户端验收；真实 IMAP 需另行授权后进行。
