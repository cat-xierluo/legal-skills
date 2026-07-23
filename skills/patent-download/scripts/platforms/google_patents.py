#!/usr/bin/env python3
"""
Google Patents 平台模块

使用 patent-downloader SDK 从 Google Patents 下载中国专利 PDF。
优势：免费、免登录、无验证码、有现成 SDK。

专利号格式说明：
- 公告号（推荐）：CN223081266U、CN118198150A、CN118198150B
- 申请号（自动转换）：202421964517.8 → 通过 PatentGuru 查公告号

申请号结构（2003年后13位数字）：
  第1-4位 = 申请年份
  第5位 = 专利类型（1=发明, 2=实用新型, 3=外观设计, 8=PCT发明, 9=PCT实用新型）
  第6-12位 = 序列号
  第13位（小数点后）= 校验位

依赖：
  pip install patent-downloader
"""

import os
import re
import sys
from typing import Optional, List, Tuple


# ── 申请号 → 公告号转换 ──────────────────────────────────────────

def parse_application_number(patent_number: str) -> Optional[dict]:
    """
    解析中国专利申请号。

    格式：YYYYTXXXXXXX.C （2003年后）
      YYYY = 年份
      T = 类型（1=发明, 2=实用新型, 3=外观设计）
      XXXXXXX = 序列号
      C = 校验位

    返回解析结果字典，或 None（如果不是申请号格式）。
    """
    cleaned = patent_number.replace(".", "").replace("-", "").strip()
    if not cleaned.isdigit():
        return None
    if len(cleaned) not in (12, 13):
        return None

    year_str = cleaned[:4]
    type_str = cleaned[4]
    serial_str = cleaned[5:12]
    check_digit = cleaned[12] if len(cleaned) == 13 else "?"

    type_map = {"1": "发明", "2": "实用新型", "3": "外观设计",
                "8": "PCT发明", "9": "PCT实用新型"}

    return {
        "year": year_str,
        "type_code": type_str,
        "type_name": type_map.get(type_str, "未知"),
        "serial": serial_str,
        "check_digit": check_digit,
    }


def is_application_number(patent_number: str) -> bool:
    """判断是否为申请号格式（13位数字或带校验位）"""
    return parse_application_number(patent_number) is not None


APP_LOOKUP_TIPS = """
📋 申请号 → 公告号 查询方法：
   方法1: 浏览器打开 https://www.patentguru.com/cn/search?q={num}
   方法2: 用度衍专利 (uyanip) 或其他平台查公告号
   方法3: 确认专利类型后，公告号格式为 CNXXXXXXXU/A/B/S（7-9位数字+字母）

   示例：申请号 202421964517.8 → 公告号 CN223081266U
"""


def to_publication_format(patent_number: str) -> str:
    """
    标准化专利号格式供 Google Patents 使用。

    - 公告号 CN223081266U → 保持原样
    - 纯公告号 223081266U → 加 CN 前缀
    - 申请号 202421964517.8 → 保持原样，后续自动查公告号
    """
    cleaned = patent_number.strip()

    # 如果已经是 CN 开头
    if cleaned.upper().startswith("CN"):
        return cleaned

    # 申请号格式 → 保持原样（后续自动查公告号）
    if is_application_number(cleaned):
        return cleaned

    # 其他 → 加 CN 前缀
    return f"CN{cleaned}"


# ── 专利信息下载（带自动公告号查询）─────────────────────────────

def _get_downloader():
    """获取 patent-downloader 实例"""
    try:
        from patent_downloader import PatentDownloader
        return PatentDownloader()
    except ImportError:
        print("❌ 请先安装依赖: pip install patent-downloader")
        print("   或: pip install -r requirements.txt")
        return None


def _try_fetch(patent_number: str, downloader) -> Tuple[bool, Optional[str]]:
    """
    尝试用公告号获取专利信息。

    返回: (是否成功, 修正后的公告号)
    """
    # 直接尝试
    try:
        info = downloader.get_patent_info(patent_number)
        if info:
            return True, patent_number
    except Exception:
        pass

    # 如果是申请号，直接提示查公告号
    if is_application_number(patent_number):
        parsed = parse_application_number(patent_number)
        print(f"ℹ️  输入的是申请号（{parsed['year']}年{parsed['type_name']}），")
        print(f"   Google Patents 需要用公告号检索，申请号无法直接查询。")
        print(APP_LOOKUP_TIPS.format(num=patent_number))

    return False, None


def download_patent(
    patent_number: str,
    output_dir: str = ".",
) -> Optional[str]:
    """
    从 Google Patents 下载专利 PDF。

    自动处理：
    - 公告号 → 直接下载
    - 申请号 → 先查公告号再下载

    Args:
        patent_number: 专利号（公告号或申请号）
        output_dir: 输出目录
        
    Returns:
        成功返回 PDF 文件路径，失败返回 None
    """
    downloader = _get_downloader()
    if not downloader:
        return None

    formatted = to_publication_format(patent_number)

    # 尝试获取信息（公告号直接查，申请号自动转）
    success, actual_pub = _try_fetch(formatted, downloader)

    if not success:
        print(f"❌ 未找到该专利")
        if is_application_number(patent_number):
            parsed = parse_application_number(patent_number)
            if parsed:
                print(f"   申请号解析: {parsed['year']}年 {parsed['type_name']} 专利")
            print(f"   💡 提示：Google Patents 用公告号索引（如 CN223081266U）")
            print(f"   申请号无法直接查。建议：")
            print(f"     1. 尝试用其他平台（度衍/PatentGuru）查公告号")
            print(f"     2. 或用 python cli.py google <公告号> 下载")
        return None

    # 用公告号下载
    try:
        os.makedirs(output_dir, exist_ok=True)
        success_dl = downloader.download_patent(actual_pub, output_dir)

        if success_dl:
            # 查找下载的 PDF
            pdf_files = [f for f in os.listdir(output_dir) if f.lower().endswith('.pdf')]
            if pdf_files:
                latest = max(
                    [os.path.join(output_dir, f) for f in pdf_files],
                    key=os.path.getmtime
                )
                size_kb = os.path.getsize(latest) / 1024
                print(f"✅ 下载成功: {latest}")
                print(f"   📏 大小: {size_kb:.1f} KB")
                print(f"   🔗 公告号: {actual_pub}（原始输入: {patent_number}）")
                return latest
            else:
                print(f"✅ 下载完成（已保存到: {output_dir}）")
                return os.path.join(output_dir, f"{actual_pub}.pdf")
        else:
            print("❌ 下载失败")
            return None
    except Exception as e:
        print(f"❌ 下载出错: {e}")
        return None


def get_info(patent_number: str):
    """获取专利基本信息"""
    downloader = _get_downloader()
    if not downloader:
        return

    formatted = to_publication_format(patent_number)

    success, actual_pub = _try_fetch(formatted, downloader)

    if success:
        try:
            info = downloader.get_patent_info(actual_pub)
            if info:
                print(f"专利号: {patent_number}")
                if actual_pub != formatted:
                    print(f"公告号: {actual_pub}")
                print(f"标题: {info.title or 'N/A'}")
                print(f"申请人: {info.assignee or 'N/A'}")
                print(f"公开日: {info.publication_date or 'N/A'}")
                abstract = (info.abstract or 'N/A')[:300]
                print(f"摘要: {abstract}...")
                return
        except Exception:
            pass

    # 查不到信息时的提示
    print(f"❌ 未找到专利信息")
    if is_application_number(patent_number):
        print(f"   💡 提示：申请号不能直接在 Google Patents 查询。")
        print(f"   建议先用公告号，如: python cli.py google CN223081266U --info")


# ── 命令行入口 ──────────────────────────────────────────────────

def main():
    """命令行入口"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Google Patents 专利下载",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
专利号格式说明:
  公告号（推荐）: CN223081266U, CN118198150A
  申请号（自动转换）: 202421964517.8 → 自动查公告号

示例:
  python google_patents.py CN223081266U
  python google_patents.py 202421964517.8 -o ~/Downloads
  python google_patents.py CN223081266U --info
        """
    )

    parser.add_argument("patent", help="专利号（公告号或申请号）")
    parser.add_argument("-o", "--output", default=".", help="输出目录")
    parser.add_argument("--info", action="store_true", help="仅查询信息，不下载")

    args = parser.parse_args()

    print("=" * 60)
    print(f"📥 Google Patents 专利下载")
    print(f"   专利: {args.patent}")
    print("=" * 60)
    print()

    if args.info:
        get_info(args.patent)
    else:
        download_patent(args.patent, args.output)


if __name__ == "__main__":
    main()
