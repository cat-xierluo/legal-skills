# AI SaaS 场景包

## 适用对象

- 面向企业或公众提供 AI SaaS 产品
- 调用第三方模型或自研模型，对外提供文本、图片、音频、视频生成或分析能力
- 做 AI 工作流、AI 助手、AI 客服、AI 知识库、AI 审核等产品

## 默认风险组合

- `ai-compliance`：标识、公示、模型核验、投诉处置
- `data-compliance`：客户材料、日志、个人信息、数据输入边界
- `contracts`：客户合同、模型服务商协议、SLA、赔偿责任
- `ip`：输出归属、训练材料、提示词和商业秘密
- `regulatory`：宣传表述、误导、未成年人和高风险行业场景

## 先补关键事实

1. 是 ToB、ToC 还是平台型产品
2. 使用自研模型还是第三方模型 / API
3. 用户是否上传客户材料、合同、音视频、个人信息
4. AI 输出是否直接展示、下载、导出或二次传播
5. 是否涉及医疗、金融、法律、教育、未成年人等高风险行业

## 高频场景的下一跳

- 上线前核查：`references/ai-compliance.md` + `assets/template-ai-launch-report.md`
- 企业客户上传材料：`references/data-compliance.md` + `references/contracts.md`
- 宣传“替代人工”“准确率 100%”：`references/regulatory.md`
- 输出版权和训练边界：`references/ip.md`

## 风险信号

- 🔴 公开提供 AI 生成，却没有模型公示、协议和投诉入口
- 🔴 把客户敏感资料直接交给第三方模型，未核验条款
- 🔴 宣传语把 AI 输出包装成绝对准确或可替代专业意见
- 🟡 客户合同没有写模型来源、数据处理和责任边界
