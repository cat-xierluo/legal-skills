#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
图表处理模块
处理 Mermaid 等图表的渲染与转换
"""

import os
import re
import subprocess
import shutil
import time
from PIL import Image

# 导入配置模块
from config import get_config

# 导入图片处理函数（延迟导入避免循环）
# from md2word import insert_image_to_word


def preprocess_mermaid_code(mermaid_code: str) -> str:
    """预处理Mermaid源码，避免Mermaid v11 对标签内Markdown解析导致的错误"""
    s = mermaid_code

    # 反引号替换，避免 codespan 被解析
    s = s.replace("`", "'")

    # 1) 针对节点标签内部：有序列表 1. -> 1:
    def _repl_number_dot(m: re.Match) -> str:
        brace = m.group('brace')
        quote = m.group('quote') or ''
        num = m.group('num')
        return f"{brace}{quote}{num}: "

    s = re.sub(r"(?m)(?P<brace>[\[\({\>])(?P<quote>\"?\s*)(?P<num>\d+)\.\s", _repl_number_dot, s)

    # 2) 针对节点标签内部：无序列表 - / * -> •
    def _repl_bullet(m: re.Match) -> str:
        brace = m.group('brace')
        quote = m.group('quote') or ''
        return f"{brace}{quote}• "

    s = re.sub(r"(?m)(?P<brace>[\[\({\>])(?P<quote>\"?\s*)[-*]\s", _repl_bullet, s)

    # 3) 兜底：整行以列表开头的情况（极少出现在Mermaid内，但保留以防万一）
    s = re.sub(r"(?m)^(\s*)-\s+", r"\1• ", s)
    s = re.sub(r"(?m)^(\s*)\*\s+", r"\1• ", s)
    s = re.sub(r"(?m)^(\s*)(\d+)\.\s+", r"\1\2: ", s)

    return s


def try_local_mermaid_render(insert_image_func, get_image_path_func, mermaid_code, md_file_path):
    """尝试使用本地mermaid-cli渲染图表

    Args:
        insert_image_func: 插入图片到Word的函数
        get_image_path_func: 获取图片输出路径的函数
        mermaid_code: Mermaid源码
        md_file_path: Markdown文件路径
    """

    # 为Mermaid文件和输出图片准备路径
    timestamp = str(int(time.time() * 1000))
    mmd_filename = f"mermaid-src-{timestamp}.mmd"
    png_filename = f"mermaid-chart-{timestamp}.png"

    # 获取保存图片的最终路径
    output_png_path = get_image_path_func(md_file_path, png_filename)
    if not output_png_path:
        print("⚠️ 无法获取图片输出路径，跳过本地渲染。")
        return False

    # 临时文件放在脚本所在目录，避免 cwd 不一致导致路径问题
    script_dir = os.path.dirname(os.path.abspath(__file__))
    temp_mmd_path = os.path.join(script_dir, mmd_filename)

    try:
        print("🖥️ 尝试本地Mermaid渲染...")

        # 创建临时的.mmd文件
        with open(temp_mmd_path, 'w', encoding='utf-8') as f:
            f.write(mermaid_code)

        # 检查 mmdc 命令：优先环境变量 MMDCCMD，其次脚本同目录 node_modules，再其次系统 PATH
        mmdc_env = os.environ.get('MMDCCMD', '').strip()
        mmdc_path = mmdc_env if mmdc_env else os.path.join(script_dir, "node_modules", ".bin", "mmdc")
        if not os.path.exists(mmdc_path):
            mmdc_path = shutil.which("mmdc") or ""
        if not mmdc_path:
            print("⚠️ 本地 mmdc 命令未找到（已跳过本地渲染）")
            return False

        # 使用mmdc命令生成高分辨率PNG图片
        abs_in = os.path.abspath(temp_mmd_path)
        abs_out = os.path.abspath(output_png_path)
        cfg = os.path.join(script_dir, "mermaid-config.json")
        cmd = [mmdc_path, "-i", abs_in, "-o", abs_out, "-t", "neutral", "-w", "2200", "-H", "1500", "--scale", "2.0"]
        if os.path.exists(cfg):
            cmd.extend(["-c", cfg])

        print(f"🔧 执行命令: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            print(f"⚠️ mmdc 命令执行失败: {result.stderr}")
            return False

        # 检查生成的PNG文件是否存在
        if not os.path.exists(output_png_path):
            print("⚠️ PNG文件未生成")
            return False

        # 加载图片并插入Word
        image = Image.open(output_png_path)
        insert_image_func(image)

        print(f"✅ 本地Mermaid图表渲染成功！图片已保存至: {os.path.relpath(output_png_path)}")
        return True

    except subprocess.TimeoutExpired:
        print("⚠️ mmdc命令执行超时")
        return False
    except Exception as e:
        print(f"⚠️ 本地渲染失败: {e}")
        return False
    finally:
        # 无论成功与否，都清理临时的mmd文件
        if os.path.exists(temp_mmd_path):
            try:
                os.unlink(temp_mmd_path)
            except:
                pass


def create_simple_diagram_text(add_paragraph_func, set_format_func, mermaid_code):
    """创建简化的流程图文本描述"""
    p = add_paragraph_func()
    run = p.add_run("【流程图】")
    run.bold = True

    # 解析节点和连接关系
    lines = mermaid_code.split('\n')
    connections = []

    for line in lines:
        line = line.strip()
        if '-->' in line or '->' in line:
            parts = line.split('-->' if '-->' in line else '->')
            if len(parts) == 2:
                from_node = parts[0].strip()
                to_node = parts[1].strip()
                connections.append(f"{from_node} → {to_node}")

    # 添加解析结果
    if connections:
        p.add_run("\n主要流程:")
        for conn in connections[:8]:  # 最多显示8个连接
            p.add_run(f"\n• {conn}")

    set_format_func(p)


def create_simple_pie_text(add_paragraph_func, set_format_func, mermaid_code):
    """创建简化的饼图文本描述"""
    p = add_paragraph_func()
    run = p.add_run("【数据分析】")
    run.bold = True

    # 解析饼图数据
    lines = mermaid_code.split('\n')
    for line in lines:
        if ':' in line and '"' in line:
            # 解析数据项
            match = re.search(r'"([^"]+)"\s*:\s*(\d+(?:\.\d+)?)', line)
            if match:
                label, value = match.groups()
                p.add_run(f"\n• {label}: {value}")

    set_format_func(p)


def create_simple_gantt_text(add_paragraph_func, set_format_func, mermaid_code):
    """创建简化的甘特图文本描述"""
    p = add_paragraph_func()
    run = p.add_run("【时间安排】")
    run.bold = True

    # 解析甘特图任务
    lines = mermaid_code.split('\n')
    current_section = ""

    for line in lines:
        line = line.strip()
        if line.startswith('section '):
            current_section = line.replace('section ', '')
            p.add_run(f"\n\n{current_section}:")
        elif ':' in line and not line.startswith('title'):
            # 解析任务
            task = line.split(':')[0].strip()
            p.add_run(f"\n• {task}")

    set_format_func(p)


def create_fallback_text(add_paragraph_func, set_format_func, mermaid_code):
    """创建后备文本方案"""
    # 解析图表类型并创建简化版本
    if 'graph' in mermaid_code.lower():
        create_simple_diagram_text(add_paragraph_func, set_format_func, mermaid_code)
    elif 'pie' in mermaid_code.lower():
        create_simple_pie_text(add_paragraph_func, set_format_func, mermaid_code)
    elif 'gantt' in mermaid_code.lower():
        create_simple_gantt_text(add_paragraph_func, set_format_func, mermaid_code)
    else:
        # 默认处理
        p = add_paragraph_func()
        run = p.add_run("【图表内容】")
        run.bold = True
        p.add_run("\n" + mermaid_code)
        set_format_func(p)


def create_mermaid_chart(doc, insert_image_func, get_image_path_func, add_paragraph_func, set_format_func, mermaid_code, md_file_path):
    """将Mermaid图表转换为图片并插入Word文档（本地渲染优先）

    Args:
        doc: Word文档对象
        insert_image_func: 插入图片的函数
        get_image_path_func: 获取图片路径的函数
        add_paragraph_func: 添加段落的函数
        set_format_func: 设置段落格式的函数
        mermaid_code: Mermaid源码
        md_file_path: Markdown文件路径
    """

    # 预处理，规避 Mermaid 11 对列表/反引号的 Markdown 解析造成的报错
    mermaid_code = preprocess_mermaid_code(mermaid_code)

    # 首先尝试本地渲染
    local_success = try_local_mermaid_render(insert_image_func, get_image_path_func, mermaid_code, md_file_path)
    if local_success:
        return

    # 仅使用本地渲染：失败则改为文本，不再尝试在线服务
    print("⚠️ 本地渲染失败，已禁用在线服务，使用文本替代")
    create_fallback_text(add_paragraph_func, set_format_func, mermaid_code)
