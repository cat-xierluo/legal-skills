#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""抖音视频无登录下载器（video_id → aweme.snssdk.com 直连法）

无需 cookie / 登录态 / a_bogus 签名。利用抖音新旧 API 并存的窗口期：
旧版播放直连接口 aweme.snssdk.com/aweme/v1/play/ 仅凭 video_id 即返回 302 CDN 直链，
不走需要签名的 www.douyin.com 业务 API。

三步流程：
  1. 短链 → numeric_id（v.douyin.com 302 落到 www.douyin.com/video/<numeric>）
  2. SSR share 页 → video_id（iesdouyin.com/share/video/<numeric>/ 渲染出的 "uri":"v0..."）
  3. video_id → 302 CDN 直链 → 带 referer 下载 mp4

适用：公开视频。不适用：私密/仅好友可见、已删除、异地限制、直播/直播回放、图文笔记
（图文笔记走 download_douyin_note.py，本接口对图文只返回首图）。
直链有效期约 1-2 小时（CDN 时间戳签名过期），过期重跑本脚本即可续链。

原理依据：references/douyin-nocookie-approach.md（2026-08-02 实测可用）

使用方法:
    python download_douyin_video_nocookie.py "<url>" [--out-dir <dir>] [--ratio 540p|720p|1080p] [--out-name <name>]

示例:
    python download_douyin_video_nocookie.py "https://v.douyin.com/aAQgycBvBp0/"
    python download_douyin_video_nocookie.py "https://www.douyin.com/video/7665930064613199114" --ratio 1080p

输出:
    最后一行打印 SAVED_FILEPATH=<绝对路径>，便于 AI 与下游脚本（cubox/content-manager）解析。
"""

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

import requests

SCRIPT_DIR = Path(__file__).parent.parent
DEFAULT_OUT_DIR = SCRIPT_DIR / "downloads"

# iPhone UA：抖音 SSR 页与 v1/play 接口对移动端 UA 友好；
# Referer 必带 douyin.com，否则 CDN 返回 403。
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15"
HEADERS = {
    "User-Agent": UA,
    "Referer": "https://www.douyin.com/",
    "Accept": "*/*",
}

NUMERIC_RE = re.compile(r"/(?:share/)?video/(\d+)")
# video_id（页面里叫 uri）：抖音用 v 开头的「小写字母+数字」串，不是纯 hex
# （曾误用 v0[0-9a-f]+，遇到 g/h/i 等字符会在结尾 " 断言处失配，已修正）
URI_PATTERNS = [
    re.compile(r'"play_addr":\{"uri":"([^"]+)"'),  # 精确锚 play_addr，首选
    re.compile(r'"uri":"(v[0-9a-z]{10,})"'),        # 兜底：任意 v 开头 uri
]


def resolve_numeric_id(url: str) -> str | None:
    """从任意抖音链接解析 numeric_id。

    优先从原 URL 直接提取；若是短链（v.douyin.com），跟随 302 后从最终落点提取。
    落点是博主主页（/user/）时给出准确提示——主页不是单视频，本就无法下载。
    """
    m = NUMERIC_RE.search(url)
    if m:
        return m.group(1)
    try:
        resp = requests.head(url, headers=HEADERS, allow_redirects=True, timeout=15)
        m = NUMERIC_RE.search(resp.url)
        if m:
            return m.group(1)
        if re.search(r"/(?:share/)?user/", resp.url):
            print("[warning] 落点是博主主页链接（share/user/），不是单视频，无法下载")
        elif "douyin.com" not in resp.url:
            print(f"[warning] 短链 302 落到非抖音页面: {resp.url}")
    except Exception as e:
        print(f"[warning] 解析短链失败: {e}")
    return None


def fetch_video_id(numeric_id: str) -> str | None:
    """从 SSR share 页提取 video_id（页面 HTML 中渲染的 uri 字段）。"""
    share_url = f"https://www.iesdouyin.com/share/video/{numeric_id}/"
    try:
        resp = requests.get(share_url, headers=HEADERS, timeout=15)
        for pat in URI_PATTERNS:
            m = pat.search(resp.text)
            if m:
                return m.group(1)
    except Exception as e:
        print(f"[warning] 获取 SSR share 页失败: {e}")
    return None


def fetch_cdn_url(video_id: str, ratio: str = "540p") -> str | None:
    """用 video_id 换 CDN 直链。

    v1/play 正常返回 302，Location 即 CDN 直链；不跟随重定向以便取出 Location。
    """
    play_url = (
        f"https://aweme.snssdk.com/aweme/v1/play/?video_id={video_id}&ratio={ratio}&line=0"
    )
    try:
        resp = requests.get(play_url, headers=HEADERS, allow_redirects=False, timeout=15)
        if resp.status_code in (301, 302, 303, 307, 308):
            loc = resp.headers.get("Location", "")
            if loc:
                return loc
        # 极少数情况直接 200 返回视频流
        if resp.status_code == 200 and "video" in resp.headers.get("Content-Type", "").lower():
            return play_url
        print(f"[warning] v1/play 未返回 302，status={resp.status_code}（接口可能已被纳入签名墙）")
    except Exception as e:
        print(f"[warning] 调用 v1/play 失败: {e}")
    return None


def download(url: str, out_path: Path, referer: str = "https://www.douyin.com/") -> bool:
    """下载 CDN 直链到文件。

    优先 aria2c 多线程（16 连接 + 断点续传，大文件明显更快），未安装则回退 requests 单线程。
    抖音 CDN 校验 referer，两种方式都带上。
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if shutil.which("aria2c"):
        cmd = [
            "aria2c", "-x16", "-s16", "-k1M",
            "--max-tries=3", "--retry-wait=3", "--continue=true",
            "--auto-file-renaming=false",
            "--console-log-level=notice",
            f"--header=Referer: {referer}",
            f"--header=User-Agent: {UA}",
            "-d", str(out_path.parent),
            "-o", out_path.name,
            url,
        ]
        try:
            r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            sys.stdout.write(r.stdout)
            if r.returncode == 0 and out_path.exists():
                return True
            print(f"[warning] aria2c 未成功（rc={r.returncode}），回退单线程")
        except Exception as e:
            print(f"[warning] aria2c 调用异常，回退单线程: {e}")

    # requests 兜底（单线程流式）
    try:
        with requests.get(url, headers=HEADERS, stream=True, timeout=60) as r:
            r.raise_for_status()
            with open(out_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=64 * 1024):
                    if chunk:
                        f.write(chunk)
            return True
    except Exception as e:
        print(f"[error] 下载失败: {e}")
        return False


def ffprobe_check(path: Path) -> None:
    """可选：用 ffprobe 确认产物可播放。未安装则跳过，不影响下载结果。"""
    try:
        subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration,size,bit_rate",
                "-of", "default=noprint_wrappers=1",
                str(path),
            ],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True,
        )
        print("[info] ffprobe 校验通过")
    except Exception:
        print("[info] ffprobe 未安装或校验跳过（不影响下载结果）")


def main() -> int:
    ap = argparse.ArgumentParser(description="抖音视频无登录下载器")
    ap.add_argument("url", help="抖音视频链接（短链 / www.douyin.com/video/ / iesdouyin share 均可）")
    ap.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR), help=f"输出目录（默认 {DEFAULT_OUT_DIR}）")
    ap.add_argument(
        "--ratio", default="540p", choices=["540p", "720p", "1080p"],
        help="清晰度（默认 540p；部分老视频无 1080 源会自动回退）",
    )
    ap.add_argument("--out-name", default="", help="自定义文件名（不含扩展名）；默认 douyin_<numeric_id>")
    args = ap.parse_args()

    out_dir = Path(args.out_dir).expanduser().resolve()

    print(f"[1/4] 解析链接: {args.url}")
    numeric = resolve_numeric_id(args.url)
    if not numeric:
        print("[error] 无法解析 numeric_id（链接已删除/受异地限制，或为主页、聚合页等非单视频链接）")
        return 1
    print(f"      numeric_id = {numeric}")

    print("[2/4] 提取 video_id（SSR share 页）")
    video_id = fetch_video_id(numeric)
    if not video_id:
        print("[error] 无法提取 video_id（私密/仅好友可见视频的 SSR 页不渲染 play_addr）")
        return 1
    print(f"      video_id  = {video_id}")

    print(f"[3/4] 换取 CDN 直链（ratio={args.ratio}）")
    cdn = fetch_cdn_url(video_id, args.ratio)
    if not cdn:
        print("[error] 未拿到 CDN 直链（接口可能已纳入签名墙，参见 references 中的监控信号）")
        return 1
    print(f"      CDN 直链长度 = {len(cdn)}")

    name = args.out_name or f"douyin_{numeric}"
    out_path = (out_dir / f"{name}.mp4").resolve()

    print(f"[4/4] 下载 → {out_path}")
    if not download(cdn, out_path):
        return 1

    size = out_path.stat().st_size
    print(f"\n[完成] {size / 1024 / 1024:.2f} MB → {out_path}")
    ffprobe_check(out_path)
    print(f"SAVED_FILEPATH={out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
