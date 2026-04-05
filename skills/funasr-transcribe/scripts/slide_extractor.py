#!/usr/bin/env python3
# -*- encoding: utf-8 -*-
"""
视频关键帧（PPT 幻灯片）提取模块

四层过滤流水线：
  视频 → 第1层：场景检测 + 定时兜底采样
      → 第2层：pHash 去重
      → 第3层：空白回查补帧
      → 第4层：最小间隔过滤 + 兜底帧清理

仅对视频文件生效，音频文件会被跳过。

依赖:
    pip install scenedetect[opencv] imagehash Pillow
"""

import os
from dataclasses import dataclass
from pathlib import Path

# 视频文件扩展名
VIDEO_EXTENSIONS = {'.mp4', '.avi', '.mov', '.mkv', '.wmv', '.webm'}


@dataclass
class SlideFrame:
    """提取的关键帧"""
    timestamp_ms: int       # 毫秒时间戳，用于与转录文本对齐
    image_path: str         # 保存的图片绝对路径
    time_label: str         # 可读标签如 "02m15s"
    relative_path: str = ""  # 相对于 Markdown 文件的路径
    description: str = ""      # 截图描述（用于 alt 文本）
    is_fallback: bool = False  # 是否为兜底帧


class SlideExtractor:
    """视频关键帧提取器

    四层过滤流水线:
        视频 → 场景检测+兜底采样 → pHash 去重 → 空白回查补帧 → 最终过滤

    Args:
        threshold: ContentDetector 灵敏度阈值（默认 20.0，值越低越灵敏）
        min_scene_len: 最小场景时长（秒），短于此间隔的切换会被过滤
        hash_threshold: pHash 汉明距离阈值，低于此值视为相同画面
        fallback_interval: 兜底采样间隔（秒），保证每 N 秒至少有一帧
        gap_threshold: 空白回查阈值（秒），间隔超过此值时触发二次扫描
    """

    def __init__(
        self,
        threshold: float = 20.0,
        min_scene_len: float = 3.0,
        hash_threshold: int = 12,
        fallback_interval: int = 180,
        gap_threshold: int = 300,
    ):
        self.threshold = threshold
        self.min_scene_len = min_scene_len
        self.hash_threshold = hash_threshold
        self.fallback_interval = fallback_interval
        self.gap_threshold = gap_threshold

    def extract(self, video_path: str, output_dir: str) -> list:
        """主入口：提取关键帧，返回按时间排序的 SlideFrame 列表"""
        ext = Path(video_path).suffix.lower()
        if ext not in VIDEO_EXTENSIONS:
            print(f"[slide_extractor] 跳过非视频文件: {video_path}")
            return []

        os.makedirs(output_dir, exist_ok=True)

        import cv2
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            print(f"[slide_extractor] 无法打开视频: {video_path}")
            return []
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration_ms = int(total_frames / fps * 1000)
        cap.release()

        # 第 1 层：场景检测 + 定时兜底采样
        raw_frames = self._detect_with_fallback(video_path, output_dir, fps, total_frames)
        if not raw_frames:
            print("[slide_extractor] 未检测到任何帧")
            return []
        print(f"[slide_extractor] 第1层（场景+兜底）: {len(raw_frames)} 个候选帧")

        # 第 2 层：pHash 去重
        deduped = self._deduplicate(raw_frames)
        print(f"[slide_extractor] 第2层（pHash去重）: {len(deduped)} 个帧")

        # 第 3 层：空白回查补帧
        backfilled = self._backfill_gaps(video_path, output_dir, deduped, fps, duration_ms)
        print(f"[slide_extractor] 第3层（空白回查）: {len(backfilled)} 个帧")

        # 第 4 层：最小间隔过滤 + 兜底帧清理
        filtered = self._final_filter(backfilled)
        print(f"[slide_extractor] 第4层（最终过滤）: {len(filtered)} 个关键帧")

        # 清理被过滤掉的图片文件
        kept_paths = {f.image_path for f in filtered}
        for f in raw_frames + backfilled:
            if f.image_path not in kept_paths and os.path.exists(f.image_path):
                os.remove(f.image_path)

        return filtered

    def _detect_with_fallback(self, video_path: str, output_dir: str,
                               fps: float, total_frames: int) -> list:
        """第 1 层：双通道合并（场景检测 + 定时兜底采样）"""
        import cv2

        frames = {}  # key: timestamp_ms, value: SlideFrame

        # --- 通道 A：PySceneDetect ---
        scene_frames = self._detect_scenes(video_path, output_dir)
        for f in scene_frames:
            if f.timestamp_ms not in frames:
                frames[f.timestamp_ms] = f

        # --- 通道 B：定时兜底采样 ---
        duration_ms = int(total_frames / fps * 1000)
        fallback_ms = self.fallback_interval * 1000
        cap = cv2.VideoCapture(video_path)
        idx = 1

        ts_ms = 0
        while ts_ms <= duration_ms:
            if ts_ms not in frames:
                frame_pos = int(ts_ms / 1000.0 * fps)
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_pos)
                ret, frame = cap.read()
                if ret:
                    ts_s = ts_ms / 1000.0
                    time_label = self._format_time_label(ts_s)
                    img_filename = f"slide_fb_{idx:03d}_{time_label}.jpg"
                    img_path = os.path.join(output_dir, img_filename)
                    cv2.imwrite(img_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                    frames[ts_ms] = SlideFrame(
                        timestamp_ms=ts_ms,
                        image_path=img_path,
                        time_label=time_label,
                        is_fallback=True,
                    )
                    idx += 1
            ts_ms += fallback_ms

        cap.release()

        # 按时间排序
        return sorted(frames.values(), key=lambda f: f.timestamp_ms)

    def _detect_scenes(self, video_path: str, output_dir: str) -> list:
        """场景检测子函数"""
        try:
            from scenedetect import SceneManager, open_video
            from scenedetect.detectors import ContentDetector
        except ImportError:
            print("[slide_extractor] 缺少依赖，请安装: pip install scenedetect[opencv]")
            return []

        try:
            video = open_video(video_path)
        except Exception as e:
            print(f"[slide_extractor] 无法打开视频: {e}")
            return []

        scene_manager = SceneManager()
        scene_manager.add_detector(
            ContentDetector(
                threshold=self.threshold,
                min_scene_len=int(self.min_scene_len * video.frame_rate) if video.frame_rate else 90,
            )
        )

        scene_manager.detect_scenes(video)
        scene_list = scene_manager.get_scene_list()

        if not scene_list:
            return []

        import cv2
        frames = []
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0

        for i, (start, _end) in enumerate(scene_list):
            frame_num = start.get_frames()
            timestamp_sec = frame_num / fps
            timestamp_ms = int(timestamp_sec * 1000)

            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
            ret, frame = cap.read()
            if not ret:
                continue

            time_label = self._format_time_label(timestamp_sec)
            img_filename = f"slide_{i + 1:03d}_{time_label}.jpg"
            img_path = os.path.join(output_dir, img_filename)

            cv2.imwrite(img_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 85])

            frames.append(SlideFrame(
                timestamp_ms=timestamp_ms,
                image_path=img_path,
                time_label=time_label,
            ))

        cap.release()
        return frames

    def _deduplicate(self, frames: list) -> list:
        """第 2 层：使用感知哈希去除视觉上相似的帧"""
        try:
            from PIL import Image
            import imagehash
        except ImportError:
            print("[slide_extractor] 缺少依赖，请安装: pip install imagehash Pillow")
            return frames

        if not frames:
            return frames

        result = []
        prev_hash = None

        for frame in frames:
            try:
                img = Image.open(frame.image_path)
                current_hash = imagehash.phash(img)

                if prev_hash is not None:
                    distance = current_hash - prev_hash
                    if distance < self.hash_threshold:
                        # 视觉上相似，跳过
                        continue

                prev_hash = current_hash
                result.append(frame)
            except Exception:
                result.append(frame)

        return result

    def _backfill_gaps(self, video_path: str, output_dir: str,
                       frames: list, fps: float, duration_ms: int) -> list:
        """第 3 层：扫描空白区域，二次检测或强制补帧"""
        if len(frames) < 2:
            return frames

        result = list(frames)
        gaps_to_fill = []

        # 找出所有大间隔
        for i in range(len(result) - 1):
            gap_ms = result[i + 1].timestamp_ms - result[i].timestamp_ms
            if gap_ms > self.gap_threshold * 1000:
                gaps_to_fill.append((result[i].timestamp_ms, result[i + 1].timestamp_ms))

        # 也检查开头和结尾的空白
        if result[0].timestamp_ms > self.gap_threshold * 1000:
            gaps_to_fill.append((0, result[0].timestamp_ms))
        if duration_ms - result[-1].timestamp_ms > self.gap_threshold * 1000:
            gaps_to_fill.append((result[-1].timestamp_ms, duration_ms))

        if not gaps_to_fill:
            return result

        print(f"[slide_extractor] 发现 {len(gaps_to_fill)} 个空白区域，开始回查...")

        import cv2
        cap = cv2.VideoCapture(video_path)
        backfill_frames = []
        idx = 1

        for start_ms, end_ms in gaps_to_fill:
            # 用更低阈值对该区域重新检测
            mid_ms = (start_ms + end_ms) // 2
            mid_frame_pos = int(mid_ms / 1000.0 * fps)

            # 尝试在中间位置采样
            cap.set(cv2.CAP_PROP_POS_FRAMES, mid_frame_pos)
            ret, frame = cap.read()
            if not ret:
                continue

            ts_s = mid_ms / 1000.0
            time_label = self._format_time_label(ts_s)
            img_filename = f"slide_bf_{idx:03d}_{time_label}.jpg"
            img_path = os.path.join(output_dir, img_filename)
            cv2.imwrite(img_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 85])

            backfill_frames.append(SlideFrame(
                timestamp_ms=mid_ms,
                image_path=img_path,
                time_label=time_label,
                is_fallback=True,
            ))
            idx += 1

        cap.release()

        # 合并并重新排序
        all_frames = result + backfill_frames
        all_frames.sort(key=lambda f: f.timestamp_ms)

        # 对补帧做 pHash 去重（只检查补帧与邻近帧）
        try:
            from PIL import Image
            import imagehash
        except ImportError:
            return all_frames

        final = []
        for frame in all_frames:
            if not frame.is_fallback:
                final.append(frame)
                continue

            # 补帧：检查与前一帧的 pHash 距离
            if final:
                try:
                    prev_img = Image.open(final[-1].image_path)
                    cur_img = Image.open(frame.image_path)
                    prev_h = imagehash.phash(prev_img)
                    cur_h = imagehash.phash(cur_img)
                    if cur_h - prev_h < self.hash_threshold:
                        # 视觉上确实没变化，删除补帧图片
                        if os.path.exists(frame.image_path):
                            os.remove(frame.image_path)
                        continue
                except Exception:
                    pass

            final.append(frame)

        return final

    def _final_filter(self, frames: list) -> list:
        """第 4 层：最小间隔过滤 + 兜底帧智能清理"""
        if not frames:
            return frames

        min_ms = int(self.min_scene_len * 1000)
        result = [frames[0]]

        for frame in frames[1:]:
            gap = frame.timestamp_ms - result[-1].timestamp_ms
            if gap >= min_ms:
                result.append(frame)
            elif frame.is_fallback and gap < min_ms:
                # 兜底帧距离前一帧太近，说明场景检测已覆盖，删除
                if os.path.exists(frame.image_path):
                    os.remove(frame.image_path)

        return result

    @staticmethod
    def _format_time_label(seconds: float) -> str:
        """将秒数格式化为可读标签，如 '02m15s'"""
        m = int(seconds) // 60
        s = int(seconds) % 60
        if m > 0:
            return f"{m:02d}m{s:02d}s"
        return f"{s:02d}s"

    @staticmethod
    def is_video_file(file_path: str) -> bool:
        """判断是否为视频文件"""
        return Path(file_path).suffix.lower() in VIDEO_EXTENSIONS
