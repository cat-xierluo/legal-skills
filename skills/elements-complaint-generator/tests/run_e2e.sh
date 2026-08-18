#!/usr/bin/env bash
# elements-complaint-generator 多案由端到端回归
# 每案由：md → extract → fill → 带标签断言；外加 sample 全要素填充
set -e
SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SKILL_DIR"

echo "[e2e] ========== 案由 09 民间借贷 =========="
python3 -B scripts/extract_from_markdown.py \
  --case-type 09-private-lending \
  --input tests/fixtures/09-private-lending-complaint.md \
  --output tests/output/09-e2e-elements.json >/dev/null
python3 -B scripts/fill_template.py \
  --case-type 09-private-lending \
  --elements tests/output/09-e2e-elements.json \
  --output tests/output/09-e2e.docx 2>&1 | grep -E "rules|完整性"

echo "[e2e] ========== 案由 05 离婚 =========="
python3 -B scripts/extract_from_markdown.py \
  --case-type 05-divorce \
  --input tests/fixtures/05-divorce-complaint.md \
  --output tests/output/05-e2e-elements.json >/dev/null
python3 -B scripts/fill_template.py \
  --case-type 05-divorce \
  --elements tests/output/05-e2e-elements.json \
  --output tests/output/05-e2e.docx 2>&1 | grep -E "rules|完整性"

echo "[e2e] ========== sample 全要素填充（两案由）=========="
python3 -B scripts/fill_template.py --case-type 09-private-lending \
  --elements tests/fixtures/09-private-lending-sample.json \
  --output tests/output/09-sample.docx 2>&1 | grep -E "rules|完整性"
python3 -B scripts/fill_template.py --case-type 05-divorce \
  --elements tests/fixtures/05-divorce-sample.json \
  --output tests/output/05-sample.docx 2>&1 | grep -E "rules|完整性"
for ct in 06-sale 15-labor 21-traffic 22-copyright 23-trademark 27-tradesecret 24-patent 28-tech 13-construction 08-loan 10-creditcard 07-house-sale 11-lease 14-property 12-lease-finance 16-securities-fraud 17-property-loss 18-liability 19-guarantee 20-personal 25-design-patent 29-unfair-competition 30-civil-monopoly 60-enforcement; do
  python3 -B scripts/fill_template.py --case-type $ct \
    --elements tests/fixtures/$ct-sample.json \
    --output tests/output/$ct.docx 2>&1 | grep -E "rules"
done

echo "[e2e] ========== 断言（带标签形态，防标签吃字/勾选错位回归）=========="
python3 - <<'PYEOF'
import sys, zipfile
from lxml import etree
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"
Wp = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"

def full_of(path):
    with zipfile.ZipFile(path) as z:
        xml = etree.fromstring(z.read("word/document.xml"))
    return "\n".join("".join(x.text or "" for x in p.iter(W)).strip() for p in xml.iter(Wp))

CHECKS = {
    "tests/output/09-e2e.docx": [
        "姓名：张三", "姓名：李四", "证件号码：110105850312001", "证件号码：310105900725001",
        "联系电话：12300000001", "500000", "性别：男☑", "男□    女☑",
    ],
    "tests/output/09-sample.docx": [
        "姓名：张三", "姓名：李四", "性别：男☑", "男□    女☑", "民族：汉",
        "出生日期：1985年3月12日", "出生日期：1990年7月25日", "利率12% / 年",
        "实际清偿之日止：是☑", "到期一次性还本付息☑", "合同条款：第三条",
        "了解☑    不了解□", "具状人（签字、盖章）：张三（签名）", "日期：2026年8月17日",
    ],
    "tests/output/05-e2e.docx": [
        "姓名：王五", "姓名：赵六", "性别：男☑", "男□    女☑", "结婚时间：2012年5月20日",
        "王小一", "归属：原告☑ / 被告□", "抚养费承担主体：原告□ / 被告☑", "每月 2000 元",
        "探望权行使主体：原告□ / 被告☑", "房屋明细：归属：原告☑",
        "汽车明细：归属：原告□ / 被告☑", "存款明细：归属：原告☑", "是☑ 否□", "了解☑    不了解□",
    ],
    "tests/output/06-sale.docx": [
        "给付价款（元）500000 元", "迟延给付价款的利息 12000 元、违约金 5000 元", "迟延履行☑",
        "退货☑", "判令解除合同☑", "费用明细：律师费 20000 元", "出卖人（卖方）：某科技有限公司",
        "买受人（买方）：王五", "名称：某置业有限公司",
    ],
    "tests/output/15-labor.docx": [
        "拖欠 2026 年 5 月至 7 月工资 35000 元", "加班费 8000 元", "经济补偿金 21000 元",
        "名称：某科技有限公司",
    ],
    "tests/output/21-traffic.docx": [
        "2026年3月1日至2026年5月20日期间在某市第一医院住院（门诊）治疗，累计发生医疗费 45000 元",
        "营养费 3000 元", "住院伙食补助费 4000 元", "交通费 1500 元", "误工费 20000 元",
        "精神损害抚慰金 5000 元", "医疗费发票、医疗费清单、病历资料：有☑ 无□", "交通费凭证：有☑ 无□",
    ],
    "tests/output/22-copyright.docx": [
        "经济损失 300000 元", "计算依据或参考因素：按原告实际损失+法定赔偿综合主张",
        "侵权链接 / 标题：https://example.com/infringe/12345",
        "律师费 20000 元 律师费凭证：有☑", "取证费 3000 元 取证费凭证：有☑", "差旅费 2000 元 差旅费凭证：有☑",
        "原告损失☑", "合作作品☑",
    ],
    "tests/output/23-trademark.docx": ["经济损失 300000 元", "律师费 20000 元 律师费凭证：有☑", "法定赔偿☑"],
    "tests/output/27-tradesecret.docx": ["经济损失 300000 元", "被告获利☑", "律师费 20000 元 律师费凭证：有☑", "公证费 3000 元 公证费凭证：有☑"],
    "tests/output/24-patent.docx": [
        "有☑ 内容：立即停止制造、销售侵权产品",
        "是否包含惩罚性赔偿：包含☑ 计算方法：基数 100000 元 ×（1+ 1 倍数）", "经济损失 300000 元",
    ],
    "tests/output/28-tech.docx": [
        "判令解除合同☑", "确认合同已于 2026年6月30日 解除☑", "有☑ 支付赔偿金 80000 元",
        "具体情形：被告未按期交付开发成果", "鉴定内容：对技术成果完成度鉴定", "鉴定机构名称：某知识产权鉴定中心",
    ],
    "tests/output/13-construction.docx": [
        "截至2026年8月17日止，迟延支付工程款的利息 56000 元、违约金 20000 元",
        "实际清偿之日止：是☑", "是☑ 内容：工程款优先受偿权", "是☑ 责任主体姓名或者名称：某建设集团公司",
        "是☑ 停工损失金额 150000 元", "是☑ 支付赔偿金 60000 元",
    ],
    "tests/output/11-lease.docx": ["截至2026年8月17日止，迟延支付租金的利息 8000 元", "是☑ 否□"],
    "tests/output/14-property.docx": ["截至2026年8月31日止，尚欠物业费 24000 元", "截至2026年8月31日止，欠逾期物业费的违约金 3600 元"],
    "tests/output/12-lease-finance.docx": ["违约金 32000 元", "滞纳金 15000 元", "判令解除融资租赁合同☑"],
    "tests/output/16-securities-fraud.docx": ["投资差额损失 500000 元", "费用明细：律师费 30000 元"],
    "tests/output/17-property-loss.docx": ["保险金 120000 元"],
    "tests/output/18-liability.docx": ["保险金 80000 元"],
    "tests/output/19-guarantee.docx": ["截至2026年8月17日止，保险费、违约金等共计 12000 元"],
    "tests/output/20-personal.docx": ["保险金 200000 元"],
    "tests/output/25-design-patent.docx": ["经济损失 150000 元", "律师费 15000 元 律师费凭证：有☑"],
    "tests/output/29-unfair-competition.docx": ["经济损失 200000 元", "律师费 20000 元 律师费凭证：有☑"],
    "tests/output/30-civil-monopoly.docx": ["经济损失 300000 元", "律师费☑"],
    "tests/output/60-enforcement.docx": [
        "判决书☑", "金钱给付☑", "本金☑", "迟延履行利息☑",
        "杭州市中级人民法院", "(2026)浙XXXX民终XXXX号", "2026年5月20日",
        "被告于判决生效之日起十日内偿还",
    ],
    "tests/output/08-loan.docx": [
        "截至2026年8月17日止，尚欠本金 2000000 元（人民币",
        "截至2026年8月17日止，欠利息 180000 元、期内利息 120000 元、复利 30000 元、罚息（违约金） 50000 元",
        "实际清偿之日止：是☑", "提前还款（加速到期）☑", "明细：律师费 50000 元",
        "名称：某银行股份有限公司某支行", "股份有限公司☑",
        "贷款人：某银行股份有限公司某支行", "借款人：王五", "等额本息☑",
        "合同条款及内容：《借款合同》第 12 条约定由贷款人住所地法院管辖",
    ],
    "tests/output/10-creditcard.docx": [
        "截至2026年8月17日止，尚欠本金 80000 元（人民币",
        "截至2026年8月17日止，欠利息、罚息、复利、滞纳金、违约金、手续费等合计 15600 元",
        "自 2026年8月18日 之后的利息、罚息", "费用明细：律师费 8000 元",
        "透支金额：本金 80000 元", "违约责任：按最低还款额未还部分 5% 收取违约金",
    ],
    "tests/output/05-sample.docx": [
        "姓名：王五", "姓名：赵六", "孙律师", "出生日期：1988年2月15日", "出生日期：1990年4月28日",
        "民族：汉", "证件号码：110105880215002", "证件号码：110105900428003",
        "判决准予原告与被告离婚。", "有财产☑", "无债务☑", "有此问题☑",
        "房屋明细：归属：原告☑", "汽车明细：归属：原告□ / 被告☑", "存款明细：归属：原告☑",
        "王小一", "归属：原告☑ / 被告□", "抚养费承担主体：原告□ / 被告☑",
        "金额及明细：每月 2000 元", "支付方式：按月支付至原告银行账户",
        "探望权行使主体：原告□ / 被告☑", "行使方式：每月探望两次",
        "结婚时间：2012年5月20日", "离婚事由：双方性格不合", "婚后购置位于北京市海淀区的房屋一套",
        "第一千零七十九条", "结婚证", "具状人（签字、盖章）：王五（签名）", "日期：2026年8月17日",
    ],
}

failed = False
for path, checks in CHECKS.items():
    import re as _re
    full = _re.sub(r"\s+", " ", full_of(path))
    miss = [k for k in checks if _re.sub(r"\s+", " ", k) not in full]
    # 全局回归哨兵：双日 / 调解双勾 / 标签吃字
    sentinels = [("双日", "日日" in full), ("调解双勾", "了解☑    不了解☑" in full)]
    bad = [n for n, hit in sentinels if hit]
    status = "✓" if not miss and not bad else "✗"
    print(f"[e2e] {status} {path.split('/')[-1]}: {len(checks)-len(miss)}/{len(checks)}"
          + (f" 缺失={miss}" if miss else "") + (f" 哨兵={bad}" if bad else "")
          + (f"（有此问题☑={full.count('有此问题☑')}）" if "05-sample" in path else ""))
    if miss or bad:
        failed = True

if failed:
    sys.exit(1)
print("[e2e] ✅ 全部案由回归通过")
PYEOF
echo "[e2e] ========== 全案由冒烟（68 编号通用级渲染）=========="
python3 -B tests/smoke_all.py 2>&1 | tail -2
