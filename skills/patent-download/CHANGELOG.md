# Changelog

本文件记录 patent-download 的用户可见变更。最新在前。

## [2.6.0] - 2026-07-23 发布前审查修复

### 改进
- **定位拓宽**：description 与标题从「中国专利下载工具」改为「专利下载工具」，反映平台本身支持通用专利（Google Patents 覆盖全球）；中国专利号格式说明作为客观事实保留
- **隐私去具体化**：实测案例中的真实公司名泛化为占位符「某信息科技公司」
- **文档结构**：EXAMPLES.md 下沉到 references/examples.md（渐进式披露，根目录只留核心文档）
- **文档清理**：删除 SKILL.md 目录图中已废弃的 `pss_cookies.txt` 行；删除 accounts-setup.md 中对已废弃 cookies 文件机制的引导

## [2.5.0] - 2026-07-23 凭证隔离安全加固

### 新增
- **防泄露自检**：`_creds.py` 新增 `check_leak()`，运行 `python scripts/platforms/_creds.py` 时自动检查 `config/.env` 是否被 git 误追踪；若追踪则报警并给出可直接执行的 `git rm --cached` 修复命令，避免真实账号入库

### 改进
- **凭证自检输出优化**：自检只列出需要账号的 4 个平台（uyanip/patentstar/gpic/pss），google/epub 单独标为免登录，不再对免登录平台报"无账号"造成误导
- **`.env.example` 顶部加防提交警示**：明确标注"切勿提交真实账号"及误操作后的修复方式、自检命令

### 修复
- **`check_leak()` 报警路径修正**：原实现报警命令的 `git -C` 路径指向 skill 目录而非 git 仓库根，用户照做会失败；改用 `git rev-parse --show-toplevel` 取真实仓库根，报警命令可直接复制执行

## [2.4.0] - 2026-07-23 依赖防护与发布就绪

### 技术优化
- **依赖缺失优雅降级**：6 个脚本的外部依赖 import 加 try/except 防护，未安装时打印清晰的中文安装提示并退出，不再抛晦涩的 `ImportError`
  - `download.py`：`playwright`（含 `playwright install chromium` 提示）
  - `uyanip.py` / `epub.py` / `patentstar.py` / `pss.py` / `gpic.py`：`requests`
- 符合 AGENTS.md「脚本依赖防护要求」硬依赖规范

### 改进
- **SKILL.md 依赖章节重构**：按 AGENTS.md「SKILL.md 依赖声明要求」区分"开箱即用"（信息查询、凭证自检零依赖）和"需安装依赖"（按通道列出依赖表）两档，就近给出安装说明

## [2.3.0] - 2026-07-23 技术债务清理与一致性修复

### 改进
- **文档/注释对齐凭证来源**：修正 v2.2.0 改造后残留的"账号见 `config/platforms.yaml`"表述（platform-status.md、gpic/pss/uyanip 文件头、cli.py 注释），统一改为"环境变量，见 `config/.env.example`"，与 `_creds.py` 实际行为一致
- **半成品平台显式标注**：给 patentstar / patentstar_browser / gpic / pss / epub 五个未完成或已失效的平台脚本在 docstring 顶部加 `⚠️ 实验性` 标记，说明失效原因并指向 Google Patents
- **静默失败改为明确提示**：上述脚本 `download_pdf` 末尾的静默 `return None` 改为打印"未实现 + 推荐改用 Google Patents"提示，避免用户看到流程跑完却无文件
- **度衍浏览器流程提示**：uyanip 浏览器方式流程可用但未监听 download 事件保存文件，补充明确说明
- **wrapper 注释**：`patent-download.sh` 补充分流逻辑说明（google → cli.py，其他 → download.py epub 旧入口）

### 文档完善
- **LICENSE.txt 版权行**：修正为项目统一的 `Copyright (c) 2025 杨卫薪律师（微信ywxlaw）`（原为 `2026 杨卫薪`，缺后缀）
- **download.py / epub.py 交叉注释**：说明 `download.py` 是 epub 平台的相对完整实现，`platforms/epub.py` 为 cli.py 统一架构下的占位

### 技术优化
- 确认 `scripts/platforms/__pycache__/` 未被 Git 跟踪（`.gitignore` 的 `__pycache__/` 规则已正确生效），本地 `.pyc` 为运行时产物，无需清理

## [2.2.0] - 2026-07-12 公开发布改造

- **凭证改环境变量**：账号不再入仓库，通过 `PATENT_<平台>_USERNAME/_PASSWORD` 环境变量配置；新增 `config/.env.example` 模板，用户 `cp` 为 `.env` 填写（.gitignore 不入库）
- **_creds.py 重写**：读 os.environ，回退手动解析 `.env`（无 python-dotenv 依赖）
- **platforms.yaml 解耦**：去掉所有账号字段，只保留平台元数据
- **cookies 忽略**：`config/pss_cookies.txt` 从仓库移除（git rm --cached）+ .gitignore
- **文件归位**：`patent-download.sh` 移入 `scripts/`；`config/accounts.md` → `references/accounts-setup.md`（改写为账号获取 + ToS 合规说明，无密码）
- **LICENSE.txt**：补 MIT 全文（frontmatter 已声明）
- **ToS 合规**：账号登录通道（度衍/PatentStar/粤港澳/PSS）在 references 标注，由用户自评风险

## [2.1.0] - 2026-07-12 目录结构规范化

- **凭证集中**：`data/` → `config/`，账号单一来源 `config/platforms.yaml`
- **代码零硬编码**：`cli.py` 与 5 个平台脚本（pss / patentstar / uyanip / gpic / patentstar_browser）移除明文账号密码，统一改读 `config/platforms.yaml`
- 新增 `scripts/platforms/_creds.py`：共享凭证加载工具
- **删除死代码**：`scripts/api/`、`scripts/browser/`（共 353 行无人调用的历史遗留）
- 抽取参考文档：`references/patent-number-formats.md`、`references/platform-status.md`
- SKILL.md 按渐进式披露瘦身，目录图与实际对齐
- 安全：移除 `patentstar.py` 把 session cookie 打印到 stdout 的逻辑

## [2.0.0] - 2026-07-11 Google Patents 成为首选通道

- 新增 Google Patents 平台（推荐），实测 `202421964517.8` 成功下载
- 标记 PatentStar API 失效（Ret=206），调低推荐度
- 标记润桐 RainPat 服务器维护中（预计 2026-07-17 恢复）
- 明确申请号 vs 公告号的区别说明

## [1.0.0] - 2026-02-27 多平台架构

- 添加度衍专利支持
- 初始版本，解耦为多平台架构
