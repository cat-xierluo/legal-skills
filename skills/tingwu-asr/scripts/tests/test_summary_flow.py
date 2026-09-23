#!/usr/bin/env python3
"""验证 local-asr 摘要脚本路径及已有 JSON 的注入和校验。"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent  # scripts/ 目录（tests/ 的上一级）
SKILL_ROOT = SCRIPTS.parent
SUMMARY_PY = SKILL_ROOT.parent / "local-asr" / "scripts" / "summary.py"

md_tpl = "# 转录：测试\n\n> 时长: 60秒 | 字数: 100\n\n## 转录内容\n\n发言人1 00:00\n这是测试发言内容。\n"

tmp = Path(tempfile.mkdtemp(prefix="tingwu_summary_test_"))
ok = True
try:
    # Case 1: 无 summary json —— 记录当前脚本的错误路径，不将其算作注入成功。
    md1 = tmp / "case1.md"
    md1.write_text(md_tpl, encoding="utf-8")
    r1 = subprocess.run(
        [sys.executable, str(SUMMARY_PY), "inject", str(md1), str(tmp / "case1.json")],
        capture_output=True, text=True, timeout=60,
    )
    print(f"[case1 无json] rc={r1.returncode} out={r1.stdout.strip()[:80]} err={r1.stderr.strip()[:120]}")
    print(f"  SUMMARY_PY={SUMMARY_PY} exists={SUMMARY_PY.exists()}")
    if not (SUMMARY_PY.is_file() and r1.returncode == 1 and "总结文件不存在" in r1.stdout):
        ok = False

    # Case 2: 有 summary json —— 真实注入成功
    md2 = tmp / "case2.md"
    md2.write_text(md_tpl, encoding="utf-8")
    summary = {
        "full_summary": "这是一段测试全文总结，交代背景、问题与行动建议，超过一定长度以验证段落格式化逻辑。",
        "speaker_summary": [{"speaker_order": "发言人1", "speaker_name": "未知", "summary": "发言人1的测试总结，涵盖观点与依据。"}],
        "highlights": ["重点一：测试重点内容"],
        "keywords": ["测试", "总结"],
    }
    (tmp / "case2.json").write_text(json.dumps(summary, ensure_ascii=False), encoding="utf-8")
    r2 = subprocess.run(
        [sys.executable, str(SUMMARY_PY), "inject", str(md2), str(tmp / "case2.json")],
        capture_output=True, text=True, timeout=60,
    )
    injected = "AI-SUMMARY:START" in md2.read_text(encoding="utf-8")
    print(f"[case2 有json] rc={r2.returncode} injected={injected} out={r2.stdout.strip()[:60]}")
    if not (r2.returncode == 0 and injected):
        ok = False

    # Case 3: verify 命令应识别注入结果
    r3 = subprocess.run(
        [sys.executable, str(SUMMARY_PY), "verify", str(md2)],
        capture_output=True, text=True, timeout=60,
    )
    print(f"[case3 verify] rc={r3.returncode} out={r3.stdout.strip().splitlines()[0][:60]}")
    if r3.returncode != 0:
        ok = False
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("ALL PASS" if ok else "FAILED")
sys.exit(0 if ok else 1)
