# Changelog

## [0.4.0] - 2026-08-13

### 新增
- 新增两遍式时间簇择优：先结合候选帧前后关系识别稳定段、短切换段和持续运动段，再在簇内选择清晰、完整、停留更稳定的代表帧
- 新增横向混合页三帧分析与纵向拼接风险指标，为滑页中间态过滤和视觉审计选组提供时序证据
- 新增经济型多模态审计包：`prepare_vision_audit.py` 默认最多选择 8 组、24 张唯一图片，并生成前后帧联系表和带哈希 manifest
- 新增结构化视觉决策应用器 `apply_vision_review.py`，支持 `keep/drop/replace`，以非破坏方式生成 `_curated/` 和完整排除清单
- 新增 `check_pipeline.py` 回归检查，覆盖簇内择优、混合过渡帧、审计预算、合法审计和越界引用失败关闭

### 改进
- OCR 去重不再自动禁用 SSIM；未安装 RapidOCR 时继续优雅降级到纯图像流程
- `min-gap` 从主要选帧机制降为时间簇后的安全限流，避免机械保留切换开始时的第一张
- 多模态默认入口由最多 200 张丢弃候选改为本地风险短名单；完整候选只用于漏帧排查
- `_report.json` 新增时间簇统计、选择置信度、源候选序号、拼接风险和对应丢弃计数
- 重新抽帧或准备审计包时若发现既有视觉审计、人工决策或精选目录，改为拒绝使其失效；旧候选目录也只清理可确认由本工具生成的普通文件，并拒绝跟随符号链接
- 修复稀疏长停留页可能因单候选跨度为零而被误判成短切换的问题；短切换改用两侧稳定页之间的真实时间跨度判定

### 文档完善
- 重写基础模式与视觉模式分支，新增 `references/vision-audit.md` 的预算、决策合同和失败边界
- 按项目规范补齐 MIT 许可证版权信息
- 记录 213.6 秒真实小红书录屏复测：同样 411 个初始候选，基础保留由 0.3.2 的 141 张降至 55 张；预算审计处理 8 组、23 张唯一图片，剔除 1 张加载中页、1 张未加载页和 1 张视觉重复页后生成 52 张精选帧

## [0.3.2] - 2026-06-02

### 新增
- 新增复合复核候选帧模式：`--keep-drop-candidates` 会保存被去重或过滤规则丢弃的候选帧，供多模态模型回查漏帧风险
- 新增 `--drop-candidate-limit` 参数，限制复核候选帧保存数量，默认最多保存 200 张

### 改进
- `_report.json` 新增 `review.drop_candidates`、`review.drop_candidate_count` 和视觉复核状态字段，记录候选帧文件名、丢弃原因、时间戳和 SHA256
- 归档结果新增 `_review_candidates/`，与正式 `frames/` 分离，避免复核候选帧污染证据清单

### 文档完善
- 补充复合复核模式说明：当前模型支持图像输入时才执行视觉复核；文字模型跳过复核并明确说明未做图像判断
- 校正参数文档中的场景阈值、dHash、SSIM、滚动合并和最小时间间隔默认值

## [0.3.1] - 2026-05-20

### 修复
- 修复 archive 污染问题：归档时只复制 `_report.json` 中记录的有效帧，不再把输出目录内所有 JPG 残留一并复制
- 修复输出目录残留问题：每次运行前自动清理旧的 `frame_*.jpg`、`_report.json` 和工具元数据文件，避免旧帧混入新结果

### 技术优化
- 新增 archive 一致性校验，确保 `archive/frames/` 文件名与 `_report.json` 的帧清单完全一致
- 报告和归档元数据新增 `cleanup.stale_deleted_count`、`cleanup.stale_deleted_files`；归档元数据新增 `archive_validation` 信息

## [0.3.0] - 2026-05-20

### 改进
- 新增内容区聚焦去重：dHash、像素差异、SSIM 和滚动合并默认排除顶部状态栏、底部导航栏及左右边缘
- 新增 SSIM 结构相似度去重：`--ssim-threshold` 默认 0.70，作为 dHash 的补充判断
- 新增滚动帧合并：`--scroll-merge` 默认开启，支持 `--no-scroll-merge` 和 `--scroll-diff-threshold` 调参
- 修正 scene/keyframe/smart 模式下基于 `-frame_pts` 的捕获时间戳计算，优先使用视频帧率避免时间戳被输入 time_base 缩小

### 文档完善
- 更新 `SKILL.md` 和 `references/strategy-and-params.md`，补充内容区裁剪、SSIM、滚动合并的参数说明和调参建议

## 0.2.0 (2026-05-20)

- 新增模糊帧过滤：`--filter-blur` 可选参数，基于 Laplacian 方差检测模糊帧（默认阈值 50.0）
- 新增内容质量过滤：`--filter-quality` 可选参数，自动过滤空白页、启动/控制画面、页面切换过渡帧
- 去重流程扩展为六级：SHA256 → dHash → 像素差异 → 质量过滤 → 模糊过滤 → OCR 文本
- 归档元数据新增 `filter_blur`、`blur_threshold`、`filter_quality` 参数和 `blur_drops`、`quality_drops` 统计
- 参考：移植自 fachuan（法穿）项目，质量检测算法为新增实现

## 0.1.0 (2026-05-20)

- 初始版本，核心算法移植自 fachuan（法穿）项目 `chat_records/services/` 模块
- 四种抽帧策略：scene（场景检测）、keyframe（关键帧）、interval（固定间隔）、smart（智能去重）
- 四级去重：SHA256 → dHash → 像素差异 → OCR 文本相似度
- 独立 Python CLI，无 Django 依赖
- 本地 RapidOCR 离线 OCR 去重
- 默认保持原始分辨率、最高 JPEG 质量，优先保证证据清晰度
- archive 归档机制：每次分析自动留存参数、报告和帧副本，便于溯源调参
