"""Shared focus classification for the workmode report and preference tools."""
from __future__ import annotations

import json
from pathlib import Path
from self_evolve_paths import SKILL_ROOT

CONFIG_PATH = SKILL_ROOT / "config" / "workmode.local.json"
DEFAULT_FOCUS_KEYWORDS = {
    "项目开发": ["开发", "代码", "测试"],
    "内容创作": ["写作", "文章", "编辑"],
    "学习与教学": ["学习", "课程", "教学"],
    "流程改进": ["流程", "自动化", "工作流"],
}


def _object_no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate field")
        result[key] = value
    return result


def _validate_mapping(value):
    if not isinstance(value, dict):
        raise ValueError("invalid mapping")
    for label, keywords in value.items():
        if (not isinstance(label, str) or not label.strip() or len(label) > 114
                or any(ord(c) < 32 or ord(c) == 127 for c in label)
                or label == "未匹配" or not isinstance(keywords, list) or not keywords):
            raise ValueError("invalid classification")
        if any(not isinstance(k, str) or not k.strip() or len(k) > 256
               or any(ord(c) < 32 or ord(c) == 127 for c in k) for k in keywords):
            raise ValueError("invalid keyword")
    return value


def load_focus_config(path: Path | None = None) -> dict[str, list[str]]:
    """Read a complete override; malformed configuration always fails closed."""
    path = CONFIG_PATH if path is None else Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {label: words[:] for label, words in DEFAULT_FOCUS_KEYWORDS.items()}
    except (OSError, UnicodeError):
        raise ValueError("Invalid workmode configuration: cannot read file") from None
    try:
        data = json.loads(text, object_pairs_hook=_object_no_duplicates)
        if not isinstance(data, dict) or set(data) - {"focus_keywords", "focus_extra_keywords"}:
            raise ValueError("invalid fields")
        if "focus_keywords" not in data:
            raise ValueError("missing focus keywords")
        base = _validate_mapping(data["focus_keywords"])
        extra = _validate_mapping(data.get("focus_extra_keywords", {}))
        if set(extra) - set(base):
            raise ValueError("unknown focus label")
        return {name: words + extra.get(name, []) for name, words in base.items()}
    except (ValueError, TypeError, RecursionError):
        raise ValueError("Invalid workmode configuration") from None


def match_focus(text: str, categories: dict[str, list[str]]) -> list[str]:
    return [name for name, words in categories.items() if any(word in text for word in words)]
