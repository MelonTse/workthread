# WORKTHREAD-GOAL-002：G4 离线部署资料包交付报告

记录时间：2026-11-05T22:56:55+08:00（Asia/Shanghai）。

**阶段 G4：PASS。完整资料包已在 Mac 本地生成并审核；停止于 G4 闸门，尚未传输或执行 G5。**

授权：WORKTHREAD-GOAL-002-G4-APPROVAL-001。用户已验收 G3，本轮只制作和审核离线资料，不延伸到 Windows 安装、真实邮箱或正式任务。

## 1. 实际交付位置和版本

目录：`/Users/nova/AI/Codex/workthread/artifacts/goal002-g4/WorkThread-Offline-Deploy-V2`。

唯一程序交付为 **WorkThread 1.0.0rc2 Windows x64**；仍保留候选版本及真机待验边界，不是公开 Release。资料版本 GOAL002-G4-V1，部署提示词 ID：**WORKTHREAD-WINDOWS-DEPLOY-ACCEPT-002-G4-V1**。目录含 10 个文件，总计 16,413,655 字节（文件字节相加，不含文件系统开销）。本报告保存在 docs，未放进资料包，不形成清单循环。

## 2. Artifact 来源与本轮重新下载

| 项目 | 实际值 |
|---|---|
| Repository | MelonTse/workthread，来源运行中的 repository.private=true |
| Branch | codex/workthread-1.0.0rc2 |
| Commit | `8f4cea4d37b0ee9ecca0ec21c3d4394fbe45d5ea` |
| Actions Run | [42038443289](https://github.com/MelonTse/workthread/actions/runs/42038443289)，success |
| Artifact | 13420580650 / WorkThread-windows-candidate，未过期 |
| 外层 Artifact ZIP | WorkThread-rc2-G4-artifact.zip，16,110,136 字节 |
| 外层 SHA-256 | `95cb4371cbae60520ac41a59e2f09ea663c1f533452dcfb8bfb31bf61f7f0972`，对应 GitHub digest |
| 内部 Windows 程序 ZIP | WorkThread-1.0.0rc2-windows-x64.zip，16,355,133 字节 |
| 内部程序 SHA-256 | `769286f29c13deab2c86c98d93f5ac1a71c553e6904b3bf8be4e71eede539eb8` |

通过 GitHub 连接器重新读取指定 run/artifact 并重新下载实际字节；没有只引用 G3 旧文件或使用 Mac 包。外层只含程序 ZIP、程序 `.zip.sha256` 和 Windows JUnit；外层容器留在 `.runtime/goal002-g4/` 审核证据，未当作 Windows 程序放入离线包。

内部 ZIP 与本次下载内件、G3 已验收程序和 CI 打包日志的 SHA 一致，内容未经重新构建/重压缩/编辑。离线根文档基于真实构建重新编写；程序 ZIP 内阶段报告/旧状态是不可改的构建快照，START_HERE 明确要求使用离线根目录的当前 rc2 部署说明，不从快照提取旧版本/旧哈希作为操作依据。

## 3. 内部程序重新核验结果

| 检查 | G4 本轮实际结果 |
|---|---|
| ZIP CRC、路径、重复大小写、符号链接、加密标志 | PASS |
| SHA256SUMS.json | 853 载荷全部匹配，精确集合，无多余/缺失；含清单共 854 文件 |
| BUILD_INFO.version | 1.0.0rc2 |
| BUILD_INFO.commit_sha | 8f4cea4d37b0ee9ecca0ec21c3d4394fbe45d5ea |
| BUILD_INFO.runner_os / machine | Windows / AMD64 |
| HTML/JS/CSS、Schema、模板 | 3 + 3 + 6 = 12 资源逐项匹配构建源输入 |
| 原生 EXE/DLL/PYD | 73 个均 AMD64 PE32+；必要 Python/VC DLL 齐全（静态） |
| Windows JUnit | 下载原件记录 133 tests / 0 failures / 0 errors / 0 skipped |
| Install/Start/Health/Backup/Restore.cmd | 全部包含，与构建源码逐项一致 |
| tools/install.ps1、tools/upgrade.ps1 | 包含，双空间 init/doctor；原地升级入口停止覆盖 |
| 当前业务/运行数据 | 无数据库、JSONL、工作空间、业务备份、密钥或凭证文件 |

G4 执行的是下载后的 Mac ZIP/资源/哈希/PE 静态复核。133 项测试和 EXE HTTP 冒烟是在 G3 的 Windows Server 2022 runner 实际执行的历史证据，**本轮未重新运行 Windows Actions，也没有将 Mac 检查记为 Windows 10 真机验收**。G4 没有改动程序，不为纯文档重复运行全部应用测试。

## 4. 完整离线文件清单及逐文件 SHA-256

| 文件 | 字节 | SHA-256 |
|---|---:|---|
| `FILE_MANIFEST.sha256` | 826 | `e5a32abcce90a661d41de469067122c85bb06b45cebc0904f37670f9b6816c49` |
| `START_HERE.md` | 3,717 | `e2712fbd803c51a33f0699fc1607b93e3545ba0fb56799d63b1ebbc7a69c4984` |
| `VERSION_INFO.md` | 2,631 | `ddb8abac2304f86af7389606aeb3a00c58544022215de3503257f3cca9dd1717` |
| `WINDOWS_ACCEPTANCE.md` | 6,454 | `c00ca7de22dc183f20c4be838e88d06a087979b65aa42309762bbeb3d2533172` |
| `WINDOWS_BUILD_REPORT.md` | 4,185 | `71f4da815602790ae8b157a241200fb306a3f39416430dc493e933fffee86df7` |
| `WINDOWS_QUICK_START.md` | 10,101 | `6b37756fcd18a091eb9719ac319f904c9db02626cb84e7413708ddef6440ab96` |
| `WINDOWS_WORKBUDDY_DEPLOY_PROMPT.md` | 25,117 | `c92792d2a7d08ba5fcdaaaf7acd4f52053f066719ae1d4fffead94d744d53980` |
| `WORKBUDDY_SETUP.md` | 5,388 | `2795d50ad93413eb9a45a127262d80299685b7935f54ed44d842501e88ce366f` |
| `WorkThread-1.0.0rc2-windows-x64.zip` | 16,355,133 | `769286f29c13deab2c86c98d93f5ac1a71c553e6904b3bf8be4e71eede539eb8` |
| `WorkThread-1.0.0rc2-windows-x64.zip.sha256` | 103 | `671a9220e1cbb505fc39cde4b73156c29b2fc54e119bcabe2bf541c373c39a9f` |

`FILE_MANIFEST.sha256` 含其他 9 文件的 GNU 风格 SHA-256 行，不列自身，避免自引用循环。上表给出了清单自身 SHA，供用户审核/传输后作为外部锚点。实际清单集合、所有文件哈希及程序旁置校验文件均已重算通过。目录只含这 10 个文件，无隐藏运行产物或额外依赖。

## 5. Skills、规则与双空间模板完整性

程序内模板根为：

```text
app/_internal/workthread/resources/workbuddy_template/
├── CODEBUDDY.md
├── .codebuddy/rules/workthread.md
├── .workthread-template.json
└── .workbuddy/skills/
    ├── workthread-analysis/SKILL.md
    ├── workthread-intake/SKILL.md
    └── workthread-knowledge/SKILL.md
```

| Skill | 完整文件 SHA-256 | frontmatter / 原业务前缀 / 完整源码 |
|---|---|---|
| `workthread-analysis` | `04703e0fde53a9301b4fe6f798dbce8d2d420c9f34e4ea7ea8a17021617a9bb4` | PASS |
| `workthread-intake` | `f69ef158df859aff971512930431f55e86dc97a38fd4613ffde03704d3ab5245` | PASS |
| `workthread-knowledge` | `0065c6d646f6d870505f989c698aff3907e406a6b6cd796be9904f033c7a2fa3` | PASS |

三个 Skill 的 name 与目录名一致、description 非空，原业务正文前缀哈希及完整字节通过，保留三个原职责，没有合并或改写。CODEBUDDY.md、项目规则和 .workthread-template.json 实际包含且对应模板版本 1.0.0rc2；三个 Schema 同时纳入。新包中不存在旧 .codebuddy/skills 模板目录。

Install.cmd / tools/install.ps1 分别初始化 workspace、acceptance，并部署相同版本模板/Schema/交换目录；Windows G3 源测试已执行两空间隔离、初始空白、自定义文件保护和冲突退出。本轮重新检查脚本/模板内容，未初始化目标 Windows 目录。

提示词要求：通过 GUI Open Folder 选正确合成项目，确认信任，新建会话；分别证明文件存在、两份规则加载、三个 Skill 发现、三个 Skill 实际调用和 Python 入库；第二独立会话再次发现/调用。不能用读取 SKILL.md、模型自报或 CI 文件存在代替客户端证据。当前仍未宣称 WorkBuddy 实际发现成功。

## 6. 固定部署目录和离线操作审核

| 用途 | Windows 路径 |
|---|---|
| 离线资料 | `F:\WorkThread-Offline-Deploy-V2` |
| 程序 | `F:\WorkThread` |
| 正式空间 | `F:\WorkThread\workspace` |
| 正式 WorkBuddy 项目 | `F:\WorkThread\workspace\agent-workspace` |
| 合成空间 | `F:\WorkThread\acceptance` |
| 本次 GUI Open Folder 必选 | `F:\WorkThread\acceptance\agent-workspace` |

离线资料目录和程序根不是 WorkBuddy 项目。新会话需重新传入完整任务上下文并标明安装进度，不重复覆盖安装。目标 F 盘/目录/端口异常时停止，不自行改盘符或杀未知进程。

提示词可独立提供给目标 WorkBuddy，包含：固定身份、完整本地 SHA/文件清单核验、唯一临时目录解压及顶层目录处理、复制前后 853 文件检查、两空间 init/doctor、初始空白 serve 取证后再 demo、两份健康检查和网页、CSRF 的 API 日期四组合/Progress、三 Skill 自然语言路由/实际调用/新会话、真实 AI 文件交换/回执/重复/过期、两类普通 ZIP/新目录预览恢复/重启、失败停止及报告格式。特别说明 schema_version 仍为 1.0，重复回执为 completed + duplicate=true，CLI restore preview 会先初始化新目标，避免按错误预期执行。

Mac 静态审阅已将所有 CLI 参数、HTTP 路由/正文和回执字段对应到 8f4cea4d 构建源；速查与完整提示词前三段 PowerShell 校验/安装/启动命令逐字一致。Mac 环境未运行 PowerShell 5.1 或 Windows GUI，命令真机执行仍归 G5，静态审阅通过不冒充运行通过。

安装不需 GitHub 登录、git、在线下载、系统 Python、pip/uv 或额外依赖；所有必要程序资源均在已校验 ZIP 内。来源链接只供追溯，不是操作依赖。WorkBuddy 真实 AI 使用其已配置模型能力，本资料包不包含离线模型，也不承诺断网推理；不要求新填任何凭证。

## 7. 敏感信息与业务数据隔离

检查 7 份交付 Markdown，以及程序内 48 个 Markdown/JSON/PowerShell/CMD/HTML/JS/CSS 文本资源；常见私钥/GitHub/AWS/模型 Token 模式未发现。路径检查未见业务数据库、JSONL、真实 To Do、客户知识、运行回执/日志、业务备份或凭证。`app/_internal/base_library.zip` 为 PyInstaller 标准库资源，不是备份。未读取旧版 Shelley 项目。

自有源码/文档邮箱域仅 example.org。扫描额外发现两份**公开第三方依赖**文件含域名：jsonschema 的 Swagger 示例 issue.json（swagger.io）和 Werkzeug 的 ICON_LICENSE.md 公开作者署名（gmail.com）。两者均按精确文件哈希与本地已锁定依赖逐字节比对通过；它们不是用户邮件/业务知识，未采用对 gmail.com 等域名整体放行，也未删除许可证或改动程序 ZIP。完整分类证据在 delivery-audit.json。

本轮未扫描被忽略的个人资料或其他项目来寻找信息；扫描结论限于上述文件集合、路径和模式，不能保证任意自然语言绝无敏感信息。

原 79 个 G3 构建源文件逐一指纹不变，G3 报告指纹不变，原始本地 HEAD `2c3838a1769ca1af9e99520ce380b1ec707b46d6` 和主 Git 索引保留。最终远端只读核对 main 仍为 `1a5c32356e30f4903f484dfb266fe714566c1e7c`、候选仍为 8f4cea4d；没有提交、推送、Actions、Release 或修改其他仓库。本轮新增的可审阅文档仅本报告，资料及证据位于被忽略的 artifacts/.runtime。

## 8. Windows 10 边界及真机未完成事项

目标是 Windows 10 Professional 22H2 19045 x64 / WorkBuddy 5.9.3；原生 CI 是 Windows Server 2022 20348。包内 x64 头部/导入表和依赖静态核对通过，但无法由此证明目标系统上的 UCRT/VC 加载、动态系统 API、权限、Defender、文件占用或客户端行为。

下列均保留为 G5 待执行，不填 PASS：

- 全新 F 盘目录安装和启动；PowerShell 5.1/cmd、Explorer 普通 ZIP、中文/空格路径、系统依赖及健康检查。
- 两个工作空间初始空白、合成数据隔离，正式无账号/业务/计划；To Do 四组合全部入口和 Progress/人工保护。
- GUI 绑定/信任、两份项目规则真实加载、三个 Skill 各自被发现/实际调用、第二独立会话再次发现/调用。
- 真实 WorkBuddy 合成 AI 输出、Python saved/completed 及业务记录；重复零增量和 superseded 保护。
- 两类无密码 ZIP、manifest/哈希、隔离新目录恢复/重启、损坏/manifest/路径负例拒绝且原数据保留。

报告模板和部署提示词都要求逐项 PASS/FAIL/BLOCKED/未测试，提供会话/工具调用/HTTP/回执/业务 ID，而非模型口头确认。失败停止相应验收；只有真机报告的关键项通过且用户最终批准后，才可能讨论真实 IMAP，G4/G5 完成均不自动授权邮箱或正式计划。

## 9. 本地审核证据

`.runtime/goal002-g4/` 保存 remote-source.json、重新下载的外层 Artifact ZIP、verified-inner/、artifact-audit.json、package-file-inventory.json、delivery-audit.json、delivery-files.json、document-build.json、remote-final.json 和本轮入口状态/源指纹。没有将签名下载 URL、凭证、临时日志或运行证据放入交付目录。程序和资料文件均留在本机，未传输。

## 10. 闸门审批记录

阶段：G4 — 完整 Windows 离线部署资料包制作与审核。

完成情况：**PASS**；10 文件资料目录、逐文件校验清单、完整可单独提供的 WorkBuddy 提示词和本报告已完成。本轮没有执行 G5。

通过项目：指定 Artifact 重新下载及来源核对；Windows 程序原件/853 文件/BUILD_INFO/3 Skills/规则/双空间脚本；10 文件及哈希；固定路径、日期/AI/ZIP/新会话验收指令；本地依赖/敏感信息隔离静态审核；旧源/报告/HEAD/main 保持。

失败项目：最终 G4 必要检查无失败。第三方公开示例/署名域已具体分类并匹配锁定依赖，不作为用户业务数据，也没有忽略未知发现。

尚未验证项目：全部 Windows 10 19045 真机安装、客户端加载/发现/调用、真实 WorkBuddy AI 回执、系统/文件恢复与重启；PowerShell 指令实际运行。详见第 8 节，不能用本轮静态审核代替。

是否存在数据风险：本轮只读构建产物和现有源码，写入全新本地交付目录/证据/报告；未安装、恢复或修改任何现有 Windows 工作空间，无真实数据操作。后续真机执行遇现有路径、哈希异常、关键失败必须停止，仍须保留文件系统及环境未验证边界。

下一阶段准备执行的操作：获用户批准后才允许传输该资料目录，并由 Shelley Windows 上的 WorkBuddy 在指定目标环境执行 G5 全新合成安装验收，完成真机报告后再次停止。

需要用户授权的事项：**审核本资料包并明确批准传输及进入 G5。** 当前不传输、不安装、不连接真实邮箱、不创建正式任务，不发布公开 Release。

**停止于 G4 闸门，等待用户明确回复。**
