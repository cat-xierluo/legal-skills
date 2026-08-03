#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Universal media downloader for video sites and podcasts.

This script is designed to be called by AnyGen as a deterministic helper.
It relies on yt-dlp, which supports many video sites (YouTube/Bilibili/Douyin, etc.)
AND can often download podcast audio when the page exposes a direct audio URL.

Examples:
  # Download best video+audio (mp4)
  python scripts/download_media.py "https://www.youtube.com/watch?v=xxxx"

  # Download audio only (mp3)
  python scripts/download_media.py --audio-only --audio-format mp3 "https://www.xiaoyuzhoufm.com/episode/xxxx"

  # Download with subtitles (auto-detect all available)
  python scripts/download_media.py --subtitles "https://www.youtube.com/watch?v=xxxx"

  # Download with Chinese subtitles only
  python scripts/download_media.py --subtitles --sub-lang "zh" "https://www.youtube.com/watch?v=xxxx"

  # Use cookies when needed (e.g., Douyin/Bilibili/YouTube age-gated)
  python scripts/download_media.py --cookies "/path/to/cookies.txt" "<URL>"

Output:
  - Prints the final saved filepath (absolute) as the last line: SAVED_FILEPATH=<path>
"""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from pathlib import Path

# Default output directory: relative to skill root
SCRIPT_DIR = Path(__file__).parent.parent
DEFAULT_OUT_DIR = SCRIPT_DIR / "downloads"


def run(cmd: list[str]) -> tuple[int, str]:
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return p.returncode, p.stdout


def main() -> int:
    parser = argparse.ArgumentParser(description="Download video/audio by URL using yt-dlp")
    parser.add_argument("url", help="Video or podcast episode URL")

    parser.add_argument(
        "--out-dir",
        default=str(DEFAULT_OUT_DIR),
        help=f"Output directory (default: {DEFAULT_OUT_DIR})",
    )
    parser.add_argument(
        "--cookies",
        default="",
        help="Path to cookies.txt (Netscape format). Useful when 403/login required.",
    )
    parser.add_argument(
        "--cookies-from-browser",
        default="",
        help="Browser to read cookies from directly (chrome/firefox/safari/edge). "
             "Avoids manually exporting cookies.txt — useful for Bilibili 412, "
             "YouTube age-gating, or Douyin with login. Mutually exclusive with --cookies.",
    )
    parser.add_argument(
        "--proxy",
        default="",
        help="Proxy URL, e.g. socks5://127.0.0.1:7890 or http://127.0.0.1:7890",
    )

    parser.add_argument(
        "--audio-only",
        action="store_true",
        help="Extract audio only (no video). For podcasts, this is usually what you want.",
    )
    parser.add_argument(
        "--audio-format",
        default="mp3",
        help="Audio format when --audio-only is set (default: mp3)",
    )

    parser.add_argument(
        "--subtitles",
        action="store_true",
        help="Download subtitles if available.",
    )
    parser.add_argument(
        "--sub-lang",
        default="all",
        help="Subtitle language(s) to download (default: all, e.g., 'zh,en')",
    )

    args = parser.parse_args()

    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    # Output template: keep title short + id to avoid collisions
    outtmpl = str(out_dir / "%(title).120B_%(id)s.%(ext)s")

    cmd = [
        "yt-dlp",
        "--no-playlist",
        "--js-runtimes",
        "node",
        "-o",
        outtmpl,
        "--print",
        "after_move:filepath",
    ]

    if args.cookies and args.cookies_from_browser:
        parser.error("--cookies 与 --cookies-from-browser 互斥，请二选一。")

    if args.cookies:
        cookies_path = Path(args.cookies).expanduser().resolve()
        if not cookies_path.exists():
            raise FileNotFoundError(f"cookies file not found: {cookies_path}")
        cmd.extend(["--cookies", str(cookies_path)])

    if args.cookies_from_browser:
        cmd.extend(["--cookies-from-browser", args.cookies_from_browser])

    if args.proxy:
        cmd.extend(["--proxy", args.proxy])

    if args.audio_only:
        cmd.extend([
            "--extract-audio",
            "--audio-format",
            args.audio_format,
            "--audio-quality",
            "0",
        ])
    else:
        # Prefer mp4 for convenience (may still be webm depending on source)
        cmd.extend(["--merge-output-format", "mp4"])

    if args.subtitles:
        cmd.extend([
            "--write-sub",
            "--sub-langs",
            args.sub_lang,
        ])

    cmd.append(args.url)

    rc, out = run(cmd)

    # Echo full yt-dlp output for debugging.
    sys.stdout.write(out)

    if rc != 0:
        # 抖音域名 + 未带 cookies + 非纯音频：yt-dlp 撞签名墙时，自动 fallback 到
        # 无登录直连（aweme.snssdk.com/v1/play，仅需 video_id，不要 a_bogus 签名）。
        # 用户主动传 --cookies 时走登录态，不抢戏；--audio-only 时保守不走（接口只保证视频流）。
        from urllib.parse import urlparse

        host = (urlparse(args.url).hostname or "").lower()
        is_douyin = any(d in host for d in ("douyin.com", "iesdouyin.com", "snssdk.com"))
        if is_douyin and not args.cookies and not args.audio_only:
            sys.stdout.write(
                "\n[download_media] yt-dlp 在抖音失败，自动尝试无登录直连 fallback "
                "（aweme.snssdk.com/v1/play）...\n"
            )
            nocookie_script = Path(__file__).parent / "download_douyin_video_nocookie.py"
            fb_cmd = [
                sys.executable, str(nocookie_script), args.url,
                "--out-dir", str(out_dir),
            ]
            fb_rc, fb_out = run(fb_cmd)
            sys.stdout.write(fb_out)
            if fb_rc == 0:
                for ln in reversed([l.strip() for l in fb_out.splitlines() if l.strip()]):
                    if ln.startswith("SAVED_FILEPATH="):
                        sys.stdout.write(f"\nSAVED_FILEPATH={ln.split('=', 1)[1].strip()}\n")
                        return 0
                # 兜底：取输出目录最新文件
                files = sorted(
                    [p for p in out_dir.glob('*') if p.is_file()],
                    key=lambda p: p.stat().st_mtime, reverse=True,
                )
                if files:
                    sys.stdout.write(f"\nSAVED_FILEPATH={files[0]}\n")
                    return 0
            sys.stdout.write("[download_media] 无登录 fallback 也失败，回到 yt-dlp 报错。\n")

        sys.stderr.write("\n[download_media] yt-dlp failed. Command was:\n")
        sys.stderr.write("  " + " ".join(shlex.quote(c) for c in cmd) + "\n")
        return rc

    # yt-dlp prints the moved file path via --print after_move:filepath.
    # Usually the last non-empty line.
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    saved = ""
    if lines:
        cand = lines[-1]
        if os.path.exists(cand):
            saved = cand

    if saved:
        sys.stdout.write(f"\nSAVED_FILEPATH={saved}\n")
    else:
        # Fallback: pick newest file in out_dir
        files = sorted([p for p in out_dir.glob('*') if p.is_file()], key=lambda p: p.stat().st_mtime, reverse=True)
        if files:
            saved = str(files[0])
            sys.stdout.write(f"\nSAVED_FILEPATH={saved}\n")
        else:
            sys.stdout.write("\nSAVED_FILEPATH=\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
