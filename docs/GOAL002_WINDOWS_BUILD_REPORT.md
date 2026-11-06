# WORKTHREAD-GOAL-002：G3 Windows 候选构建报告

记录时间：2026-11-05T21:55:58+08:00。

**阶段 G3：PASS。只完成源码候选提交、私有分支发布、Windows 原生构建及 Artifact 检查；停止于 G3 闸门，等待用户批准 G4。**

授权：WORKTHREAD-GOAL-002-G3-APPROVAL-001，以及用户对“两项修复并继续 G3”的明确追加批准。此报告是构建后的本地验收交付，尚未提交到远端，也不在此次已构建 ZIP 内；程序构建 SHA 始终为下列 8f4cea4d，不混用文档生成时间或历史 rc1 SHA。

## 1. Git 基线、分支和真实提交

| 项目 | 实际值 |
|---|---|
| 仓库 | [MelonTse/workthread](https://github.com/MelonTse/workthread)，最终复核 visibility=private |
| 实际远端 base/main | `1a5c32356e30f4903f484dfb266fe714566c1e7c` |
| 独立候选分支 | `codex/workthread-1.0.0rc2` |
| 第一笔 G2 完整修改提交 | [7f119dd468b826861ccf852097cdb32c1dcb490e](https://github.com/MelonTse/workthread/commit/7f119dd468b826861ccf852097cdb32c1dcb490e) |
| 用户批准的附加修复提交 / 实际构建 SHA | [8f4cea4d37b0ee9ecca0ec21c3d4394fbe45d5ea](https://github.com/MelonTse/workthread/commit/8f4cea4d37b0ee9ecca0ec21c3d4394fbe45d5ea) |
| 最终 source tree | `fcecf19d9cea333a7ffd2d51ee64972430ef0f2e` |
| main → 候选 | ahead 2 / behind 0，merge base 即上述 main |
| 最终差异 / 源文件集合 | 58 个逻辑差异项（含 3 次 Skill 迁移；61 个物理路径）/ 79 个源文件 |
| 原本地 HEAD | `2c3838a1769ca1af9e99520ce380b1ec707b46d6`，保持不动，主索引无本轮暂存 |

重新读取 GitHub main 及其完整递归树（未截断、62 个文件），比对 rc1 基线：62 个文件内容相同，无额外远端文件、无冲突。独立 Git 副本以真实远端 main 为父提交应用 G2 完整补丁，首笔 tree 精确等于 G2 审阅树 `53b4c36473c8d3e071d0d1f715b67dc9f1ead7b4`。没有把不相干的本地历史推到远端。

通过已连接 GitHub 连接器创建 Git tree/commit/ref，更新候选分支使用 expected SHA 和 force=false。没有改写 main、force push 或覆盖 rc1。最终再次读取 main 和候选 ref，值与表格一致。原始 rc1 的 62 文件隔离快照、G0/G1/G2 的 8 份报告逐文件指纹保持；当前源文件与远端构建提交逐字节匹配（本报告是另行新增的本地文档）。

## 2. 首轮失败、原因和已批准修复

首轮 [Actions 42036275554](https://github.com/MelonTse/workthread/actions/runs/42036275554) 对应 7f119dd：128 passed / 1 failed / 2 warnings；后续构建/上传步骤被跳过，无 Windows rc2 ZIP。

1. `test_all_three_original_business_bodies_preserved`：Windows checkout 的 autocrlf 将 LF 转成 CRLF，破坏原业务正文的固定字节前缀哈希。本地转换可精确复现失败哈希。新增 `.gitattributes` 仅固定模板、Schema 和相关 JSON 夹具为 LF；保留原测试断言及原 Skill 正文。真实 `core.autocrlf=true` checkout 模拟验证三个哈希一致。
2. ZIP 下载临时目录：`send_file` 的 direct_passthrough 绕过 Response.call_on_close；Mac 可能过早删除仍在发送的 ZIP，Windows 因文件未关闭而清理失败。`server.py` 改用 `ClosingIterator`，保持目录至流关闭，先关闭文件再清理目录。

附加修复正好 4 个文件：`.gitattributes`、`src/workthread/server.py`、`tests/test_download_lifecycle.py`、`tests/test_zip_backups.py`，49 行新增/1 行删除。新增 4 例 To Do/Full × 完整读取/提前关闭测试：修复前 4 failed，修复后通过；已有测试显式关闭下载响应。未 skip/xfail、放宽断言或更改 UI、日期规则、AI 业务逻辑、数据库结构。用户先审阅并明确批准后才追加 8f4cea4d。

最终源集合与 G2 的 77 文件逐一核对：只新增 `.gitattributes`、`tests/test_download_lifecycle.py`，只修改 `server.py`、`test_zip_backups.py`；其余 G2 文件指纹全部一致，Skill 迁移无遗漏。首轮提交、日志及修复前失败证据保留。

## 3. 自动测试和 Windows Actions

最终成功运行：[Actions 42038443289](https://github.com/MelonTse/workthread/actions/runs/42038443289)；job 127282605431，head SHA=`8f4cea4d37b0ee9ecca0ec21c3d4394fbe45d5ea`，所有步骤 success。

| 环节 | 结果 |
|---|---|
| Mac 提交前 G2 完整源集合 | 129 passed in 3.99s |
| 远端 base 独立候选副本 | 129 passed in 5.03s |
| 附加修复后 Mac 全量 | 133 passed in 4.04s |
| 最终 Windows 全量 | **133 passed in 82.94s；JUnit 133 / 0 failures / 0 errors / 0 skipped** |
| Windows 源码隔离 | PASS，79 个已审路径 |
| PyInstaller onedir 原生打包 | PASS，生成 `app/WorkThread.exe` |
| 冻结 EXE HTTP 冒烟 | PASS |
| rc2 ZIP / SHA-256 / 文件清单 | PASS |
| Actions Artifact 上传及 Mac 下载 | PASS |

JUnit 记录的累计时长为 82.899s；控制台总时长 82.94s，统计口径不同。原生 runner 为 Microsoft Windows Server 2022 10.0.20348 / windows-2022（并非 Windows 10 19045），Python 3.13.17 AMD64，uv 0.13.7，PyInstaller 6.22.3，Werkzeug 3.1.9。使用现有 `.github/workflows/windows.yml`，配置未改，`uv sync --frozen --python 3.13` 使用提交内依赖锁。

| 测试组 | 数量 | 结果 |
|---|---:|---|
| 日期全部入口 | 37 | PASS |
| 日期领域规则 | 8 | PASS |
| 项目模板初始化 | 5 | PASS |
| ZIP 下载流生命周期 | 4 | PASS |
| M0 | 2 | PASS |
| M1 | 3 | PASS |
| M2 | 6 | PASS |
| M3 | 6 | PASS |
| M4 | 4 | PASS |
| M5 | 3 | PASS |
| 邮件草稿保护 | 3 | PASS |
| 韧性/保护 | 10 | PASS |
| 恢复故障注入 | 9 | PASS |
| 源码安全 | 4 | PASS |
| ZIP 备份恢复 | 29 | PASS |

Windows 本轮实际覆盖：四种日期组合、新建/编辑/AI 全部写入入口；To Do/Progress/人工确认/重复及过期结果保护；两类无密码 ZIP 的创建、预览、独立恢复与重启；损坏/CRC/manifest/hash/数据库/JSONL/危险路径拒绝；9 个恢复故障注入回滚；三个 Skill 模板、自定义文件保护、两个空工作空间隔离；4 个 HTTP ZIP 流关闭/清理场景。测试均使用隔离临时合成目录，无真实邮箱或业务数据。

最终 pytest 没有应用测试警告。Actions 仍有 Node.js 20 action 运行时弃用（runner 强制使用 Node 24）及 url.parse 弃用提示，步骤成功；属于现有 CI 依赖维护项，未在本轮追加无关 workflow 修改，也不称“零告警”。

## 4. 冻结 EXE 实际冒烟边界

CI 在中文/空格的新临时路径直接运行 Windows `WorkThread.exe --workspace <tmp>/workspace demo`，完成 HTTP 冷启动、HTML/JS 获取、CSRF、To Do 新建及状态更新、两条 Progress Log、SQLite 健康检查、无密码 Full ZIP 创建和恢复、恢复后状态/日志核对，以及打包 Schema 的初始化存在检查。控制台明确输出：`Frozen native startup, HTML/JS, schemas, SQLite, plain ZIP full backup and restore: passed`。

这是 Windows runner 上实际运行 EXE 的结果；没有在 Mac 执行 Windows EXE。该脚本使用合成单空间；正式/合成双空间隔离及恢复故障注入由 Windows 全量源测试覆盖，CMD/PowerShell GUI 全新安装体验仍属 G5。

## 5. Artifact 下载及 ZIP 完整性

| 项目 | 实际值 |
|---|---|
| Artifact | `WorkThread-windows-candidate`，ID `13420580650` |
| Artifact ZIP 大小 | 16,110,136 字节 |
| Artifact SHA-256 | `95cb4371cbae60520ac41a59e2f09ea663c1f533452dcfb8bfb31bf61f7f0972`（与 GitHub digest 一致） |
| 程序 ZIP 名称 | `WorkThread-1.0.0rc2-windows-x64.zip` |
| 程序 ZIP 大小 | **16,355,133 字节**（约 15.60 MiB） |
| 程序 ZIP SHA-256 | **`769286f29c13deab2c86c98d93f5ac1a71c553e6904b3bf8be4e71eede539eb8`** |
| 载荷文件清单 | `SHA256SUMS.json`，853 个载荷文件全部匹配；加清单本身共 854 文件 |
| BUILD_INFO | version=1.0.0rc2 / commit=8f4cea4d… / Windows / AMD64 |

从私有 Actions 下载实际 Artifact，Mac 上重新计算外层 SHA 对应 GitHub digest；外层正好包含程序 ZIP、`.zip.sha256` 和 `windows-tests.xml`。程序 SHA 同时对应旁置校验文件及 CI 打包日志。外层/内层 ZIP 的 CRC、路径穿越、盘符、重复/大小写冲突、符号链接和加密标志检查通过。包内文件集合与清单集合完全一致，无漏项/多余文件。

本地产物位于 `artifacts/goal002-g3/`：

- `WorkThread-rc2-G3-artifact.zip`：下载原件。
- `WorkThread-1.0.0rc2-windows-x64.zip`：Windows 候选程序。
- `WorkThread-1.0.0rc2-windows-x64.zip.sha256`：程序哈希。
- `windows-tests.xml`：实际 Windows JUnit。

没有制作 G4 离线资料目录，没有把候选产物交付为正式安装版，没有传输至 Shelley Windows。

## 6. 三个 Skills、隐藏目录及初始化模板

ZIP 内模板根目录：

```text
WorkThread-1.0.0rc2-windows-x64/app/_internal/workthread/resources/workbuddy_template/
├── CODEBUDDY.md
├── .codebuddy/rules/workthread.md
├── .workthread-template.json
└── .workbuddy/skills/
    ├── workthread-analysis/SKILL.md
    ├── workthread-intake/SKILL.md
    └── workthread-knowledge/SKILL.md
```

| Skill | frontmatter | 原业务正文前缀 | 完整文件 SHA-256 |
|---|---|---|---|
| `workthread-analysis` | PASS | PASS | `04703e0fde53a9301b4fe6f798dbce8d2d420c9f34e4ea7ea8a17021617a9bb4` |
| `workthread-intake` | PASS | PASS | `f69ef158df859aff971512930431f55e86dc97a38fd4613ffde03704d3ab5245` |
| `workthread-knowledge` | PASS | PASS | `0065c6d646f6d870505f989c698aff3907e406a6b6cd796be9904f033c7a2fa3` |

三个文件各自存在；`name` 与目录名一致、`description` 非空，完整字节与最终源码一致、LF 固定，模板版本 1.0.0rc2。原业务前缀依 `.workthread-template.json` 的 bytes/SHA 逐一通过，三个 Skill 未合并。新包不存在旧 `.codebuddy/skills/` 模板目录。

HTML/JS/CSS 3 件、JSON Schema 3 件及模板 6 件共 12 个资源逐项比对通过；模板/Schema 字节完全一致，网页允许 Git checkout 的 CRLF/LF 等价。CODEBUDDY、规则和元数据均完整，不只检查三个文件名。

`Install.cmd`、`Start.cmd`、`Health.cmd`、`Backup.cmd`、`Restore.cmd`、`tools/install.ps1`、`tools/upgrade.ps1` 全部包含且与最终源码一致（行尾归一）。CMD/PowerShell 初始化脚本分别处理 workspace 和 acceptance；Python 初始化的独立性、保持空白、自定义保护与冲突退出已在 Windows 源测试执行。Backup/Restore 无密码输入；Restore 要求新目录并先预览/确认。

**文件打包/模板初始化 PASS 不等于 Windows WorkBuddy 5.9.3 已自动发现或加载规则。** 本轮未取得客户端注册表、可用 Skill 列表、三个 Skill 实际调用、新会话再次调用的证据；这些均留待 G5。

## 7. Windows 10 19045 静态兼容检查与未验证边界

实际 ZIP 中 73 个 EXE/DLL/PYD 全部为 Machine=0x8664、PE32+=0x20b；子系统版本为 5.2/6.0/10.0，无高于 10.0 的头部要求。`python313.dll`、`python3.dll`、`VCRUNTIME140.dll` 已随包；逐个解析普通和延迟导入，非系统依赖均可在包内找到。外部依赖名单为 Windows 系统 DLL/API-set：advapi32.dll, api-ms-win-core-path-l1-1-0.dll, bcrypt.dll, bcryptprimitives.dll, crypt32.dll, iphlpapi.dll, kernel32.dll, ntdll.dll, ole32.dll, oleaut32.dll, propsys.dll, rpcrt4.dll, user32.dll, version.dll, ws2_32.dll。

官方 [Python 3.13 Windows 文档](https://docs.python.org/3.13/using/windows.html)列出 Windows 8.1 及更新版本支持。实际导入的 [PathCchCombineEx](https://learn.microsoft.com/en-us/windows/win32/api/pathcch/nf-pathcch-pathcchcombineex)、[PathCchSkipRoot](https://learn.microsoft.com/en-us/windows/win32/api/pathcch/nf-pathcch-pathcchskiproot) 和 [ProcessPrng](https://learn.microsoft.com/en-us/windows/win32/seccng/processprng) 的文档最低客户端为 Windows 8；[PssCaptureSnapshot](https://learn.microsoft.com/en-us/windows/win32/api/processsnapshot/nf-processsnapshot-psscapturesnapshot) 为 Windows 8.1。结合导入名单及成功的原生 smoke，静态检查未发现阻断 Windows 10 19045 的已知缺失依赖；这是有边界的静态判断，不能证明全部动态 API、系统组件及真机行为。

必须在 G5 使用 Windows 10 19045 x64 / WorkBuddy 5.9.3 实际验证：

- 全新解压、Install/Start/Health/Backup/Restore、PowerShell 5.1/cmd、中文/空格路径、Explorer ZIP、权限/Defender/文件占用。
- 程序依赖及 UCRT/VC 运行时的真机加载、重启后数据完整性、两类 ZIP 与故障行为。
- 正式和合成工作空间独立；GUI Open Folder 打开正确 agent-workspace 并信任；项目规则实际加载。
- 三个 Skill 的客户端可用列表/注册记录、逐一真实调用和独立新会话再调用，不能人工读取 SKILL.md 替代。
- 真实 WorkBuddy AI（仅合成输入）的结果文件与 Python completed 回执、重复/过期保护，不能以 AI 生成文件替代入库完成。

本轮未连接真实邮箱、操作 Credential Manager 中的真实凭证或创建任何正式任务。Windows runner 成功不替代上述真机验收。

## 8. 提交安全审核及文件清单

提交前两轮 Mac 全量测试、staged/working diff --check、79 文件最终源码隔离检查通过。最终独立副本 HEAD/索引/工作区逐字节一致；完整最终补丁及文件指纹保留。扫描 staged 字节及当前源码的运行/数据/备份/日志/凭证路径、私钥/GitHub/AWS/模型 Token 模式；额外邮箱域扫描只见 example.org，真实业务域发现为 0。11 个忽略探针通过。

没有提交 `.runtime`、artifacts、dist/build、SQLite、JSONL、运行 To Do、知识/业务资料、备份、凭证、临时日志或回执。安装包也未包含工作空间、数据库、JSONL、备份或密钥；唯一内嵌 ZIP 为 PyInstaller 必需的 `app/_internal/base_library.zip` 标准库资源。该审查不宣称可证明任意自然语言绝无敏感内容。

第一笔提交 56 个逻辑差异项，附加修复 4 文件，其中 2 文件已在第一笔差异内；累计如下 **58 项**（Skill 迁移各计一项，展开删除/新增为 61 物理路径）。完整源集合 79 文件指纹见本地 `final-source-manifest.json`。

| 状态 | 已提交路径 |
|---|---|
| added | `.gitattributes` |
| modified | `.gitignore` |
| modified | `README.md` |
| modified | `WORKBUDDY_SETUP.md` |
| modified | `docs/ARCHITECTURE.md` |
| added | `docs/GOAL002_BASELINE.md` |
| added | `docs/GOAL002_G1_ACCEPTANCE.md` |
| added | `docs/GOAL002_G1_BACKUP_REPORT.md` |
| added | `docs/GOAL002_G1_FAILURE_REVIEW.md` |
| added | `docs/GOAL002_G1_SKILLS_REPORT.md` |
| added | `docs/GOAL002_G1_WINDOWS10_STATIC.md` |
| added | `docs/GOAL002_MAC_ACCEPTANCE.md` |
| added | `docs/GOAL002_RELEASE_AUDIT.md` |
| modified | `docs/UI_GUIDELINES.md` |
| modified | `docs/WINDOWS_ACCEPTANCE.md` |
| modified | `docs/WINDOWS_QUICK_START.md` |
| modified | `docs/WINDOWS_WORKBUDDY_DEPLOY_PROMPT.md` |
| modified | `pyproject.toml` |
| modified | `scripts/check_source.py` |
| modified | `scripts/create_schemas.py` |
| modified | `scripts/install.ps1` |
| modified | `scripts/package_release.py` |
| modified | `scripts/portable-backup.cmd` |
| modified | `scripts/portable-health.cmd` |
| added | `scripts/portable-install.cmd` |
| modified | `scripts/portable-restore.cmd` |
| modified | `scripts/portable-start.cmd` |
| modified | `scripts/smoke_frozen.py` |
| modified | `scripts/upgrade.ps1` |
| modified | `src/workthread/__init__.py` |
| modified | `src/workthread/ai.py` |
| modified | `src/workthread/cli.py` |
| modified | `src/workthread/core.py` |
| modified | `src/workthread/demo.py` |
| modified | `src/workthread/deployment.py` |
| modified | `src/workthread/operations.py` |
| modified | `src/workthread/schemas/ai-output.json` |
| modified | `src/workthread/schemas/intake.json` |
| modified | `src/workthread/server.py` |
| modified | `src/workthread/web/static/app.js` |
| added | `tests/fixtures/rc1-project-files.json` |
| added | `tests/test_deadline_entries.py` |
| modified | `tests/test_deadlines.py` |
| added | `tests/test_deployment.py` |
| added | `tests/test_download_lifecycle.py` |
| modified | `tests/test_m1.py` |
| modified | `tests/test_m4.py` |
| modified | `tests/test_m5.py` |
| modified | `tests/test_resilience.py` |
| added | `tests/test_restore_safety.py` |
| added | `tests/test_zip_backups.py` |
| modified | `uv.lock` |
| modified | `workbuddy_template/.codebuddy/rules/workthread.md` |
| renamed | `workbuddy_template/.codebuddy/skills/workthread-analysis/SKILL.md → workbuddy_template/.workbuddy/skills/workthread-analysis/SKILL.md` |
| renamed | `workbuddy_template/.codebuddy/skills/workthread-intake/SKILL.md → workbuddy_template/.workbuddy/skills/workthread-intake/SKILL.md` |
| renamed | `workbuddy_template/.codebuddy/skills/workthread-knowledge/SKILL.md → workbuddy_template/.workbuddy/skills/workthread-knowledge/SKILL.md` |
| added | `workbuddy_template/.workthread-template.json` |
| modified | `workbuddy_template/CODEBUDDY.md` |

## 9. 证据索引与 G4 内容预览

本地证据位于 `.runtime/goal002-g3/`（均不推送）：

- `candidate-baseline.json`、`remote-base.json`：实际 main 和完整树。
- `pre-submit-audit.json`、`final-source-audit.json`、`final-source-manifest.json`：审核和指纹。
- `final-submitted-diff.patch`、`final-submitted-name-status.txt`、`final-compare.json`：实际提交差异。
- `windows-failure-1.log`、`line-ending-reproduction.json`、`download-lifecycle-before.log`：首轮问题证据。
- `REPAIR_REVIEW.md`、`repair-proposal.patch`、`repair-approval.json`、`repair-tests.xml`：追加审批/修复测试（REPAIR_REVIEW 保留审批前原文状态，以本报告的实际提交为准）。
- `windows-success.log`、`windows-success-run.json`、`windows-success-artifact.json`：最终 CI 原始证据。
- `artifact-audit.json`、`package-file-inventory.json`、`pe-import-symbols.json`：包内全量校验/静态 PE 导入。
- `final-remote-audit.json`：最终 private/main/candidate/steps 复核。

下一阶段仅准备制作、审阅 `WorkThread-Offline-Deploy-V2/`，至少纳入当前 Windows rc2 ZIP、SHA 文件、WINDOWS_BUILD_REPORT.md、WINDOWS_QUICK_START.md、WINDOWS_ACCEPTANCE.md、WORKBUDDY_SETUP.md、WINDOWS_WORKBUDDY_DEPLOY_PROMPT.md、VERSION_INFO.md 及资料校验清单。版本、SHA 和本次报告将写入真实值；现有部署提示词仍为 `WORKTHREAD-WINDOWS-DEPLOY-ACCEPT-002-G1-DRAFT`，G4 需整理为离线交付版。

路径预览保持 `F:\WorkThread-Offline-Deploy-V2`（资料）、`F:\WorkThread`（程序）、`F:\WorkThread\workspace\agent-workspace`（正式项目）和 `F:\WorkThread\acceptance\agent-workspace`（合成项目）；资料目录不得用作 WorkBuddy 项目。G4 完成后仍需独立审批，才允许传输资料并开始 Windows 安装。当前未建立/传输此离线资料包。

## 10. 闸门审批记录

阶段：G3 — GitHub 源码提交、私有候选分支及 Windows 构建。

完成情况：**PASS**；实际 rc2 提交、Windows 原生候选 ZIP、下载校验及本报告已完成。此 PASS 仅针对 G3 必要条件，不是正式安装或 G5 真机通过。

通过项目：远端 main 基线和独立分支；G2 完整差异及已批准的 4 文件修复；Mac 133/Windows 133 测试；源隔离；原生 EXE/HTTP 冒烟；853 文件哈希；3 Skills/12 资源/7 脚本；73 PE 的 x64 静态检查；原始基线/8 报告保护；main 不变/仓库私有。

失败项目：最终关键测试无失败。首轮 1 失败和 ZIP 清理问题已修复并复测；Actions 运行时弃用提示为非阻断维护项，保留记录。

尚未验证项目：Windows 10 19045 x64 全新安装、实际客户端规则加载/3 Skills 列表及调用/新会话、真实 WorkBuddy 合成 AI→Python 回执、真机文件系统/运行时/Defender/Explorer 行为；G4 离线资料包尚未制作。

是否存在数据风险：本轮未触碰真实业务数据、旧版 Shelley 项目或历史备份；所有执行恢复均在隔离合成临时目录。已测故障回滚通过，无已知未修复数据安全阻断；断电、磁盘故障或回滚时第二次 I/O 失败等未验证边界仍需保留，不能据此承诺任意环境零风险。

下一阶段准备执行的操作：获得批准后才制作 G4 全新 Windows 离线部署资料包，统一路径/版本/真实 SHA，完善 WorkBuddy GUI/信任/三个 Skill 真调用取证说明并生成校验清单；完成后再次停止。

需要用户授权的事项：**批准进入 G4（只制作并审核完整离线资料包）。** 不默认包含传输、安装、正式发布、真实 IMAP 或正式定时任务；传输/全新安装须通过 G4 闸门后另行明确批准。

**停止于 G3 闸门，等待用户明确回复。不自动进入 G4。**
