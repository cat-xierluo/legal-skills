#!/usr/bin/env python3
"""通义听悟内部 API 客户端 — 纯 HTTP，无需浏览器"""

import json
import os
import sys
import time
import uuid
from pathlib import Path

try:
    import requests
except ImportError:
    print("错误: 缺少 requests 库。请运行: pip3 install requests")
    sys.exit(1)

try:
    import oss2
except ImportError:
    oss2 = None

BASE_URL = "https://tingwu.aliyun.com/api"
SKILL_ROOT = Path(__file__).resolve().parent.parent
COOKIE_PATH = SKILL_ROOT / "config" / "cookies.json"

AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".wma", ".aac", ".ogg", ".amr", ".flac", ".aiff"}
VIDEO_EXTS = {".mp4", ".wmv", ".m4v", ".flv", ".rmvb", ".dat", ".mov", ".mkv", ".webm", ".avi", ".mpeg", ".3gp"}
ALL_EXTS = AUDIO_EXTS | VIDEO_EXTS

LANG_MAP = {"cn": "cn", "zh": "cn", "中文": "cn", "en": "en", "英文": "en", "英语": "en",
            "ja": "ja", "日文": "ja", "日语": "ja", "cant": "cant", "粤语": "cant",
            "cn_en": "cn_en", "中英": "cn_en", "中英文": "cn_en"}

MIME_MAP = {
    ".mp3": "audio/mpeg", ".wav": "audio/wav", ".m4a": "audio/mp4",
    ".aac": "audio/aac", ".ogg": "audio/ogg", ".flac": "audio/flac",
    ".mp4": "video/mp4", ".avi": "video/x-msvideo", ".mov": "video/quicktime",
    ".mkv": "video/x-matroska", ".webm": "video/webm",
}


def _trace_id():
    return uuid.uuid4().hex[:32]


class TingwuClient:
    def __init__(self, cookie_path=None):
        self.cookie_path = Path(cookie_path) if cookie_path else COOKIE_PATH
        self.session = requests.Session()
        self._load_cookies()

    def _load_cookies(self):
        if not self.cookie_path.exists():
            raise FileNotFoundError(
                f"Cookie 文件不存在: {self.cookie_path}\n"
                "请先运行: python3 scripts/login.py"
            )
        with open(self.cookie_path) as f:
            data = json.load(f)
        cookies = data.get("cookies", data)
        for name, value in cookies.items():
            self.session.cookies.set(name, value, domain=".aliyun.com")

    def _headers(self):
        return {
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "x-b3-traceid": _trace_id(),
            "x-b3-spanid": _trace_id()[:16],
            "x-b3-sampled": "1",
            "x-tw-canary": "",
            "Referer": "https://tingwu.aliyun.com/home",
        }

    def _post(self, path, body, params=None):
        url = f"{BASE_URL}{path}"
        resp = self.session.post(url, json=body, headers=self._headers(), params=params, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != "0":
            raise RuntimeError(f"API 错误 [{data.get('code')}]: {data.get('message')}")
        return data.get("data", data)

    def _get(self, path, params=None):
        url = f"{BASE_URL}{path}"
        resp = self.session.get(url, headers=self._headers(), params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != "0":
            raise RuntimeError(f"API 错误 [{data.get('code')}]: {data.get('message')}")
        return data.get("data", data)

    # --- Step 0: 认证检查 ---
    def check_auth(self):
        try:
            info = self._get("/account/v2/user/info", {"c": "web"})
            return {"valid": True, "user": info}
        except Exception as e:
            return {"valid": False, "error": str(e)}

    def get_account_info(self):
        return self._get("/tingwu/account/info", {"c": "web"})

    # --- Step 1: 获取上传凭证 ---
    def generate_put_link(self, file_path, lang="cn", role_split_num=4):
        path = Path(file_path)
        ext = path.suffix.lower()
        if ext not in ALL_EXTS:
            raise ValueError(f"不支持的文件格式: {ext}，支持: {', '.join(sorted(ALL_EXTS))}")

        file_size = path.stat().st_size
        file_name = path.stem[:150]
        file_type = "video" if ext in VIDEO_EXTS else "audio"
        is_video = ext in VIDEO_EXTS
        content_type = MIME_MAP.get(ext, "application/octet-stream")

        body = {
            "action": "generatePutLink",
            "version": "1.0",
            "taskId": f"local-{uuid.uuid4().hex[:16]}",
            "useSts": 1,
            "fileSize": file_size,
            "dirId": 0,
            "fileContentType": content_type,
            "tag": {
                "showName": file_name,
                "fileFormat": ext.lstrip("."),
                "fileType": "local",
                "lang": lang,
                "roleSplitNum": role_split_num,
                "translateSwitch": False,
                "transTargetValue": "",
                "originalFlag": 0,
                "originalTag": json.dumps({"isVideo": 1 if is_video else 0}),
            },
        }
        result = self._post("/trans/request", body, params={"generatePutLink": ""})
        return {
            "transId": result.get("transId"),
            "putLink": result.get("putLink"),
            "getLink": result.get("getLink"),
            "sts": result.get("sts"),
            "file_size": file_size,
            "file_name": file_name,
            "is_video": is_video,
        }

    # --- Step 2: 上传文件到 OSS ---
    def upload_to_oss(self, file_path, put_link_result):
        sts = put_link_result["sts"]
        if not sts:
            raise RuntimeError("generatePutLink 返回的 sts 为空")

        file_path = str(file_path)

        if oss2 is not None:
            auth = oss2.StsAuth(
                sts["accessKeyId"],
                sts["accessKeySecret"],
                sts["securityToken"],
            )
            bucket = oss2.Bucket(auth, sts["endpoint"], sts["bucket"])
            print(f"  正在上传到 OSS (使用 oss2 SDK)...")
            oss2.resumable_upload(
                bucket,
                sts["fileKey"],
                file_path,
                progress_callback=_oss_progress,
                num_threads=4,
            )
        else:
            _upload_via_requests(file_path, put_link_result)

        print("  上传完成")

    # --- Step 3: 确认上传 ---
    def sync_put_link(self, put_link_result, duration=None):
        file_link = put_link_result.get("putLink") or put_link_result.get("getLink", "")
        body = {
            "action": "syncPutLink",
            "version": "1.0",
            "fileLink": file_link,
            "fileSize": put_link_result["file_size"],
            "transId": put_link_result["transId"],
        }
        if duration:
            body["duration"] = duration
        return self._post("/trans/request", body, params={"syncPutLink": ""})

    # --- Step 4: 启动转录 ---
    def start_trans(self, trans_ids, lang="cn", role_split_num=4):
        if isinstance(trans_ids, str):
            trans_ids = [trans_ids]
        body = {
            "action": "startTrans",
            "version": "1.0",
            "userId": "",
            "transIds": trans_ids,
            "tag": {"lang": lang, "roleSplitNum": role_split_num},
        }
        return self._post("/trans/request", body, params={"startTrans": ""})

    # --- Step 5: 轮询状态 ---
    def get_trans_list(self, trans_id=None):
        body = {
            "action": "getTransList",
            "version": "1.0",
            "userId": "",
            "filter": {"status": [0, 1, 2, 3, 4, 11]},
            "preview": 1,
            "pageNo": 1,
            "pageSize": 1000,
        }
        result = self._post("/trans/request", body, params={"getTransList": ""})
        if trans_id and isinstance(result, list):
            for item in result:
                if item.get("transId") == trans_id:
                    return item
            return None
        return result

    def poll_until_done(self, trans_id, interval=10, timeout=3600):
        start = time.time()
        status_names = {0: "已完成", 1: "排队中", 2: "转录中", 3: "已完成", 4: "失败", 11: "上传中"}
        while time.time() - start < timeout:
            try:
                info = self.get_trans_list(trans_id)
                if info is None:
                    elapsed = time.time() - start
                    print(f"\r  任务暂未出现在列表中 (已等待 {elapsed:.0f}s)        ", end="", flush=True)
                    time.sleep(interval)
                    continue
                status = info.get("status", -1)
                name = status_names.get(status, f"未知({status})")

                extra = ""
                forecast = info.get("forecastTransDoneTime")
                now = info.get("serverCurrentTime")
                if forecast and now and status in (1, 2):
                    remain_s = max(0, (forecast - now) / 1000)
                    remain_m = remain_s / 60
                    extra = f" | 预计剩余: {remain_m:.1f} 分钟"

                duration = info.get("duration")
                if duration:
                    extra += f" | 音频时长: {duration / 60:.0f} 分钟"

                print(f"\r  转录状态: {name}{extra}        ", end="", flush=True)
                if status in (0, 3):
                    print()
                    return info
                if status == 4:
                    print()
                    raise RuntimeError(f"转录失败: {info.get('statusMsg', '未知原因')}")
            except RuntimeError:
                raise
            except Exception as e:
                print(f"\n  查询异常: {e}")
            time.sleep(interval)
        raise TimeoutError(f"转录超时 ({timeout}秒)")

    # --- Step 6: 获取结果 ---
    def get_trans_result(self, trans_id):
        body = {
            "action": "getTransResult",
            "version": "1.0",
            "transId": trans_id,
        }
        return self._post("/trans/getTransResult", body, params={"c": "web"})

    # --- 完整流程 ---
    def transcribe(self, file_path, lang="cn", role_split_num=4, poll_interval=10, poll_timeout=1800):
        print("[1/5] 获取上传凭证...")
        put_link = self.generate_put_link(file_path, lang=lang, role_split_num=role_split_num)
        trans_id = put_link["transId"]
        print(f"  任务ID: {trans_id}")

        print("[2/5] 上传文件到 OSS...")
        self.upload_to_oss(file_path, put_link)

        print("[3/5] 确认上传（自动启动转录）...")
        self.sync_put_link(put_link)

        print("[4/5] 等待转录完成...")
        task_info = self.poll_until_done(trans_id, interval=poll_interval, timeout=poll_timeout)

        print("[5/5] 获取转录结果...")
        result = self.get_trans_result(trans_id)

        return {
            "trans_id": trans_id,
            "task_info": task_info,
            "result": result,
            "duration": result.get("duration"),
            "word_count": result.get("wordCount"),
        }

    def submit_transcribe(self, file_path, lang="cn", role_split_num=4):
        """上传文件并启动转录，不等待结果。返回任务信息供异步轮询。"""
        print("[1/3] 获取上传凭证...")
        put_link = self.generate_put_link(file_path, lang=lang, role_split_num=role_split_num)
        trans_id = put_link["transId"]
        print(f"  任务ID: {trans_id}")

        print("[2/3] 上传文件到 OSS...")
        self.upload_to_oss(file_path, put_link)

        print("[3/3] 确认上传（自动启动转录）...")
        self.sync_put_link(put_link)

        return {
            "trans_id": trans_id,
            "file_name": Path(file_path).name,
            "lang": lang,
            "role_split_num": role_split_num,
        }

    # --- 智能分析 (Lab) ---
    def get_lab_info(self, trans_id):
        body = {"action": "getLabInfo", "version": "1.0", "transId": trans_id}
        return self._post("/lab/request", body, params={"getLabInfo": ""})

    def get_ppt_info(self, trans_id):
        """获取 PPT 提取结果（含每张幻灯片的图片 URL 和摘要）"""
        body = {
            "action": "getAllLabInfo",
            "content": ["labPptInfo"],
            "transId": trans_id,
        }
        url = f"{BASE_URL}/lab/getAllLabInfo"
        resp = self.session.post(url, json=body, headers=self._headers(), params={"c": "web"}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != "0":
            raise RuntimeError(f"API 错误 [{data.get('code')}]: {data.get('message')}")
        result = data.get("data", data)
        cards = result.get("labCardsMap", {}).get("labPptInfo", [])
        slides = []
        for card in cards:
            for content in card.get("contents", []):
                for item in content.get("contentValues", []):
                    slides.append({
                        "index": item.get("index", 0),
                        "time": item.get("time", 0),
                        "image_url": item.get("pictureOssLink", ""),
                        "thumbnail_url": item.get("pictureThumbnailOssLink", ""),
                        "summary": item.get("pptSummary", ""),
                        "id": item.get("id"),
                    })
        slides.sort(key=lambda s: s["time"])
        return slides

    def download_ppt_images(self, slides, output_dir, file_stem=None):
        """下载 PPT 幻灯片图片到指定目录。file_stem 非空时使用 {stem}_slides 子目录避免冲突。"""
        dir_name = f"{file_stem}_slides" if file_stem else "slides"
        slides_dir = Path(output_dir) / dir_name
        slides_dir.mkdir(parents=True, exist_ok=True)
        downloaded = []
        for slide in slides:
            if not slide["image_url"]:
                continue
            img_path = slides_dir / f"slide_{slide['index']:03d}.png"
            if img_path.exists():
                slide["local_path"] = img_path
                downloaded.append(slide)
                continue
            print(f"  下载幻灯片 {slide['index']}/{len(slides)}...")
            resp = self.session.get(slide["image_url"], timeout=60)
            resp.raise_for_status()
            img_path.write_bytes(resp.content)
            slide["local_path"] = img_path
            downloaded.append(slide)
        return downloaded

    def compress_slides(self, slides_dir, target_kb=100):
        """将 slides_dir 中的 PNG 图片压缩为 WebP 格式。

        逐张适配质量参数，确保每张图片在 target_kb KB 以内。
        压缩后删除原始 PNG 文件，返回新扩展名 '.webp'。
        """
        try:
            from PIL import Image
        except ImportError:
            print("  跳过压缩: 需要 Pillow 库 (pip3 install Pillow)")
            return ".png"

        slides_dir = Path(slides_dir)
        png_files = sorted(slides_dir.glob("slide_*.png"))
        if not png_files:
            return ".png"

        print(f"  压缩 {len(png_files)} 张幻灯片 (目标 <{target_kb}KB)...")
        compressed = 0
        for png_path in png_files:
            webp_path = png_path.with_suffix(".webp")
            try:
                img = Image.open(png_path)
                # 跳过已经小于目标的文件
                if png_path.stat().st_size <= target_kb * 1024:
                    # 重命名为 webp 但保持 PNG 数据（实际上保留原文件即可）
                    png_path.rename(webp_path)
                    # 真正转一下格式以保持一致性
                    img.save(str(webp_path), "WEBP", quality=95, lossless=False)
                    compressed += 1
                    continue

                # 二分搜索最佳质量：从高到低尝试
                lo, hi = 50, 95
                best_quality = hi
                while lo <= hi:
                    mid = (lo + hi) // 2
                    img.save(str(webp_path), "WEBP", quality=mid, lossless=False)
                    if webp_path.stat().st_size <= target_kb * 1024:
                        best_quality = mid
                        hi = mid - 1
                    else:
                        lo = mid + 1
                # 用找到的最佳质量重新保存
                img.save(str(webp_path), "WEBP", quality=best_quality, lossless=False)
                png_path.unlink()
                compressed += 1
            except Exception as e:
                print(f"  压缩失败 {png_path.name}: {e}")
                continue

        if compressed:
            total = sum(f.stat().st_size for f in slides_dir.glob("slide_*.webp"))
            print(f"  压缩完成: {compressed} 张, 总计 {total / 1024 / 1024:.1f}MB")

        # 压缩后更新 Markdown 中的图片引用（.png → .webp）
        self._update_md_slide_refs(slides_dir, ".webp")

        return ".webp"

    def _update_md_slide_refs(self, slides_dir, new_ext):
        """压缩后自动更新 Markdown 文件中的图片引用格式。

        根据 slides 目录名推导对应的 .md 文件并替换引用。
        """
        import re

        slides_dir = Path(slides_dir)
        dir_name = slides_dir.name

        # 推导 Markdown 文件路径：{stem}_slides → {stem}.md
        md_path = None
        if dir_name.endswith("_slides"):
            stem = dir_name[:-7]
            candidate = slides_dir.parent / f"{stem}.md"
            if candidate.exists():
                md_path = candidate

        # 回退：扫描父目录下所有引用了该 slides 目录的 .md 文件
        if not md_path:
            for md_file in slides_dir.parent.glob("*.md"):
                content = md_file.read_text(encoding="utf-8")
                if f"./{dir_name}/slide_" in content:
                    md_path = md_file
                    break

        if not md_path:
            return

        content = md_path.read_text(encoding="utf-8")
        # 精确替换：./{dir_name}/slide_XXX.png → ./{dir_name}/slide_XXX.webp
        updated = re.sub(
            rf'(\./{re.escape(dir_name)}/slide_\d{{3}})\.png\)',
            rf'\1{new_ext})',
            content,
        )
        if updated != content:
            md_path.write_text(updated, encoding="utf-8")
            count = len(re.findall(rf'\./{re.escape(dir_name)}/slide_\d{{3}}{re.escape(new_ext)}\)', updated))
            print(f"  已更新 {md_path.name} 中 {count} 处图片引用 (.png → {new_ext})")

    # --- 删除任务 ---
    def delete_trans(self, trans_ids, permanently=False):
        if isinstance(trans_ids, str):
            trans_ids = [trans_ids]
        body = {
            "action": "delTrans",
            "version": "1.0",
            "userId": "",
            "transIds": trans_ids,
            "deletePermanently": permanently,
        }
        return self._post("/trans/request", body, params={"delTrans": ""})


def _oss_progress(consumed, total):
    if total:
        pct = int(consumed / total * 100)
        print(f"\r  上传进度: {pct}%", end="", flush=True)


def _upload_via_requests(file_path, put_link_result):
    """备用上传方式：通过 PUT 直接上传（不使用 oss2 SDK）"""
    put_link = put_link_result.get("putLink")
    if not put_link:
        raise RuntimeError("无 putLink，需要 oss2 库进行 STS 上传。请运行: pip3 install oss2")

    ext = Path(file_path).suffix.lower()
    content_type = MIME_MAP.get(ext, "application/octet-stream")
    file_size = Path(file_path).stat().st_size

    print(f"  正在上传 (PUT 直传)...")
    with open(file_path, "rb") as f:
        resp = requests.put(
            put_link,
            data=f,
            headers={"Content-Type": content_type},
            timeout=600,
        )
    resp.raise_for_status()
