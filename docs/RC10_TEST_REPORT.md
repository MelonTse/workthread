# RC10 开发与验收报告

开发分支：`codex/rc10-updates-pagination`。基线：`9d38e01a69c41ce9e4e77fa5448c78e59c5587a3`（RC9 源码及独立升级工具 1.0.1）。候选源码构建 SHA：`762ced234d042bf5dab4b41db4b61d675e603465`。本轮只推送候选分支、执行 Actions；没有修改 main、创建 Release 或操作用户电脑。

## 修改范围

1. 把独立工具已验证的安全复制提取为 `updating/copying.py`，网页/离线升级均复用。空目标继承权限与源不一致时先停下；不复制 ACL，不提权；DAT 复制后验证内容、权限、隐藏项/数据流。复制日志中非零系统错误即使退出码为 0 也拒绝。
2. 全新安装网页更新使用与当前 EXE 指纹绑定的 helper；不复用历史 bootstrap 的旧复制实现。重启选择当前活动程序。
3. 新版离线 bootstrap 增加同盘合成自检、进度心跳及明确的整体成功/失败记录。RC9 首次过渡必须从 RC10 包执行；详见 RC9_TO_RC10_UPGRADE.md。
4. 邮件全库分页接口与紧凑分页工具栏：每页 50、上限100；真实总数、上一页/下一页/跳页/刷新；搜索也支持分页。翻页固定 rowid 边界，避免新归档插入造成页间重复。无数据库结构变化。

## 本地已执行

- 326 项自动测试全部通过，JUnit：`artifacts/rc10-tests.xml`。
- 新分页测试覆盖 623 条追加合成邮件（连同3条demo共626）、全部页可达、搜索623条、稳定排序、只读事务、并发新归档、空结果/非法参数/特殊查询。
- RC9→RC10→下一测试版本保留所有表及自定义/交换/备份文件；五个切换点故障恢复；旧 bootstrap 不复用；自检失败留下明确失败结果且不进入业务快照。
- 原有跨进程中断恢复、磁盘不足、损坏签名/ZIP、写入冲突、迁移失败及中断后新写入保护测试继续通过。
- 浏览器新增8项分页检查通过（1440×960与390×844）；现有全界面112项回归通过。全部为独立临时目录合成数据；未连接真实邮箱或模型。
- 代码风格与 diff 空白检查通过。

## Windows 验收设计与当前边界

`rc10-qualification.yml`：从官方 RC9 ZIP（SHA-256 `8638fb190766b63422260c9ef4511a70d64839c01fc9ad5bba5d6b3c5a402ae6`）创建两套合成工作空间，使用新 RC10 EXE 过渡；随后在真实浏览器执行下一测试版本的检查/下载/取消/确认/重启/重连。另测全新 RC10 的首次网页更新及原生失败恢复。

验收在 Windows Server 2022 普通用户下执行；使用一次性签名密钥和隔离源码中的本地发布源。测试 ZIP 不发布、不交给用户安装；生产候选包由独立 windows.yml 嵌入正式公钥构建。Windows 10/11 客户端验收仍需安排，不能由 Actions 替代。

## Windows 普通用户原生验收：PASS

[升级验收 Actions 43379816674](https://github.com/MelonTse/workthread/actions/runs/43379816674) 已成功完成。`administrator=false`，使用中文带空格路径，12 项场景全部通过：

| 场景 | 实际结果 |
|---|---|
| 官方 RC9 → RC10，新 RC10 EXE 执行升级 | 两个空间所有37张表、邮件、待办、进展、知识、草稿、队列、交换文件、自定义文件和旧备份保留；旧 bootstrap 存在但未被复用；原入口 doctor 版本为 RC10 |
| 已过渡 RC10 → 签名的后续测试版本 | 真实浏览器完成检查、下载、取消、再次确认、停服、切换、原地址重连和新版本确认 |
| 全新 RC10 → 后续测试版本 | 未预建 base/bootstrap 目录仍可完成首次网页更新；数据保留 |
| 损坏 ZIP、错误签名、磁盘不足、复制失败、试迁移失败 | 5项均停止切换，原版本、原业务记录保持可用 |
| 正式空间放置后、验收空间放置后、版本指针切换处中断 | 3项均恢复匹配的 RC9 程序与原数据，原入口健康检查通过 |
| 中断后新增写入 | 拒绝自动覆盖；新增内容与旧数据副本均保留 |

网页测试启动了真实后台工作线程，测试中故意放入的无效 `outputs/unread.json` 会被正常隔离。验收明确检查：原始字节完整保留、只有对应的隔离结果和错误说明新增、错误为“无效的任务编号”；两套空间所有数据库表无变化，其他业务文件逐项一致。服务身份文件按重启后的实际身份验证。没有把整个队列目录或数据库表排除；另有3项篡改反例确认丢失待办、自定义文件或隔离原文必定失败。

Windows 同时完成8项邮件分页浏览器检查，桌面与窄屏通过。

下载证据 Artifact `14016421975`（外层ZIP）：189,324 字节；SHA-256 `3c5ae74adc5f65264a7679f9188f543448f22b768469ddd7a726447edec1791d`，已与 GitHub digest 比对一致。解包后的 `WINDOWS_REPORT.json`、两份逐项差异、标准用户日志和浏览器结果均已复核。

## 验收中发现及处理的问题

1. 首轮 Windows 自动测试10项失败：子进程使用 CP1252，中文进度输出抛编码异常，打断了原本要测试的故障恢复。已修复共享日志器：先写完整 UTF-8 日志，控制台编码/关闭管道问题不再阻断升级；磁盘日志写入错误仍向上传递。新增编码与关闭管道回归测试。
2. 原生验收脚本重复向固定启动器传入 maintenance launch，导致启动命令错误。已按用户实际入口的普通参数修正测试脚本；没有修改产品启动语义。
3. Runner 预装 Chrome 拒绝新标准用户的调试启动。验收改用独立 Playwright Chromium，没有关闭浏览器安全检查或更改用户系统配置。
4. 首次真实网页数据比对发现上述后台隔离和服务身份变化；已先在本地复现，再按精确转换规则验收，未放宽业务数据一致性要求。最终 Windows 两份差异均仅包含这些已验证变化。

## 候选包与发布边界

[Windows 候选构建 Actions 43379816717](https://github.com/MelonTse/workthread/actions/runs/43379816717) 为 PASS：326 项测试通过（273.66秒，0失败/错误/跳过），156个受控源码路径隔离检查通过，PyInstaller Windows 原生 x64 onedir 构建成功。冻结 EXE 实际完成 HTTP 启动、HTML/JS/Schema、单实例与端口排他、To Do/进展、普通 ZIP 备份恢复检查。

| 项目 | 实际值 |
|---|---|
| 源码构建 Commit | `762ced234d042bf5dab4b41db4b61d675e603465` |
| 候选 Artifact | `14016601359`，外层ZIP 20,358,796 字节 |
| 外层 Artifact SHA-256 | `e9cc871e25ebff254fe06c92e625b3e4d1e6ec1b3adb5dd4eb16e86f2c99d019` |
| 内部 Windows 程序 ZIP | `WorkThread-1.0.0rc10-windows-x64.zip` |
| 内部 ZIP 大小 | 20,619,755 字节 |
| 内部 ZIP SHA-256 | `e129e15cf26c4c0ae840baa58ef6af32bf941a7d34c0688e9007c80897fefbc1` |
| 包内文件 | 886个；SHA256SUMS.json 中885项逐一通过，清单自身单列 |
| BUILD_INFO / 架构 | 1.0.0rc10 / 上述Commit / Windows / AMD64；EXE PE头AMD64、python313.dll存在 |

已下载真实 Windows Artifact 并分别核验外层和内层ZIP。12项网页、Schema、WorkBuddy模板资源通过核对；3个网页文本文件在Windows检出为CRLF，归一化行尾后与源码完全一致（Windows构建端已逐字节比对）。三个 `.codebuddy/skills/*/SKILL.md` 的内容、frontmatter、CODEBUDDY.md、项目规则、模板标记及启动/安装/备份/恢复脚本齐全。嵌入的发布公钥与正式公钥一致；检查冻结Python归档确认发布下载函数仍使用HTTPS，未带入验收用本地feed替身。无业务数据库、邮件归档或私钥文件。

候选包不等于正式更新发布：本轮没有生成正式签名更新清单，也没有创建 Release。不能现在直接通知用户从网页升级到 RC10。报告收尾只改文档，未重打包；包内报告为构建时的中间记录，请以候选分支最新两份验收/操作文档为准。

RC9 首次过渡须使用新版包内升级入口；RC10 后续网页升级已经实际验收，但后续版本仍须经维护者签名并声明兼容来源。Windows 10 19045 / Windows 11 客户端、实际用户工作空间与真实网络下载尚未在本轮验收；Actions 不能替代这些结论。


## 本地交付位置

相对于本工作树：

- `docs/RC9_TO_RC10_UPGRADE.md`：首次过渡步骤及给 WorkBuddy 的提示词。
- `artifacts/rc10-tests.xml`、`rc10-tests.log`：326项本地自动测试。
- `artifacts/rc10-ui-regression/results.json`：112项原界面回归。
- `artifacts/rc10-mail-browser/`：8项本地分页检查及三张截图。
- `artifacts/rc10-local-web-update.log`：本地网页升级交互验证。
- `artifacts/rc10-windows-evidence/contents/`：下载的原生验收报告、逐项差异、日志及Windows浏览器截图。
- `artifacts/rc10-candidate/PACKAGE_VERIFICATION.json`：真实候选包校验记录；`contents/` 保存内部程序ZIP、旁证SHA-256及Windows JUnit。
- `artifacts/rc10-local-evidence.json`：本地证据文件大小及SHA-256。

结论：本轮开发及 Windows Actions 验收 PASS；正式签名发布、Windows 10/11 真机安装、真实业务工作空间升级尚未执行。本轮到此停止，等待发布审核。
