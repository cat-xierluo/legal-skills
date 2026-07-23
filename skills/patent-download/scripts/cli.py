#!/usr/bin/env python3
"""
专利下载工具 - 统一入口
支持多平台、多方式的专利下载
"""

import os
import sys
import argparse

# 平台配置（按推荐度排序）
PLATFORMS = {
    "google": {
        "name": "Google Patents ⭐",
        "script_api": "platforms.google_patents",
        "script_browser": "platforms.google_patents",
        "need_login": False,
        "api_support": True,
        "note": "免费免登录，推荐首选。支持公告号(CN...)和申请号(如202421964517.8)"
    },
    "uyanip": {
        "name": "度衍专利",
        "script_api": "platforms.uyanip",
        "script_browser": "platforms.uyanip",
        "need_login": True,
        "api_support": False,
        "note": "浏览器自动化，有PDF下载按钮，无验证码"
    },
    "patentstar": {
        "name": "专利之星",
        "script_api": "platforms.patentstar",
        "script_browser": "platforms.patentstar_browser",
        "need_login": True,
        "api_support": True,
        "note": "⚠️ API 接口已失效(Ret=206)，浏览器方式详情页有验证码"
    },
    "gpic": {
        "name": "粤港澳知识产权大数据平台",
        "script_api": "platforms.gpic",
        "script_browser": "platforms.gpic",
        "need_login": True,
        "api_support": False,
        "note": "浏览器自动化，PDF下载待完善"
    },
    "pss": {
        "name": "PSS专利检索系统",
        "script_api": "platforms.pss",
        "script_browser": "platforms.pss",
        "need_login": True,
        "api_support": False,
        "note": "浏览器自动化，PDF下载待完善"
    },
    "epub": {
        "name": "专利公布公告系统",
        "script_api": "platforms.epub",
        "script_browser": "platforms.epub",
        "need_login": False,
        "api_support": False,
        "note": "无需登录，但有验证码和强反爬"
    },
}

DEFAULT_PLATFORM = "google"


def _load_platform_creds(platform: str) -> dict:
    """从环境变量读取指定平台账号（凭证单一来源，公开发布版）。

    委托 platforms._creds.load_creds：优先 os.environ 的
    PATENT_<PLATFORM>_USERNAME / _PASSWORD，回退 config/.env 文件。
    读不到返回空字符串，由调用方提示用户。
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)
    try:
        from platforms._creds import load_creds
        return load_creds(platform)
    except Exception:
        return {}


def run_platform(platform: str, method: str, patents: list, args):
    """运行指定平台的下载"""
    config = PLATFORMS.get(platform, PLATFORMS[DEFAULT_PLATFORM])
    
    # 特殊处理 Google Patents（使用独立 SDK，不需要动态加载 main）
    if platform == "google":
        _run_google_patents(patents, args)
        return
    
    # 动态导入模块（其他平台）
    script_name = config[f"script_{method}"]
    module_path = f"platforms.{script_name.split('.')[-1]}"
    
    # 添加路径
    script_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, script_dir)
    
    # 导入模块
    try:
        if method == "browser":
            # 浏览器方式
            module = __import__(f"platforms.{script_name.split('_')[0]}", fromlist=["main"])
        else:
            module = __import__(f"platforms.{script_name.split('.')[-1]}", fromlist=["main"])
        
        # 修改 sys.argv
        old_argv = sys.argv
        sys.argv = [script_name] + patents
        
        if args.username:
            sys.argv.extend(["--username", args.username])
        if args.password:
            sys.argv.extend(["--password", args.password])
        if args.output:
            sys.argv.extend(["--output", args.output])
        if args.headless:
            sys.argv.append("--headless")
        
        # 运行
        module.main()
        
        sys.argv = old_argv
        
    except Exception as e:
        print(f"❌ 运行失败: {e}")
        import traceback
        traceback.print_exc()


def list_platforms():
    """列出所有支持的平台（按推荐度排序）"""
    print("\n支持的平台（按推荐度排序）:")
    print("-" * 70)
    for i, (key, config) in enumerate(PLATFORMS.items(), 1):
        api_status = "✅" if config["api_support"] else "❌"
        star = " ⭐" if i == 1 else ""
        print(f"  {i}. {key:15} {config['name']:25} API:{api_status}")
        note = config.get("note", "")
        if note:
            print(f"     {note}")
    print()
    print("💡 提示：申请号和公告号的区别")
    print("   申请号（如 202421964517.8）= 提交申请时的编号")
    print("   公告号（如 CN223081266U）= 专利公开后的编号")
    print("   Google Patents 优先用公告号，也支持输入申请号自动匹配")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="专利下载工具 - 多平台、多方式",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
支持的平台（按推荐度排序）:
{'-' * 50}
{chr(10).join(f"  {i}. {k:15} - {v['name']}" for i, (k, v) in enumerate(PLATFORMS.items(), 1))}

💡 申请号 vs 公告号:
   - 申请号: 202421964517.8（提交时编号）
   - 公告号: CN223081266U（公开后编号）
   - Google Patents 优先用公告号，也支持输入申请号自动匹配

示例:
  # Google Patents 下载（推荐，免费免登录）
  python cli.py google CN223081266U
  
  # Google Patents 也支持申请号自动匹配
  python cli.py google 202421964517.8
  
  # 度衍浏览器自动化下载
  python cli.py uyanip CN223081266U -m browser
  
  # 列出所有平台
  python cli.py --list
  
  # 仅查询专利信息不下载
  python cli.py google CN223081266U --info
        """
    )
    
    parser.add_argument("--list", "-l", action="store_true", help="列出所有支持的平台")
    parser.add_argument("platform", nargs="?", default=DEFAULT_PLATFORM, help="平台名称")
    parser.add_argument("patents", nargs="*", help="专利号列表")
    parser.add_argument("-m", "--method", choices=["api", "browser"], default="api", 
                       help="下载方式 (api 或 browser)")
    parser.add_argument("-u", "--username", help="用户名")
    parser.add_argument("-p", "--password", help="密码")
    parser.add_argument("-o", "--output", default=".", help="输出目录")
    parser.add_argument("--headless", action="store_true", help="无头模式（浏览器方式）")
    parser.add_argument("--info", action="store_true", help="仅查询信息，不下载（仅 Google Patents）")
    
    args = parser.parse_args()
    
    if args.list:
        list_platforms()
        return
    
    if not args.patents:
        parser.print_help()
        list_platforms()
        return
    
    platform = args.platform.lower()
    if platform not in PLATFORMS:
        print(f"❌ 不支持的平台: {platform}")
        list_platforms()
        return
    
    config = PLATFORMS[platform]
    
    # 检查 API 支持
    if args.method == "api" and not config["api_support"]:
        print(f"⚠️ {config['name']} 暂不支持 API 方式，将使用浏览器方式")
        args.method = "browser"
    
    # 从环境变量加载账号（凭证单一来源；回退 config/.env，见 platforms/_creds.py）
    creds = _load_platform_creds(platform)
    if not args.username:
        args.username = creds.get("username")
    if not args.password:
        args.password = creds.get("password")
    
    print("=" * 60)
    print(f"📥 专利下载工具")
    print(f"   平台: {config['name']}")
    print(f"   方式: {args.method}")
    print(f"   专利: {', '.join(args.patents)}")
    print("=" * 60)
    
    # 运行
    run_platform(platform, args.method, args.patents, args)


def _run_google_patents(patents: list, args):
    """运行 Google Patents 下载"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, script_dir)
    
    try:
        module = __import__("platforms.google_patents", fromlist=["main"])
    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        print("   请执行: pip install patent-downloader")
        return
    
    for pn in patents:
        if getattr(args, "info", False):
            module.get_info(pn)
        else:
            module.download_patent(pn, args.output)


if __name__ == "__main__":
    main()
