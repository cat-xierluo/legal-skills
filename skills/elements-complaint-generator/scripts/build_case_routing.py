#!/usr/bin/env python3
"""案由路由表生成器（T3）：从 templates-manifest.json 生成 references/case-routing.md。

输出 68 案由 ×（树 / 文书类型 / 册 / 规则支持 / reference / 识别关键词提示）。
关键词列仅作 Agent 案由匹配的提示锚点（Agent 语义匹配为主），高频案由附别名。

用法
----
python scripts/build_case_routing.py [--manifest templates/templates-manifest.json] \
    [--output references/case-routing.md]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# 精调案由：起诉状树全名 → (case-type key, reference 文档)
SUPPORTED_TREES = {
    "05-离婚纠纷-民事起诉状": ("05-divorce", "case-types/05-divorce.md"),
    "09-民间借贷纠纷-民事起诉状": ("09-private-lending", "case-types/09-private-lending.md"),
    "06-买卖合同纠纷-民事起诉状": ("06-sale", "skeletons/06-买卖合同纠纷-民事起诉状.md（精调规则在 fill_template）"),
    "15-劳动争议纠纷-民事起诉状": ("15-labor", "skeletons/15-劳动争议纠纷-民事起诉状.md（精调规则在 fill_template）"),
    "21-机动车交通事故责任纠纷-民事起诉状": ("21-traffic", "skeletons/21-机动车交通事故责任纠纷-民事起诉状.md（精调规则在 fill_template）"),
    "22-侵害著作权及邻接权纠纷-民事起诉状": ("22-copyright", "case-types/22-copyright.md"),
    "23-侵害商标权纠纷-民事起诉状": ("23-trademark", "case-types/23-trademark.md"),
    "27-侵害商业秘密纠纷-民事起诉状": ("27-tradesecret", "case-types/27-tradesecret.md"),
    "24-侵害发明专利权纠纷-民事起诉状": ("24-patent", "case-types/24-patent.md"),
    "28-技术合同纠纷-民事起诉状": ("28-tech", "case-types/28-tech.md"),
    "13-建设工程施工合同纠纷-民事起诉状": ("13-construction", "case-types/13-construction.md"),
    "08-金融借款合同纠纷-民事起诉状": ("08-loan", "case-types/08-loan.md"),
    "10-信用卡纠纷-民事起诉状": ("10-creditcard", "case-types/10-creditcard.md"),
    "07-房屋买卖合同纠纷-民事起诉状": ("07-house-sale", "skeletons/07-房屋买卖合同纠纷-民事起诉状.md"),
    "11-房屋租赁合同纠纷-民事起诉状": ("11-lease", "skeletons/11-房屋租赁合同纠纷-民事起诉状.md"),
    "14-物业服务合同纠纷-民事起诉状": ("14-property", "skeletons/14-物业服务合同纠纷-民事起诉状.md"),
    "12-融资租赁合同纠纷-民事起诉状": ("12-lease-finance", "skeletons/12-融资租赁合同纠纷-民事起诉状.md"),
    "16-证券虚假陈述责任纠纷-民事起诉状": ("16-securities-fraud", "skeletons/16-证券虚假陈述责任纠纷-民事起诉状.md"),
    "17-财产损失保险合同纠纷-民事起诉状": ("17-property-loss", "skeletons/17-财产损失保险合同纠纷-民事起诉状.md"),
    "18-责任保险合同纠纷-民事起诉状": ("18-liability", "skeletons/18-责任保险合同纠纷-民事起诉状.md"),
    "19-保证保险合同纠纷-民事起诉状": ("19-guarantee", "skeletons/19-保证保险合同纠纷-民事起诉状.md"),
    "20-人身保险合同纠纷-民事起诉状": ("20-personal", "skeletons/20-人身保险合同纠纷-民事起诉状.md"),
    "25-侵害外观设计专利权纠纷-民事起诉状": ("25-design-patent", "skeletons/25-侵害外观设计专利权纠纷-民事起诉状.md"),
    "29-不正当竞争纠纷-民事起诉状": ("29-unfair-competition", "skeletons/29-不正当竞争纠纷-民事起诉状.md"),
    "30-垄断纠纷-民事起诉状": ("30-civil-monopoly", "skeletons/30-垄断纠纷-民事起诉状.md"),
    "60-强制执行申请书": ("60-enforcement", "skeletons/60-强制执行申请书.md"),
    "31-商标申请驳回复审纠纷-行政起诉状": ("31-tm-rejection", "skeletons/31-商标申请驳回复审纠纷-行政起诉状.md"),
    "32-商标撤销复审行政纠纷-行政起诉状": ("32-tm-cancellation", "skeletons/32-商标撤销复审行政纠纷-行政起诉状.md"),
    "33-商标无效行政纠纷-行政起诉状": ("33-tm-invalidity", "skeletons/33-商标无效行政纠纷-行政起诉状.md"),
    "34-专利申请驳回复审行政纠纷-行政起诉状": ("34-patent-rejection", "skeletons/34-专利申请驳回复审行政纠纷-行政起诉状.md"),
    "35-专利无效行政纠纷-行政起诉状": ("35-patent-invalidity", "skeletons/35-专利无效行政纠纷-行政起诉状.md"),
    "61-暂时解除乘坐飞机、高铁限制措施申请-暂时解除乘坐飞机、高铁限制措施申请书": ("61-limit-lift", "skeletons/61-暂时解除乘坐飞机、高铁限制措施申请-暂时解除乘坐飞机、高铁限制措施申请书.md"),
    "62-参与分配申请书-参与分配申请": ("62-distribution", "skeletons/62-参与分配申请书-参与分配申请.md"),
    "63-执行担保-执行担保申请书": ("63-guarantee", "skeletons/63-执行担保-执行担保申请书.md"),
    "64-确认优先购买权-确认优先购买权申请书": ("64-preemption", "skeletons/64-确认优先购买权-确认优先购买权申请书.md"),
    "65-执行异议-执行异议申请书": ("65-objection", "skeletons/65-执行异议-执行异议申请书.md"),
    "66-执行复议-执行复议申请书": ("66-reconsideration", "skeletons/66-执行复议-执行复议申请书.md"),
    "67-执行监督-执行监督申请书": ("67-supervision", "skeletons/67-执行监督-执行监督申请书.md"),
    "68-申请不予执行仲裁裁决、调解书或公证债权文书-不予执行申请书": ("68-non-execution", "skeletons/68-申请不予执行仲裁裁决、调解书或公证债权文书-不予执行申请书.md"),
}

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent))
import generic_rules as _g

_TEMPLATES = _Path(__file__).resolve().parent.parent / "templates"
# 主文书树 → 两位编号（通用级 key）
_PRIMARY = {}
for _nn in _g.generic_case_numbers(_TEMPLATES):
    _t = _g.primary_tree_for(_nn, _TEMPLATES)
    if _t:
        _PRIMARY[_t] = _nn

# 高频案由识别关键词（别名；其余案由以案由名本身为关键词）
ALIASES = {
    "离婚纠纷": "解除婚姻、感情破裂、抚养权、探望、离婚",
    "民间借贷纠纷": "借款、欠款、借条、欠条、出借、利息",
    "买卖合同纠纷": "货款、购销、交付货物、付款",
    "金融借款合同纠纷": "贷款、银行借款、借款合同金融",
    "劳动争议纠纷": "劳动仲裁、工资、加班费、经济补偿、违法解除",
    "机动车交通事故责任纠纷": "交通事故、交强险、赔偿金、伤残",
    "物业服务合同纠纷": "物业费、物业服务",
    "信用卡纠纷": "信用卡透支、信用卡欠款",
    "房屋租赁合同纠纷": "租金、租赁房屋、退租",
    "房屋买卖合同纠纷": "购房、商品房、房屋买卖合同",
    "建设工程施工合同纠纷": "工程款、施工、竣工、结算",
    "融资租赁合同纠纷": "融资租赁、租金逾期",
    "侵害商标权纠纷": "商标侵权、近似商标",
    "侵害著作权及邻接权纠纷": "著作权侵权、盗版、信息网络传播",
    "行政处罚": "行政处罚决定、罚款",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifest", type=Path, default=Path(__file__).resolve().parent.parent / "templates" / "templates-manifest.json")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parent.parent / "references" / "case-routing.md")
    args = parser.parse_args()

    data = json.loads(args.manifest.read_text(encoding="utf-8"))
    trees = data["trees"]

    lines = [
        "# 案由路由表（case-routing）",
        "",
        "> 由 `scripts/build_case_routing.py` 从 `templates/templates-manifest.json` 生成；勿手改，重新生成。",
        "> Agent 案由匹配以**语义理解为主**，本表是锚点索引：识别关键词仅提示，未列别名时以案由名匹配。",
        "> 文书类型对（起诉状/答辩状/第三人意见陈述书）成对的树，生成起诉状优先路由到起诉状树。",
        "",
        "| 编号 | 案由 | 册 | 文书 | 模板树 | 规则支持 | case-type key | reference | 识别关键词提示 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    vol_order = {"上册": 1, "中册": 2, "下册": 3}
    trees = sorted(trees, key=lambda e: (e["tree"][:2]))
    for e in trees:
        tree = e["tree"]
        nn = tree[:2]
        parts = tree.split("-")
        if len(parts) >= 3:
            cause, doc_type = parts[1], parts[-1]
        else:  # 单文书目录（如 55-行政答辩状、60-强制执行申请书）
            cause = doc_type = parts[1]
        if tree in SUPPORTED_TREES:
            key, ref = SUPPORTED_TREES[tree]
            status = "✅ 精调（extract+fill+e2e）"
        elif tree in _PRIMARY:
            key = _PRIMARY[tree]
            ref = f"skeletons/{tree}.md"
            status = "✅ 通用级（当事人/填空/调解/落款；勾选与金额待精调）"
        elif any(tree == _g.primary_tree_for(x, _TEMPLATES) for x in [nn] if x) or True:
            # 同编号主文书已支持的其余文书（答辩状/第三人意见陈述书）
            primary = _g.primary_tree_for(nn, _TEMPLATES)
            key = _PRIMARY.get(primary, nn)
            ref = f"skeletons 可由 dump 生成"
            status = "⬜ 同编号主文书已接入，本文书待接入"
        kw = ALIASES.get(cause, cause)
        lines.append(f"| {nn} | {cause} | {e['volume'][0]} | {doc_type} | `{tree}` | {status} | {key} | {ref} | {kw} |")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[routing] {len(trees)} 行 → {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())