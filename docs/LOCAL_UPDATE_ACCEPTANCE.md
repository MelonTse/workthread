# 保留本机数据升级：本地验收报告

日期：2026-11-08（上海）。独立分支 `codex/local-preserving-updates`，基线 `1ce8e085f6a1578f7cb94f649df96c4d42983e36`，候选源码版本 `1.0.0rc4`。本地合成数据验收 **PASS**。本报告不构成 Windows 构建、正式发布或 Shelley 真机部署通过。

| 实际执行 | 结果与证据 |
|---|---|
| macOS arm64 / Python 3.13.18 全量 pytest | **170 passed**（原有 146 项及 24 项升级相关用例）；机器可读结果 `artifacts/local-update/tests.xml`。 |
| 两个历史 rc3 → 新候选 | 分别从 Git 中提取 `66fea8f746963561268382b6ab3735eefdc0704f`、`1ce8e085f6a1578f7cb94f649df96c4d42983e36` 的源码及模板，确认导入的是对应旧源码，生成两套独立的合成数据。以固定的两个原工作空间路径运行升级事务；副本探测由实际冻结的 Mac 程序执行。每套空间 **37 张 SQLite 表**全部逐行比对，归档、交换文件、未处理结果、历史备份和自定义文件比对一致；工作空间 ID、epoch 与项目路径保留。部署登记允许按新模板重写；数据库比较逻辑记录而非 SQLite 页布局。见 `artifacts/local-update/old-source-upgrades.txt`。这不是运行旧 Windows EXE 的测试。 |
| 两个空间的故障恢复 | 在正式空间移出、候选移入，验收空间移出、候选移入，以及活动版本指针更新后，分别在真实子进程内执行硬退出，绕过异常清理。另一个进程读取磁盘事务记录，恢复两套旧目录和旧版本指针；恢复可重复。对中断后的新写入另设测试：保留现场、禁止静默回滚。此为进程中断故障注入，不是物理断电试验。 |
| 拒绝路径 | 验证签名无效、包内容损坏、磁盘空间不足、模拟写入者、活动会话、复制期间发生写入、副本迁移异常、切换 I/O 故障、模板冲突、未知构建及未知 schema。原数据保留；未知旧安装可只读诊断。 |
| 软件更新网页 | Chromium 实际点击检查、下载、取消、确认；使用真实签名验证与事务引擎，旧服务进程退出、新服务在相同端口重开，网页重连并显示测试版 rc5，两个工作空间再次比对通过。使用本地发布响应、临时测试密钥、合成包和测试进程监督器；未连接 GitHub Releases，也未运行 Windows 的进程监督代码。另外单测实际运行 Waitress，验证提交确认响应后能排空并退出。见 `artifacts/local-update/update-browser.log`。 |
| 既有 UI 与独立程序 | 原 v3 浏览器回归 **106 项通过**；重新冻结 Mac 程序，原生启动、HTTP、HTML/JS、Schema、SQLite 和普通 ZIP 备份恢复冒烟通过。见 `artifacts/local-update/browser.log`、`mac-smoke.log`。 |
| 历史归档静态检查 | 本地早期 rc3 原始 Windows 内包 SHA-256 为 `4777fce941e4049e01378ea110f85fcf0f3aeaf84a5cf4c46f7ab3c736b32623`，BUILD_INFO 对应 `66fea8f`，清单 856 个载荷哈希全部符合。v3 UI 内包预期哈希 `41e4c90d6a48cc15bbd6bf0e5bd0e59e056371d65cd7c44acb6f9f36bdcded8d` 来自构建日志，用于 Windows 验收入口的精确匹配；未将外层 Artifact 哈希当成程序 ZIP 哈希。 |

**仍需验证：** 本机是 Apple Silicon Mac，没有 Windows 运行环境。未在 Windows 执行两个历史 EXE、C# 固定启动器、PowerShell 停写检查、NTFS 权限复制/占用、掉电耐久性和 Win32 同端口重启。仅手动触发的 `Windows rc3 upgrade qualification` 工作流及 `scripts/check_windows_upgrade.py` 已准备，但本轮未运行 Actions。Windows 10 19045 + WorkBuddy 真机发现和实际调用仍需独立验收。没有使用真实邮箱、真实业务库、正式定时任务或 Shelley 的电脑。

**发布条件：** 需要 Windows 验收通过、维护者提供并保管正式签名密钥、构建嵌入可信公钥、对经审核的源版本清单签名，再明确授权发布。测试密钥没有作为生产信任根。未经签名、哈希不符、未验证来源或未完成事务不开放升级。普通 Git 推送或 Actions 通过均不会自动发布。

**复核：** 在本分支执行 `uv sync --frozen`、`uv run pytest -q`；Mac 运行 `uv run pyinstaller --clean --noconfirm packaging/workthread.spec`、`uv run python scripts/smoke_frozen.py dist/WorkThread/WorkThread` 和 `uv run python scripts/verify_local_upgrade.py --exe dist/WorkThread/WorkThread`（需本地保留两个历史 Git 对象）。GUI 复核使用 `scripts/check_update_browser.py`、`scripts/check_ui.py` 的 Node、Playwright 和 Chromium 参数。合成运行数据和测试日志只在临时或忽略目录，未纳入提交。
