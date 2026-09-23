#!/usr/bin/env python3
# -*- encoding: utf-8 -*-
"""本地转录一键安装：Apple Silicon 默认 MOSS-MLX，--legacy 保留 FunASR。"""

import os
import sys
import json
import platform
import subprocess
import argparse
import shutil
from pathlib import Path


# 获取脚本所在目录和 skill 根目录
SCRIPT_DIR = Path(__file__).parent.absolute()
SKILL_DIR = SCRIPT_DIR.parent
REQUIREMENTS_FILE = SKILL_DIR / "assets" / "requirements.txt"
MOSS_REQUIREMENTS_FILE = SKILL_DIR / "assets" / "requirements-moss-mlx.txt"
MODELS_CONFIG = SKILL_DIR / "assets" / "models.json"
MOSS_MODELSCOPE_ID = "OpenMOSS/MOSS-Transcribe-Diarize"
# FunASR 1.3.x 的 `cam++` 别名实际映射到此模型；预下载必须与运行时一致。
CAMPP_MODELSCOPE_ID = "iic/speech_campplus_sv_zh-cn_16k-common"

# 最低系统要求
MIN_MEMORY_GB = 4  # 最低内存要求
MIN_DISK_GB = 5    # 最低磁盘空间要求（模型约 1.2GB + 依赖）
MIN_PYTHON_VERSION = (3, 10)


def print_step(msg: str):
    """打印步骤信息"""
    print(f"\n{'='*60}")
    print(f"  {msg}")
    print(f"{'='*60}\n")


def print_success(msg: str):
    print(f"✅ {msg}")


def print_error(msg: str):
    print(f"❌ {msg}")


def print_warning(msg: str):
    print(f"⚠️  {msg}")


def print_info(msg: str):
    print(f"ℹ️  {msg}")


def get_system_info():
    """获取系统信息"""
    info = {
        'os': platform.system(),
        'os_version': platform.version(),
        'machine': platform.machine(),
        'python_version': sys.version_info,
        'memory_gb': None,
        'disk_free_gb': None,
        'gpu': None,
    }

    # 获取内存信息
    try:
        if info['os'] == 'Darwin':  # macOS
            import subprocess
            result = subprocess.run(['sysctl', '-n', 'hw.memsize'], capture_output=True, text=True)
            info['memory_gb'] = int(result.stdout.strip()) / (1024**3)
        elif info['os'] == 'Windows':
            import ctypes
            kernel32 = ctypes.windll.kernel32
            c_ulong = ctypes.c_ulong
            class MEMORYSTATUS(ctypes.Structure):
                _fields_ = [
                    ('dwLength', c_ulong),
                    ('dwMemoryLoad', c_ulong),
                    ('dwTotalPhys', c_ulong),
                    ('dwAvailPhys', c_ulong),
                    ('dwTotalPageFile', c_ulong),
                    ('dwAvailPageFile', c_ulong),
                    ('dwTotalVirtual', c_ulong),
                    ('dwAvailVirtual', c_ulong),
                ]
            memstatus = MEMORYSTATUS()
            memstatus.dwLength = ctypes.sizeof(MEMORYSTATUS)
            kernel32.GlobalMemoryStatus(ctypes.byref(memstatus))
            info['memory_gb'] = memstatus.dwTotalPhys / (1024**3)
        else:  # Linux
            with open('/proc/meminfo', 'r') as f:
                for line in f:
                    if line.startswith('MemTotal:'):
                        info['memory_gb'] = int(line.split()[1]) / (1024**2)
                        break
    except:
        pass

    # 获取磁盘空间
    try:
        cache_dir = get_model_cache_dir().parent
        cache_dir.mkdir(parents=True, exist_ok=True)
        _, _, free = shutil.disk_usage(cache_dir)
        info['disk_free_gb'] = free / (1024**3)
    except:
        pass

    return info


def check_system_requirements(backend: str = "moss-mlx"):
    """检查系统环境是否满足要求"""
    print_step("检查系统环境")

    info = get_system_info()
    warnings = []
    errors = []

    # 操作系统
    os_name = info['os']
    if backend == "moss-mlx" and (os_name != 'Darwin' or info['machine'] != 'arm64'):
        errors.append("MOSS-MLX 默认安装需要 Apple Silicon macOS；旧 FunASR 管线请使用 --legacy")
    if os_name == 'Darwin':
        print_success(f"操作系统: macOS ({info['os_version']})")
        print_info(f"架构: {info['machine']}")
        if info['machine'] == 'arm64':
            print_info("Apple Silicon 检测到，将使用 MPS 加速")
    elif os_name == 'Windows':
        print_success(f"操作系统: Windows ({info['os_version']})")
        print_info(f"架构: {info['machine']}")
    elif os_name == 'Linux':
        print_success(f"操作系统: Linux ({info['os_version']})")
    else:
        warnings.append(f"未测试的操作系统: {os_name}")

    # Python 版本
    py_version = info['python_version']
    print(f"Python 版本: {py_version.major}.{py_version.minor}.{py_version.micro}")
    min_python = MIN_PYTHON_VERSION
    if py_version < min_python:
        errors.append(f"需要 Python {min_python[0]}.{min_python[1]} 或更高版本")
    elif py_version >= (3, 13):
        errors.append("完整安装保留 funasr-onnx 0.4.1，需 Python 3.10–3.12（建议原生 3.11 虚拟环境）")
    else:
        print_success("Python 版本符合要求")

    # 内存检查
    if info['memory_gb']:
        print(f"系统内存: {info['memory_gb']:.1f} GB")
        if info['memory_gb'] < MIN_MEMORY_GB:
            errors.append(f"内存不足，需要至少 {MIN_MEMORY_GB} GB（当前 {info['memory_gb']:.1f} GB）")
        elif info['memory_gb'] < 8:
            warnings.append(f"内存较低（{info['memory_gb']:.1f} GB），大文件转录可能较慢")
            print_warning(f"建议 8GB 以上内存以获得更好性能")
        else:
            print_success("内存充足")
    else:
        warnings.append("无法检测内存大小")

    # 磁盘空间检查
    if info['disk_free_gb']:
        print(f"可用磁盘空间: {info['disk_free_gb']:.1f} GB")
        if info['disk_free_gb'] < MIN_DISK_GB:
            errors.append(f"磁盘空间不足，需要至少 {MIN_DISK_GB} GB（当前 {info['disk_free_gb']:.1f} GB）")
        else:
            print_success("磁盘空间充足")
    else:
        warnings.append("无法检测磁盘空间")

    # GPU 检测（预检测，不需要 PyTorch）
    gpu_info = detect_gpu_without_torch()
    if gpu_info:
        print_info(f"检测到 GPU: {gpu_info}")
    else:
        print_info("未检测到 GPU，将使用 CPU 推理（速度较慢）")

    # 输出警告
    if warnings:
        print("\n注意事项:")
        for w in warnings:
            print_warning(w)

    # 输出错误
    if errors:
        print("\n发现以下问题:")
        for e in errors:
            print_error(e)
        return False

    print_success("\n系统环境检查通过")
    return True


def detect_gpu_without_torch():
    """在不依赖 PyTorch 的情况下检测 GPU"""
    system = platform.system()

    try:
        if system == 'Darwin':
            # macOS: 检查是否有 Apple Silicon
            if platform.machine() == 'arm64':
                return "Apple Silicon (MPS)"
            return None

        elif system == 'Windows':
            # Windows: 尝试使用 nvidia-smi
            result = subprocess.run(
                ['nvidia-smi', '--query-gpu=name', '--format=csv,noheader'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip().split('\n')[0]
            return None

        elif system == 'Linux':
            # Linux: 尝试使用 nvidia-smi
            result = subprocess.run(
                ['nvidia-smi', '--query-gpu=name', '--format=csv,noheader'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip().split('\n')[0]
            return None

    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        pass

    return None


def check_python_version():
    """检查 Python 版本"""
    version = sys.version_info
    if version < MIN_PYTHON_VERSION:
        print_error(f"需要 Python {MIN_PYTHON_VERSION[0]}.{MIN_PYTHON_VERSION[1]} 或更高版本")
        return False
    return True


def is_externally_managed_env():
    """检测是否为外部管理的 Python 环境（如 Homebrew）"""
    try:
        import sysconfig
        stdlib_path = Path(sysconfig.get_path('stdlib'))
        if (stdlib_path / 'EXTERNALLY-MANAGED').exists():
            return True
        # 尝试 dry-run 检测
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--dry-run", "pip"],
            capture_output=True, text=True, timeout=10
        )
        return "externally-managed-environment" in result.stderr
    except:
        return False


def install_dependencies(backend: str = "moss-mlx"):
    """安装 pip 依赖"""
    print_step("安装依赖包")

    if not REQUIREMENTS_FILE.exists():
        print_error(f"找不到 requirements.txt: {REQUIREMENTS_FILE}")
        return False
    if backend == "moss-mlx" and not MOSS_REQUIREMENTS_FILE.exists():
        print_error(f"找不到 MOSS 依赖文件: {MOSS_REQUIREMENTS_FILE}")
        return False

    print(f"从 {REQUIREMENTS_FILE} 安装依赖...")
    print_info("这可能需要几分钟，请耐心等待...")

    # 构建安装命令
    cmd = [sys.executable, "-m", "pip", "install", "-r", str(REQUIREMENTS_FILE)]
    if backend == "moss-mlx":
        cmd.extend(["-r", str(MOSS_REQUIREMENTS_FILE)])

    # 检测是否为外部管理环境（如 Homebrew Python）
    if is_externally_managed_env():
        print_info("检测到外部管理的 Python 环境（如 Homebrew）")
        print_info("使用 --break-system-packages 标志安装")
        cmd.append("--break-system-packages")

    try:
        subprocess.check_call(cmd)
        print_success("依赖安装完成")
        return True
    except subprocess.CalledProcessError as e:
        print_error(f"依赖安装失败: {e}")
        return False


def load_models_config():
    """加载模型配置"""
    if not MODELS_CONFIG.exists():
        print_error(f"找不到模型配置文件: {MODELS_CONFIG}")
        return None

    with open(MODELS_CONFIG, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_model_cache_dir():
    """获取 ModelScope 模型缓存目录"""
    cache_dir = os.environ.get('MODELSCOPE_CACHE', os.path.expanduser('~/.cache/modelscope/hub'))
    return Path(cache_dir) / "models"


def check_model_exists(model_id: str) -> bool:
    """检查模型是否已下载"""
    cache_dir = get_model_cache_dir()
    model_path = cache_dir / model_id.replace('/', os.sep)
    return model_path.exists() and any(model_path.iterdir())


def download_models(backend: str = "moss-mlx"):
    """下载所有需要的模型"""
    print_step("下载 ASR 模型")

    if backend == "moss-mlx":
        try:
            from modelscope.hub.snapshot_download import snapshot_download
        except ImportError:
            print_error("MOSS 模型下载需要 modelscope；请先安装依赖")
            return False
        local_model = os.environ.get("FUNASR_MOSS_MODEL_ID")
        model_ids = (CAMPP_MODELSCOPE_ID,) if local_model and Path(local_model).exists() else (MOSS_MODELSCOPE_ID, CAMPP_MODELSCOPE_ID)
        for model_id in model_ids:
            if check_model_exists(model_id):
                print_success(f"已缓存模型: {model_id}")
                continue
            try:
                print_info(f"下载模型: {model_id}")
                snapshot_download(model_id)
            except Exception as exc:
                print_error(f"模型下载失败 {model_id}: {exc}")
                return False
        return True

    config = load_models_config()
    if not config:
        return False

    models = config.get('models', [])
    if not models:
        print_info("没有需要下载的模型")
        return True

    # 检查 modelscope 是否可用
    try:
        from modelscope.hub.snapshot_download import snapshot_download
    except ImportError:
        print_error("modelscope 未安装，请先运行依赖安装")
        return False

    cache_dir = get_model_cache_dir()
    print(f"模型缓存目录: {cache_dir}")

    success_count = 0
    total_count = len([m for m in models if m.get('required', True)])

    for model in models:
        model_id = model['id']
        model_name = model.get('name', model_id)
        required = model.get('required', True)

        if not required:
            continue

        print(f"\n[{success_count + 1}/{total_count}] 处理: {model_name}")
        print(f"    模型 ID: {model_id}")

        # 检查是否已存在
        if check_model_exists(model_id):
            print_success(f"已存在，跳过下载")
            success_count += 1
            continue

        # 下载模型
        print(f"    正在下载...")
        try:
            snapshot_download(model_id)
            print_success(f"下载完成")
            success_count += 1
        except Exception as e:
            print_error(f"下载失败: {e}")
            if required:
                return False

    print(f"\n模型下载完成: {success_count}/{total_count}")
    return success_count == total_count


def verify_installation(backend: str = "moss-mlx"):
    """验证安装结果"""
    print_step("验证安装")

    errors = []

    # 检查依赖
    try:
        import fastapi
        print_success(f"FastAPI {fastapi.__version__}")
    except ImportError:
        errors.append("FastAPI 未安装")

    try:
        import uvicorn
        print_success(f"Uvicorn {uvicorn.__version__}")
    except ImportError:
        errors.append("Uvicorn 未安装")

    if backend == "moss-mlx":
        import importlib.util
        if platform.system() != "Darwin" or platform.machine() != "arm64":
            errors.append("MOSS-MLX 需要 Apple Silicon macOS；旧管线可使用 --legacy")
        if sys.version_info < (3, 10):
            errors.append("MOSS-MLX 需要 Python 3.10+")
        if importlib.util.find_spec("mlx_audio") is None:
            errors.append("mlx-audio[stt] 未安装")
        else:
            print_success("mlx-audio 已安装")
        if shutil.which("ffmpeg") is None:
            errors.append("ffmpeg 未安装（macOS: brew install ffmpeg）")
        if not (os.environ.get("FUNASR_MOSS_MODEL_ID") and Path(os.environ["FUNASR_MOSS_MODEL_ID"]).exists()) \
                and not check_model_exists(MOSS_MODELSCOPE_ID):
            print_warning("未检测到 ModelScope 本地 MOSS 权重；若 Hugging Face 缓存也不存在，首次转录会下载")
        if not check_model_exists(CAMPP_MODELSCOPE_ID):
            print_warning("CAM++ 未缓存；超过约 10 分钟的录音首次使用时需下载")

    try:
        import funasr
        print_success(f"FunASR 已安装")
    except ImportError:
        errors.append("FunASR 未安装")

    try:
        import funasr_onnx
        print_success(f"funasr-onnx {getattr(funasr_onnx, '__version__', '已安装')}")
    except ImportError:
        errors.append("funasr-onnx 未安装，ONNX 加速功能不可用")

    try:
        import torch
        print_success(f"PyTorch {torch.__version__}")

        # 检查设备
        if torch.cuda.is_available():
            print_success(f"CUDA 可用: {torch.cuda.get_device_name(0)}")
        elif hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            print_success("Apple MPS 可用")
        else:
            print_info("将使用 CPU 推理")
    except ImportError:
        errors.append("PyTorch 未安装")

    # 检查说话人分离依赖（scikit-learn）
    try:
        import sklearn
        print_success(f"scikit-learn {sklearn.__version__} (说话人分离需要)")
    except ImportError:
        errors.append("scikit-learn 未安装，说话人分离功能将不可用")
    except Exception as e:
        errors.append(f"scikit-learn 导入失败: {e}，说话人分离功能将不可用")

    # 检查 numpy 版本（避免不兼容问题）
    try:
        import numpy
        print_success(f"numpy {numpy.__version__}")
        if numpy.__version__.startswith('2.') and sys.version_info < (3, 13):
            print_warning("检测到 numpy 2.x；如旧 FunASR 扩展出现二进制兼容问题，可在 Python 3.12 环境尝试 numpy<2")
    except ImportError:
        errors.append("numpy 未安装")

    # 检查模型
    config = load_models_config()
    if config and backend != "moss-mlx":
        models = config.get('models', [])
        for model in models:
            if model.get('required', True):
                if check_model_exists(model['id']):
                    print_success(f"模型: {model.get('name', model['id'])}")
                else:
                    errors.append(f"模型未下载: {model['id']}")

    if errors:
        print("\n发现以下问题:")
        for err in errors:
            print_error(err)
        return False

    print_success("\n安装验证通过!")
    return True


def main():
    parser = argparse.ArgumentParser(
        description='本地语音转文字一键安装（默认 Apple Silicon MOSS-MLX；--legacy 安装旧 FunASR）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python setup.py              # 完整安装（环境检查 + 依赖 + 模型）
  python setup.py --skip-deps  # 只下载模型
  python setup.py --skip-models # 只安装依赖
  python setup.py --verify     # 只验证安装
  python setup.py --check      # 只检查系统环境
  python setup.py --legacy     # 安装原 FunASR 管线（含 Paraformer / ONNX）
"""
    )
    parser.add_argument('--skip-deps', action='store_true', help='跳过依赖安装')
    parser.add_argument('--skip-models', action='store_true', help='跳过模型下载')
    parser.add_argument('--verify', action='store_true', help='只验证安装，不安装任何内容')
    parser.add_argument('--check', action='store_true', help='只检查系统环境')
    parser.add_argument('--legacy', action='store_true', help='安装/验证原 FunASR 管线；默认安装 MOSS-MLX')

    args = parser.parse_args()
    backend = "paraformer" if args.legacy else "moss-mlx"
    setup_env = os.environ.copy()
    setup_env["FUNASR_SERVER_DEFAULT_MODEL"] = backend

    print("\n" + "="*60)
    print(f"  本地语音转文字 - 一键安装（{backend}）")
    print("  MOSS 默认仅支持 Apple Silicon；--legacy 可安装旧管线")
    print("="*60)

    # 只验证安装
    if args.verify:
        success = verify_installation(backend)
        if success:
            print_info("正在刷新环境配置 skill-env.json ...")
            subprocess.run(
                [sys.executable, str(SCRIPT_DIR / "init_env.py"), "--force"],
                check=False,
                env=setup_env,
            )
        sys.exit(0 if success else 1)

    # 只检查环境
    if args.check:
        success = check_system_requirements(backend)
        sys.exit(0 if success else 1)

    # 检查系统环境
    if not check_system_requirements(backend):
        print_error("\n系统环境不满足要求，请解决上述问题后重试")
        sys.exit(1)

    # 安装依赖
    if not args.skip_deps:
        if not install_dependencies(backend):
            sys.exit(1)
    else:
        print_info("跳过依赖安装")

    # 下载模型
    if not args.skip_models:
        if not download_models(backend):
            sys.exit(1)
    else:
        print_info("跳过模型下载")

    # 验证
    if not verify_installation(backend):
        print_error("\n安装可能不完整，请检查上述错误")
        sys.exit(1)

    print_step("安装完成!")
    print("现在可以启动服务:")
    print(f"  python {SCRIPT_DIR / 'server.py'}")
    print()

    # 生成环境配置
    print_info("正在生成环境配置 skill-env.json ...")
    try:
        subprocess.run(
            [sys.executable, str(SCRIPT_DIR / "init_env.py"), "--force"],
            check=False,
            env=setup_env,
        )
    except Exception:
        print_warning("生成 skill-env.json 失败，不影响正常使用")


if __name__ == '__main__':
    main()
