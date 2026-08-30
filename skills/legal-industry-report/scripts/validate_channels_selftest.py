#!/usr/bin/env python3
"""渠道稿门禁自测。"""

from __future__ import annotations

import tempfile
from pathlib import Path

from validate_channels import validate_channels


MOMENTS = """# 朋友圈文案
> DRAFT
本周有一项规则变化值得制造企业留意：新要求已经从征求意见进入正式执行阶段，重点影响产品上线前的内部核验。
- 先确认适用产品范围
- 再检查现有流程和合同
- 对窗口期内项目保留复核记录
来源：https://www.cac.gov.cn/a
本内容仅作一般信息分享，不构成针对具体事项的法律意见。
"""

WECHAT = """# 规则变化说明
> DRAFT
## 导语
本周有一项正式规则发布。
## 发生了什么
规则已发布：https://www.cac.gov.cn/a
## 为什么值得关注
影响产品上线流程。
## 给企业的提示
1. 核对适用范围。
## 信源
https://www.cac.gov.cn/a
## 免责声明
本文仅作一般信息分享，不构成针对具体事项的法律意见。
"""


def main() -> int:
    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        whitelist = root / "whitelist.txt"
        whitelist.write_text("cac.gov.cn\nnda.gov.cn\n", encoding="utf-8")
        moments = root / "朋友圈_制造业_2026-08-30_DRAFT.md"
        wechat = root / "公众号_制造业_2026-08-30_DRAFT.md"
        brief = root / "客户简报_制造业_2026-08-30_DRAFT.md"
        moments.write_text(MOMENTS, encoding="utf-8")
        wechat.write_text(WECHAT, encoding="utf-8")
        brief.write_text("DRAFT\nhttps://www.cac.gov.cn/a\n", encoding="utf-8")
        good = validate_channels(moments, wechat, whitelist, brief)
        print(f"[{'PASS' if good['status'] == 'PASS' else 'FAIL'}] 渠道正例: {good['findings']}")

        wechat.write_text(WECHAT.replace("cac.gov.cn", "example.com"), encoding="utf-8")
        bad = validate_channels(moments, wechat, whitelist, brief)
        rejected = any(item["id"] == "CHANNEL-WHITELIST" for item in bad["findings"])
        print(f"[{'PASS' if rejected else 'FAIL'}] 白名单反例: {bad['findings']}")
        wechat.write_text(WECHAT.replace("cac.gov.cn", "nda.gov.cn"), encoding="utf-8")
        drift = validate_channels(moments, wechat, whitelist, brief)
        drifted = any(item["id"] == "CHANNEL-SOURCE-DRIFT" for item in drift["findings"])
        print(f"[{'PASS' if drifted else 'FAIL'}] 渠道信源漂移反例: {drift['findings']}")
        return 0 if good["status"] == "PASS" and rejected and drifted else 1


if __name__ == "__main__":
    raise SystemExit(main())
