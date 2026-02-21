#!/usr/bin/env python3
"""
repo-research 配置管理
统一管理所有配置项
"""

import os
from pathlib import Path

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

# 默认配置
DEFAULT_CONFIG = {
    "output_dir": "",  # 空字符串表示使用当前工作目录
    "report_format": "markdown",
    "auto_open_report": False,
    "clone_depth": 1,
}

# 配置文件路径
CONFIG_FILE = Path(__file__).parent.parent / "assets" / "config.yaml"
EXAMPLE_CONFIG_FILE = Path(__file__).parent.parent / "assets" / "config.yaml.example"


def load_config():
    """
    加载配置文件
    
    优先级：
    1. 环境变量
    2. 配置文件 (config.yaml)
    3. 默认值
    """
    config = DEFAULT_CONFIG.copy()
    
    # 1. 尝试加载配置文件
    if CONFIG_FILE.exists():
        try:
            if HAS_YAML:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    file_config = yaml.safe_load(f)
                    if file_config:
                        # 递归更新配置
                        def deep_update(base, update):
                            for key, value in update.items():
                                if isinstance(value, dict) and key in base and isinstance(base[key], dict):
                                    deep_update(base[key], value)
                                else:
                                    base[key] = value
                        deep_update(config, file_config)
        except Exception as e:
            print(f"⚠️  加载配置文件失败: {e}")
            print("   使用默认配置")
    
    # 2. 环境变量覆盖
    env_overrides = {
        'REPO_RESEARCH_OUTPUT_DIR': 'output_dir',
        'REPO_RESEARCH_FORMAT': 'report_format',
        'REPO_RESEARCH_AUTO_OPEN': 'auto_open_report',
        'REPO_RESEARCH_CLONE_DEPTH': 'clone_depth',
    }
    
    for env_var, key in env_overrides.items():
        value = os.environ.get(env_var)
        if value:
            # 类型转换
            if key in ['clone_depth']:
                value = int(value)
            elif key in ['auto_open_report']:
                value = value.lower() in ('true', '1', 'yes')
            
            config[key] = value
    
    return config


def get_output_dir():
    """
    获取输出目录
    
    优先级：
    1. 配置文件中的 output_dir
    2. 环境变量 REPO_RESEARCH_OUTPUT_DIR
    3. 当前工作目录
    """
    config = load_config()
    output_dir = config.get('output_dir', '')
    
    if output_dir and str(output_dir).strip():
        # 支持 ~ 展开和相对路径
        output_dir = Path(output_dir).expanduser()
        
        # 如果是相对路径，相对于 skill 目录
        if not output_dir.is_absolute():
            skill_dir = Path(__file__).parent.parent
            output_dir = skill_dir / output_dir
        
        return output_dir
    
    # 回退到当前工作目录
    return Path.cwd()


def get_report_format():
    """获取报告格式"""
    config = load_config()
    return config.get('report_format', 'markdown')


def should_auto_open():
    """是否自动打开报告"""
    config = load_config()
    return config.get('auto_open_report', False)


def get_clone_depth():
    """获取克隆深度"""
    config = load_config()
    return config.get('clone_depth', 1)


def get_research_dir(topic_slug: str) -> Path:
    """
    获取研究目录路径
    
    Args:
        topic_slug: 主题 slug（用于目录命名）
    
    Returns:
        完整的研究目录路径
    """
    from datetime import datetime
    
    base_dir = get_output_dir()
    date_prefix = datetime.now().strftime('%Y%m%d')
    
    return base_dir / 'research' / f'{date_prefix}-{topic_slug}'


def get_report_filename(topic_slug: str) -> str:
    """
    获取报告文件名
    
    Args:
        topic_slug: 主题 slug
    
    Returns:
        报告文件名，如：twitter-skills-investigation-report.md
    """
    return f'{topic_slug}-report.md'


def ensure_config_exists():
    """
    确保配置文件存在
    
    如果 config.yaml 不存在，提示用户复制 example 文件
    """
    if not CONFIG_FILE.exists() and EXAMPLE_CONFIG_FILE.exists():
        print("📝 配置文件不存在")
        print(f"   请复制 {EXAMPLE_CONFIG_FILE.name} 为 config.yaml 并修改配置")
        print(f"   路径: {CONFIG_FILE}")


# 导出便捷函数
__all__ = [
    'load_config',
    'get_output_dir',
    'get_report_format',
    'should_auto_open',
    'get_clone_depth',
    'get_research_dir',
    'ensure_config_exists',
]
