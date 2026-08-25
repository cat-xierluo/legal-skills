# 报告个性化配置(example)

> 复制本文件为 `report-profile.md`(已加入 .gitignore,不入库),填入真实信息。
> 字段结构由本 example 决定;如需新增字段,同步更新 example 与 scripts/render.py 的读取逻辑。
>
> ⚠️ 字段值必须是合法 YAML(不留花括号占位);占位说明以行尾注释 ` # 说明` 给出。

## 抬头（封面顶部 / 页脚左侧 / 编号)

- law_firm: XX 律所 # 律所全称
- series_name: XX 律所实务手册 # 系列名
- series_subtitle: PROFESSIONAL EDITION # 副标
- report_code: YWX-IR-2026-01 # 报告编号,格式 YWX-IR-{YYYY}-{NN}

## 主办律师（封面"主编"署名)

- lead_lawyer: XX 律师 # 姓名
- lead_lawyer_title: 律师 # 头衔
- lead_lawyer_avatar: # 路径,可选;留空即无头像
- motto: "" # 【v0.4.1 暂不启用】律所引言章;cover 模板当前 {% if false %},字段保留待后续按需启用

## 联系方式（页脚右下）

- contact_wechat: {微信号占位} # 微信号
- contact_phone: "{电话占位}" # 电话,带国际区号
- contact_email: # 邮箱,可选;留空即无邮箱

## 配色

- cover_style: C-geo # 合法值:C-geo | D-diagonal | E-flip | F-grid
- color_palette: bluebook # 合法值:bluebook(蓝皮书)| service-plan(律所深棕)
- accent_color: "#D4AF37" # 主强调色

## 报告设计

- design_intensity: lite # 合法值:lite | balanced | visual
- include_toc: true # true/false,是否生成目录
- include_methodology: true # true/false,是否生成"数据方法"小节

## 页脚

- footer_brand: 行业法律调研报告 # 页脚右侧"报告名"
