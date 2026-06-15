## 企业全息画像

### 12. 企业检索（轻量候选列表，enterprise-search）

**每次调用消耗 1 积分**。按名称检索企业，返回候选列表（仅含 ID、名称、信用代码），用于定位目标企业后调用其他企业接口。

```bash
scripts/yd-run enterprise-search "华为" --top-k 5
```

### 13. 企业基本信息（enterprise-base）

根据企业 ID 或统一社会信用代码获取企业完整信息（含股东、核心成员、分支机构等）。

```bash
scripts/yd-run enterprise-base --uscc "9144030071526726XG"
```

### 14. 企业聚合总览（enterprise-summary）

一次调用获取企业各维度数据的统计摘要。

```bash
scripts/yd-run enterprise-summary --id "企业ID"
```

### 15. 企业分项列表（enterprise-list）

查询企业各维度详细记录，支持分页。**每次调用消耗 5-10 积分**（涉诉统计和涉诉文书 10 积分，其余 5 积分）。

```bash
# 查询企业涉诉文书
scripts/yd-run enterprise-list --type writ-list --uscc "9144030071526726XG"

# 查询企业对外投资
scripts/yd-run enterprise-list --type invest --uscc "9144030071526726XG" --page 1 --size 10

# 查询企业商标
scripts/yd-run enterprise-list --type brand --uscc "9144030071526726XG"
```

#### 可用类型

| TYPE | 名称 | 积分 |
|------|------|------|
| invest | 对外投资 | 5 |
| brand | 商标 | 5 |
| patent | 专利 | 5 |
| soft-right | 软件著作权 | 5 |
| works-right | 作品著作权 | 5 |
| icp | 网站备案 | 5 |
| change-info | 变更记录 | 5 |
| writ-agg | 涉诉信息统计 | 10 |
| writ-list | 涉诉文书 | 10 |
| court-session | 开庭公告 | 5 |
| court-notice | 法院公告 | 5 |
| execution | 失信被执行人 | 5 |
| executed-person | 被执行人 | 5 |
| frozen-equity | 股权冻结 | 5 |
| punishment | 行政处罚 | 5 |
| pledge | 股权出质 | 5 |
| guaranty | 对外担保 | 5 |
| abnormal | 经营异常 | 5 |
| tax | 欠税公告 | 5 |
| serious-illegal | 严重违法 | 5 |
