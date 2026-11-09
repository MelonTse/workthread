# 通过 WorkBuddy 安装 Windows 版

推荐候选 **v1.0.0rc6**。从[此版本的官方发布页](https://github.com/MelonTse/workthread/releases/tag/v1.0.0rc6)获取 Windows x64 程序。若发布页或该版本校验值尚不可用，向用户报告“rc6 尚未开放安装”，等待发布。

给 WorkBuddy 的指令：

> 请按照 https://github.com/MelonTse/workthread 首页的 Windows 安装说明，在这台电脑上安装并配置 WorkThread。完成后打开工作台，并告诉我如何检查更新。

## 下载与安装

使用普通用户会话。确认 Windows 10 22H2 build 19045 或 Windows 11、Intel/AMD x64、已安装 WorkBuddy。记录客户端版本。优先使用 Windows PowerShell 5.1，默认目录为当前用户的 `%LOCALAPPDATA%\WorkThread`；用户可指定其他本地固定盘目录。已有工作空间时告诉用户路径和版本，让其选择独立目录。只在用户明确要求启动现有程序时走已有安装流程。

1. 打开上述官方 Release，认准 `WorkThread-1.0.0rc6-windows-x64.zip`，从**发布说明正文的 Windows 程序 ZIP SHA-256** 读取 64 位校验值。若页面缺少该值，停止。将值与对应下载资产的摘要核对。源码归档无法用于本流程。
2. 读取并保存[该版本安装脚本](https://raw.githubusercontent.com/MelonTse/workthread/v1.0.0rc6/scripts/install-windows.ps1)。在系统允许的 PowerShell 会话中运行下列命令，把实际校验值传给脚本；已下载 ZIP 时附加 `-PackagePath`。脚本在运行包内程序前完成校验，初始化两套独立空间，检查健康状况并返回项目路径。若系统策略阻止执行，报告本机策略和停止位置。

   ```powershell
   & .\install-windows.ps1 -ExpectedSha256 $ReleaseZipSha256
   ```

3. 成功后使用返回的 `installRoot`，记作 `$root`。失败时保留错误和安装位置，只对本次创建的目录处理；不要删除旧安装。整个过程无需 Git、Python、管理员权限或邮箱凭证。

## 验收后打开正式工作台

1. 在合成空间运行 `& "$root\Run.cmd" --workspace "$root\acceptance" demo --port 8766 --open`（独立进程）。若端口被占用，选择空闲端口并记录。等待网页和合成数据出现。
2. 明确展示 `acceptanceProject` 的完整路径。由用户通过 WorkBuddy GUI **Open Folder** 打开该路径、确认信任并新建会话。核对项目规则已加载，在客户端可用 Skills 中分别查找并实际调用 `workthread-intake`（录入合成待办）、`workthread-knowledge`（提供合成客户偏好）、`workthread-analysis`（分析合成任务）。逐项记录客户端调用证据。如果某项不可用，记录项目路径、客户端版本和失败项。
3. 让 Python 消费合成任务的交换文件。核对对应 request_id 或 job_id 的 `exchange/receipts` 回执为 `saved` 或 `completed`，并在网页检查同一事项。记录三个调用结果和回执 ID；只有文件存在时只能报告文件部署成功。
4. 结束本次启动的合成服务。引导用户打开 `formalProject`、确认信任并新建会话。双击安装根的 `Start.cmd`，打开正式工作台。展示「设置与运行状态 → 软件更新 → 检查更新」。有兼容版本时可「下载并检查」，关闭 WorkBuddy 并暂停外部写入后点「备份并重启更新」。记录实际版本、路径、健康检查、Skills 和合成回执结果。

正式邮箱和个性化配置按用户后续要求设置。
