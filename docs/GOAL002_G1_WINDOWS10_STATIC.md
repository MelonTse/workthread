# Goal002 G1：Windows 10 兼容性静态检查

**PASS（源码/依赖/脚本静态范围）**。这不是 Windows EXE 构建或 Windows 10 真机 PASS。G1 未运行 PyInstaller、GitHub Actions、Windows 安装程序或 WorkBuddy GUI 验收；Mac 未安装 PowerShell，未执行或用实际 PowerShell 解析脚本。

目标：Windows 10 Professional 22H2、19045、x64；WorkBuddy 5.9.3。

## 官方支持范围与依赖

- [Python 3.13 Windows 文档](https://docs.python.org/3.13/using/windows.html)说明其支持 Windows 8.1 及以上。当前本地 Python 3.13.18；包仍由 Windows 原生 runner 构建，不能将 Mac 产物改名交付。
- [PyInstaller 6.22.3 requirements](https://pyinstaller.org/en/stable/requirements.html)列 Windows 8 及以上。原生 bootloader、DLL 与本项目实际冻结资源仍需 G3/G5 验证。
- [WorkBuddy Windows 安装指南](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Installation-Win-Guide)列 Windows 10 及以上 x64。当前官方页面不保证 5.9.3 的全部项目能力。
- uv.lock 仍限制 Python 3.13，含 MarkupSafe cp313-win_amd64、nh3 abi3-win_amd64、rpds-py cp313-win_amd64、PyInstaller win_amd64；keyring 为 Windows 条件依赖 pywin32-ctypes。原 Windows keyring backend 继续打包，不改真实凭证逻辑。
- 移除 py7zr 及其专属加密/压缩依赖。普通 ZIP 使用 Python 标准库；没有引入新框架、模型 API 或 Windows 11 专属库。wheel 存在仅证明可选择平台分发包，不能替代 DLL/PE 实际导入检查。

资料核对日期：2026-11-05。没有声称 Microsoft 当前系统支持政策或安全更新状态；本报告仅针对产品运行适配。

## 已落实的适配

| 项目 | 检查/修改 | 验证边界 |
|---|---|---|
| 中文路径和重定向 JSON | CLI stdout/stderr 显式 UTF-8；cmd 使用 chcp 65001；PowerShell 设置 UTF-8 输出 | 原 rc1 模拟 cp1252 实际报 UnicodeEncodeError；新用例通过。Mac 模拟，不是 Windows Console 实测 |
| PowerShell 5.1 | #requires 5.1；使用 foreach、Join-Path、Test-Path -LiteralPath、退出码检查；不使用 PS7 并行/三元语法 | 人工源码检查；无 pwsh，未执行脚本 |
| 无 PowerShell 策略调整安装 | 新 Install.cmd 对两个空间 init/doctor；候选打包脚本会包含该文件 | 静态检查，目标 cmd.exe 执行留待 G3/G5 |
| 两空间初始化 | workspace/acceptance 均不自动 seed；init 报告冲突返回 2 | Mac 同一 Python 实现的 CLI 与双空间测试通过 |
| 文件替换差异 | 模板临时文件关闭后再替换目标；只改动已知版本，current 不重写 | Mac 原子替换/保护用例通过；Windows 文件占用留待真机 |
| ZIP Windows 路径 | 拒绝盘符、绝对、穿越、反斜杠、保留名、点/空格、大小写及祖先碰撞 | 自动负例通过；Explorer 实际打开留待真机 |
| 备份/恢复 cmd | 无密码；Backup.cmd 自动日期命名；Restore.cmd 要求新目标并先预览；错误码停止 | Mac 非交互 CLI/HTTP 通过，cmd 脚本未运行 |
| rc1 保护 | upgrade.ps1 明确拒绝 rc2 原地升级，不做移动/删除；说明要求新目录解压 | 静态检查，不运行旧版程序 |
| 路径/版本文档 | 固定 F:\WorkThread 与资料/正式/合成项目位置，明确 Open Folder 与信任 | 文档检查，当前部署提示词为 G1 草稿 |
| UI | CSS 与 HTML 模板无改动；仅去掉密码输入与调整 ZIP 文案/预览 | Mac 浏览器回归通过 |
| 业务系统 API | 检查 src、scripts、packaging 的 ctypes/WinDLL/winreg/platform/subprocess 调用；无新增 Windows 11 专属系统 API | 源码检查，不是所有第三方 DLL 的 API 导入审计 |

## 后续必须验证

G3：经独立批准后记录真实 Commit，Windows runner 全部测试、原生打包、冻结 EXE 冒烟，检查隐藏资源和三个 Skills、依赖/PE 导入及实际 ZIP。

G5：Windows 10 19045 无系统 Python 全新运行，cmd/PowerShell 5.1、中文空格/换盘符、Windows Credential Manager、文件占用与 Defender 提示；GUI Open Folder/信任、规则加载、三个 Skills 的列表和真实调用、新会话及 Python 回执。不得以 CI 或 Mac 文件存在替代。

当前没有真实 IMAP、正式定时任务、文件传输、Windows 安装或后续阶段执行授权。静态未发现 G1 范围内的 Windows 11 绑定阻断项，但实际兼容性仍待上述证据。
