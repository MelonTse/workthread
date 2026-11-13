RC10 是全新安装及后续网页更新的基线。此发布不授权旧版网页直接升级；已有安装用户如要保留数据，不要按纯净安装流程删除旧数据。

- 检查更新失败时保留已确认候选与校验通过的下载；重启后再次校验并恢复状态。
- 更新结果与本次编号、目标构建及启动健康检查关联，避免误读上次结果。失败可复制脱敏诊断。
- 邮件页显示全部本地归档总数，支持分页、跳页和全库搜索。
- Windows Server 2022 普通用户使用 `Install.cmd /quiet` 初始化两套合成空间，从网页完成首次更新。Windows 10/11 用户桌面环境仍以实机结果为准。

从资产下载 **WorkThread-1.0.0rc10-windows-x64.zip**（20,635,376 字节）；旧版清理和安装步骤见同页的 **RC10_CLEAN_INSTALL.md**，可直接交给 WorkBuddy。无需 Git、Python 或管理员权限。

Windows 程序 ZIP SHA-256: `af17c8568863ee18ce87c037dc842d89e261fd41663490d4487d0887c1f65bfb`

构建：`f488b17d3f27488b1d23976c7c58990b3aa5dbda`。[Windows 构建](https://github.com/MelonTse/workthread/actions/runs/43385316785) · [原生升级验收](https://github.com/MelonTse/workthread/actions/runs/43385316756)。后续正式发布须签名声明支持此 RC10 构建；暂无兼容更新时，网页应正常显示暂无更新。
