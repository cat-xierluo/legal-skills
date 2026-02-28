#!/usr/bin/env python3
"""
快速导出 data.js - 从现有 JSON 数据和分类配置生成 HTML Dashboard 数据

不需要重新从 GitHub API 获取数据，直接使用本地缓存。
"""

import json
import yaml
from pathlib import Path
from typing import Dict, List, Optional


def load_json_data(json_path: Path) -> Dict:
    """加载 JSON 数据"""
    with open(json_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_categories(categories_path: Path) -> List[Dict]:
    """加载分类配置"""
    if not categories_path.exists():
        return []
    with open(categories_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
        return data.get('categories', []) if data else []


def match_categories(repo: Dict, categories: List[Dict], min_score: int = 3) -> List[Dict]:
    """为仓库匹配多个分类（多标签模式）

    Args:
        repo: 仓库数据
        categories: 分类列表
        min_score: 最低匹配分数阈值

    Returns:
        匹配的分类列表（按分数排序）
    """
    if not categories:
        return []

    # 收集仓库的可匹配信息
    language = (repo.get('language') or '').lower()
    description = (repo.get('description') or '').lower()
    topics = [t.lower() for t in repo.get('topics', [])]
    name = repo.get('name', '').lower()
    full_name = repo.get('full_name', '').lower()
    repo_text = f"{language} {description} {' '.join(topics)} {name} {full_name}"

    # 检查每个分类的匹配度
    matched = []

    for cat in categories:
        score = 0
        keywords = cat.get('keywords', [])

        # 统计匹配的关键词数量
        matched_keywords = 0
        for kw in keywords:
            if kw.lower() in repo_text:
                matched_keywords += 1

        # 根据匹配的关键词数量计算分数
        if matched_keywords > 0:
            score = matched_keywords * 3  # 每个匹配的关键词得3分

        # 语言精确匹配加分
        if language and any(kw.lower() == language for kw in keywords):
            score += 2

        # topic 精确匹配加分
        for topic in topics:
            if topic in [kw.lower() for kw in keywords]:
                score += 2

        if score >= min_score:
            matched.append((cat, score))

    # 按分数排序，返回分类列表
    matched.sort(key=lambda x: -x[1])
    return [cat for cat, score in matched]


def assess_value(repo: dict) -> str:
    """评估项目价值"""
    stars = repo.get('stargazers_count', 0)
    language = repo.get('language') or ''
    description = (repo.get('description') or '').lower()

    high_value_keywords = ['claude', 'ai', 'llm', 'agent', 'python', 'mcp', 'openclaw']

    if stars > 5000 or any(kw in description for kw in high_value_keywords):
        return 'high'
    elif stars > 1000 or 'Python' in language:
        return 'medium'
    return 'low'


def generate_data_js(output_path: Path, projects: List[Dict], categories: List[Dict]) -> None:
    """生成 data.js 文件，包含项目和分类数据"""

    # 准备分类数据（转换为 id -> category 的映射）
    categories_map = {}
    for cat in categories:
        cat_id = cat.get('id')
        categories_map[cat_id] = {
            'id': cat_id,
            'name': cat.get('name', cat_id),
            'icon': cat.get('icon', '📁'),
            'color': cat.get('color', '#6b7280')
        }

    # 生成项目数据
    projects_str = json.dumps(projects, ensure_ascii=False)
    projects_str = projects_str.replace('\u2028', '\\u2028').replace('\u2029', '\\u2029')

    # 生成分类数据
    categories_str = json.dumps(categories_map, ensure_ascii=False)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(f"const PROJECTS_DATA = {projects_str};\n\n")
        f.write(f"const CATEGORIES_DATA = {categories_str};\n")


def quick_export(
    json_path: Path = None,
    categories_path: Path = None,
    output_path: Path = None
) -> Dict:
    """快速导出 data.js"""

    # 默认路径
    base_dir = Path(__file__).parent.parent
    json_path = json_path or base_dir / "output" / "original_latest.json"
    categories_path = categories_path or base_dir / "output" / "categories.yaml"
    output_path = output_path or base_dir / "output" / "data.js"

    # 加载数据
    data = load_json_data(json_path)
    categories = load_categories(categories_path)

    print(f"📊 加载了 {data.get('total_count', 0)} 个项目")
    print(f"📁 加载了 {len(categories)} 个分类")

    # 处理每个项目
    export_data = []
    category_counts = {}

    for repo in data.get('repos', []):
        # 匹配多个分类
        matched_categories = match_categories(repo, categories)

        # 统计每个分类的项目数
        for cat in matched_categories:
            cat_id = cat.get('id', 'uncategorized')
            category_counts[cat_id] = category_counts.get(cat_id, 0) + 1

        # 主分类（第一个匹配的分类）用于向后兼容
        primary_cat = matched_categories[0] if matched_categories else None

        # 所有分类 ID 列表
        category_ids = [cat.get('id') for cat in matched_categories]

        export_data.append({
            'id': repo.get('id'),
            'full_name': repo.get('full_name'),
            'name': repo.get('name'),
            'owner': repo.get('owner'),
            'description': repo.get('description', ''),
            'html_url': repo.get('html_url'),
            'language': repo.get('language'),
            'topics': repo.get('topics', []),
            'stargazers_count': repo.get('stargazers_count', 0),
            'forks_count': repo.get('forks_count', 0),
            'open_issues_count': repo.get('open_issues_count', 0),
            'created_at': repo.get('created_at'),
            'updated_at': repo.get('updated_at'),
            'pushed_at': repo.get('pushed_at'),
            'starred_at': repo.get('starred_at'),
            'avatar_url': f"https://avatars.githubusercontent.com/u/{repo.get('owner', '')}" if repo.get('owner') else None,
            'value': assess_value(repo),
            # 多分类支持
            'categories': category_ids,  # 所有匹配的分类 ID
            'category': primary_cat.get('id') if primary_cat else None,  # 主分类（向后兼容）
            'category_name': primary_cat.get('name') if primary_cat else None,
            'category_icon': primary_cat.get('icon') if primary_cat else None,
            'category_color': primary_cat.get('color') if primary_cat else None,
        })

    # 生成 data.js
    generate_data_js(output_path, export_data, categories)

    print(f"\n📊 分类统计:")
    for cat_id, count in sorted(category_counts.items(), key=lambda x: -x[1]):
        cat_name = next((c.get('name', cat_id) for c in categories if c.get('id') == cat_id), cat_id)
        print(f"   {cat_name}: {count}")

    uncategorized = len(data.get('repos', [])) - sum(category_counts.values())
    if uncategorized > 0:
        print(f"   未分类: {uncategorized}")

    print(f"\n✅ 已生成: {output_path}")
    print(f"   项目数: {len(export_data)}")

    return {
        "success": True,
        "output_path": str(output_path),
        "project_count": len(export_data),
        "category_counts": category_counts
    }


if __name__ == "__main__":
    quick_export()
