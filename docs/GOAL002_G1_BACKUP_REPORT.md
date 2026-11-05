# Goal002 G1：ZIP 备份与恢复安全验收

**PASS（Mac 源码及独立合成目录范围）**。未操作真实工作空间或用户历史 7z。Windows 文件管理器、EXE、实际磁盘权限/断电行为未验收。

## 优先安全闸门

原始 rc1 代码在自建临时目录复现：首个 data 复制失败，尚未移入 rollback 的 config 和 agent-workspace 被异常清理误删。证据 `.runtime/goal002-g1/rc1-restore-fault-probe.json`：config_preserved=false、agent_preserved=false。

当前实现记录 moved 和 touched；只有完成保护重命名的原目录才计入回滚，失败只删除新生成的部分副本，并按逆序恢复对应原目录。未触及的原目录不参加清理。

9 项故障注入均 PASS：data/config/agent-workspace 各自重命名失败和部分复制失败，恢复后初始化失败、队列重建失败、健康检查失败。每次都断言注入点实际到达、三类目录全部指纹相同、原 To Do/健康检查正常、原 ZIP SHA 不变。该测试先于其他恢复操作通过；仅对独立临时合成副本注入，未触及实际工作空间。

## 新格式与保留机制

- 标准 ZIP_DEFLATED，manifest 格式 v2，数据库仍 v2。默认名 WorkThread-Todos-日期.zip、WorkThread-Full-日期.zip。
- API、网页、CLI 均无需密码；py7zr 及其专属压缩/加密依赖已从直接依赖和锁文件移除。IMAP 系统凭证库逻辑未改。
- SQLite Backup API 快照、工作空间锁、JSONL/数据库提交与邮件一致性检查保留。没有用复制活动 SQLite 文件替代快照。
- 文件集合、数量、总大小、逐文件 SHA-256、ZIP CRC、版本/范围检查；损坏和错误 manifest 明确拒绝。
- 解压前拒绝绝对/盘符/穿越/反斜杠路径、Windows 保留名、末尾点/空格、符号链接、加密条目、大小写重复与文件/目录祖先碰撞；限制总解压大小和条目数。
- 预览返回文件路径、大小及 SHA-256；预览不改变目标数据。完整恢复保留保护目录；To Do 同 ID 不同内容整笔回滚。优先选新目录，Restore.cmd 拒绝已有目标。
- Full 保留项目规则、三个 Skills、自定义文件和部署登记，运行队列由数据库重建；恢复更换 epoch，禁用邮箱及正式 AI 计划，旧结果失效。
- 备份目标存在时拒绝覆盖。用户历史 todos.7z/full.7z 不删除、不转换、不猜密码；新版仅恢复自己的新版普通 ZIP。
- 历史空日期记录按原样备份/恢复，不批量改写；新的业务写入仍遵守公共日期校验。

## 自动及实际验证

| 项目 | 结果 |
|---|---|
| 9 个恢复故障点与逐文件指纹 | PASS |
| ZIP 专项自动用例 29 项 | PASS |
| 两类 ZIP 无密码创建、预览、恢复 | PASS |
| CRC/截断/SHA/manifest/版本/统计/必需文件/JSONL/数据库损坏 | PASS，目标及原备份不变 |
| 不安全路径、碰撞、符号链接 | PASS，解压前拒绝 |
| HTTP 两类下载与恢复、CLI stdin=DEVNULL 非交互 | PASS |
| 不同中文/空格路径、重复恢复、事务冲突 | PASS |
| 原始历史空日期两类恢复 | PASS，保持原记录 |
| 浏览器下载及上传校验、实际恢复 | PASS，未出现密码字段 |
| 系统 unzip -t 检查两类实际下载 ZIP | PASS，退出 0 |
| 新目录 CLI 独立恢复及 doctor | PASS，见 local-acceptance.json |
| 最新源码服务重启 | PASS，3 条事项、已编辑事项的两条日志及日期/状态保留 |

实际浏览器下载证据：

| 文件 | ZIP 字节 | manifest 文件数/总字节 | ZIP SHA-256 |
|---|---:|---:|---|
| WorkThread-Full-20261105-163718-008849.zip | 36008 | 12 / 420279 | d3224f262a33d6b4d4ddef4e9c0267ae66fd93c3e28b8fa6bee2f912e080149f |
| WorkThread-Todos-20261105-163849-278532.zip | 2253 | 1 / 6893 | 21902da54e65c145fb94efb40043c6b6761561b0eaa7ac3216fd4c21673c5737 |

以上是**合成数据备份 ZIP**，不是 Windows 安装包。副本与下载清单位于 `.runtime/goal002-g1/browser/`；原下载文件保留在 Downloads。

证据：`all-tests.xml`、`restore-safety.xml`、`local-acceptance.json`、`source-restart.json`、`browser/download-checks.json`、两个 unzip 日志、`browser/zip-preview.jpg`、`browser/zip-restored.jpg`、`browser/restored-logs.jpg`，均在 `.runtime/goal002-g1/`，不准备上传。

未发现 G1 已验证范围内尚未修复的数据安全阻断项。尚未验证真实 Windows 文件占用/权限、磁盘物理故障、断电或回滚自身再次遭遇系统故障；不可把异常注入通过表述为覆盖所有故障。当前未修改真实数据。
