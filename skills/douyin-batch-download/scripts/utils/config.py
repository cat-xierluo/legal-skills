#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一配置加载模块

提供配置文件加载、路径解析等功能，支持：
- 自定义下载路径（留空则使用系统 Downloads 目录）
- 自动创建目录
- 路径规范化
"""

import os
import re
import yaml
from pathlib import Path
from typing import Optional, Dict, Any

# 技能目录
SKILL_DIR = Path(__file__).parent.parent.parent.resolve()
CONFIG_PATH = SKILL_DIR / "config" / "config.yaml"

# 运行时显式覆盖(DY-001):由 CLI --root/--db 设置,优先于配置文件与默认值。
# 只影响当前进程;子进程通过显式 CLI 参数继承,不依赖环境变量。
_OVERRIDE: Dict[str, Optional[str]] = {"download_root": None, "db_path": None, "following_path": None}


def set_overrides(download_root: Optional[str] = None, db_path: Optional[str] = None,
                  following_path: Optional[str] = None) -> None:
    """设置运行时路径覆盖(None 表示该项不变;传入空字符串按清除处理)"""
    if download_root is not None:
        _OVERRIDE["download_root"] = str(download_root) if download_root else None
    if db_path is not None:
        _OVERRIDE["db_path"] = str(db_path) if db_path else None
    if following_path is not None:
        _OVERRIDE["following_path"] = str(following_path) if following_path else None
    Paths.reset()


def get_active_overrides() -> Dict[str, Optional[str]]:
    """读取当前生效的覆盖(供调用方判断是否处于自定义 root/db 模式)"""
    return dict(_OVERRIDE)


def get_default_download_path() -> Path:
    """获取默认下载路径（系统 Downloads 目录下的抖音视频下载子目录）"""
    # 获取系统 Downloads 目录
    downloads = Path.home() / "Downloads"

    # 如果是 macOS，使用中文子目录名
    subfolder = "抖音视频下载"

    return downloads / subfolder


def sanitize_folder_name(name: str) -> str:
    """
    清理文件夹名称，移除不允许的字符

    Args:
        name: 原始名称（如博主昵称）

    Returns:
        清理后的安全文件夹名称
    """
    if not name:
        return "unknown"

    # 移除不允许的字符（保留中文、字母、数字、下划线、短横线、空格）
    # Windows 不允许: < > : " / \ | ? *
    # 同时移除前后空格
    name = name.strip()

    # 替换不允许的字符为下划线
    name = re.sub(r'[<>:"/\\|?*]', '_', name)

    # 移除连续的空格和下划线
    name = re.sub(r'[\s_]+', '_', name)

    # 移除首尾的下划线
    name = name.strip('_')

    # 如果清理后为空，使用 unknown
    if not name:
        return "unknown"

    # 限制长度（避免路径过长）
    if len(name) > 100:
        name = name[:100]

    return name


def load_config() -> Dict[str, Any]:
    """加载配置文件"""
    if not CONFIG_PATH.exists():
        return {}

    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def get_download_path() -> Path:
    """
    获取下载路径

    优先级：
    1. 配置文件中的 download_path
    2. 系统 Downloads 目录下的抖音视频下载子目录

    Returns:
        下载路径（绝对路径）
    """
    config = load_config()

    # 运行时显式覆盖优先(DY-001)
    if _OVERRIDE["download_root"]:
        path = Path(_OVERRIDE["download_root"]).expanduser()
    else:
        # 从配置中读取
        custom_path = config.get("download_path", "")
        if custom_path:
            # 展开用户目录 (~)
            path = Path(custom_path).expanduser()
            # 如果是相对路径，相对于技能目录
            if not path.is_absolute():
                path = SKILL_DIR / path
        else:
            # 使用默认路径
            path = get_default_download_path()

    # 确保目录存在
    path.mkdir(parents=True, exist_ok=True)

    return path.resolve()


def get_user_folder_name(nickname: str, uid: str) -> str:
    """
    获取用户文件夹名称

    使用博主昵称作为文件夹名，如果昵称为空则使用 UID

    Args:
        nickname: 博主昵称
        uid: 博主 UID

    Returns:
        安全的文件夹名称
    """
    if nickname:
        return sanitize_folder_name(nickname)
    return str(uid)


def get_user_download_path(nickname: str = "", uid: str = "") -> Path:
    """
    获取用户下载路径

    Args:
        nickname: 博主昵称
        uid: 博主 UID

    Returns:
        用户下载路径
    """
    base_path = get_download_path()

    if nickname or uid:
        folder_name = get_user_folder_name(nickname, uid)
        return base_path / folder_name

    return base_path


def get_data_output_path() -> Path:
    """
    获取数据输出路径（data.js 和 index.html 所在目录）

    Returns:
        数据输出路径
    """
    return get_download_path()


def get_db_path() -> Path:
    """
    获取数据库路径

    优先级：运行时显式覆盖(DY-001 --db) > 技能目录默认

    Returns:
        数据库路径（绝对路径）
    """
    if _OVERRIDE["db_path"]:
        return Path(_OVERRIDE["db_path"]).expanduser().resolve()
    return SKILL_DIR / "douyin_users.db"


def get_following_path() -> Path:
    """
    获取 following.json 路径（运行时显式覆盖优先，DY-001）

    Returns:
        following.json 路径
    """
    if _OVERRIDE["following_path"]:
        return Path(_OVERRIDE["following_path"]).expanduser().resolve()
    return SKILL_DIR / "config" / "following.json"


# 导出常用路径（延迟计算）
class Paths:
    """常用路径集合（延迟计算）"""

    _download_path: Optional[Path] = None
    _data_output_path: Optional[Path] = None
    _db_path: Optional[Path] = None
    _following_path: Optional[Path] = None

    @classmethod
    @property
    def DOWNLOADS(cls) -> Path:
        """下载目录"""
        if cls._download_path is None:
            cls._download_path = get_download_path()
        return cls._download_path

    @classmethod
    @property
    def DATA_OUTPUT(cls) -> Path:
        """数据输出目录"""
        if cls._data_output_path is None:
            cls._data_output_path = get_data_output_path()
        return cls._data_output_path

    @classmethod
    @property
    def DB(cls) -> Path:
        """数据库路径"""
        if cls._db_path is None:
            cls._db_path = get_db_path()
        return cls._db_path

    @classmethod
    @property
    def FOLLOWING(cls) -> Path:
        """following.json 路径"""
        if cls._following_path is None:
            cls._following_path = get_following_path()
        return cls._following_path

    @classmethod
    def reset(cls):
        """重置缓存的路径（用于配置更改后）"""
        cls._download_path = None
        cls._data_output_path = None
        cls._db_path = None
        cls._following_path = None


if __name__ == "__main__":
    # 测试
    print(f"技能目录: {SKILL_DIR}")
    print(f"配置文件: {CONFIG_PATH}")
    print(f"默认下载路径: {get_default_download_path()}")
    print(f"实际下载路径: {get_download_path()}")
    print(f"数据库路径: {get_db_path()}")
    print(f"following.json 路径: {get_following_path()}")

    # 测试文件夹名称清理
    test_names = [
        "测试博主",
        "博主/名称",
        "test<>:\"/\\|?*name",
        "  multiple   spaces  ",
        "",
    ]
    print("\n文件夹名称清理测试:")
    for name in test_names:
        print(f"  '{name}' -> '{sanitize_folder_name(name)}'")
