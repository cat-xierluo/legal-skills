"""共享工具模块 - main.py / quick_export.py 的公共实现

收敛审计发现的「分类/导出分叉」：此前在线导出（main.py）与快速导出
（quick_export.py）各自维护一份 assess_value，关键词集与阈值不一致，
同一仓库在两条路径下可能得到不同的价值评级。现在统一走本模块。
"""

import json
from pathlib import Path

# 默认价值规则（与 StarTracker._get_default_categories 同源的兜底策略）
DEFAULT_VALUE_KEYWORDS = ['claude', 'ai', 'llm', 'agent', 'python']
DEFAULT_HIGH_STARS = 5000
DEFAULT_MEDIUM_STARS = 1000


def load_value_config(settings_file: Path) -> dict:
    """从 user_settings.json 读取价值评估配置，损坏/缺失时回落默认"""
    config = {
        "value_keywords": list(DEFAULT_VALUE_KEYWORDS),
        "high_value_stars": DEFAULT_HIGH_STARS,
        "medium_value_stars": DEFAULT_MEDIUM_STARS,
    }
    try:
        if settings_file.exists():
            user_cfg = json.loads(settings_file.read_text(encoding="utf-8"))
            config["value_keywords"] = user_cfg.get(
                "value_keywords", config["value_keywords"]) or config["value_keywords"]
            config["high_value_stars"] = user_cfg.get(
                "high_value_stars", config["high_value_stars"])
            config["medium_value_stars"] = user_cfg.get(
                "medium_value_stars", config["medium_value_stars"])
    except Exception:
        pass  # 配置损坏时回落默认值，不阻塞导出
    return config


def assess_value(repo: dict, value_config: dict = None) -> str:
    """评估项目价值（统一实现）

    Args:
        repo: 仓库数据（需要 stargazers_count/language/description）
        value_config: 价值配置（load_value_config 的返回值），不传用默认
    """
    cfg = value_config or load_value_config(
        Path(__file__).parent.parent / "output" / "user_settings.json")

    stars = repo.get('stargazers_count', 0)
    language = repo.get('language') or ''
    description = (repo.get('description') or '').lower()

    if stars > cfg["high_value_stars"] or any(
            kw in description for kw in cfg["value_keywords"]):
        return 'high'
    elif stars > cfg["medium_value_stars"] or 'Python' in language:
        return 'medium'
    return 'low'
