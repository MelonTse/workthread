# WorkThread rc3：R0 差异审阅及本地验收

记录时间：2026-11-06T13:17:01+08:00。

**R0：PASS；暂停等待用户批准 R1。本轮没有提交、推送、Windows Actions、Windows 原生构建或 rc3 离线交付。**

授权目标 WORKTHREAD-RC3-GOAL-001，依据新的目标文件执行。用户提供 Windows 10 19045 / WorkBuddy 5.9.3 真机根因：rc2 .workbuddy/skills 未发现，原文复制到 .codebuddy/skills 后三个 Skill 被发现、实际调用且多个独立会话可用。本轮采用该真实反馈，不以旧推测维持错误路径；该证据来自用户，不是本轮 Mac 再次操作了 Windows。rc3 原始安装包仍必须未经人工修复地重新真机验收。

## 1. 当前源码与未提交修改归属

本地分支 `codex/workthread-1.0.0rc2`，原 HEAD `2c3838a1769ca1af9e99520ce380b1ec707b46d6`，主索引未暂存。没有为 R0 改写历史或创建提交。rc2 真实构建基线为 `8f4cea4d37b0ee9ecca0ec21c3d4394fbe45d5ea`，本地隔离候选副本保存该提交及完整源码。

进入 R0 时逐一核对：79 个源文件与 G3 最终指纹完全一致；G3 和 G4 报告与各自 completion-check 指纹一致，共 81 个文件均能归属此前授权工作，未发现无法区分归属的修改。冻结于 `.runtime/rc3-r0/rc2-before-r0.tar`、entry-files.json 和 entry-status.txt。没有 reset、丢弃或覆盖原未完成工作。

当前工作区仍叠加 rc1→rc2 的已审修改；R0 差异采用独立 Git 索引相对 rc2 真实 SHA 生成，不把原根目录 HEAD 当作 rc2。独立索引不影响用户索引。完整 diff 含两个此前未提交的 G3/G4 报告（原文不动），它们不是 R0 新功能。下表列本轮路径/版本/测试/文档修改，另新增本报告。

## 2. 文件清单及范围

| 状态 | R0 修改路径（相对 rc2） |
|---|---|
| M | `README.md` |
| M | `WORKBUDDY_SETUP.md` |
| M | `docs/ARCHITECTURE.md` |
| M | `docs/WINDOWS_ACCEPTANCE.md` |
| M | `docs/WINDOWS_QUICK_START.md` |
| M | `docs/WINDOWS_WORKBUDDY_DEPLOY_PROMPT.md` |
| M | `pyproject.toml` |
| A | `scripts/check_bundle.py` |
| M | `scripts/package_release.py` |
| M | `scripts/smoke_frozen.py` |
| M | `scripts/upgrade.ps1` |
| M | `src/workthread/__init__.py` |
| M | `src/workthread/ai.py` |
| M | `src/workthread/core.py` |
| M | `src/workthread/deployment.py` |
| A | `tests/fixtures/rc2-project-files.json` |
| M | `tests/test_deployment.py` |
| M | `tests/test_m5.py` |
| A | `tests/test_rc3_distribution.py` |
| M | `tests/test_zip_backups.py` |
| M | `uv.lock` |
| M | `workbuddy_template/.codebuddy/rules/workthread.md` |
| R100 | `workbuddy_template/.workbuddy/skills/workthread-analysis/SKILL.md → workbuddy_template/.codebuddy/skills/workthread-analysis/SKILL.md` |
| R100 | `workbuddy_template/.workbuddy/skills/workthread-intake/SKILL.md → workbuddy_template/.codebuddy/skills/workthread-intake/SKILL.md` |
| R100 | `workbuddy_template/.workbuddy/skills/workthread-knowledge/SKILL.md → workbuddy_template/.codebuddy/skills/workthread-knowledge/SKILL.md` |
| M | `workbuddy_template/.workthread-template.json` |
| M | `workbuddy_template/CODEBUDDY.md` |
| A | `docs/RC3_R0_REVIEW.md` |

三个 Skill 是 R100 原文迁移，完整字节、frontmatter、原业务前缀都保留，不重写/合并。core.py 仅产品健康版本字符串改变；ai.py 仅 rules_version 改为 rc3；Schema（仍 1.0）、数据库结构、To Do/AI/ZIP 业务逻辑及 UI 文件字节均未改。Python/Flask/SQLite 等依赖版本不变；uv.lock 仅本项目版本改为 1.0.0rc3。

## 3. 最终路径与模板哈希

模板路径：`workbuddy_template/.codebuddy/skills/<name>/SKILL.md`；初始化后位于各自 `<workspace>/agent-workspace/.codebuddy/skills/<name>/SKILL.md`。新安装不创建 .workbuddy/skills，唯一正式分发路径为 .codebuddy/skills。CODEBUDDY.md 和 .codebuddy/rules 正常保留，只更改版本/目录说明。

| 三个完整正式路径 | 完整 SHA-256（与 rc2 正文完全相同） |
|---|---|
| `.codebuddy/skills/workthread-analysis/SKILL.md` | `04703e0fde53a9301b4fe6f798dbce8d2d420c9f34e4ea7ea8a17021617a9bb4` |
| `.codebuddy/skills/workthread-intake/SKILL.md` | `f69ef158df859aff971512930431f55e86dc97a38fd4613ffde03704d3ab5245` |
| `.codebuddy/skills/workthread-knowledge/SKILL.md` | `0065c6d646f6d870505f989c698aff3907e406a6b6cd796be9904f033c7a2fa3` |

模板元数据为 1.0.0rc3，file_hashes 覆盖 8 个实际管理文件（CODEBUDDY、项目规则、3 Skills、3 Schema），原始业务前缀指纹保留。初始化先校验资源存在及哈希，缺 Skill 或资源损坏会明确失败，不能 ready=true。新增打包检查逐项比较网页/Schema/整棵模板的实际集合及字节，缺失隐藏目录或正文不符会拒绝打包；EXE 冒烟也核对新空间中三个正式文件与冻结资源的字节。

## 4. 旧 rc2 工作空间兼容性

仅在独立临时目录构造旧注册表/文件，未操作任何真实 rc2 工作空间。

- 旧 `.workbuddy/skills` 文件原样保留，不删除、不搬动；旧登记哈希用于识别 preserved/custom_preserved，legacy_files 继续报告，重复初始化仍保留该诊断。
- 新 managed_files 只登记正式 .codebuddy/skills 等实际管理路径，不假装旧路径已经迁移。旧目录的自定义内容不自动推广到新路径，报告/文档要求用户人工比较合并。
- 用户此前手工复制到 .codebuddy/skills 的原版 rc2 Skill 与本次正文相同，识别 current；正式路径为自定义内容时保留原文件，输出冲突候选和 ready=false，CLI init 退出码 2。
- 已知原版 rc2 CODEBUDDY/规则按明确旧哈希可更新；rc1 的原有识别哈希继续保留；其他自定义规则/Schema 继续保留冲突机制。
- 正式/合成两空间独立初始化；管理路径与文件哈希一致，第二次初始化为 current。没有执行用户工作空间迁移、客户端配置、全局 Skills、缓存或 app.asar 修改。

ready 仍只表示本地文件部署状态；项目规则自动注入、客户端真实列表、工具调用和 Python completed/saved 是不同证据，诊断与文档均明确区分。

## 5. 实际验证

| 项目 | 本轮结果 |
|---|---|
| 原有完整测试（先修正已证伪目录断言） | 133 passed in 4.45s |
| 全量含新增回归 | **142 passed in 4.02s；0 失败/错误/跳过** |
| 新增测试 | 4 个旧 rc2 注册表/自定义/手工复制组合；2 个模板缺失/损坏拒绝；1 个真实 ZIP 打包脚本的合成资源回归；2 个冻结隐藏资源丢失/损坏拒绝 |
| 原业务 | 日期全部入口、AI/回执/保护、ZIP/恢复故障注入等完整原套件通过 |
| Mac 原生 PyInstaller | PASS，独立输出 `.runtime/rc3-r0/dist`，原产物不覆盖 |
| Mac 冻结 HTTP 冒烟 | PASS，启动/HTML/JS/Schema、To Do、2 Progress、普通 ZIP Full 恢复及健康；3 个部署 Skill 与冻结正文一致 |
| 冻结资源 | 12 个资源逐项全路径/字节通过，无旧正式目录 |
| Git diff --check / 源隔离 | PASS，独立索引含所有新增和迁移路径；最终集合及指纹见本地证据 |
| 历史保护 | G0–G4 报告、rc2 10 文件离线包全部指纹保持，UI/Schema/旧 HEAD/用户索引保持 |

新增测试开发时曾实际失败：旧目录诊断未在第二次 init 保留，以及模板移动后遗留空旧目录被检查拒绝。随后修正旧登记诊断持续性，并移除源码模板的空目录（无用户文件）；不是删除测试或放宽拒绝机制。最终全部通过；开发失败见本次会话工具记录，tests.log/XML 保存最终全量结果。

合成 ZIP 测试在新临时目录用明确标记为 SYNTHETIC 的假 EXE，执行真实 package_release.py 的复制/ZIP/manifest 逻辑并逐文件检查 .codebuddy/skills 字节。这证明打包代码包含隐藏目录，**不表示已构建 Windows rc3 程序**，合成产物不作为交付。原生 Windows PyInstaller、EXE、最终 ZIP/SHA 和原始包真机客户端验证都待 R1/后续授权，不能由 Mac 或模拟测试代替。

## 6. 文档、风险与证据

README、WORKBUDDY_SETUP、Windows 速查/验收/部署提示词、架构和项目规则均更新为 rc3 与正确路径；历史报告/已交付 rc2 文档保留原文，不篡改其旧结论。新提示词明确：原始 rc3 包初始化后不许人工复制目录补救，必须证明自动发现/逐个调用/独立新会话，并增加不提前透露 Skill 名称的自然语言路由任务。

当前没有 rc3 Commit/Windows Actions/Windows ZIP/SHA；文档不使用 rc2 身份冒充 rc3。旧 G4 离线资料仍为不可变 rc2，不在 R0 制作 rc3 交付包。

额外风险：旧自定义 Skill 可能存在于已无效的 rc2 路径，需要人工合并到正式路径；本地 ready 不能证明客户端发现。rc3 原始包在 Windows 10 19045/WorkBuddy 5.9.3 的发现、调用、自动路由、动态系统行为仍未验证。当前无已知未修复的本地测试阻断问题；未增加依赖、DDL、UI 变更或新业务功能。

证据目录 `.runtime/rc3-r0/`：entry-files.json / entry-status.txt / rc2-before-r0.tar；tests.xml / tests.log；tests-first.log（原 133 项通过结果）；mac-build.log / mac-smoke.log；rc2-to-rc3.patch / diff-files.txt / diff-stat.txt；source-isolation.log / r0-changes.json。冻结程序仅供本地验证。报告写完后刷新完整差异和最终文件指纹。

## 7. 闸门审批记录

阶段：R0 — 检查及最小修复。

完成情况：**PASS**，本地路径、版本、文档、初始化保护、打包诊断和完整测试完成，等待审阅。

通过项目：142 项全量测试；3 个 Skill 完整正文/哈希；新双空间与 rc2 旧登记/自定义保护；资源/合成 ZIP 回归；Mac 冻结资源及 HTTP 冒烟；历史基线及产物保护；差异和隔离审核。

失败项目：最终必要本地检查无失败；开发过程发现并修正的问题如上保留记录。

尚未验证项目：原生 Windows rc3 构建/EXE/ZIP/实际哈希；未经手工复制的 rc3 新安装、客户端规则/Skills 列表及工具调用、多新会话和不透露名称的自动路由，均不能由本轮替代。

是否存在数据风险：只在隔离临时目录做合成测试，没有读取旧版 Shelley 项目、连接真实 IMAP、修改真实业务或已验收 Windows rc2 空间；旧路径文件保护有回归证据。真实目标环境仍须独立验收。

下一阶段准备执行的操作：仅获得明确 R1 批准后，复核远端基线及候选差异，提交 rc3、推送私有候选分支、运行 Windows Actions 并下载核验实际产物；不改 main、不 force push、不覆盖 rc2。

需要用户授权的事项：**批准进入 R1。** 尚未授权 R2 离线包制作或 Windows 安装。

**停止于 R0 闸门，等待用户明确回复。**
