# 本地 ASR 后端与模型安装

`local-asr` 在 Apple Silicon 上默认运行 `moss-mlx`；`paraformer` 和 `paraformer-onnx` 是保留的 FunASR 后端。先选后端，再使用同一个 Python 3.10–3.12 环境安装依赖、下载权重、启动服务；当前完整安装因旧 ONNX 依赖限制该 Python 范围。这里的说话人编号是单份录音内的匿名标签，不是实名识别。

| 后端 | 适用设备 | 转写与时间戳 | 说话人模型 | 如何选择 |
|---|---|---|---|---|
| `moss-mlx`（默认） | Apple Silicon macOS | MOSS-Transcribe-Diarize | 短录音由 MOSS 同时生成标签；超过单段约 600 秒时用 CAM++ 链接跨段标签 | 省略 `--model` |
| `paraformer` | 支持 PyTorch 的设备 | Paraformer、FSMN-VAD、标点模型 | 开启 diarization 时用 CAM++ | `--model paraformer` |
| `paraformer-onnx` | 可运行 ONNX Runtime 的设备 | Paraformer ONNX、VAD、标点后处理 | 开启 diarization 时用 CAM++ | `--model paraformer-onnx` |

## Apple Silicon：安装默认 MOSS-MLX

在技能目录运行；完整双后端安装使用 Python 3.10–3.12，建议原生 3.11。先安装 `ffmpeg`，并让服务和安装脚本使用同一个虚拟环境：

```bash
brew install python@3.11 ffmpeg
/opt/homebrew/bin/python3.11 -m venv venv
source venv/bin/activate
python3 scripts/setup.py
python3 scripts/setup.py --verify
```

`setup.py` 同时安装 [`assets/requirements.txt`](../assets/requirements.txt) 和 [`assets/requirements-moss-mlx.txt`](../assets/requirements-moss-mlx.txt)，并从 ModelScope 下载 `OpenMOSS/MOSS-Transcribe-Diarize` 与 CAM++ 权重。运行时默认逻辑模型 ID 为 Hugging Face 的 `OpenMOSS-Team/MOSS-Transcribe-Diarize`；适配器优先使用已存在的 ModelScope 本地缓存，未命中时尝试 Hugging Face，再回退 ModelScope。首次下载需要联网，音频转录本身在本机完成。

一个终端启动服务，另一个终端转录：

```bash
python3 scripts/server.py
python3 scripts/transcribe.py /path/to/meeting.m4a
```

`scripts/transcribe.py` 只调用已运行的 `127.0.0.1:8765` 服务；`scripts/auto_transcribe.py /path/to/meeting.m4a` 会在服务未运行时尝试启动它。默认服务首次转录才把模型加载到内存，空闲约 10 分钟后退出。长录音的 CAM++ 在首次需要跨段链接时加载。

若已有本地 MOSS 权重，可在启动服务前设置 `FUNASR_MOSS_MODEL_ID=/path/to/model`，或单次转录使用 `--model-id /path/to/model`。`setup.py` 检测到该本地目录后仍会准备 CAM++。若只安装依赖而暂不下载权重，可用 `python3 scripts/setup.py --skip-models`；首次转录可能联网下载，不能把它当作离线安装。内存受限时的显式量化方法见 [`SKILL.md` 的“MOSS 性能与可选量化”](../SKILL.md#MOSS-性能与可选量化)，量化不保证提速或说话人标签不变。

## 保留的 FunASR：安装与启用

仅使用原 FunASR 管线时，在已激活的虚拟环境运行：

```bash
python3 scripts/setup.py --legacy
FUNASR_SERVER_DEFAULT_MODEL=paraformer python3 scripts/server.py
python3 scripts/transcribe.py /path/to/meeting.m4a --model paraformer
```

`--legacy` 安装基础依赖并下载 Paraformer、FSMN-VAD、标点模型及实际由 FunASR `cam++` 别名加载的 CAM++ 权重；不下载 MOSS。需要 ONNX 路线时，把最后一条命令改为 `--model paraformer-onnx`，首次使用可能生成 ONNX 兼容缓存。若同一环境已完成默认双后端安装且 MOSS 服务可用，直接在现有服务请求中显式选择 `--model paraformer` 或 `--model paraformer-onnx`，无需另起一个服务。非 Apple Silicon 的旧管线服务要在启动前设置 `FUNASR_SERVER_DEFAULT_MODEL=paraformer`；CLI 仍需显式传旧模型，不能只改服务环境变量。

非 Apple Silicon 用户可用本机 Python 3.10–3.12 创建虚拟环境（例如 `python3.11 -m venv venv`）；macOS/Linux 使用 `source venv/bin/activate`，Windows PowerShell 使用 `.\venv\Scripts\Activate.ps1`，再执行上面的 `--legacy` 安装。Windows PowerShell 启动旧服务时先运行 `$env:FUNASR_SERVER_DEFAULT_MODEL="paraformer"`，再运行 `python scripts/server.py`。不同设备的 PyTorch/ONNX 加速需在本机验证。

| 用途 | ModelScope 模型 ID | 下载时机 |
|---|---|---|
| MOSS 默认转写 | `OpenMOSS/MOSS-Transcribe-Diarize` | 默认 `setup.py` |
| Paraformer 转写 | `iic/speech_paraformer-large-vad-punc_asr_nat-zh-cn-16k-common-vocab8404-pytorch` | `setup.py --legacy` |
| VAD 分段 | `iic/speech_fsmn_vad_zh-cn-16k-common-pytorch` | `setup.py --legacy` |
| 标点恢复 | `iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch` | `setup.py --legacy` |
| CAM++ 声纹 | `iic/speech_campplus_sv_zh-cn_16k-common` | 默认安装和 `--legacy`；MOSS 长录音或 FunASR 说话人分离时加载 |

模型默认缓存于 `~/.cache/modelscope/hub/models/`；若设置 `MODELSCOPE_CACHE`，以该缓存根目录为准。`python3 scripts/setup.py --verify` 检查依赖与权重缓存；它不替代一次真实音频转录。仅检查当前环境和目录时可运行 `python3 scripts/check_env.py`。服务错误、接口参数和响应格式见 [`api-reference.md`](api-reference.md)。
