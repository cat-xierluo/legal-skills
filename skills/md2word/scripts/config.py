#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
md2word 配置管理模块
支持 YAML 格式的配置文件加载和预设管理
"""

import os
import yaml
from typing import Dict, Any, Optional, TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from typing import Callable


class Config:
    """配置数据结构"""

    def __init__(self, config_dict: Dict[str, Any]):
        """初始化配置"""
        self._config = config_dict

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值，支持点分隔的路径（如 'page.width'）"""
        keys = key.split('.')
        value = self._config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
                if value is None:
                    return default
            else:
                return default
        return value if value is not None else default

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return self._config.copy()

    @property
    def name(self) -> str:
        """配置名称"""
        return self.get('name', '未命名配置')

    @property
    def description(self) -> str:
        """配置描述"""
        return self.get('description', '')


# ============================================================================
# 全局配置管理
# ============================================================================

_current_config: Config = None


def get_config() -> Config:
    """获取当前配置"""
    global _current_config
    if _current_config is None:
        _current_config = get_default_preset()
    return _current_config


def set_config(config: Config):
    """设置当前配置"""
    global _current_config
    _current_config = config


def load_config(path: str) -> Optional[Config]:
    """
    从 YAML 文件加载配置

    Args:
        path: 配置文件路径

    Returns:
        Config 对象，加载失败返回 None
    """
    if not os.path.exists(path):
        print(f"⚠️  配置文件不存在: {path}")
        return None

    try:
        with open(path, 'r', encoding='utf-8') as f:
            config_dict = yaml.safe_load(f)
        return Config(config_dict)
    except Exception as e:
        print(f"⚠️  加载配置文件失败: {e}")
        return None


def get_preset(name: str) -> Optional[Config]:
    """
    获取内置预设配置

    Args:
        name: 预设名称（legal, academic, report, simple）

    Returns:
        Config 对象，预设不存在返回 None
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    skill_dir = os.path.dirname(script_dir)  # 上级目录是 skill 根目录
    preset_path = os.path.join(skill_dir, 'assets', 'presets', f'{name}.yaml')

    if not os.path.exists(preset_path):
        print(f"⚠️  预设不存在: {name}")
        return None

    return load_config(preset_path)


def get_default_preset() -> Config:
    """
    获取默认预设（legal）

    Returns:
        Config 对象
    """
    config = get_preset('legal')
    if config is None:
        # 如果 legal 预设不存在，返回硬编码的默认配置
        return get_fallback_config()
    return config


def get_fallback_config() -> Config:
    """
    获取硬编码的默认配置（兜底方案）

    Returns:
        Config 对象
    """
    return Config({
        'name': '默认配置',
        'description': '硬编码的默认法律文书格式',
        'page': {
            'width': 21.0,
            'height': 29.7,
            'margin_top': 2.54,
            'margin_bottom': 2.54,
            'margin_left': 3.18,
            'margin_right': 3.18,
        },
        'fonts': {
            'default': {
                'name': '仿宋_GB2312',
                'ascii': 'Times New Roman',
                'size': 12,
                'color': '#000000',
            }
        },
        'titles': {
            'level1': {
                'size': 15,
                'bold': True,
                'align': 'center',
                'space_before': 6,
                'space_after': 6,
                'indent': 0,
            },
            'level2': {
                'size': 12,
                'bold': True,
                'align': 'justify',
                'indent': 24,
            },
            'level3': {
                'size': 12,
                'bold': False,
                'align': 'justify',
                'indent': 24,
            },
            'level4': {
                'size': 12,
                'bold': False,
                'align': 'justify',
                'indent': 24,
            },
        },
        'paragraph': {
            'line_spacing': 1.5,
            'first_line_indent': 24,
            'align': 'justify',
        },
        'page_number': {
            'enabled': True,
            'format': '1/x',
            'font': 'Times New Roman',
            'size': 10.5,
            'position': 'center',
        },
        'quotes': {
            'convert_to_chinese': True,
        },
        'table': {
            'border_enabled': True,
            'border_color': '#000000',
            'border_width': 4,
            'line_spacing': 1.2,
        },
    })


def merge_configs(base: Config, override: Optional[Config]) -> Config:
    """
    合并两个配置，override 中的值会覆盖 base 中的值

    Args:
        base: 基础配置
        override: 覆盖配置（可选）

    Returns:
        合并后的 Config 对象
    """
    if override is None:
        return base

    def deep_merge(base_dict: Dict, override_dict: Dict) -> Dict:
        """深度合并字典"""
        result = base_dict.copy()
        for key, value in override_dict.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    merged = deep_merge(base.to_dict(), override.to_dict())
    return Config(merged)


def list_presets() -> list:
    """
    列出所有可用的预设

    Returns:
        预设名称列表
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    skill_dir = os.path.dirname(script_dir)  # 上级目录是 skill 根目录
    presets_dir = os.path.join(skill_dir, 'assets', 'presets')

    if not os.path.exists(presets_dir):
        return []

    presets = []
    for file in os.listdir(presets_dir):
        if file.endswith('.yaml'):
            presets.append(file[:-5])  # 移除 .yaml 后缀

    return sorted(presets)
