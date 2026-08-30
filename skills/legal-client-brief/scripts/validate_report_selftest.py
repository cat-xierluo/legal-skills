#!/usr/bin/env python3
"""报告门禁的正例、失败例与窗口逃逸例。"""

from __future__ import annotations

import tempfile
from pathlib import Path

from validate_report import validate


REPORT_OK = """# 行业报告 · 人工智能
本报告不构成针对具体事项的法律意见。
## 一、执行摘要
判断。[P1] https://www.cac.gov.cn/a
## 二、研究边界与方法
方法。
## 三、行业结构与市场
结构。[P3] https://www.caict.ac.cn/b
## 四、竞争格局与代表企业
企业。
## 五、政策监管与区域
政策。
## 六、法律风险与争议
风险。
## 七、服务机会与行动建议
建议。
## 八、附录与信源
信源。
"""

BRIEF_OK = """# 客户简报
> DRAFT
## 一、编辑说明与适用范围
本简报不构成针对具体事项的法律意见。
## 二、本期一句话
有一项变化。
## 三、重点变化
### 01
- 发生日期：2026-08-28
- 相对上期的新变化：新增正式规则。
- 证据：https://www.cac.gov.cn/a
## 四、客户相关性
影响上线流程。
## 五、行动建议
核对流程。
## 六、案例观察
本期未收录可核验案例。
## 七、信源与核验
https://www.cac.gov.cn/a
"""


def main() -> int:
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        whitelist = root / "whitelist.txt"
        whitelist.write_text("cac.gov.cn\n", encoding="utf-8")
        report = root / "行业报告.md"
        report.write_text(REPORT_OK, encoding="utf-8")
        brief = root / "客户简报_weekly_2026-08-30_DRAFT.md"
        brief.write_text(BRIEF_OK, encoding="utf-8")

        cases = [
            ("正式报告正例", validate(report, "report"), True, None),
            ("客户简报正例", validate(brief, "brief", whitelist, "2026-08-24", "2026-08-30"), True, None),
        ]
        bad_report = root / "行业报告_坏.md"
        bad_report.write_text(REPORT_OK.replace("判断。", "{待填}"), encoding="utf-8")
        cases.append(("占位符反例", validate(bad_report, "report"), False, "REPORT-PLACEHOLDERS"))
        bad_brief = root / "客户简报_daily_2026-08-30_DRAFT.md"
        bad_brief.write_text(BRIEF_OK.replace("2026-08-28", "2026-07-01"), encoding="utf-8")
        cases.append(("窗口逃逸反例", validate(bad_brief, "brief", whitelist, "2026-08-24", "2026-08-30"), False, "BRIEF-WINDOW"))
        rejected = root / "客户简报_event_2026-08-30_DRAFT.md"
        rejected.write_text(BRIEF_OK.replace("cac.gov.cn", "example.com"), encoding="utf-8")
        cases.append(("白名单反例", validate(rejected, "brief", whitelist, "2026-08-24", "2026-08-30"), False, "BRIEF-WHITELIST"))

        failed = False
        for name, result, expected_pass, expected_id in cases:
            ids = {item["id"] for item in result.get("findings", [])}
            ok = (result.get("status") == "PASS") == expected_pass and (expected_id is None or expected_id in ids)
            print(f"[{'PASS' if ok else 'FAIL'}] {name}: {result.get('status')} {sorted(ids)}")
            failed = failed or not ok
        return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
