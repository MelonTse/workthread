# RC9 → RC10 保留数据升级操作方案

状态：RC10 开发验收方案；正式发布及安装包签名审核完成前，不用于用户安装。

## 为什么这次使用新版包内的升级入口

已发布 RC9 的网页更新执行的是 RC9 自己的复制代码，仍有 `/COPY:DATS` 在普通用户权限下失败的问题。独立工具 1.0.1 曾帮助用户升到 RC9，但没有改写 RC9 本身。

因此首次 RC9 → RC10 必须使用**校验后的 RC10 包内程序**执行 `tools\upgrade.ps1`。不要依赖 RC9 网页的“备份并重启更新”完成这一跳。RC10 的网页更新和离线入口已共用权限预检、DAT 复制及内容/权限复核；后续兼容版本可从网页升级。是否可升由官方签名清单中的版本与完整构建 SHA 决定。

## 发布前维护者必须补齐

- 正式 RC10 Windows ZIP、完整 Commit SHA、ZIP 字节数与 SHA-256。
- 用现有维护者密钥签名的 `update.json`、`update.sig`；来源必须包含官方 RC9 `1.0.0rc9@49381b86143bbe5ce48b4f47c6d05880927b1b48`。
- 正式包必须嵌入维护者公钥，不能使用验收的临时公钥/离线 feed。
- Windows 自动验收结果及客户端边界；不能把 Windows Server 测试写成 Windows 10/11 真机通过。

## 用户侧步骤（发布后）

1. 将上述三个文件下载到安装目录外的独立本地目录，例如 `G:\WorkThread-RC10-Upgrade`。核对完整 SHA-256 后，把 RC10 ZIP 解压到这个目录；不得覆盖 `G:\WorkThread`。
2. 在 WorkBuddy 中打开该独立目录。只读确认真实安装根、活动版本、两个工作空间、旧备份及当前任务。不要只看安装根的旧 `BUILD_INFO.json`，还要检查活动版本指针或工具 `--maintenance inspect`。
3. 运行解压后 RC10 的只读检查：

```powershell
& 'G:\WorkThread-RC10-Upgrade\WorkThread-1.0.0rc10-windows-x64\app\WorkThread.exe' --maintenance inspect 'G:\WorkThread'
```

4. 准备一个从资源管理器独立打开的普通 PowerShell 窗口。确认拉取/AI任务已结束、WorkThread服务已正常停止、端口无监听。退出 WorkBuddy；只关闭浏览器不算停写。
5. 在独立窗口执行包内官方脚本；下面的路径仅为示例，实际应按已校验文件位置填写：

```powershell
& 'G:\WorkThread-RC10-Upgrade\WorkThread-1.0.0rc10-windows-x64\tools\upgrade.ps1' -InstallRoot 'G:\WorkThread' -ReleaseDirectory 'G:\WorkThread-RC10-Upgrade' -Apply
```

6. 用户确认停写后，亲自输入大写 `UPDATE`。工具会验签与核对来源、做同盘合成复制自检，然后快照、试迁移、切换和健康检查。不要同时启动工作台；不要删除锁、失败目录或改 ACL；不用管理员权限强行绕过。
7. 以工具整体 `SUCCESS`、退出码 0、`.workthread-updates\result.json` 为准。`inspect` 成功或复制子进程返回 0 均不代表升级成功。
8. 成功后从原 `Start.cmd` 启动一次，核对网页 RC10、原地址/两个 WorkBuddy 项目路径不变、邮件/待办/进展/知识/草稿/AI队列与回执/旧备份仍可用。确认后再按用户意愿恢复邮件任务。

## 失败或断电

- 复制或试迁移失败：停止切换，原工作空间不被覆盖；保留失败证据。
- 切换中断：启动器根据事务记录恢复匹配的旧程序和旧工作空间。若发现中断后新写入，保留两份数据并停止自动恢复。
- 先读 `.workthread-updates\result.json`、`transaction.json`、`diagnostics`、事务下 `copy-*` 日志。读取日志时 UTF-8 JSON/文本、UTF-16 robocopy 日志；不要用复制退出码代替整体结果。
- 无成功记录或恢复状态不明时，不反复升级、不删除快照、不手改版本指针。先提供脱敏阶段、错误、退出码和差异摘要。

## 给 WorkBuddy 的提示词（正式发布后使用）

> 请协助使用官方 RC10 新程序包，把本机官方 RC9 保留数据升级到 RC10。先只读确认安装根和当前活动构建；在安装根外核对 RC10 ZIP 的官方完整哈希、签名元数据及包内清单。只运行新版 EXE 的 inspect，不点击 RC9 网页升级，不覆盖解压到安装根。引导我从资源管理器打开独立 PowerShell 窗口，正常停止邮件/AI任务和 WorkThread 服务，确认无写入，再退出 WorkBuddy。我亲自运行官方 tools\upgrade.ps1 -Apply 并输入 UPDATE。客户端阻止打开独立窗口时，告诉我手动打开，不绕过安全规则。升级期间不启动工作台、不删锁/快照、不改权限、不提权。回来后读取工具整体结果；仅在 SUCCESS 且 exit_code=0 后启动一次原 Start.cmd，核对网页 RC10、两套空间路径和业务记录保留。失败则报告阶段、完整脱敏错误、日志位置与事务状态，不自动重试或恢复。不要输出邮件正文或任何凭据，不发信、不运行 AI 批处理，不创建定时任务。

## 邮件分页说明

RC10 邮件页显示当前本地归档总数，每页 50 封，支持上一页、下一页、跳页、全库搜索及刷新。这里的“全部”指本地已归档邮件，不是服务器上尚未拉取的邮件。翻页固定本次归档边界，新归档邮件通过“刷新邮件”进入当前列表。只分页摘要；选中邮件时单独加载全文和对应草稿。
