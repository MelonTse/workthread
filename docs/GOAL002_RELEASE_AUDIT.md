# WORKTHREAD-GOAL-002：G2 发布前审核

记录时间：2026-11-05 17:31:53 CST。

**阶段 G2：PASS（发布准备审核完成，等待用户明确批准 G3）。G3 仍未授权。**

授权为 WORKTHREAD-GOAL-002-G2-APPROVAL-001。对应 [Mac 独立验收报告](GOAL002_MAC_ACCEPTANCE.md)。没有创建提交、推送、运行 Windows Actions、制作/传输 Windows 安装包或创建 Release。

## 1. 审核结论

| 项目 | 结果 |
|---|---|
| 原始 rc1 / G0 / G1 保存 | PASS，原始 62 文件快照、G0/G1 报告指纹及 HEAD 保持 |
| 最新完整自动测试 | PASS，129 passed in 4.15s，0 失败/错误/跳过 |
| Mac 独立构建/运行 | PASS，arm64 原生、中文/空格新路径、系统 PATH、全新 ZIP 解压运行 |
| 独立程序业务及协议 | PASS，To Do/Progress、saved/completed、duplicate、superseded、无密码 ZIP/恢复/重启 |
| 打包资源 | PASS，12 个网页/Schema/模板资源与当前程序输入相同 |
| 完整候选 diff | PASS，包含原未跟踪文件与 Skill 迁移，使用独立 Git 索引审查 |
| 敏感信息隔离 | PASS（所述扫描与人工审阅范围），最终源文件清单/扫描见本地证据 |
| Windows 配置/文档 | PASS（静态），无执行 Windows 构建或真机的结论 |
| 是否可直接推送 | **否，必须等待 G3 明确授权** |

## 2. Git 与远端基线

当前本地分支 `codex/workthread-1.0.0rc2`；HEAD 保持 `2c3838a1769ca1af9e99520ce380b1ec707b46d6`。没有移动分支、reset/rebase 或改写 rc1 历史。主 Git 索引未暂存本轮更改。

G2 通过 GitHub 连接器执行只读核对：

- 仓库 [MelonTse/workthread](https://github.com/MelonTse/workthread) 当前 visibility=private，未归档。
- 已验收的 [064972b](https://github.com/MelonTse/workthread/commit/064972b5622406d38f78c32aeccfd4a15ff3d192) 存在，内容为 Windows UTF-8/二进制路径修正。
- 远端 main 为 [1a5c323](https://github.com/MelonTse/workthread/commit/1a5c32356e30f4903f484dfb266fe714566c1e7c)，比 064972b 多 1 笔 README/Windows 部署提示词文档提交。
- 本地 HEAD 的 SHA 不是远端提交，直接 compare 返回 404。因此没有把不同 SHA 宣称为同一提交。
- 使用连接器在固定远端 SHA 下逐文件读取 Blob 标识，**本地 rc1 基线 62 个跟踪文件与远端 main 的对应文件 Blob 全部一致**。这是已列文件的内容等价证据，不是 Git ancestry 等价证明，也不声称枚举了未列出的远端文件。详细结果 `remote-baseline-check.json`。

本机 Git CLI 的只读 fetch 因无本机 GitHub 凭证而失败，终端提示关闭，没有弹窗、读取/修改凭证或要求用户提供 Token；随后通过现有连接器完成核对。该 CLI 限制不影响 G2 本地验收，G3 可使用已连接 GitHub 能力。

G3 获批后应基于届时重新核对的远端 main 建立候选提交/分支，仅应用本次审核差异，保留其他远端文件；核对实际 diff 和真实新 Commit SHA。不直接强推当前本地历史，不改写 rc1/G0/G1 基线，不使用 force push。远端有额外变化时先重新核对，不假定本次快照仍有效。

## 3. 完整 diff 审阅

使用 `.runtime/goal002-g2/review.index` 作为 GIT_INDEX_FILE，先载入 HEAD，再仅加入当前明确的新增/修改/迁移/删除路径。没有运行不受限制的根目录 git add .，没有改变主索引或创建提交。

审阅包含：

| 范围 | 核查结论 |
|---|---|
| core / ai / Schema | 日期最终状态共用领域规则，人工字段及原始时间保护仍在，无 DDL 变化；AI 接受 no_due_date |
| operations | SQLite Backup API、JSONL/数据库一致性、ZIP/manifest/SHA/路径安全；恢复只回滚已处理目录，历史 7z 不动 |
| CLI / HTTP / app.js | 无密码入口、明确字段错误、UTF-8、文件预览；未改 CSS 或 HTML 设计 |
| deployment / 模板 | .workbuddy/skills，三个原业务正文前缀哈希保留，版本/自定义保护及冲突报告 |
| Windows 脚本 | 两空间 init/doctor、普通 ZIP、新目标预览、rc2 拒绝原地升级；不注册计划、不改客户端/全局 Skills |
| 测试 | 原 14 项失败逐项有解释；原保护断言保留，新增规则/故障/独立恢复/编码用例；无 skip/xfail 掩盖失败 |
| pyproject / uv.lock | rc2，移除 py7zr 专属依赖；未引入模型 API、云服务或框架 |
| 文档 | 当前行为与历史记录分开；实际构建 SHA/SHA-256 不编造，Windows 路径/工作空间及验收边界明确 |

Skill 迁移在拟提交 diff 中识别为 R072/R074/R062，完整原正文仍保留。Git 工作区显示的 D + 未跟踪新路径不等于删除业务内容。

G2 相比已通过的 G1 **没有改动程序逻辑或 UI**。本阶段只更新 README、WORKBUDDY_SETUP 的当前审核状态与安全 Mac 输出命令，修正文档 ARCHITECTURE 两处遗留矛盾（“原始捕获可待完善”“复制后加密”），更新 Windows 提示词的草稿审核状态，并新增本报告和 Mac 验收报告。G0/G1 报告原文保持，不倒改历史。

完整补丁 `review-full.patch` 包括所有新增文件内容；`review-stat.txt`、`review-name-status.txt` 和最终文件清单均在 `.runtime/goal002-g2/`。报告写完后重新生成这些证据并再扫最终集合，不只扫描旧跟踪文件。

## 4. 敏感信息与数据隔离

扫描范围是**拟提交完整源文件集合**的暂存字节及当前内容，含新测试、三个迁移 Skill 和各阶段报告。自动门禁检查运行/数据/备份/日志/密钥路径及常见私钥、GitHub/AWS/模型 Token 模式。额外检查源文本中的邮箱域，只有 example.org（含子域）、example.com/example.net 等合成保留域，无真实业务域发现。

9 个实际忽略探针包含 G2 备份 ZIP、运行 JSON、Mac 构建 ZIP、workspace/acceptance 数据与交换文件、.env、密钥和两类备份格式，全部被忽略；不会进入提交。没有扫描被忽略的个人真实资料或读取其他项目来寻找秘密。

人工审阅：To Do、邮件、客户/项目/知识、回执和截图只来自当前项目合成夹具；未读取旧版 Shelley 项目。G0/G1/G2 报告中的本机路径和测试指纹用于溯源，没有凭证或业务正文。原生 Mac ZIP 也未打包测试数据或工作空间；它本身被 artifacts 忽略，不随源码提交。

扫描无法证明任意自然语言绝对不含敏感信息；本次 PASS 针对明确文件集合与上述模式/人工证据，不泛化到未审阅文件。后续新改动必须重新审查。

## 5. Windows 构建准备

`.github/workflows/windows.yml` 与 packaging/workthread.spec 本次保持原配置：

1. windows-2022 原生 runner；uv 0.13.7；Python 3.13 与 frozen lock。
2. 全量 pytest → 源码隔离 → PyInstaller onedir → EXE 冒烟 → 便携包 → upload-artifact。
3. packaging spec 将网页、3 Schema、整棵 workbuddy_template（含隐藏目录/元数据）纳入数据；Mac 实际 12 资源已验证。
4. package_release.py 输出新 rc2 名称、真实 GITHUB_SHA、Windows/机器信息、依赖锁/许可证、Install/Start/Health/Backup/Restore.cmd 和 tools/docs，再生成文件清单及 ZIP SHA。
5. Workflow 权限 contents:read；无发布 Release、邮箱、业务数据上传、正式调度步骤。只有 G3 经批准的提交/推送才允许触发运行，本阶段未触发。

仍待 G3 实际执行：Windows 129 项测试、原生 EXE、DLL/PE 导入、冻结资源、Artifact 下载校验、实际版本/Commit/大小/SHA。Mac 的 62 条分析提示未被当作 Windows 依赖结论。不得把当前 Mac ZIP 改名为 Windows 包。

仍待 G5：Windows 10 19045 x64、PowerShell 5.1/cmd、Explorer、Credential Manager、Defender/文件占用、规则加载与 3 Skills 的客户端列表/真实调用/新会话、真实 WorkBuddy 回执。G2 只验证合成 JSON 契约和模板部署。

## 6. 部署文档审核

当前路径统一：

- `F:\WorkThread-Offline-Deploy-V2`：资料目录，不是 WorkBuddy 项目。
- `F:\WorkThread`：全新程序位置，已有内容必须停止，不覆盖 rc1。
- `F:\WorkThread\workspace` / `agent-workspace`：正式空间，保持空白。
- `F:\WorkThread\acceptance` / `agent-workspace`：合成验收空间。

WorkBuddy 必须通过 GUI Open Folder 打开 agent-workspace 并确认信任。文件存在/读取 SKILL.md 不算发现或调用；列表、工具调用、独立新会话及 Python 回执分别取证。三个 Skill 不合并、不安装全局、不修改客户端或缓存。

两类 ZIP 均不要求密码；历史 7z 不删除/转换。Restore.cmd 和文档优先要求新目录并先预览。真实邮箱/正式任务均不在授权范围。

部署提示词仍标记 WORKTHREAD-WINDOWS-DEPLOY-ACCEPT-002-G1-DRAFT，已注明经 G2 审阅；G3 构建完成后填真实构建信息，G4 获批后才制作完整离线资料包。不把未来 WINDOWS_BUILD_REPORT.md、VERSION_INFO.md 说成已经交付。

README 明确历史 rc1 TEST_REPORT/RC_RELEASE_READINESS/GOAL_EXECUTION_REPORT/WORKBUDDY_INTEGRATION_TEST 不代替 rc2；保留它们原文以免改写历史。

## 7. GitHub 提交内容预览（尚未执行）

拟提交目标：现有 Private 仓库 MelonTse/workthread；候选分支使用 codex/ 前缀。G3 开始时重新核对远端 base 和分支状态，不覆盖历史 rc1。

拟提交说明：

```text
Prepare WorkThread 1.0.0rc2 candidate

Unify server-side To Do deadline validation across all write paths.
Replace encrypted 7z backups with password-free ZIP and protect restore rollback.
Deploy three project Skills under .workbuddy/skills with custom-file protection.
Prepare Windows 10 fresh-install scripts and record Mac G1/G2 acceptance.
```

只包含下列审核源码/模板/测试/文档差异，不包括 .runtime、artifacts、dist/build、数据库、JSONL、备份、回执、截图或凭证。完整文件集合和逐文件指纹见 final-source-manifest.json；最终审阅树标识见 final-review-tree.json，均仅保存在本地证据目录，不是新 Commit SHA。

### 拟提交差异文件

| 状态 | 路径 |
|---|---|
| M | `.gitignore` |
| M | `README.md` |
| M | `WORKBUDDY_SETUP.md` |
| M | `docs/ARCHITECTURE.md` |
| A | `docs/GOAL002_BASELINE.md` |
| A | `docs/GOAL002_G1_ACCEPTANCE.md` |
| A | `docs/GOAL002_G1_BACKUP_REPORT.md` |
| A | `docs/GOAL002_G1_FAILURE_REVIEW.md` |
| A | `docs/GOAL002_G1_SKILLS_REPORT.md` |
| A | `docs/GOAL002_G1_WINDOWS10_STATIC.md` |
| A | `docs/GOAL002_MAC_ACCEPTANCE.md` |
| A | `docs/GOAL002_RELEASE_AUDIT.md` |
| M | `docs/UI_GUIDELINES.md` |
| M | `docs/WINDOWS_ACCEPTANCE.md` |
| M | `docs/WINDOWS_QUICK_START.md` |
| M | `docs/WINDOWS_WORKBUDDY_DEPLOY_PROMPT.md` |
| M | `pyproject.toml` |
| M | `scripts/check_source.py` |
| M | `scripts/create_schemas.py` |
| M | `scripts/install.ps1` |
| M | `scripts/package_release.py` |
| M | `scripts/portable-backup.cmd` |
| M | `scripts/portable-health.cmd` |
| A | `scripts/portable-install.cmd` |
| M | `scripts/portable-restore.cmd` |
| M | `scripts/portable-start.cmd` |
| M | `scripts/smoke_frozen.py` |
| M | `scripts/upgrade.ps1` |
| M | `src/workthread/__init__.py` |
| M | `src/workthread/ai.py` |
| M | `src/workthread/cli.py` |
| M | `src/workthread/core.py` |
| M | `src/workthread/demo.py` |
| M | `src/workthread/deployment.py` |
| M | `src/workthread/operations.py` |
| M | `src/workthread/schemas/ai-output.json` |
| M | `src/workthread/schemas/intake.json` |
| M | `src/workthread/server.py` |
| M | `src/workthread/web/static/app.js` |
| A | `tests/fixtures/rc1-project-files.json` |
| A | `tests/test_deadline_entries.py` |
| M | `tests/test_deadlines.py` |
| A | `tests/test_deployment.py` |
| M | `tests/test_m1.py` |
| M | `tests/test_m4.py` |
| M | `tests/test_m5.py` |
| M | `tests/test_resilience.py` |
| A | `tests/test_restore_safety.py` |
| A | `tests/test_zip_backups.py` |
| M | `uv.lock` |
| M | `workbuddy_template/.codebuddy/rules/workthread.md` |
| R072 | `workbuddy_template/.codebuddy/skills/workthread-analysis/SKILL.md → workbuddy_template/.workbuddy/skills/workthread-analysis/SKILL.md` |
| R074 | `workbuddy_template/.codebuddy/skills/workthread-intake/SKILL.md → workbuddy_template/.workbuddy/skills/workthread-intake/SKILL.md` |
| R062 | `workbuddy_template/.codebuddy/skills/workthread-knowledge/SKILL.md → workbuddy_template/.workbuddy/skills/workthread-knowledge/SKILL.md` |
| A | `workbuddy_template/.workthread-template.json` |
| M | `workbuddy_template/CODEBUDDY.md` |

## 8. 闸门审批记录

阶段：G2 — Mac 独立运行及发布前审核。

完成情况：**PASS**；两份要求报告、本地 Mac 独立审阅产物及完整 diff/文件清单/敏感信息隔离证据已生成。

通过项目：129 自动测试；原生构建/新目录/ZIP 解压运行；To Do/两条 Progress；合成 AI 文件契约及回执、重复/过期保护；两类无密码 ZIP 及独立恢复重启；12 资源与 103 载荷文件校验；源集合与文档/Windows 配置审核。

失败项目：最终关键测试无失败。只读 Git CLI fetch 缺本机凭证已通过连接器绕开，62 个基线 Blob 匹配，不要求用户交出凭证；构建可选模块提示有记录，不声称零告警。

尚未验证项目：Windows 构建/EXE/Artifact/19045 真机、实际 WorkBuddy 列表/调用/新会话与真实模型结果；Mac 其他系统版本、系统凭证实际操作及分发签名/公证。

是否存在数据风险：未触碰真实业务数据，旧项目及用户历史备份不动；合成数据/备份与源码隔离。已验证范围内无未修复阻断问题；系统断电、磁盘/权限二次失败和真实 Windows 行为仍有未验证边界。

下一阶段准备执行的操作：仅在明确批准 G3 后，复核远端与本次源集合，基于远端 main 创建审核通过的候选提交并记录真实 SHA；推送到现有 Private 仓库并运行 Windows Actions，测试、原生打包、EXE 冒烟、检查资源与 SHA，下载 ZIP 检查并生成 GOAL002_WINDOWS_BUILD_REPORT.md，完成后再次停止。不得越过 G3 闸门制作/传输离线包或接入真实邮箱。

需要用户授权的事项：批准进入 G3，明确允许提交审核源文件、推送现有 Private 仓库并运行 Windows 构建；当前尚未执行这些操作。

**停止于 G2 闸门，等待用户明确回复。**
