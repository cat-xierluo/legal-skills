#!/usr/bin/env python3
"""
GitHub Star 追踪器 - 主入口
用于追踪 GitHub Star 项目的更新、版本变化和活跃度
"""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime
from star_tracker import StarTracker
import dashboard_generator

# 加载 .env 配置文件（从 assets/ 目录）
try:
    from dotenv import load_dotenv
    # 从 assets/ 目录加载 .env 文件
    env_path = Path(__file__).parent.parent / "assets" / ".env"
    load_dotenv(dotenv_path=str(env_path))
except ImportError:
    pass  # 如果没有安装 python-dotenv，跳过环境变量加载


def init_command(tracker: StarTracker, args):
    """初始化：首次同步并保存原始数据"""
    print(f"--- 正在获取 {args.user} 的 Star 列表（上限: {args.limit}）---")

    repos = tracker.get_starred_repos(args.user, limit=args.limit)
    print(f"找到 {len(repos)} 个 Star 项目")

    # 保存快照
    snapshot_file = tracker.save_latest(repos)
    print(f"✓ 原始数据已保存: {snapshot_file}")

    # 生成项目摘要（可选）
    if args.summarize and len(repos) > 0:
        print("\n--- 正在生成项目摘要 ---")
        report_path = Path("star_summary.md")
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(f"# GitHub Star 项目摘要\n\n")
            f.write(f"**用户**: {args.user}\n")
            f.write(f"**生成时间**: {tracker.get_readme.__self__}\n\n")

            for i, repo in enumerate(repos[:20], 1):
                print(f"[{i}/{min(20, len(repos))}] {repo['full_name']}")
                readme = tracker.get_readme(repo["full_name"])
                summary = tracker.summarize_with_ai(repo, readme)

                f.write(f"## {i}. [{repo['full_name']}]({repo['html_url']})\n\n")
                f.write(f"{summary}\n\n")

        print(f"✓ 摘要已保存: {report_path}")


def check_command(tracker: StarTracker, args):
    """检查更新"""
    print(f"--- 正在检查 {args.user} 的 Star 更新 ---")

    # 获取当前状态
    current_repos = tracker.get_starred_repos(args.user, limit=args.limit or 200)
    print(f"当前 Star 数量: {len(current_repos)}")

    # 加载历史数据
    snapshot = tracker.load_latest()
    if not snapshot:
        print("❌ 未找到历史数据，请先运行: --init")
        return

    snapshot_time = snapshot.get("timestamp", "未知")[:16].replace("T", " ")
    print(f"上次保存: {snapshot_time}")

    # 保存新数据
    tracker.save_latest(current_repos)

    # 分析变化
    old_map = {r["full_name"]: r for r in snapshot["repos"]}
    current_map = {r["full_name"]: r for r in current_repos}

    new_repos = [r for fn, r in current_map.items() if fn not in old_map]
    removed_repos = [fn for fn in old_map if fn not in current_map]
    updated_repos = []

    for fn, repo in current_map.items():
        if fn in old_map and repo.get("updated_at") != old_map[fn].get("updated_at"):
            updated_repos.append(repo)

    # 输出结果
    print("\n" + "=" * 50)
    if new_repos:
        print(f"\n🆕 新增 Star ({len(new_repos)} 个):")
        for repo in new_repos[:10]:
            print(f"  • {repo['full_name']}")
        if len(new_repos) > 10:
            print(f"  ... 还有 {len(new_repos) - 10} 个")

    if removed_repos:
        print(f"\n🗑️ 取消 Star ({len(removed_repos)} 个):")
        for name in removed_repos[:10]:
            print(f"  • {name}")

    if updated_repos:
        print(f"\n🔄 有更新的项目 ({len(updated_repos)} 个):")
        for repo in updated_repos[:10]:
            updated = repo.get("updated_at", "")[:10]
            print(f"  • {repo['full_name']} ({updated})")
        if len(updated_repos) > 10:
            print(f"  ... 还有 {len(updated_repos) - 10} 个")

    if not new_repos and not updated_repos:
        print("\n✓ 没有检测到新项目或更新")

    print("=" * 50)


def report_command(tracker: StarTracker, args):
    """生成完整报告"""
    print(f"--- 正在生成 {args.user} 的更新报告 ---")

    days = args.report_days or 7
    report = tracker.generate_report(args.user, days=days)

    output_path = Path(args.output or "star_report.md")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"✓ 报告已保存: {output_path}")
    print(f"  追踪时间范围: 最近 {days} 天")


def export_command(tracker: StarTracker, args):
    """导出 JSON 数据用于 HTML Dashboard"""
    print(f"--- 正在导出 {args.user} 的 Star 数据 ---")

    repos = tracker.get_starred_repos(args.user, limit=args.limit or 9999)
    print(f"获取到 {len(repos)} 个项目")

    # 获取每个项目的详细信息
    export_data = []
    for i, repo in enumerate(repos, 1):
        print(f"[{i}/{len(repos)}] {repo['full_name']}", end='\r')

        # 获取最新 release 信息
        release = tracker.get_latest_release(repo['full_name'])
        has_new_release = False
        if release:
            # 检查 release 是否是最近的（7天内）
            try:
                release_date = datetime.fromisoformat(release.get('published_at', '').replace('Z', '+00:00'))
                days_since = (datetime.now(release_date.tzinfo) - release_date).days
                has_new_release = days_since <= 7
            except:
                pass

        # 获取项目健康度
        health = tracker.get_repo_health(repo['full_name'])

        export_data.append({
            'id': repo['id'],
            'full_name': repo['full_name'],
            'name': repo['name'],
            'owner': repo['owner']['login'],
            'description': repo.get('description', ''),
            'html_url': repo['html_url'],
            'language': repo.get('language'),
            'topics': repo.get('topics', []),
            'stargazers_count': repo.get('stargazers_count', 0),
            'forks_count': repo.get('forks_count', 0),
            'open_issues_count': repo.get('open_issues_count', 0),
            'created_at': repo.get('created_at'),
            'updated_at': repo.get('updated_at'),
            'pushed_at': repo.get('pushed_at'),
            'starred_at': repo.get('starred_at'),  # 用户何时 Star 的
            'avatar_url': repo['owner'].get('avatar_url'),
            'has_new_release': has_new_release,
            'value': assess_value(repo, health),
            'category': repo.get('category'),  # 分类信息
            'matched_keywords': repo.get('matched_keywords', []),  # 匹配的关键词
            'reason': repo.get('notes', '')
        })

    # 使用 dashboard_generator 生成 HTML 和数据文件
    result = dashboard_generator.generate_dashboard(export_data, "output")

    print(f"\n✓ 数据已导出: {result['data_js_path']}")
    print(f"  Dashboard: {result['dashboard_path']}")
    print(f"  项目数量: {result['project_count']}")
    print(f"  可以直接双击 output/dashboard.html 查看可视化面板")


def export_config_command(tracker: StarTracker, args):
    """导出配置到文件"""
    config = tracker.export_config(args.user, include_repos=True)

    output_path = Path("config-export.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    print(f"✓ 配置已导出: {output_path}")
    print(f"  包含价值关键词、忽略列表、追踪仓库等设置")


def import_config_command(tracker: StarTracker, args):
    """导入配置文件"""
    config_path = Path(args.import_config)

    if not config_path.exists():
        print(f"❌ 配置文件不存在: {config_path}")
        return

    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    if not tracker.import_config(config):
        print(f"❌ 配置格式无效: {config.get('error', '未知错误')}")
        return

    # 应用导入的配置
    print(f"✓ 已导入配置: {config_path}")
    print(f"  价值关键词: {', '.join(config.get('value_keywords', []))}")
    print(f" ��星阈值: {config.get('min_stars', 0)}")
    if "ignore_repos" in config:
        print(f"  忽略列表: {', '.join(config.get('ignore_repos', []))}")


def version_diff_command(tracker: StarTracker, args):
    """查看版本差异"""
    import json

    # 首先需要获取两个版本号
    print("\n请提供两个版本号进行比较：")
    print("格式: owner/repo 按标签号 (如 v1.0.0)")

    try:
        old_version = input("旧版本: ").strip()
        new_version = input("新版本: ").strip()

        if not old_version or not new_version:
            print("❌ 请提供完整的版本号")
            return

        # 解析仓库
        parts = old_version.split("/", 1)
        if len(parts) != 2:
            print("❌ 版本格式错误，应为 owner/repo")
            return

        owner, repo = parts

        # 获取版本差异
        diff_data = tracker.get_version_diff(f"{owner}/{repo}", old_version, new_version)

        print(f"\n### 版本差异: {owner}/{repo}")
        print(f"  旧版本: {old_version}")
        print(f"  新版本: {new_version}")
        print(f"  Commits 数量: {diff_data['commits_count']}")

        if diff_data['commits']:
            print("\n最近的 Commits:")
            for commit in diff_data['commits']:
                date = commit.get('date', '')[:10]
                msg = commit.get('message', '')[:60]
                print(f"  [{date}] {msg[:80] if len(msg) > 80 else msg}")

        print(f"\n对比链接: {diff_data['compare_url']}")

    except Exception as e:
        print(f"❌ 错误: {e}")


def star_command(tracker: StarTracker, args):
    """为仓库添加 Star"""
    if not args.star:
        print("❌ 请指定仓库 (--star owner/repo)")
        return

    success, msg = tracker.star_repo(args.star)
    print(msg)


def unstar_command(tracker: StarTracker, args):
    """取消仓库的 Star"""
    if not args.unstar:
        print("❌ 请指定仓库 (--unstar owner/repo)")
        return

    success, msg = tracker.unstar_repo(args.unstar)
    print(msg)


def cleanup_command(tracker: StarTracker, args):
    """清理长期未更新的仓库"""
    print(f"\n检查 {args.user} 的 Star 项目（阈值: {args.cleanup_days} 天）...")

    count, repos = tracker.cleanup_stale_repos(args.user, args.cleanup_days, dry_run=not args.execute)

    if count == 0:
        print("\n✓ 没有需要清理的项目")
        return

    print(f"\n找到 {count} 个长期未更新的项目")

    if args.execute:
        print("\n⚠️  即将取消这些项目的 Star...")
        confirm = input("确认执行? (y/N): ")
        if confirm.lower() != 'y':
            print("已取消")
            return

        success, failed, _ = tracker.batch_unstar(repos, dry_run=False)
        print(f"\n✓ 完成: 成功 {success} 个, 失败 {failed} 个")
    else:
        print("\n💡 使用 --execute 参数实际执行清理")
        print(f"  python scripts/main.py --cleanup --cleanup-days {args.cleanup_days} --execute")


def batch_unstar_command(tracker: StarTracker, args):
    """批量取消 Star"""
    import json

    file_path = args.batch_unstar

    if not Path(file_path).exists():
        print(f"❌ 文件不存在: {file_path}")
        return

    with open(file_path, "r", encoding="utf-8") as f:
        repos = json.load(f)

    if isinstance(repos, dict):
        repos = repos.get("repos", repos.get("tracked_repos", []))

    if not repos:
        print("❌ 仓库列表为空")
        return

    print(f"\n将从 Star 列表中移除 {len(repos)} 个仓库:")
    for r in repos[:10]:
        print(f"  - {r}")
    if len(repos) > 10:
        print(f"  ... 还有 {len(repos) - 10} 个")

    print("\n💡 使用 --execute 参数实际执行（当前是预览模式）")
    confirm = input("确认执行? (y/N): ")
    if confirm.lower() != 'y':
        print("已取消")
        return

    success, failed, _ = tracker.batch_unstar(repos, dry_run=False)
    print(f"\n✓ 完成: 成功 {success} 个, 失败 {failed} 个")


def batch_star_command(tracker: StarTracker, args):
    """批量添加 Star"""
    import json

    file_path = args.batch_star

    if not Path(file_path).exists():
        print(f"❌ 文件不存在: {file_path}")
        return

    with open(file_path, "r", encoding="utf-8") as f:
        repos = json.load(f)

    if isinstance(repos, dict):
        repos = repos.get("repos", repos.get("recommendations", []))

    if not repos:
        print("❌ 仓库列表为空")
        return

    print(f"\n将为 {len(repos)} 个仓库添加 Star:")
    for r in repos[:10]:
        print(f"  - {r}")
    if len(repos) > 10:
        print(f"  ... 还有 {len(repos) - 10} 个")

    print("\n💡 使用 --execute 参数实际执行（当前是预览模式）")
    confirm = input("确认执行? (y/N): ")
    if confirm.lower() != 'y':
        print("已取消")
        return

    success, failed, _ = tracker.batch_star(repos, dry_run=False)
    print(f"\n✓ 完成: 成功 {success} 个, 失败 {failed} 个")


def assess_value(repo: dict, health: dict) -> str:
    """评估项目对用户的价值"""
    # 这里可以根据自定义规则评估
    stars = repo.get('stargazers_count', 0)
    language = repo.get('language') or ''

    # 高价值判断规则（可自定义）
    high_value_keywords = ['claude', 'ai', 'llm', 'agent', 'python']
    description = (repo.get('description') or '').lower()

    if stars > 5000 or any(kw in description for kw in high_value_keywords):
        return 'high'
    elif stars > 1000 or 'Python' in language:
        return 'medium'
    return 'low'


def main():
    parser = argparse.ArgumentParser(
        description="GitHub Star 追踪器 - 监控你 Star 的项目更新",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 首次使用，初始化并保存快照
  python scripts/main.py --init --user yourname --limit 50

  # 检查更新（对比上次快照）
  python scripts/main.py --check --user yourname

  # 生成完整报告
  python scripts/main.py --report --user yourname --days 7

  # 导出 JSON 数据供 HTML Dashboard 使用
  python scripts/main.py --export --user yourname

  # 快速启动 Dashboard
  python scripts/main.py --export --user yourname && open dashboard.html

  # 导出配置
  python scripts/main.py --export-config --user yourname

  # 导入配置
  python scripts/main.py --import-config config.json

  # 查看版本差异
  python scripts/main.py --version-diff --repo owner/repo

  # 为单个仓库添加 Star
  python scripts/main.py --star owner/repo

  # 取消单个仓库的 Star
  python scripts/main.py --unstar owner/repo

  # 批量清理长期未更新的仓库（先预览）
  python scripts/main.py --cleanup --days 90

  # 批量清理（实际执行，需要 --execute）
  python scripts/main.py --cleanup --days 90 --execute

  # 批量取消 Star（从配置文件）
  python scripts/main.py --batch-unstar repos.json

  # 带项目摘要的初始化
  python scripts/main.py --init --user yourname --summarize
        """,
    )

    parser.add_argument("--user", help="GitHub 用户名（不提供则自动从 Token 获取）")
    parser.add_argument("--init", action="store_true", help="初始化模式：首次同步并保存快照")
    parser.add_argument("--check", action="store_true", help="检查模式：对比快照检测更新")
    parser.add_argument("--report", action="store_true", help="报告模式：生成完整更新报告")
    parser.add_argument("--export", action="store_true", help="导出模式：生成 projects.json 供 HTML Dashboard 使用")
    parser.add_argument("--export-config", action="store_true", help="导出配置：将当前配置保存到文件")
    parser.add_argument("--import-config", help="导入配置：从文件导入配置")
    parser.add_argument("--version-diff", action="store_true", help="版本差异：查看两个版本之间的 commits")
    parser.add_argument("--star", help="为指定仓库添加 Star (owner/repo)")
    parser.add_argument("--unstar", help="取消指定仓库的 Star (owner/repo)")
    parser.add_argument("--cleanup", action="store_true", help="清理长期未更新的仓库")
    parser.add_argument("--cleanup-days", type=int, default=90, help="清理阈值天数 (默认: 90)")
    parser.add_argument("--execute", action="store_true", help="实际执行清理操作（默认只预览）")
    parser.add_argument("--batch-unstar", help="批量取消 Star：从 JSON 文件读取仓库列表")
    parser.add_argument("--batch-star", help="批量添加 Star：从 JSON 文件读取仓库列表")
    parser.add_argument("--limit", type=int, default=9999, help="处理的 Star 数量上限 (默认: 9999，即获取全部)")
    parser.add_argument("--report-days", type=int, default=7, help="报告时间范围（天）(默认: 7)")
    parser.add_argument("--summarize", action="store_true", help="是否使用 AI 生成项目摘要")
    parser.add_argument("--no-ai", action="store_true", help="强制不使用 AI，使用基础摘要替代")
    parser.add_argument("--output", "-o", help="报告输出文件路径")

    args = parser.parse_args()

    # 初始化追踪器
    github_token = os.getenv("GITHUB_PAT")
    tracker = StarTracker(github_token)

    # 如果没有提供用户名，尝试从 Token 自动获取
    username = args.user
    if not username:
        username = tracker.get_authenticated_user()
        if not username:
            print("❌ 错误: 未提供用户名且无法从 Token 获取")
            print("💡 解决方法:")
            print("   1. 设置 GITHUB_PAT 环境变量")
            print("   2. 或使用 --user 参数指定用户名")
            return 1
        print(f"✓ 自动获取用户名: {username}")
        args.user = username

    # 检查操作模式
    if not any([args.init, args.check, args.report, args.export, args.export_config,
                args.import_config, args.version_diff, args.star, args.unstar,
                args.cleanup, args.batch_unstar, args.batch_star]):
        parser.print_help()
        print("\n❌ 错误: 请指定操作模式")
        return 1

    # 执行对应命令
    try:
        if args.init:
            init_command(tracker, args)
        elif args.check:
            check_command(tracker, args)
        elif args.report:
            report_command(tracker, args)
        elif args.export:
            export_command(tracker, args)
        elif args.export_config:
            export_config_command(tracker, args)
        elif args.import_config:
            import_config_command(tracker, args)
        elif args.version_diff:
            version_diff_command(tracker, args)
        elif args.star:
            star_command(tracker, args)
        elif args.unstar:
            unstar_command(tracker, args)
        elif args.cleanup:
            cleanup_command(tracker, args)
        elif args.batch_unstar:
            batch_unstar_command(tracker, args)
        elif args.batch_star:
            batch_star_command(tracker, args)
        return 0
    except KeyboardInterrupt:
        print("\n\n⚠️ 操作已取消")
        return 130
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
