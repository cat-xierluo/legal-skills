#!/usr/bin/env python3
"""
GitHub Star 分类动态生成器

功能：
1. 首次运行：根据 JSON 数据中的 topics 频率自动生成分类
2. 后续运行：增量更新（保留现有分类，只添加新高频 topics）

使用：
    python generate_categories.py                    # 使用默认路径
    python generate_categories.py --json path.json  # 指定 JSON 文件
    python generate_categories.py --force           # 强制重新生成
"""

import json
import yaml
import argparse
from pathlib import Path
from collections import Counter
from typing import Dict, List, Optional, Tuple
from datetime import datetime


class CategoryGenerator:
    """动态分类生成器"""

    # 默认路径配置
    DEFAULT_JSON_PATH = Path(__file__).parent.parent / "output" / "original_latest.json"
    DEFAULT_CATEGORIES_PATH = Path(__file__).parent.parent / "output" / "categories.yaml"
    TEMPLATE_CATEGORIES_PATH = Path(__file__).parent.parent / "assets" / "categories.yaml"

    # 生成分类的最小频次阈值
    MIN_FREQUENCY = 5

    # 高频 topics 的分类映射（将相似 topics 合并为一个分类）
    TOPIC_GROUPS = {
        "ai-agents": ["ai", "agent", "agents", "ai-agent", "ai-agents", "agentic", "autonomous", "agentic-ai"],
        "claude-code": ["claude-code", "claude", "mcp", "openclaw", "clawdbot", "moltbot", "superpowers", "claude-skills", "claude-desktop"],
        "llm": ["llm", "llms", "rag", "ollama", "deepseek", "gemini", "anthropic", "openai", "gpt", "chatgpt", "codex", "qwen"],
        "chinese-platform": ["wechat", "weixin", "bilibili", "douyin", "tiktok", "xiaohongshu", "jianying", "lark", "feishu"],
        "devtools": ["typescript", "python", "javascript", "electron", "tauri", "swiftui", "cli", "vscode", "docker", "rust", "golang", "swift"],
        "workflow": ["automation", "workflow", "n8n", "webhook", "integration"],
        "productivity": ["obsidian", "productivity", "note", "notes", "markdown", "task", "todo"],
        "content-processing": ["ocr", "pdf", "tts", "speech", "video", "download", "transcript", "whisper"],
        "network": ["proxy", "vpn", "shadowsocks", "v2ray", "gfw", "clash"],
        "crawler": ["crawler", "scraper", "spider", "web-scraping", "scraping", "playwright", "puppeteer"],
        "rss": ["rss", "rsshub", "feed", "newsletter"],
    }

    # 分类图标和颜色映射
    CATEGORY_STYLES = {
        "ai-agents": {"icon": "🤖", "color": "#22c55e", "name": "AI Agents"},
        "claude-code": {"icon": "🐛", "color": "#8b5cf6", "name": "Claude Code"},
        "llm": {"icon": "🧠", "color": "#3b82f6", "name": "LLM/大模型"},
        "chinese-platform": {"icon": "🇨🇳", "color": "#ef4444", "name": "中国平台"},
        "devtools": {"icon": "🔧", "color": "#f59e0b", "name": "开发工具"},
        "workflow": {"icon": "🔄", "color": "#06b6d4", "name": "工作流自动化"},
        "productivity": {"icon": "⚡", "color": "#eab308", "name": "效率工具"},
        "content-processing": {"icon": "📄", "color": "#6366f1", "name": "内容处理"},
        "network": {"icon": "🌐", "color": "#64748b", "name": "网络工具"},
        "crawler": {"icon": "🕷️", "color": "#84cc16", "name": "爬虫/抓取"},
        "rss": {"icon": "📡", "color": "#f97316", "name": "RSS/订阅"},
    }

    def __init__(self, json_path: Optional[Path] = None, categories_path: Optional[Path] = None):
        self.json_path = json_path or self.DEFAULT_JSON_PATH
        self.categories_path = categories_path or self.DEFAULT_CATEGORIES_PATH

    def load_json_data(self) -> Optional[Dict]:
        """加载 JSON 数据"""
        if not self.json_path.exists():
            print(f"❌ JSON 文件不存在: {self.json_path}")
            return None

        with open(self.json_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def load_existing_categories(self) -> List[Dict]:
        """加载现有分类（如果存在）"""
        if self.categories_path.exists():
            with open(self.categories_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
                if data and 'categories' in data:
                    return data['categories']
        return []

    def count_topics(self, data: Dict) -> Counter:
        """统计所有 topics 的频次"""
        topics_counter = Counter()

        repos = data.get('repos', [])
        for repo in repos:
            for topic in repo.get('topics', []):
                topics_counter[topic.lower()] += 1

        return topics_counter

    def find_matching_group(self, topic: str) -> Optional[str]:
        """找到 topic 所属的分组"""
        topic_lower = topic.lower()
        for group_id, topics in self.TOPIC_GROUPS.items():
            if topic_lower in topics:
                return group_id
        return None

    def generate_categories_from_topics(self, topics_counter: Counter, existing_categories: List[Dict]) -> Tuple[List[Dict], List[str]]:
        """根据 topics 频率生成分类

        Returns:
            (新分类列表, 新增的分类ID列表)
        """
        # 获取现有分类的 ID
        existing_ids = {cat['id'] for cat in existing_categories}
        existing_keywords = set()
        for cat in existing_categories:
            existing_keywords.update(k.lower() for k in cat.get('keywords', []))

        # 统计每个分组的总频次
        group_scores = Counter()
        ungrouped_high_freq = []

        for topic, freq in topics_counter.items():
            if freq < self.MIN_FREQUENCY:
                continue

            group = self.find_matching_group(topic)
            if group:
                group_scores[group] += freq
            else:
                # 未分组的高频 topic
                ungrouped_high_freq.append((topic, freq))

        # 生成新分类
        new_categories = []
        added_ids = []

        # 1. 添加高分分组（如果不在现有分类中）
        for group_id, score in group_scores.most_common():
            if group_id not in existing_ids and score >= self.MIN_FREQUENCY:
                style = self.CATEGORY_STYLES.get(group_id, {
                    "icon": "📁",
                    "color": "#6b7280",
                    "name": group_id.replace("-", " ").title()
                })
                keywords = self.TOPIC_GROUPS.get(group_id, [group_id])

                new_categories.append({
                    "id": group_id,
                    "name": style["name"],
                    "icon": style["icon"],
                    "color": style["color"],
                    "keywords": keywords,
                    "generated": True,
                    "generated_at": datetime.now().isoformat(),
                    "frequency": score
                })
                added_ids.append(group_id)

        # 2. 添加未分组的高频 topics 作为独立分类（频次 >= 10）
        for topic, freq in sorted(ungrouped_high_freq, key=lambda x: -x[1]):
            if freq >= 10 and topic not in existing_keywords:
                # 清理 topic 名称作为分类 ID
                cat_id = topic.lower().replace("_", "-").replace(" ", "-")

                if cat_id not in existing_ids and cat_id not in added_ids:
                    new_categories.append({
                        "id": cat_id,
                        "name": topic.replace("-", " ").replace("_", " ").title(),
                        "icon": "📁",
                        "color": "#6b7280",
                        "keywords": [topic],
                        "generated": True,
                        "generated_at": datetime.now().isoformat(),
                        "frequency": freq
                    })
                    added_ids.append(cat_id)

        return new_categories, added_ids

    def merge_categories(self, existing: List[Dict], new: List[Dict]) -> List[Dict]:
        """合并现有分类和新分类"""
        # 按 frequency 排序（新分类），现有分类保持原顺序
        existing_ids = {cat['id'] for cat in existing}
        new_sorted = sorted(new, key=lambda x: x.get('frequency', 0), reverse=True)

        # 清理内部字段（不保存到文件）
        for cat in new_sorted:
            cat.pop('frequency', None)

        return existing + new_sorted

    def save_categories(self, categories: List[Dict]) -> None:
        """保存分类到 YAML 文件"""
        # 确保目录存在
        self.categories_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "categories": categories,
            "_meta": {
                "generated_at": datetime.now().isoformat(),
                "source": "generate_categories.py",
                "description": "基于 GitHub Star 数据动态生成的分类"
            }
        }

        with open(self.categories_path, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    def update(self, force: bool = False) -> Dict:
        """执行分类更新

        Args:
            force: 是否强制重新生成（忽略现有分类）

        Returns:
            更新结果统计
        """
        # 1. 加载 JSON 数据
        data = self.load_json_data()
        if not data:
            return {"success": False, "error": "无法加载 JSON 数据"}

        total_repos = data.get('total_count', 0)
        print(f"📊 加载了 {total_repos} 个 Star 项目")

        # 2. 统计 topics
        topics_counter = self.count_topics(data)
        unique_topics = len(topics_counter)
        print(f"📈 发现 {unique_topics} 个不同的 topics")

        # 3. 加载现有分类
        existing = [] if force else self.load_existing_categories()
        print(f"📁 现有分类: {len(existing)} 个")

        # 4. 生成新分类
        new_categories, added_ids = self.generate_categories_from_topics(topics_counter, existing)
        print(f"✨ 新增分类: {len(new_categories)} 个")

        if added_ids:
            print(f"   → {', '.join(added_ids)}")

        # 5. 合并并保存
        merged = self.merge_categories(existing, new_categories)
        self.save_categories(merged)
        print(f"💾 已保存到: {self.categories_path}")

        # 6. 输出高频 topics 统计
        print("\n📊 Top 20 Topics:")
        for topic, count in topics_counter.most_common(20):
            group = self.find_matching_group(topic)
            group_str = f"→ {group}" if group else ""
            print(f"   {topic}: {count} {group_str}")

        return {
            "success": True,
            "total_repos": total_repos,
            "unique_topics": unique_topics,
            "existing_categories": len(existing),
            "new_categories": len(new_categories),
            "total_categories": len(merged),
            "added_ids": added_ids
        }


def main():
    parser = argparse.ArgumentParser(description="GitHub Star 分类动态生成器")
    parser.add_argument(
        "--json", "-j",
        type=Path,
        help="指定 JSON 数据文件路径"
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        help="指定输出分类文件路径"
    )
    parser.add_argument(
        "--force", "-f",
        action="store_true",
        help="强制重新生成（忽略现有分类）"
    )

    args = parser.parse_args()

    generator = CategoryGenerator(
        json_path=args.json,
        categories_path=args.output
    )

    result = generator.update(force=args.force)

    if not result["success"]:
        print(f"\n❌ 更新失败: {result.get('error')}")
        return 1

    print(f"\n✅ 更新完成!")
    print(f"   总分类数: {result['total_categories']}")

    return 0


if __name__ == "__main__":
    exit(main())
