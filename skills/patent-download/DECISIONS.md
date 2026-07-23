# 决策记录

> 本技能的重要技术决策、架构选择和实施记录

## [DEC-001] 多平台架构：cli.py 统一入口 + 各平台独立模块

**背景**
专利下载需要对接多个平台（Google Patents、度衍、PatentStar、粤港澳、PSS、CNIPA epub），各平台接入方式（API / 浏览器）和登录要求差异大。

**决策**
采用 **统一入口 + 平台模块化** 架构：
- `scripts/cli.py` 作为统一入口，内置 `PLATFORMS` 字典管理各平台元数据（推荐度、是否需登录、API/浏览器支持）
- `scripts/platforms/<平台>.py` 各自独立实现 `main()` 入口，cli.py 通过动态导入调度
- 共享凭证加载逻辑集中在 `scripts/platforms/_creds.py`

**理由**
1. **可扩展**：新增平台只需加一个模块 + 在 PLATFORMS 字典注册，不动 cli.py 调度逻辑
2. **可降级**：cli.py 对不支持 API 的平台自动降级到浏览器方式
3. **关注点分离**：平台特定逻辑（选择器、登录流程）封装在各自模块，不污染统一入口

**影响**
- 后续平台维护只需改对应模块文件
- cli.py 通过 `__import__` 动态调度，平台脚本需遵循 `def main()` 约定

---

## [DEC-002] Google Patents 作为首选通道

**背景**
2026-07-11 实测发现各平台可用性差异显著，需要明确推荐优先级。

**选项**
| 平台 | 方式 | 状态 |
|:-----|:-----|:-----|
| Google Patents | API (SDK) | ✅ 免费免登录，全球专利 |
| 度衍专利 | 浏览器 | ✅ 可用，需账号 |
| PatentStar | API | ❌ 失效（Ret=206） |
| 粤粤港澳/PSS | 浏览器 | 🚧 PDF 下载未完成 |
| CNIPA epub | 浏览器 | ⚠️ 有验证码强反爬 |

**决策**
选 **Google Patents 为首选**，通过 `patent-downloader` SDK 直连。

**理由**
1. **免费免登录**：无 ToS 合规风险
2. **有现成 SDK**：`patent-downloader` 封装了 API 调用
3. **覆盖广**：全球专利，公开后 1 天内收录
4. **稳定**：无验证码、无 IP 限制

**影响**
- PatentStar API 失效后保留代码但标为 `⚠️ 实验性`，不删除（见 DEC-004）
- 默认平台设为 `google`

---

## [DEC-003] 凭证完全环境变量化（公开发布改造）

**背景**
早期版本把真实账号密码硬编码在 `data/accounts.md` 和 `config/platforms.yaml`，无法公开发布。

**决策**
**凭证一律通过环境变量配置**，代码零硬编码，仓库零存储：
- 命名：`PATENT_<平台>_USERNAME` / `PATENT_<平台>_PASSWORD`
- `config/.env.example` 提供模板（入库），用户 `cp` 为 `.env` 填写（`.gitignore` 不入库）
- `_creds.py` 优先读 `os.environ`，回退手动解析 `config/.env`（无 python-dotenv 依赖）

**理由**
1. **安全**：真实账号绝不进 git 历史
2. **无依赖**：手动解析 `.env`，不引入 python-dotenv
3. **符合惯例**：与 tianyancha、badminton-scoring 等 skill 的 `config/.env` 模式一致

**影响**
- `platforms.yaml` 剥离所有账号字段，降级为纯元数据参考
- 历史提交（初始入库）曾含明文账号，详见 DEC-006 泄露处置

---

## [DEC-004] 半成品平台保留但不删除（技术债务策略）

**背景**
5 个平台脚本（patentstar / patentstar_browser / gpic / pss / epub）是半成品或已失效：`download_pdf` 始终 `return None`，未实现真正的文件保存。

**选项**
| 方案 | 优势 | 劣势 |
|:-----|:-----|:-----|
| 删除半成品 | 代码精简 | 丢失可复用的登录/搜索流程，违背"不想删"意愿 |
| 保留并标注 | 保留历史实现供参考 | 列表里有不可用平台 |

**决策**
**保留全部代码，但显式标注实验性**：
- docstring 顶部加 `⚠️ 实验性（原因）` 标记，指向 `references/platform-status.md`
- 静默 `return None` 改为打印"未实现 + 推荐改用 Google Patents"提示

**理由**
1. **尊重用户意愿**：明确表示不想真正删掉历史代码
2. **不误导**：标注让维护者一眼知道哪些是可用功能
3. **低风险**：Google 是默认首选，半成品不会被误触发

**影响**
- `cli.py --list` 仍列出全部平台，但每个都有 note 说明状态

---

## [DEC-005] 依赖防护：硬依赖 try/except + 中文安装提示

**背景**
6 个脚本顶部裸 import 外部依赖（playwright / requests），用户未安装时抛晦涩的 `ImportError`。AGENTS.md「脚本依赖防护要求」明确要求硬依赖必须做优雅降级。

**决策**
所有外部依赖 import 用 try/except 包裹，捕获后打印清晰中文安装提示并 `raise SystemExit(1)`。

**理由**
1. **符合项目硬规范**：AGENTS.md 明文要求
2. **用户体验**：缺依赖时给出 `pip install -r scripts/requirements.txt` 明确指引
3. **不阻塞主流程**：`SystemExit` 穿透 cli.py 的 `except Exception`，正确终止

**影响**
- 依赖缺失时不再有晦涩 traceback
- `google_patents.py` 的函数内延迟 import 是正确范式参考

---

## [DEC-006] 凭证隔离三层防御 + 防泄露自检

**背景**
初始提交曾将真实账号（含手机号、密码、PSS cookies）入库到 git 历史。虽然后续改造删除了文件，但 blob 仍留在历史中。private-skills 是私有仓库，但发布到公开 legal-skills 前必须确保隔离。

**决策**
建立**三层凭证隔离防御**：
1. **被动拦截**：`.gitignore` 的 `**/.env` 规则忽略真实配置
2. **主动自检**：`_creds.py` 新增 `check_leak()`，运行自检时检查 `.env` 是否被 git 误追踪，报警并给出可直接执行的 `git rm --cached` 修复命令
3. **发布隔离**：从 private-skills 迁移到 legal-skills 时只复制文件快照，不带 git 历史

**理由**
1. **gitignore 可能被 `--force` 绕过**，需要主动检查兜底
2. **`check_leak()` 用 `git rev-parse --show-toplevel` 取真实仓库根**，报警命令可直接复制执行（初版指向 skill 目录导致照做失败，已修正）
3. **只复制快照**确保公开仓库历史永远不含泄露 commit

**影响**
- 运行 `python scripts/platforms/_creds.py` 即可自检凭证配置与泄露风险
- 历史泄露的账号应视为已暴露，需改密（手机号无法改，需提高警惕）

---

## [DEC-007] 发布定位拓宽：从「中国专利」到「通用专利」

**背景**
skill 原定位为「中国专利下载工具」，但 Google Patents 等平台本身支持全球专利，定位过窄。

**决策**
- description 与标题从「中国专利下载工具」改为「专利下载工具」
- platform-status.md 的覆盖从「全量中国专利」改为「全球专利（中国专利为主要测试场景）」
- **保留** `references/patent-number-formats.md` 的「中国专利号格式说明」——这是客观事实（CN 编号体系确实是中国特有），不是定位问题

**理由**
平台能力是通用的，不应被当前测试范围窄化；但编号格式说明是事实性描述，保留不影响通用定位。

---

## 工作日志

### 2026-07-23（发布前完整改造，v2.3.0 → v2.6.0）

**技术债务清理（v2.3.0）**
- 修正凭证来源文档/注释残留（platforms.yaml → 环境变量）
- 半成品平台加 `⚠️ 实验性` 标注 + 静默 return 改提示
- LICENSE.txt 版权行统一为项目规范

**依赖防护（v2.4.0）**
- 6 个脚本外部依赖加 try/except 防护
- SKILL.md 依赖章节区分「开箱即用 / 需安装」两档

**凭证隔离加固（v2.5.0）**
- `_creds.py` 新增 `check_leak()` 防泄露自检
- 修正报警路径 bug（指向仓库根而非 skill 目录）

**发布前审查修复（v2.6.0）**
- 真实公司名泛化为占位符（隐私去具体化）
- 定位拓宽为中国专利 → 通用专利
- 文档清理（删除已废弃 pss_cookies.txt 引用）
- EXAMPLES.md 下沉到 references/examples.md（渐进式披露）

**安全审查**
- 确认 git 历史中存在真实账号泄露（初始提交），已在 private-skills 私有仓库
- 迁移到 legal-skills 采用只复制文件快照方式，公开仓库历史不含泄露

**工作流修正**
- 放弃在主工作区切分支的做法，改用 `.claude/worktrees/codex-patent-download-publish` 独立 worktree 推进，避免污染并行工作
