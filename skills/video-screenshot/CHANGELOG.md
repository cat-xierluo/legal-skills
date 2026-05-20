# Changelog

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
