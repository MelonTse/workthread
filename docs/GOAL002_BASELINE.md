# WORKTHREAD-GOAL-002：G0 现有项目检查与基线冻结

记录时间：2026-11-05 16:09:55 CST。项目：`/Users/nova/AI/Codex/workthread`。

**G0：PASS（检查及基线冻结完成；等待用户批准进入 G1）。**

本报告区分修改前 rc1 基线、收到阶段闸门前已经产生的未完成修改、未来需要批准的阶段。不将当前工作副本称为已验收 rc2，不以 Mac 或 CI 结果代替 Windows 真机验收。

## 1. 执行边界及当前状态

- 本轮开始时分支为 `main`，HEAD 为 `2c3838a1769ca1af9e99520ce380b1ec707b46d6`，`git status --short` 输出为空，原工作区干净。
- 收到阶段闸门前已创建本地分支 `codex/workthread-1.0.0rc2`，HEAD 未改变，没有新建提交、暂存或推送。
- 收到闸门前，按原目标开始了部分核心修改；收到闸门后立即停止继续修改程序，仅执行 G0 检查、隔离基线测试及撰写本报告。未自动恢复或删除这些修改。
- 待审修改共 24 个文件路径（17 个跟踪文件修改、3 个原 Skills 路径显示删除、4 个未跟踪新路径；精确状态见第 8 节）。三个 Skills 内容迁至新目录并附加接口说明，原始版本完整保存在 Git HEAD 与隔离快照中。本报告新增后，Git 还会显示本报告为未跟踪文件。
- 所有业务测试使用新建临时合成目录。未读取或修改真实业务工作空间，未读取旧版 Shelley 项目，未连接真实 IMAP，未启动正式调度，未处理历史 `.7z` 文件。
- 未修改 WorkBuddy 客户端内部程序、缓存或全局 Skills。未执行 GitHub 写入、推送、构建或发布。

## 2. 修改前版本及测试基线

| 检查 | 结果 | 证据范围 |
|---|---|---|
| 原始产品版本 | PASS：1.0.0rc1 | HEAD 中 pyproject.toml、__init__.py、core.health、package_release.py 一致 |
| 数据库版本 | v2 | 本次尚未修改 DDL 或数据库迁移版本 |
| AI JSON 契约 | 1.0 | 原始 schemas 与 Bridge |
| 原始完整自动测试 | **PASS：49 passed in 4.42s** | 从 HEAD 导出的独立 rc1 副本，Python 3.13.18，原始 uv.lock，独立虚拟环境 |
| 原始源码隔离检查 | **PASS：62 reviewed paths** | 在独立 rc1 副本自身 Git 索引检查，不借用已修改工作副本 |
| 修改前文件清单 | PASS：62 个跟踪文件 | 第 9 节含每个文件 SHA-256；机器清单位于 .runtime/goal002-g0/baseline-files.json |
| 当前未完成修改试运行 | **FAIL：35 passed，14 failed** | 收到阶段闸门前运行。旧测试仍要求“不定日期可写入”和加密备份；尚未调整与补测，不计作 rc2 验收 |
| 当前 diff 基本检查 | PASS：git diff --check 无输出 | 仅说明无 diff 空白错误，不代表功能通过 |

隔离副本：`.runtime/goal002-g0/rc1-source-frozen/`。由 `git archive HEAD` 导出，仅含原跟踪源码，没有工作空间数据；另建独立虚拟环境与本地 Git 索引用于测试。未重建或运行新的 Mac 冻结程序。

冻结证据（均被忽略，不准备上传）：

- `.runtime/goal002-g0/baseline-source.tar`：原始源码快照。
- `.runtime/goal002-g0/baseline-files.json`：62 个文件的大小及 SHA-256。
- `.runtime/goal002-g0/baseline-tests.log`、`baseline-tests.xml`：本次原始基线测试。
- `.runtime/goal002-g0/baseline-source-isolation.log`、`baseline-results.json`：本次隔离检查及退出码。
- `.runtime/goal002-g0/work-in-progress.patch`、`work-in-progress-status.txt`、`work-in-progress-files.json`：收到闸门后冻结的未完成改动及指纹。未跟踪文件另有指纹，实际内容保留在工作副本。
- `.runtime/goal002-g0/existing-mac-resource-check.json`：现有 Mac 包资源与原始 HEAD 的逐字节比较结果。

## 3. 现有 Mac 产物与 Windows 配置

### Mac

现有 `dist/WorkThread/WorkThread` 为 Mach-O arm64 程序，大小 6,548,448 字节。已静态比较其 11 个网页、Schema 与规则/Skills 资源，均与原始 rc1 HEAD 相同。

现有历史包 `artifacts/WorkThread-1.0.0rc1-macos-arm64-20261104.zip` 大小 17,139,889 字节，本次重算 SHA-256：

`83aa9472f5f849caca0a50f77b972d057517776d60691a2f8fea51598a4f4dd2`

与 `artifacts/rc-mac-package.json` 一致。历史报告记载 Mac 冻结冒烟与浏览器回归通过；**G0 本次只检查产物和资源，没有重新执行该二进制或浏览器流程。**

### Windows

`.github/workflows/windows.yml` 已配置 windows-2022、uv 0.13.7、Python 3.13、frozen lock、pytest、源码隔离、原生 PyInstaller、EXE HTTP 冒烟及 ZIP artifact。打包脚本仍固定 rc1 名称，现有冻结冒烟仍验证加密 7z。安装脚本只初始化 workspace，不自动初始化 acceptance。

用户目标给出的 Windows 已验收构建提交为 `064972b5622406d38f78c32aeccfd4a15ff3d192`；本地 HEAD 为 `2c3838a1769ca1af9e99520ce380b1ec707b46d6`，且前者不在本地对象库。**不能声称本地 HEAD 就是该 Windows 构建源码。** 本次未拉取远端或重跑 Actions；经批准进入后续发布审核时应核对来源差异，G3 记录新构建真实 SHA。

本地文档中的旧 Actions 链接、校验值及“尚无 runner”的历史描述不能作为 rc2 验收依据，需要按阶段更新；不得提前填造 rc2 构建信息。

## 4. 发现的问题

### A. 截止日期

原始 `_create_todo` 只拒绝同时设置日期与无限期，允许 `null / false`；`_edit` 只对人工修改拒绝该组合。AI normalize_todo 未接收 no_due_date，AI 与人工校验不一致。已有 test_deadlines 明确断言新建可不填日期，说明 49 项原测试通过并不代表满足新规则。

G1 需集中实现 Python 最终状态校验，覆盖 HTML/API 新建编辑、intake、AI create_todo / normalize_todo、人工接受建议等写入路径；追加四种组合、无效日期、事务原子性、人工保护、原始录入时点解释和历史数据不改写测试。不得把未知日期自动改成无限期。

### B. ZIP 备份

原始 operations 使用 py7zr 加密 7z；API、网页、CLI 与 cmd 均依赖密码；完整快照采用 SQLite Backup API，此能力必须保留。需同步替换普通 ZIP 容器、命名、完整性校验、预览和恢复保护，移除正式依赖，保留历史 7z 文件不处理。

**额外数据安全风险（静态发现，未在业务数据执行）：** 原始完整恢复的异常清理遍历 data/config/agent-workspace 全部目录，即便失败发生在前面目录复制时，也可能删除尚未移入 rollback 的后续原目录。已产生的未完成修改尝试按实际处理目录回滚，但尚无故障注入测试，不能判为已修复。G1 必须优先验证此问题；当前暂停所有相关恢复操作，不在已有工作空间验证。

G1 还需验证 ZIP 损坏、错误 manifest、SHA-256、不安全 Windows 路径、恢复冲突、不同目录及重启。无密码不能削弱快照/JSONL一致性和事务保护。

### C. Skills 发现、规则与初始化

修改前三个 Skills 都有独立 name/description frontmatter，业务职责分开；路径为 `.codebuddy/skills/<name>/SKILL.md`。原 initializer 只复制缺失模板，没有版本报告；Schema 总是覆盖已有文件，缺少自定义保护；双工作空间未自动初始化。

G1 目标路径为 `.workbuddy/skills/<name>/SKILL.md`，继续保留 CODEBUDDY.md 和 .codebuddy/rules/workthread.md。保留三 Skill 原始业务内容，仅补充本次接口变化和明确调用映射，不合并重写。

证据需要区分：文件已部署、项目规则实际加载、客户端可用列表发现、真实 Skill 工具调用、Python 入库回执。G0 仅检查文件及规则，没有运行客户端调用。实际可用列表缺失时应报告不可用，不能用读取 SKILL.md 替代。

当前本机 WorkBuddy Info.plist 为 5.9.3。2026-11-05 查询的官方项目文档仍将 .codebuddy/skills 列为代码开发兼容目录，与用户提供的 5.9.3 Windows 实测不一致，不能据此宣称该版本一定自动发现；按目标部署 .workbuddy/skills，后续分别验收并保留版本依据。

官方来源：[WorkBuddy 项目配置](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Project)。

### D. Windows 10 与部署

现有部署说明写 Windows 11，安装只初始化正式空间；备份脚本及升级回退说明仍为 7z。需审查 Windows 10 Professional 22H2 build 19045 x64、PowerShell 5.1、Python/PyInstaller 依赖与 API、中文空格路径、离线运行资源及全新目录保护。

官方 Windows 安装指南列 Windows 10 及以上 x64；这只是客户端支持范围文档，**不证明本产品或 WorkBuddy 5.9.3 已完成真机验收**。

官方来源：[WorkBuddy Windows 安装指南](https://www.workbuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Installation-Win-Guide)。

后续统一路径：F:\WorkThread-Offline-Deploy-V2（资料）；F:\WorkThread（程序）；F:\WorkThread\workspace\agent-workspace（正式 WorkBuddy）；F:\WorkThread\acceptance\agent-workspace（合成验收 WorkBuddy）。资料目录不能作为业务项目目录。G4 文档必须要求 GUI Open Folder 选正确目录并确认信任。

## 5. .gitignore 与敏感信息隔离

原始规则已排除 .venv、.tools、.runtime、workspace、data、backups、数据库、JSONL、7z、密钥、凭证、日志、artifacts/build/dist。原 source gate 检查跟踪路径、暂存字节及工作副本中的常见密钥模式。原始隔离快照本次通过，未扫描或读取被忽略的个人业务资料。

rc1 未显式排除新 ZIP 和 acceptance；未完成修改已补上，尚待 G1 补充用例及 G2 对实际准备提交集合重新检查。G0 的 PASS 只覆盖原始 62 个源码文件，不等于对当前 rc2 所有待审文件给出提交批准。模式扫描也不能保证任意自然语言内容无敏感信息。

## 6. 准备修改范围（须 G1 批准后继续）

| 工作项 | 主要文件 |
|---|---|
| 截止日期统一 | src/workthread/core.py、ai.py、server.py；schemas/intake.json、ai-output.json；scripts/create_schemas.py；tests/test_deadlines.py、test_m1.py、test_m3.py、test_resilience.py 及必要新用例 |
| 普通 ZIP / 数据保护 | src/workthread/operations.py、cli.py、server.py、web/static/app.js；scripts/portable-backup.cmd、portable-restore.cmd、upgrade.ps1、smoke_frozen.py；pyproject.toml、uv.lock；备份恢复用例 |
| Skills / 双空间初始化 | src/workthread/deployment.py、cli.py；workbuddy_template/CODEBUDDY.md、.codebuddy/rules/workthread.md、.workbuddy/skills 下三个原 Skills 与模板版本信息；scripts/install.ps1、初始化用例 |
| Windows 10 / 版本及部署 | src/workthread/__init__.py、core.health；scripts/package_release.py、install.ps1、cmd 入口；packaging/workthread.spec 与 workflow 仅在发现必要问题时调整；README.md、WORKBUDDY_SETUP.md、docs/WINDOWS_QUICK_START.md、WINDOWS_ACCEPTANCE.md、WINDOWS_WORKBUDDY_DEPLOY_PROMPT.md、ARCHITECTURE.md |
| 隔离与验收记录 | .gitignore、scripts/check_source.py、tests/test_source_safety.py / test_m5.py；本阶段及后续约定报告 |

不调整已经确认的 UI 设计，不引入新框架，不改变数据库结构，不重写已经通过的 AI 文件交换核心，不读取旧版项目。需要变更数据库结构时另提供迁移及回滚方案后再实施。

## 7. 阶段闸门

- G0：**PASS**，原始基线冻结与检查完成，人工批准待定。
- G1：尚未获阶段批准；现有尝试未完成，试运行 **FAIL**。不得进入 G2。
- G2：**BLOCKED（闸门未授权）**，未构建新的 Mac 独立版本或执行发布审核。
- G3：**BLOCKED（闸门未授权）**，无新提交、推送或 Windows 构建。
- G4：**BLOCKED（闸门未授权）**，无新离线部署交付。
- G5：**BLOCKED（闸门未授权，需 Windows WorkBuddy 真机执行）**。

以上 BLOCKED 只是阶段准入状态，不宣称整体目标因技术原因受阻。用户未回复不视为批准。

阶段：G0 — 现有项目检查与基线冻结。

完成情况：PASS；本报告与 62 文件原始基线、隔离测试证据已生成。

通过项目：原始 rc1 49 项测试；原始源码隔离；现有 Mac 11 资源一致；代码、模板、Windows 配置及忽略规则检查。

失败项目：原始基线无失败；收到闸门前的未完成修改试运行 14 项失败，不列为阶段成果。

尚未验证项目：rc2 全量自动测试、浏览器、备份故障回滚、独立 Mac 构建、Windows 构建与真机、Skills 实际发现/调用。

是否存在数据风险：发现原始恢复异常清理风险，相关操作已停止；未触碰真实数据。当前未完成副本不适合正式使用。

下一阶段准备执行的操作：获批后继续 G1，优先补故障回滚测试，完成四项修改与文档、全量 Mac 测试和浏览器回归；完成 G1 报告后再次停止。不构建发布或推送。

需要用户授权的事项：批准进入 G1，并在保留现有未完成改动基础上继续实现与验证。

**等待用户明确批准。**

## 8. 收到闸门后的未完成修改冻结清单

Git 中 D + ?? 表示目录迁移尚未暂存，不表示历史源文件已从 Git 历史删除。此处逐文件状态来自冻结时刻；不包括随后新增的本报告。

| Git 状态 | 路径 | 当前 SHA-256（D 保留在原始基线） |
|---|---|---|
| ` M` | `.gitignore` | `4aa8e56336939f5e475d527994fca23407f4774947636637d0944bd1862fe839` |
| ` M` | `pyproject.toml` | `53e028db9bf02fece7f3b57b493a5cbbbd677e87fad9941a600de5d10aa7ccfe` |
| ` M` | `scripts/check_source.py` | `d8db2cd1fe442ff187a1a9d691248d1948220c5103edf9af78288ecf1e049fe1` |
| ` M` | `scripts/create_schemas.py` | `45c59b50647d03f9e55612fa21b25085f93f6de99514495efa88c36c1ba4bb63` |
| ` M` | `src/workthread/ai.py` | `3e44009ae32a04ca6719e277805bb2351f11de632c813525ada56e9913eaa4ce` |
| ` M` | `src/workthread/cli.py` | `f1f02847da7a607e8e7f7d01378c8b56fe450597e130218a81b4886c61e599df` |
| ` M` | `src/workthread/core.py` | `a174446bb8eee265341f54907f569380f9b28f14b7c787a71ef2b143585f1108` |
| ` M` | `src/workthread/demo.py` | `9bfec5c1ad74e1bb4c4754af1edd175c4bc06956b78b8fccfdec27d04de440a7` |
| ` M` | `src/workthread/deployment.py` | `fd92f21d04f97d3923e46851b39d7244f6f4f66c2b08dfd778bbc6f05694aee4` |
| ` M` | `src/workthread/operations.py` | `02b5b4772b5468078542e8f985fa23e38da979a2ecdc82cfb4ba0664203ed246` |
| ` M` | `src/workthread/schemas/ai-output.json` | `30313c7f58f7f2217a9f6a2b739a9514563c57398849770e3637cada9863835a` |
| ` M` | `src/workthread/schemas/intake.json` | `18342162d1dda592184e548d033d3e25f595b8043b2dc66d09c02784a41e034b` |
| ` M` | `src/workthread/server.py` | `5716b60063d8b628efe3ba4b0750f31b2e6788416f8dbdb173321e2b3c5bfbf9` |
| ` M` | `src/workthread/web/static/app.js` | `fad6113442fb1e3b9f4a749ccd6374f01a0f863a00dae2920c73c83eee13f07a` |
| ` M` | `uv.lock` | `07ed10f82a43b80a52bc49cf73b1ab8999f871f930dc4b5109950b8b0f64fd72` |
| ` M` | `workbuddy_template/.codebuddy/rules/workthread.md` | `b8e4c355163c2f0f25efcf9b596cc636c57f6b74575c5f87a4f52c64785d2387` |
| ` D` | `workbuddy_template/.codebuddy/skills/workthread-analysis/SKILL.md` | `—` |
| ` D` | `workbuddy_template/.codebuddy/skills/workthread-intake/SKILL.md` | `—` |
| ` D` | `workbuddy_template/.codebuddy/skills/workthread-knowledge/SKILL.md` | `—` |
| ` M` | `workbuddy_template/CODEBUDDY.md` | `e7e7b6915978d60457b4339cbc2069699601cd0e7fab77a8b2c585a81db2f00f` |
| `??` | `workbuddy_template/.workbuddy/skills/workthread-analysis/SKILL.md` | `04703e0fde53a9301b4fe6f798dbce8d2d420c9f34e4ea7ea8a17021617a9bb4` |
| `??` | `workbuddy_template/.workbuddy/skills/workthread-intake/SKILL.md` | `f69ef158df859aff971512930431f55e86dc97a38fd4613ffde03704d3ab5245` |
| `??` | `workbuddy_template/.workbuddy/skills/workthread-knowledge/SKILL.md` | `0065c6d646f6d870505f989c698aff3907e406a6b6cd796be9904f033c7a2fa3` |
| `??` | `workbuddy_template/.workthread-template.json` | `76b6052bdec6f18edcd6f06d001d7a1905294911a0386d60ca5957d52a597b72` |

## 9. 修改前 HEAD 文件清单及 SHA-256

所有指纹均由原始 HEAD 导出副本计算，和当前未完成修改分开。原始源码 tar SHA-256：

`dae0b10adee654d476769e0782d944085928d1e7f9107b5b79d929863d62a663`

| 原始路径 | 字节数 | SHA-256 |
|---|---:|---|
| `.github/workflows/windows.yml` | 1036 | `2214470f863ebbd1f97de7880e5c45692aef086f1afbcf43e50f3d17644399b1` |
| `.gitignore` | 211 | `414a5d0b31fe9918ccbefa4ad1d8d1e86b350274c3fb90a990951e0e02cd4088` |
| `GOAL_EXECUTION_REPORT.md` | 5786 | `35b9a9d25823cbf3c7fcd6633bff4e2d6829e0a23c8077d233739971f81e4866` |
| `RC_RELEASE_READINESS.md` | 4165 | `9a34245a1eb2941c246bc969e2fffdf6dba7581a8b1c63af802d83adee10d842` |
| `README.md` | 3695 | `197d2b44ac1f5f028cea74fffb4847604088020d73cbb93070ac2ded85c04c1e` |
| `WORKBUDDY_INTEGRATION_TEST.md` | 3985 | `df225e362278bd39da81346c02369fbafb1aa1dce6c448556f405a248c6a6f18` |
| `WORKBUDDY_SETUP.md` | 6647 | `90d6cc9471707cb729708df6d83138a972f6fb9e7cd7c445383788b15b296de7` |
| `docs/ARCHITECTURE.md` | 4660 | `1becebc8d09e633ff9f098664affe1175d01a7ee24974f99fab2d8d35c34e967` |
| `docs/LEGACY_IMPORT.md` | 1601 | `da6ed659d6b68ed2e9bd56ff110241e74f13b55761bd6b4a6779e390fb908bf5` |
| `docs/RC_RUFF_REVIEW.md` | 1883 | `142d687c5aba66db5e4ebb0a6ad46087570730c6cad766c556057bd9def52b65` |
| `docs/TEST_REPORT.md` | 11612 | `2369f18654d28fcef136eaaa4755dee736933a9ed2de11ea9c78c66b5211d59e` |
| `docs/UI_GUIDELINES.md` | 2738 | `17ea1128cd4a48c435c26ceae6f538b93a76f63fee9a7b01d9aa67906a3f673f` |
| `docs/WINDOWS_ACCEPTANCE.md` | 2899 | `05762960a91313769d0e529dd1913b645754fb317ea5525baaa03eb6a455980a` |
| `docs/WINDOWS_QUICK_START.md` | 2028 | `3a6afcbc682b4ad01896c19456065a1f04f0e7ccd3501f7c916a466b16985e9e` |
| `docs/WINDOWS_WORKBUDDY_DEPLOY_PROMPT.md` | 13937 | `3264cc9894e24c11ae77ccacd8ef30989fc1650b5ec9dcebbd233f906a2737bc` |
| `packaging/entry.py` | 39 | `c923bff6b10d5b05363fda3c19deeb2ce3d11f8381a0a2d0307ac3c47912ca52` |
| `packaging/workthread.spec` | 684 | `3df18143be153de1b274fa71e7d0a0cea3e28f19ddcff9df4c713aca024ab5f7` |
| `pyproject.toml` | 599 | `ec8cc5241335ff57531b3b3f0e2f8ad54c33b7dae4ceedc242dad638d62ddc15` |
| `scripts/bootstrap.sh` | 335 | `75438a5b5fca069672e6cb3b8e8841713b596463c636ab670f9c8bb120a1581c` |
| `scripts/check_source.py` | 1854 | `74eaf0398cf3005db39462988d80cef51a38a3a49ac745c50818056c7dce5612` |
| `scripts/create_schemas.py` | 4737 | `7b0961cab02c24d6c25c4bcc2409840acc776a4d752f58f066a48c6b26ccd3cd` |
| `scripts/demo.command` | 106 | `32449ae93d8f27ccc5c786d66af21c868c7c27d5a3a48390b87a069c1d69bcb4` |
| `scripts/install.ps1` | 452 | `fb1049b79604cafa78a31ac113ad1d2e564fdf9c961729f4187fb070db02bfb3` |
| `scripts/package_release.py` | 2782 | `1a86427d6be1023e4cb1d3b456f7ce9d3b9f4ff6d01539405e7e97359590af1d` |
| `scripts/portable-backup.cmd` | 155 | `418839a59915fe67827701bf53f64e108e1949a8b4f54efa967c326cc6cdf071` |
| `scripts/portable-health.cmd` | 85 | `5adabf1e287ee0edf3d04901ea30c72e3299ef89e976181de59a55eb6987f1cf` |
| `scripts/portable-restore.cmd` | 360 | `8f544bc50b1d32081f3c319a1ca1891bfd7305aef420f62e7f0e80d33280c4a6` |
| `scripts/portable-start.cmd` | 91 | `1d1bc7027641b18cf1e0fb2f0af4fc8bd174437d4bab6dde1b66f02a261da1a8` |
| `scripts/smoke_frozen.py` | 4143 | `495abee3be13d9b68a4f24bcca5056e4be5da463f185ae1197bd235a83ee35ca` |
| `scripts/start.command` | 81 | `fc7088f840b5a22cbbe52cb16efd737d03eea56427aa6f92542b0e4b410f51f6` |
| `scripts/upgrade.ps1` | 1234 | `14d5cbfcefe194fee95b57bb1f2862ab001ffb1954c953c249bbed6dff94e413` |
| `src/workthread/__init__.py` | 25 | `8b00e2d13533e3948c60896c844021f943deaea21eee7c546af6cb630120491f` |
| `src/workthread/ai.py` | 25172 | `5c5434d9327c4df998c2d3f2895f494031503f0077f0c5f36585ab352b2cdd76` |
| `src/workthread/cli.py` | 6012 | `7ce1ab5356b4f6be21f511ff113d605f56c790462937ada5bd9d0ac3fd55a419` |
| `src/workthread/core.py` | 29390 | `82c8ba266b57d3581e75463a866dcef5a72c29d88cc9b694bee38346f3838bc4` |
| `src/workthread/demo.py` | 7913 | `b23c84aebf893d9136e48d227824f586145bb915ee712a2bebd94a52f65c4195` |
| `src/workthread/deployment.py` | 857 | `574f646f2079fd76b92b7e23c139d250db6c15f70dd2646e215692719e9b92f6` |
| `src/workthread/mail.py` | 19125 | `3431ee506c588f4e8424458d26ed93c5bb08b10325ddd675c8f9d3c594f3a170` |
| `src/workthread/operations.py` | 22914 | `f81ec01d6a376a99bf7a13805b1085bc297dd5ecfb77940eed2f1bd3b92a2c0c` |
| `src/workthread/schemas/ai-input.json` | 1577 | `b8e7b23e087054c2799100997a6033cb8557f0f5d15e3bc905e9ac2d748c2731` |
| `src/workthread/schemas/ai-output.json` | 23566 | `0548b6c010b33bb20a3b4e5398e8daae56dc6c85b93e0071792d07c29e8b2101` |
| `src/workthread/schemas/intake.json` | 676 | `ccba2fdf61225a1e60ea8979c933dacde4e69144a2975f77851505ea6818ac95` |
| `src/workthread/server.py` | 15211 | `81a292adc80c439a504a31f61b621cc777af0fefd758bd0e97ffdc8110a3786f` |
| `src/workthread/web/static/app.css` | 20608 | `9bba1e35575566596c3adf27ea73419bf8d8933d4599aff6f803f583409386c7` |
| `src/workthread/web/static/app.js` | 52262 | `401674809286ea49d1d251a7422e7b14ce10873170f35ac8a77b15699ece3ffb` |
| `src/workthread/web/templates/index.html` | 1984 | `2f7c8293cca59c685d80ad2227f34c7714c42d5c00beed4dc93aba13696ee6d0` |
| `tests/test_deadlines.py` | 5369 | `bdd5e9b6ad0e4ba0a099a228e650fdd813872543c629597adb722083dc6e2faa` |
| `tests/test_m0.py` | 824 | `072929192f0f96036c914d82f6b7a5ff07134aa47854a246e496920b3858c59a` |
| `tests/test_m1.py` | 2471 | `87a22f58c8492861257cbde8bda0a09238475331c346649455f5c9192c68da4a` |
| `tests/test_m2.py` | 3075 | `517474b7f4d9fd614db4ad6f4264a4a8e80d270836d08b55610bd145903dd647` |
| `tests/test_m3.py` | 6201 | `bd83d812e918b9ac577e3c502a35dc65a6045fe2932ff689234b9277ec074e9e` |
| `tests/test_m4.py` | 3783 | `0131c1859a2f5e8d245aba685793d5ecba539b1348d1d4aecad1ec56a16d7965` |
| `tests/test_m5.py` | 1441 | `c6cd0b5e27aeab1baf916d2c5b3749758ac1ece6c7aa13bbfb8979aa8c496e6e` |
| `tests/test_mail_replies.py` | 3843 | `22dabd88bbab9da61186a03e1e2ee883df2f956e441b5cd4a961ab742d6e0f66` |
| `tests/test_resilience.py` | 7223 | `f7d5251e4b949880aae88bdd58c530583ea9a57ae62db2dbc043b26cc362c723` |
| `tests/test_source_safety.py` | 1217 | `9e0d9d17ed0ca9cc8d2ba9e75b2cf591cd9e00333f4f9735663da125456652fb` |
| `uv.lock` | 110891 | `5b814e1ba97618229511b72f476367029c42a0790f6be37c5ebd5e9b30b205a7` |
| `workbuddy_template/.codebuddy/rules/workthread.md` | 3574 | `e1954ac55337f24cd719ef551b921905722d83fe85d949cb946b5c8fb89ca893` |
| `workbuddy_template/.codebuddy/skills/workthread-analysis/SKILL.md` | 842 | `7408b9766bddd00c72b0fc62b278fe547ebcf0c3d400fbe5019c1c5ad57a276f` |
| `workbuddy_template/.codebuddy/skills/workthread-intake/SKILL.md` | 971 | `6d4717e38b9b22ad120124b161649ac055a3639a2f986cd668e8bbd67ba4e805` |
| `workbuddy_template/.codebuddy/skills/workthread-knowledge/SKILL.md` | 553 | `45f73ac342eb18856656e6784d887573a6e47b223556e827142f41614ea2d1d6` |
| `workbuddy_template/CODEBUDDY.md` | 963 | `b4c97f8d2985e5f073fcdc9f4ab7766a5e09ac23bd10332b856dd935c7258f43` |
