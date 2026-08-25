# 报告个性化配置(example)

> 复制本文件为 `report-profile.md`(已加入 .gitignore,不入库),填入真实信息。
> 字段结构见 `industry-research-report/config/report-profile.example.md`,本 skill 在此基础上多两个字段:
> - audience_label:客户画像标签,显示在封面"目标读者"位
> - period_label:期数标签模板,render.py 渲染时按当期替换 {N} / {YYYY-MM-DD}
>
> ⚠️ 字段值必须是合法 YAML(不留花括号占位);占位说明以行尾注释 ` # 说明` 给出。

## 抬头

- law_firm: XX 律所 # 律所全称
- series_name: XX 律所实务手册 # 系列名
- series_subtitle: LEGAL INTELLIGENCE EDITION # 副标
- report_code: YWX-WB-2026 # 报告编号前缀,期数自动追加 -N{NN}

## 主办律师

- lead_lawyer: XX 律师 # 姓名
- lead_lawyer_title: 律师 / 专利代理师 # 头衔
- lead_lawyer_avatar: # 路径,可选;留空即无头像
- motto: "以专业为本 · 以客户为先" # 【v0.4.1 暂不启用】律所引言章;cover 模板当前 {% if false %},字段保留待后续按需启用

## 联系方式

- contact_wechat: {微信号占位} # 微信号
- contact_phone: "{电话占位}" # 电话
- contact_email: # 邮箱,可选

## 配色

- cover_style: C-geo # 合法值:C-geo | D-diagonal | E-flip | F-grid
- color_palette: bluebook # 合法值:bluebook(蓝皮书)| service-plan(律所深棕)
- accent_color: "#D4AF37" # 主强调色

## 报告设计

- design_intensity: lite # 合法值:lite | balanced | visual
- include_toc: true # true/false,周报一般不开
- include_methodology: false # true/false,周报一般不开

## 周报专属

- audience_label: 科技型制造企业 # 客户画像标签
- period_label: "第 {N} 期 · {YYYY-MM-DD}" # 期数标签模板

## 页脚

- footer_brand: 法律周报 · 第 {N} 期 # 页脚右侧品牌
