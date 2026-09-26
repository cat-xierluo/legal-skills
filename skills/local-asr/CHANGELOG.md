# 变更日志

本项目的所有重要变更都将记录在此文件。

## [2.2.0] - 2026-09-27

### 修复

- **R1 声纹输入校验与识别故障隔离（Task-017，P1）**：注册端点此前只要求向量至少 16 维，32 维坏向量可入库并在下次转录时使整次 MOSS 转录 HTTP 500、无法交付已识别出的文字；`1e40` 溢出值也能注册并写入 NaN。现按当前声纹模型（CAM++）显式校验维度/数值有限性/有效范数，非法输入返回明确 4xx 且库文件字节不变；库内历史坏条目读取时逐条隔离并告警，不影响其他有效记录；识别或声纹提取故障只降级身份识别（保持匿名并附具体原因），不再阻断文字稿交付；MOSS 本身转录失败仍正常报错。
- **R3 声纹库原子保存与并发安全（Task-018）**：HTTP 与本地 CLI 此前均原地截断覆盖 JSON，保存中断会损坏旧库，且服务把损坏库当空库、下次注册即覆盖全部记录。现新增共用存储层 `speaker_store.py`：同目录临时文件写入/校验/fsync 后原子替换，进程间锁覆盖整个读改写事务；库损坏时读路径降级告警、注册/删除以 409 拒绝并保留原件；历史坏条目不被写操作顺带清理；库/锁/临时文件仅当前用户可读写。
- **R2 完整说话人状态与首次空库认领（Task-019）**：首次空库时 `speaker_identification` 此前整体缺失，库非空时也只覆盖有向量的标签，短发言/提取失败的人被漏掉导致认领流程无法按文档触发。现以全部转录段的稳定 speaker ID 为全集逐人返回识别结果（空库全 null），并新增 `speaker_states` 显式区分 `matched` / `unknown`（可认领注册）/ `insufficient_audio`（仅可本稿标注，不能注册）/ `extraction_failed` / `disabled`（fast、显式关闭提取、CAM++ 不可用），不再让 Agent 从字段缺失猜状态。
- **R4 自动 CLI 交付结构化结果与认领入口（Task-020）**：推荐入口 `auto_transcribe.py` 此前丢弃识别结果、向量与段落，无法完成首次认领。现新增 `--json`（stdout 仅输出完整响应 JSON，可被标准解析器直接读取，人类日志走 stderr）、`--save-result`（结果文件 0600 权限）与 `speaker_registry.py claim` 子命令（按标签确定性取向量注册，避免手工复制 192 个浮点数）；普通 CLI `--json` 模式的日志同步分离到 stderr；默认人类输出新增未识别说话人的认领提示。
- **R5 摘要保留说话人归属并验证覆盖（Task-021）**：摘要预处理此前删除 `HH:MM:SS` 匿名标签却保留实名，超过一小时即丢归属；发言人提取只认旧 `speaker_N` 格式；验证器只检查四个章节标题，漏人也放行。现提取文本逐行保留发言标签归属（支持 `MM:SS`、`HH:MM:SS`、实名、匿名与旧格式）；提示词要求 `speaker_order` 逐字使用稿件发言标签；验证器区分"章节齐全"与"发言人覆盖完整"，漏人/重复凑数/杜撰发言人都会以非零退出码和明确字段传递给调用方；无发言行结构的稿件明确报告"无法验证"而不假定通过。
- **R6 截图默认阈值全入口一致（Task-022）**：服务与提取器默认 20，两个 CLI 默认 27 且显式传给服务，同一视频因入口不同漏页。现以 `slide_extractor.DEFAULT_SLIDE_THRESHOLD = 20.0` 为唯一权威源：CLI 未指定时不携带该字段由服务决定，显式值仍覆盖；`--help` 与文档不再出现矛盾默认值。

### 改进

- **R7 分数名称与效果声明准确化（Task-023）**：Markdown 识别注记由"置信度"改为"声纹相似度"（保留 `score` 字段兼容）；`/speaker/test` 新增 `best_is_match` / `identified` 字段，最高分低于阈值时明确"未识别"而不是把最佳候选当命中；文档明示 score 是归一化向量的余弦相似度，不是经过校准的身份正确概率；历史实测样本（参与注册/调参）与未见录音泛化能力的边界在参考文档中说明，独立准确率评估（Task-024）保持 NOT_VERIFIED。
- `api-reference.md` 补齐声纹端点（register/list/remove/test 的参数、响应、错误语义与认领流程）及 `speaker_states`/`speaker_identification`/`speaker_embeddings`/`slide_threshold` 字段契约。
- `speaker-registry.md` 更新逐人识别契约、`speaker_states` 语义、claim 用法、存储保护与准确率边界说明。
- SKILL.md 步骤 3 改按 `speaker_states` 驱动认领流程（unknown 才注册、insufficient_audio 只能本稿标注），步骤 6 补充发言人覆盖验证的处置；自动转录流程补充 `--json`/`--save-result`/`claim` 用法。

### 验证

- `verify_speaker_registry.py` 重写并扩展：新增输入校验反例（16/32/191/193 维、空、全零、NaN、Inf、溢出、非数值全部拒绝且库文件不变）、坏条目隔离、识别异常降级、六路说话人状态契约、原子保存（写入中断保旧库）、损坏库 409 拒绝、双进程并发注册不丢项、文件权限检查。
- 新增 `verify_summary_coverage.py`：小时边界/实名匿名混合/旧 speaker_N 归一提取、漏人/重复凑数/杜撰发言人正反例、CLI 非零退出码、注入不损坏正文与实名标注。
- `verify_default_routes.py` 扩展：CLI payload 一致性（未指定不带 threshold 字段、显式覆盖）、自动 CLI `--json` 纯 JSON 交付与 `--json`/`--prompt-only` 互斥、claim 确定性取向量。
- 既有 `verify_moss_mlx.py` 回归继续通过；模型路由、批量错误状态、服务标识与视频场景检测回归通过。

## [2.1.1] - 2026-09-24

### 改进

- 认领工作流新增"说话人叙述"环节（用户提议）：转录后对每位未识别说话人，Agent 按响应 `segments` 归纳简要叙述——发言占比、内容概述、身份线索（自称/被称呼/角色口吻）——随认领询问一并呈现，用户凭内容即可打标真实姓名，无需回听音频。SKILL.md 步骤 3 与 `references/speaker-registry.md` 注册流程同步更新，并附呈现示例。
- 声纹库注册名按用户要求由职业称呼更正为本人真名（仅本机声纹库文件，不涉及公开文档；六段验收录音确认用户在场但旧稿未带名的，可重转录补标）。

## [2.1.0] - 2026-09-23

### 新增

- 认领式声纹注册与自动识别（Task-014）：默认 MOSS 路径开启 `diarize` 时，为每个文件内说话人提取 CAM++ 声纹向量并在转录响应中透出 `speaker_embeddings`；与本地声纹库比对后返回 `speaker_identification`，命中的说话人在 Markdown 中直接显示注册名并附置信度注记，未识别的保持匿名。
- 新增服务端点 `POST /speaker/register`（认领注册，同名覆盖）、`GET /speaker/list`、`POST /speaker/remove`、`POST /speaker/test`（音频声纹与库比对）；新增 `scripts/speaker_registry.py` 管理 CLI（list / remove 无需服务运行，test 调用服务）。
- 单段短录音在 `diarize` 时也提取声纹（此前仅多段长录音的跨段链接提取），使首次认领注册在任意长度录音上可用；`FUNASR_MOSS_SPEAKER_EMBEDDINGS=0` 可跳过单段提取以省资源。
- 识别阈值默认 0.55（六段真实录音验收标定：同人跨录音 0.56–0.87、非同人 ≤0.14，与跨段链接阈值一致），`FUNASR_SPEAKER_IDENTIFY_THRESHOLD` 可调；同一次录音内一个注册名最多命中一个说话人标签。
- 新增 `references/speaker-registry.md`：注册/认领流程、阈值与置信度解读、跨信道限制、纠错方法与声纹隐私合规（客户声纹注册需单独同意）；SKILL.md Agent 工作流新增"说话人识别与认领"步骤。

### 安全

- 声纹库文件 `assets/speaker-profiles.json`（姓名+声纹向量，属生物识别信息）由根目录 `.gitignore` 精确排除，仅限本机使用。

### 验证

- 新增 `scripts/verify_speaker_registry.py` 回归：向量比对逻辑（命中/阈值拦截/同名唯一分配）、MOSS 转录集成（embeddings 透出、识别 warnings、fast 模式跳过）与库读写端点（注册/覆盖/列表/删除/非法输入），全部通过。
- 既有 `verify_moss_mlx.py`、`verify_default_routes.py` 回归通过；真实服务上经 HTTP 完成 注册→列表→测试→删除 全流程，真实 CAM++ 192 维向量注册后同一音频识别得分 1.0。
- 真实验收（用户提供六段录音，共约 79 分钟、12 个说话人向量）：跨录音声纹聚类 + 转录文本身份证据（"我是杨律师"/"杨律师是吧"）双重确认四个本人声纹，以四段簇中心注册"杨律师"后，四段本人 0.75–0.87 全命中、四位客户 0.04–0.14 零误识；重转录验证端到端 Markdown 自动标注（含置信度注记）与匿名说话人认领提示。据此将识别阈值从 0.60 起步值调整为 0.55（弱信道漏识修正）。

## [2.0.0] - 2026-09-23

### 改进

- 技能 ID 与目录从 `funasr-transcribe` 迁移为 `local-asr`；默认仍为 MOSS-MLX，原 FunASR 原生及 ONNX 管线继续可显式选择。
- 更新本技能的服务标识、CLI 提示和安装指引，并迁移同仓技能的实际调用路径。本机虚拟环境与模型缓存保留，虚拟环境脚本和本地配置中的旧绝对路径改为新目录。
- 客户端启动检查核对服务标识，避免端口被其他服务占用时误判；移除按端口无差别强制终止进程的故障排除命令，给出指定其他端口的用法。
- 不再随技能提交本机生成的 `assets/skill-env.json`；根目录忽略规则阻止其绝对路径被再次加入 Git，安装验证时仍可在本机重新生成。

### 文档完善

- README 展示新入口；已发布的旧名下载包仍按历史版本标注，不冒充本次源码版本。

### 验证

- 新目录的虚拟环境、安装验证、依赖检查、MOSS 适配器、默认/旧模型路由与服务标识回归通过；备用端口真实服务将合成双人音频转为 `S01/S02` 两段 Markdown。听悟摘要注入与校验通过。Skill 静态安全扫描无 high/critical；旧端口被其他服务占用，因此未将其终止。
- 含音轨的三页合成视频在默认 MOSS 路由、`--slide-threshold 20` 下生成两段说话人文本和三张按时间插入的截图；默认阈值 27 在该样本只提取一张，真实课件视频的最佳阈值仍待验证。

## [1.11.2] - 2026-09-23

### 新增

- 新增双后端模型安装参考，分别说明 Apple Silicon 默认 MOSS-MLX 与保留的 Paraformer/ONNX 的设备条件、依赖、模型下载、缓存、服务启动及显式选择方式；SKILL 和 API 参考均提供入口。

### 修复

- `setup.py` 预下载的 CAM++ 权重改为 FunASR `cam++` 别名实际加载的 `iic/speech_campplus_sv_zh-cn_16k-common`；`--legacy` 安装也下载并验证 CAM++，避免默认说话人分离首次调用时另行获取权重。`check_env.py` 的 Python 版本提示同步为完整安装实际要求的 3.10–3.12。

### 文档完善

- 说明 `funasr-transcribe` 是沿用的技能标识、当前默认后端为 MOSS-MLX；评估中性名称 `local-asr`，因其他技能存在路径级调用，本次不直接更名。

### 验证

- 本机核对 FunASR `cam++` 别名、安装脚本与模型清单均指向同一权重；MOSS 与保留的 FunASR 安装验证通过，适配器与默认路由回归通过。新增 reference 链接、版本一致性和 `git diff --check` 通过；未在干净设备重新下载全部模型。

## [1.11.1] - 2026-09-23

### 文档完善

- 增加 MOSS-MLX 4-bit/8-bit 独立量化副本与 `--model-id` 使用说明，明确 API 中旧 ONNX 的 `quantize` 参数不作用于 MOSS；原始权重继续为默认。

### 验证

- 本机 M1 Max 上的约 4 分半重复合成双人语音两轮对照：原始权重 13.4/14.7 秒，4-bit 18.4/19.4 秒，8-bit 21.6/20.3 秒；量化降低 MLX Metal 峰值，但未带来长样本提速。4-bit 时间戳与原始权重不完全一致；8-bit 在该合成样本输出一致。留存的真实通话短片段中，两种量化权重均多出短说话人标签，尚无人工真值可判断正确性。此前用户提供的三段完整录音本轮已不在原路径，因此完整真实录音的量化效果未验证。
- 约 55 秒合成双人语音的 `prefill_step_size=2048/4096/8192` 对照输出一致；预填充仅约 804 tokens，未发现足以调整默认值的收益。
- 同一约 4 分半合成语音缩短到 120 秒分段后，MOSS + CAM++ 完整路径两轮约 17.0/14.8 秒，未优于 600 秒默认单段，且转写文本不同；分段默认值未改。

## [1.11.0] - 2026-09-23

### 改进

- 将 Apple Silicon 上的 `moss-mlx` 设为服务/API、命令行及自动转录的默认模型；原 `paraformer`、`paraformer-onnx` 和 `server-onnx.py` 保留为显式选项，不在 MOSS 出错时静默回退。
- `setup.py` 默认安装 MLX-Audio 并准备 MOSS 与 CAM++ 模型；`--legacy` 保留旧 FunASR 安装。环境检测和启动预检不再要求默认 MOSS 用户预先下载 Paraformer/VAD 权重，缺少 Apple Silicon、MLX-Audio 或 ffmpeg 时给出明确提示。
- `FUNASR_MOSS_MODEL_ID` 可为默认路由指定本地模型目录；文档、示例和 API 说明同步为 MOSS 默认。
- 视频关键帧检测改由 OpenCV 完成，避免 PySceneDetect 与 MLX-Audio 的 Click 依赖冲突；批量转录指定新输出目录时自动创建目录，并在单项失败时正确返回整体失败。
- 环境配置更新为记录实际运行的虚拟环境 Python 与默认后端，避免旧 `skill-env.json` 继续调用未安装 MLX-Audio 的全局解释器。
- 默认 MOSS 服务启动时延迟加载 FunASR、ONNX 与 librosa，仅在旧模型或长录音 CAM++ 路径需要时导入，减少无关初始化。
- 默认完整安装约束 Python 3.10–3.12、FunASR 1.3.x、`funasr-onnx` 0.4.1 与 NumPy ≤1.26.4，以保持旧 ONNX 路线与新 MLX 后端的依赖可共存；建议原生 Python 3.11 虚拟环境。

### 验证

- 本机已缓存权重的 13 秒合成双人音频：省略 `model` 的 HTTP 请求返回 `moss-mlx`、2 段及 `S01/S02`；两个 CLI 省略 `--model` 均生成 Markdown；显式 `paraformer` 请求完成转写。批量 API 省略 `model` 且指定新输出目录，修复后完成转写并返回 `moss-mlx`。
- OpenCV 场景检测在合成三页视频上输出 0、4、8 秒三张关键帧；MOSS 适配器回归、默认安装系统预检及环境配置生成通过。真实长视频截图效果仍待样本验证。
- 在干净的 Apple Silicon Python 3.11 环境联合安装两组 requirements，`pip check` 无冲突；`setup.py --verify`、默认 MOSS 与显式原生 Paraformer、Paraformer-ONNX 的实际请求均通过。源码静态安全扫描无 high/critical，Harness 静态审查无 finding；这些检查不能代替人工标注的说话人准确率评估。

## [1.10.0] - 2026-09-23

### 新增

- 新增 Apple Silicon 的 `moss-mlx` 可选后端：一次生成文字、时间戳和匿名说话人；长录音按静音位置分段，并借 CAM++ 声纹链接跨段标签；Hugging Face 加载失败时自动回退 ModelScope。默认 FunASR 路由不变。
- 单文件 API 可返回 MOSS 结构化 `segments`、`speaker_scope` 和分阶段耗时；CLI/API 支持 MOSS 热词与本地模型目录。
- 增加独立的 `assets/requirements-moss-mlx.txt`，普通 FunASR 安装无需下载 MOSS。

### 改进

- 视频截图可用 `--no-slides` / `extract_slides=false` 显式关闭；`include_summary_prompt=false` 可跳过摘要提示词，自动转录客户端复用已返回的提示词，避免重复生成。
- 延长客户端长录音等待上限，增加模型加载、转录、说话人处理、截图、归档和摘要阶段计时。
- MOSS 输出缺失时间戳、说话人或达到生成上限时拒绝写稿；纯静音分段跳过推理，对近乎零能量音频中的模型幻觉句进行剔除并提示；总发言不足 3 秒的匿名说话人提示人工核对。

### 验证

- 合成约 13 秒双人中文对话：本机 M1 Max 上 MOSS 输出 S01/S02 两段，FunASR 原生路径转写成功但仅给出一位说话人。这是合成样本结果，不代表真实会议准确率。
- 合成约 605 秒双人录音：MOSS 分段 + CAM++ 后四段说话人顺序为 S01/S02/S01/S02；近乎静音处的一条多余模型输出被剔除。MOSS 真实模型、CAM++ 和 FastAPI HTTP 路径均已运行验证；真实会议、多说话人噪声环境和连续语音长录音的资源峰值仍待评估。
- 同一长样本在 M1 Max 上的 HTTP 请求约 17.8 秒，MLX Metal 报告峰值约 3.18 GiB、进程峰值 RSS 约 3.2 GiB（两者可能重叠，不能相加）；音频大部分为静音，不可外推到连续讲话的会议。
- 三段用户授权的真实双人通话（分别约 12 分 12 秒、6 分 05 秒、5 分 39 秒）同机对照：MOSS-MLX 首次进程用时约 55.6/50.7/44.9 秒，默认 FunASR 约 188.1/99.9/102.8 秒；共同有声时间内的说话人标签对应率约 97.2%/95.0%/90.1%。该对应率是两个模型互相一致，不是人工真值准确率。一段 MOSS 额外输出总计约 1.7 秒的第三说话人标签，触发复核提示；12 分钟录音跨段前后标签对应率分别约 97.1%/97.5%。逐字稿与原录音不纳入仓库。
- 上述三次 FunASR 进程 RSS 峰值约 3.85–4.24 GiB，MOSS 约 2.40–3.22 GiB；MOSS 另在一段复测中报告 Metal 峰值约 2.87 GiB。RSS 与 Metal 可能重叠，不能据此认定统一内存总占用更低；运行时间也只是各样本单次测量。

## [1.9.4] - 2026-04-19

### 修复

- **ONNX 导出依赖延迟加载** — 移除 `torch` 与 `funasr.utils.export_utils` 的模块级导入，仅在 ONNX 兼容导出时按需加载，避免非 ONNX 路径受 FunASR 内部导出模块变更影响
- **ONNX 导出猴子补丁显式失败** — 对 `funasr.utils.export_utils._onnx` 增加存在性检查；当 FunASR 内部 API 变化时直接报错，而不是静默回退到不兼容导出路径

### 改进

- **模型下载与兼容缓存提示** — 模型缺失时打印下载提示，ONNX 兼容导出缓存增加 `compat_export_version` 过期检查，并提示缓存目录可删除后重建
- **ONNX 后处理兼容说明** — 为 funasr-onnx VAD 兼容补丁、raw token 归一化和句子级时间戳近似映射补充注释与文档说明
- **中文标点切句增强** — `split_text_by_punctuation()` 增补顿号和冒号，减少长句合并

## [1.9.3] - 2026-04-19

### 改进

- **单人 Paraformer ONNX 全局标点恢复** — `paraformer-onnx` 关闭 diarization 时，先拼接 VAD 分段 ASR 文本，再统一做一次标点恢复，减少逐段标点带来的边界断裂
- **单人 ONNX 速度进一步提升** — 5 分钟讲课样本中，单人 ONNX 分段路径的服务常驻第二次耗时从约 `17.508s` 降至约 `11.751s`
- **单人 ONNX 文本格式更接近原生 Paraformer** — 同一样本中，原始文本相似度从约 `0.9607` 提升至约 `0.9733`，去除标点/空白后的相似度约 `0.9829`

### 技术优化

- **保留 VAD 默认阈值** — 对比 `max_end_sil=600/800/1000/1200` 及相邻段合并策略后，确认默认 `800ms` 在单人 5 分钟样本上质量最佳，暂不引入新的 VAD 合并参数

## [1.9.2] - 2026-04-19

### 修复

- **单人 Paraformer ONNX 整段推理质量差** — `paraformer-onnx` 在关闭 diarization 时不再直接整段调用 ONNX ASR，改为复用多人路径的 ONNX VAD 分段 ASR、文本清理、标点恢复和句子级时间戳映射

### 改进

- **单人 ONNX 稳态速度提升** — 5 分钟讲课样本中，旧单人 ONNX 整段推理耗时约 `37.489s`；改为 VAD 分段后，服务常驻同进程第二次耗时约 `17.508s`
- **单人 ONNX 质量恢复** — 同一样本中，旧整段 ONNX 相对原生 `paraformer` 的文本相似度约 `0.6079`；改为 VAD 分段后，去除标点/空白后的相似度约 `0.9829`
- **ONNX 路由一致性** — `paraformer-onnx` 单人和多人现在共享同一套 VAD 分段 ASR 后处理，多人路径仅额外执行 CAM++ 说话人聚类

## [1.9.1] - 2026-04-19

### 修复

- **ONNX 兼容导出失败** — 为 Python 3.14 / PyTorch 2.11 环境补充 FunASR ONNX 兼容导出层，强制使用 `dynamo=False` 与 opset 18，并将产物缓存到 `~/.cache/funasr-onnx-compat`
- **ONNX VAD `feats_len` 兼容问题** — 修复 `funasr_onnx` 当前版本将数组长度当作标量处理导致的 VAD 调用失败
- **auto_transcribe 自动启动服务失败** — 修复自动拉起服务后健康检查未传入 `api_url` 的问题，并按传入 API 地址设置 host/port

### 改进

- **多人 ONNX 文本质量优化** — `paraformer-onnx + diarize` 会清理 ONNX 文本输出，修复逐字空格问题，并补做标点恢复
- **ONNX 文本源调参** — 默认文本源从 `raw_tokens` 调整为清理后的 `preds`，并保留 `FUNASR_ONNX_TEXT_SOURCE=raw_tokens` 回退开关；90 秒样本相对原生 `paraformer` 的文本相似度从约 `0.9911` 提升到 `0.9974`
- **多人 ONNX 时间戳优化** — 按补完标点后的句子重新映射时间戳，避免整段 VAD 片段只输出一个粗时间点
- **中文输出拼接优化** — 合并同一说话人的句子时使用中文友好的拼接逻辑，减少无意义空格
- **fast 路由回归 Paraformer** — `fast` 仅关闭 diarization，不再自动切到 SenseVoice；`sensevoice` 保留为显式实验选项

### 验证

- 使用 18 分 07 秒多人微信通话样本验证：修复后的 `paraformer-onnx + diarize` 耗时约 `272.443s`，约 `3.99x realtime`
- 文本源调参后同一完整样本耗时约 `291.332s`，约 `3.73x realtime`
- 与此前同样本原生 `paraformer + diarize` 基线 `551.59s` 相比，最终默认配置仍保留约 `1.89x` 速度优势

## [1.9.0] - 2026-04-16

### 新增

- **SenseVoice-Small ONNX 单人快速模式** — `/transcribe`、`transcribe.py`、`auto_transcribe.py` 支持 `fast` 快速路径与 `sensevoice` / `sensevoice-onnx` 模型别名，用于单人讲课、语音笔记等不需要 diarization 的场景
- **ONNX 加速服务入口** — 新增 `scripts/server-onnx.py`，默认预设 `paraformer-onnx` 和 INT8 量化，便于直接启动快速服务
- **运行时解析字段** — `/transcribe` 响应新增 `resolved_model`、`resolved_runtime`、`warnings`，方便客户端确认最终路由结果
- **技能级协作文档** — 为 `funasr-transcribe` 新增 `TASKS.md` 与 `DECISIONS.md`，补齐 issue 驱动开发的上下文传递文档

### 改进

- **Paraformer ONNX 路由** — 服务端新增 `paraformer-onnx` 逻辑模型，支持通过 API / CLI 显式指定更快的 ONNX 路径
- **ONNX diarization 组合路径** — `paraformer-onnx + diarize` 采用 `ONNX VAD + ONNX Paraformer + CAM++ 聚类` 的组合实现，保留多人对话场景的说话人分离能力
- **依赖与环境检测同步** — `requirements.txt`、`setup.py`、`init_env.py`、`check_env.py` 增补 `funasr-onnx` 与 `server-onnx.py` 检测逻辑
- **技能文档更新** — `SKILL.md` 与 `references/api-reference.md` 补充 ONNX、`--model`、`--fast`、`server-onnx.py` 的使用说明

### 技术优化

- **服务端模型路由层** — `server.py` 新增逻辑模型映射、自动参数解析与按需预加载能力，统一处理 `torch` / `onnx` 运行时
- **按需下载 SenseVoice** — `assets/models.json` 增加可选 `SenseVoiceSmall` 条目，首次使用快速模式时自动拉取，不阻塞默认安装流程

## [1.8.0] - 2026-04-16

### 改进

- **视频文件自动启用关键帧提取** — 转录 mp4/mov/avi/mkv/wmv/webm 等视频文件时，自动启用 `extract_slides`，无需手动传入参数。显式传 `"extract_slides": false` 可禁用
- **slide 依赖升级为正式依赖** — `scenedetect[opencv]` 和 `imagehash` 不再标记为 optional，随 setup.py 一并安装

### 新增

- **文件级摘要注入 CLI** — `summary.py` 新增 `inject` 和 `verify` 子命令
  - `python3 summary.py inject <md_path> <summary_file>` — 从 JSON/文本文件读取总结并注入，自动解析 JSON 格式化
  - `python3 summary.py verify <md_path>` — 验证 Markdown 文件中是否存在 AI 摘要及章节完整性
  - `python3 summary.py prompt <md_path>` — 生成总结提示词
- **摘要验证端点** — server.py 新增 `POST /verify_summary` 端点，返回摘要存在状态、字符数、缺失章节
- **摘要验证函数** — summary.py 新增 `verify_summary_in_file()` 和 `inject_from_file()` 函数

### 修复

- **摘要注入失败问题** — Agent（MiniMax）在多步骤工具调用中不可靠，声称完成注入但实际未执行。改为文件注入方式（写 JSON 到临时文件 → 调用 Python 脚本注入），避免 curl JSON 转义问题
- **强制验证步骤** — 注入后必须运行 `summary.py verify` 验证，失败则重试，防止 Agent "声称完成但实际未执行"
- **agent-executor 环境下命令找不到** — headless 模式 PATH 被限制为只有插件目录，`curl`/`python3` 找不到。SKILL.md 所有 bash 命令前加 `export PATH=...` 确保系统命令可用

## [1.6.0] - 2026-04-11

### 新增

- **环境自动检测与配置** — 新增 `scripts/init_env.py` 脚本
  - 通过 login shell 获取完整 PATH，解决受限环境（如 Raycast Electron 沙箱）下命令不可用的问题
  - 自动检测 python3、curl、ffmpeg 等工具的实际路径
  - 检测 Python 版本和 funasr、torch 等关键依赖的安装状态
  - 生成 `skill-env.json` 供 agent-executor 读取并注入执行环境
  - 支持 `--check`（只检测不写文件）、`--force`（强制重新检测）参数

### 改进

- **setup.py 集成环境配置** — 安装和验证完成后自动调用 `init_env.py`
  - `python3 scripts/setup.py` 安装完成后自动生成 `skill-env.json`
  - `python3 scripts/setup.py --verify` 验证时刷新环境配置
- **SKILL.md Agent 工作流优化** — 新增步骤 0 环境检测
  - Agent 执行转录前自动检查 `skill-env.json` 是否存在
  - 不存在则先运行环境检测，确保依赖就绪

### 技术变更

- 新增 `scripts/init_env.py` 环境检测与配置生成脚本
- `scripts/setup.py` 安装/验证后自动调用 `init_env.py --force`

## [1.5.1] - 2026-04-09

### 改进

- **移除外部 API Key 依赖** — 简化 `--auto-summary` 实现
  - 不再依赖 `ANTHROPIC_API_KEY` 或 `OPENAI_API_KEY`
  - 直接利用 Claude Code 原生 AI 能力生成总结
  - 脚本输出结构化总结请求，Claude Code 自动处理

### 技术变更

- `summary.py` 移除 `_call_claude_api()` 和 `_call_openai_api()` 外部 API 调用
- `summary.py` 移除 `_is_claude_code_environment()` 检测函数
- `generate_summary_via_api()` 改为输出结构化总结请求
- `transcribe.py` 修复自动模式下的逻辑错误（成功时不再重复输出提示词）
- 移除 `anthropic` 和 `openai` 依赖

### 文档更新

- SKILL.md 更新 `--auto-summary` 说明，明确无需外部 API Key

## [1.5.0] - 2026-04-09

### 新增

- **自动 AI 总结生成** — 新增 `--auto-summary` 参数，转录后自动调用 LLM API 生成并注入总结
  - 支持 `ANTHROPIC_API_KEY`（Claude）或 `OPENAI_API_KEY` 自动调用
  - 无需手动复制提示词到 LLM，彻底自动化
  - 使用方式：`python scripts/transcribe.py audio.m4a --auto-summary`
- **summary.py 新增 `generate_summary_via_api()` 函数** — 直接调用 LLM API 生成总结并注入文件

### 依赖更新

- 新增 `anthropic>=0.18.0` — Claude API 支持
- 新增 `openai>=1.0.0` — OpenAI API 支持（备选）

## [1.4.1] - 2026-04-08

### 修复

- **修复说话人分离功能不可用** — 解决 `ClusterBackend` 导入失败的问题
  - 原因：numpy 2.x 与用旧版本编译的 pandas/sklearn 二进制不兼容
  - 修复：添加 `numpy>=1.20,<2`、`pandas>=1.3,<3`、`scikit-learn>=1.0,<2` 版本约束
  - `setup.py --verify` 现在会检测 sklearn 导入状态和 numpy 版本兼容性

### 改进

- **requirements.txt 依赖声明完善** — 明确声明说话人分离所需的间接依赖
  - 新增 `numpy>=1.20,<2` — 避免与 pandas/sklearn 的二进制兼容问题
  - 新增 `pandas>=1.3,<3` — FunASR CAM++ speaker model 的传递依赖
  - 新增 `scikit-learn>=1.0,<2` — 说话人分离核心依赖
- **setup.py 验证增强** — 验证安装时会检查：
  - scikit-learn 是否能正常导入
  - numpy 版本是否与依赖兼容

## [1.4.0] - 2026-04-05

### 改进

- **说话人分离默认启用** — `diarize` 参数默认值从 `false` 改为 `true`
  - 两方以上对话是常态，默认启用更符合实际使用场景
  - CLI 新增 `--no-diarize` 参数用于显式禁用
- **转录后自动附带总结提示词** — `/transcribe` 响应新增 `summary_prompt` 和 `text_preview` 字段
  - Agent 一次调用即可拿到转录结果 + 总结提示词，无需额外请求 `/summary`
  - 直接生成总结 JSON 后调用 `/inject_summary` 即可完成全流程
- **SKILL.md 新增默认工作流** — 平台无关的 Agent 工作流章节，任何 Agent 平台均可遵循
- **移除环境检测** — 删除 `detect_agent_environment()` 函数，总结由 Agent 自行完成，server 无需感知运行平台

### 清理

- 移除 `detect_agent_environment()` 环境检测函数，server 无需感知运行平台
- 移除 SKILL.md 中对特定平台的绑定描述（OpenClaw、Claude Code 等）
- 移除 Nano/E2E 模型死代码（`get_model_type()` 函数、`init_model()` 中的 E2E 分支、`--model` 参数）
- 移除 `models.json` 中不可用的 Nano 模型条目
- 移除 `--claude-code` 参数（功能已被 `/transcribe` 返回 `summary_prompt` 取代）
- 移除未使用的全局变量 `model`/`model_with_spk` 和 `inject_summary_to_file` 导入
- 修复 API 文档字符串中 `diarize` 默认值描述（false → true）
- 简化 `transcribe.py` 帮助文本，移除 Nano 模型示例

## [1.3.0] - 2026-04-05

### 新增

- **视频关键帧（PPT 幻灯片）自动提取** — 转录视频时可同时提取画面变化截图
  - 四层过滤流水线：场景检测+兜底采样 → pHash 去重 → 空白回查补帧 → 最终过滤
  - PySceneDetect 检测画面变化 + 每 3 分钟兜底采样防止空白
  - 5 分钟以上无变化区域自动回查补帧
  - 截图插入转录文本对应时间戳位置
  - 通过 `--slides` 参数启用
- **转录归档（Archive）机制** — 每次转录自动归档完整记录
  - 归档目录：`archive/YYYYMMDD_HHMMSS_文件名/`
  - 包含：Markdown 副本、截图副本（如有）、`transcription_meta.json` 元数据
  - API 响应新增 `archive_path` 字段

### 改进

- `result_to_markdown()` 支持在转录段落间插入截图引用
- `/transcribe` 端点新增 `extract_slides`、`slide_threshold` 参数
- `auto_transcribe.py` 新增 `--slides`、`--slide-threshold` 命令行参数
- `assets/requirements.txt` 新增 `scenedetect[opencv]`、`imagehash` 依赖

### 依赖

- `scenedetect[opencv]>=0.6.4` — 视频场景检测
- `imagehash>=4.3.1` — 感知哈希去重

## [1.2.0] - 2026-02-14

### 修复

- **时间戳分段输出** - 修复非说话人分离模式下转录结果为整段文本的问题
  - 之前：FunASR 返回 `timestamp` 字段而非 `sentence_info`，导致代码 fallback 到整段输出
  - 现在：正确处理 `timestamp` 字段，按句子（。！？）分割文本并分配时间戳
  - 新增 `split_text_by_sentences()` 函数，支持中文句子分割

### 技术变更

- `result_to_markdown()` 函数重构，新增 `timestamp` 字段处理分支
- 根据字符位置比例计算每个句子对应的时间戳索引
- 支持处理没有结束符的剩余文本段落

### 效果对比

- 修复前：1 个大段落，时间戳固定为 00:00
- 修复后：按句子分成 74 个段落，每个段落有对应的准确时间戳

## [1.1.1] - 2025-01-07

### 改进

- **代码精简** - summary.py 从 475 行精简到 285 行(-40%)
  - 移除所有外部 API 集成代码(OpenAI, SiliconFlow)
  - 移除环境变量加载和配置文件处理
  - 专注 Claude Code 环境原生能力

### 功能优化

- **默认启用总结** - 转录完成后自动显示总结提示词
- **简化参数** - 移除 `--summary`,新增 `--no-summary` 禁用选项
- **移除配置** - 删除 `config/summarization.env`(无需外部 API 配置)
- **优化交互** - 移除 input() 交互,直接输出提示词供 Claude 使用

### 技术变更

- summary.py 专注 Claude Code 环境功能
- transcribe.py 默认启用总结流程
- 清理所有外部 API 依赖代码

## [1.1.0] - 2025-01-07

### 新增

- **AI 智能总结功能** - 转录完成后可自动生成结构化会议纪要
- **Claude Code 环境原生支持** - 使用 Claude Code 内置 AI 能力生成总结,无需外部 API
- **结构化总结输出** - 包含全文总结、发言人总结、重点内容、关键词等模块
- **说话人视角识别** - 自动识别发言人顺序并保留对话上下文
- **总结注入功能** - 自动将生成的总结注入到 Markdown 文件的对应位置
- **交互式总结流程** - 转录完成后自动提示是否需要生成 AI 总结

### 技术实现

- **summary.py** - AI 总结工具模块
  - `summarize_file_for_claude()` - 为 Claude Code 环境准备总结提示词
  - `inject_summary_to_file()` - 将总结注入到 Markdown 文件
  - `get_transcription_text()` - 提取纯文本转录内容
  - `create_summary_prompt()` - 生成结构化总结提示词
  - `_extract_speaker_orders()` - 智能识别发言人顺序
  - `_build_summary_markdown()` - 构建 Markdown 格式总结
- **中文对话优化** - 专门针对中文口语化对话的提示词模板
- **JSON 结构化输出** - 支持解析和格式化 AI 生成的总结结果

### 总结内容

- **全文总结** - 400+ 字,包含背景、问题、关键事实
- **发言人总结** - 每个发言人的观点、态度和贡献
- **重点内容** - 6-10 条核心要点
- **关键词** - 5-8 个关键术语

### 使用改进

- 转录完成后自动提示是否生成总结
- 支持命令行参数 `--summary` 自动启用总结
- 交互式输入 AI 生成的总结结果
- 自动解析 JSON 或纯文本格式总结

### 依赖更新

- `openai` - AI 总结 API 支持（保留用于向后兼容）
- `httpx` - 异步 HTTP 客户端

## [1.0.0] - 2025-01-07

### 初始功能

- FunASR 语音转文字技能初始版本
- 支持多种音视频格式（mp4、mov、mp3、wav、m4a、flac、aac、opus、wma、caf）
- 自动生成带时间戳的 Markdown 转录结果
- 说话人分离（diarization）功能
- 单文件转录 API
- 批量目录转录 API
- 健康检查 API
- 一键安装脚本（自动检测系统环境）
- 自动下载和配置 ASR 模型

### 核心技术

- 基于 FunASR 和 ModelScope 的本地 ASR 服务
- FastAPI HTTP API 服务器（替代 Flask）
- Uvicorn ASGI 服务器
- VAD + ASR + Punctuation + Speaker Diarization 完整流程
- PyTorch 和 torchaudio 深度学习框架
- 自动模型缓存系统（~/.cache/modelscope/hub/models/）

### 智能特性

- **自动启动**：首次请求时自动加载模型
- **空闲关闭**：默认 10 分钟无活动后自动关闭以节约资源
- **可配置超时**：支持自定义空闲超时时间（--idle-timeout 参数）
- **后台监控**：独立的空闲监控线程
- **优雅关闭**：支持 SIGTERM/SIGINT 信号处理

### 文档

- 完整的 SKILL.md 使用指南
- 详细的 API 参考文档（references/api-reference.md）
- 交互式 Swagger UI 文档（/docs）
- 系统环境检测和故障排除指南
- 服务生命周期管理说明

### 服务架构

- RESTful API 设计
- Pydantic 数据模型验证
- HTTP 中件间自动活动时间跟踪
- 线程安全的模型管理
- 跨平台支持（Windows、macOS、Linux）
