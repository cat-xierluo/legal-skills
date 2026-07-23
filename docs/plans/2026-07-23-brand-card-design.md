# legal-skills 项目名片卡(brand 页)设计

> 日期:2026-07-23
> 状态:设计确认,实现中
> 关联:visual-card(brand 内容与渲染都在这里);skill-showcase 只生成 skill 内容文本,不参与 brand

## 目标

visual-card 渲染任何 skill 的小红书卡组时,**最后一页自动读 brand-card-handoff**(固定项目名片内容)+ skill 卡组当前 preset + 实时 star/skill 数,动态渲染一张「legal-skills 项目名片卡」(brand 角色),风格跟 skill 卡组统一。

## 架构(关键)

- **brand 内容是固定的**(项目名片,不需要每次"生成")
- **skill-showcase 只负责 skill 内容文本**(底稿/交接),**不参与 brand**
- **brand-card-handoff 放 visual-card**(渲染方)——visual-card 渲染 skill 卡组时,读 skill-showcase 的 skill 内容 + 自己的 brand-card-handoff,拼成完整卡组(skill 内容卡 + brand 卡)

## 三部分

### 1. 交接文件(内容数据源,放 visual-card)

- **位置**:`visual-card/assets/brand-card-handoff.md`
- **内容**:品牌/定位/类型矩阵/平台/作者/仓库短地址(固定)+ star/skill 数(**生成时 gh api 实时取**,自己的仓库)
- **格式**:Markdown(内容数据 + gh api 取数说明),人和 Agent 都能读

### 2. visual-card「brand 项目名片页」(独立骨架 + 风格跟随)

- **新角色**:visual-card 页面角色路由(cover/workflow/evidence/closing...)新增 `brand` 角色
- **独立骨架**(brand 专用,不套常规角色布局):
  ```
  Legal Skills(项目名居中放大)
  面向法律人的 Agent 库
  ──
  cat-xierluo/legal-skills(仓库短地址,star 上方,方便搜索)
  ★ {star} stars / {skill}+ skills(实时数据)
  ──
  能力矩阵 2×3(获取/处理/写作/可视化/检索/分析 + 代表 skill)
  ──
  兼容平台 + 作者
  ```
- **风格跟随**:骨架结构固定,但**配色/字体/强调色/材质跟 skill 卡组 preset**——bento 出靛蓝、classic-french 出深蓝金、luxury 出金箔……布局一样,视觉统一
- **内容注入**:渲染时读 `brand-card-handoff.md` + `gh api` 取实时 star/skill 数

### 3. 嵌入机制(visual-card 自动,skill-showcase 不参与)

- visual-card 渲染 skill 卡组时,**最后一页自动读 brand-card-handoff** + skill preset + gh star,动态生成 brand 页
- 输出 = N 张 skill 内容卡 + 1 张项目名片卡(同风格收尾)
- 实现:`visual-card/SKILL.md` + `references/page-role-layout-router.md` 加 `brand` 角色 + 骨架规范 + 风格 token 跟 preset + "skill 卡组最后一页自动 brand 页"规则

## 与 15 风格独立素材库的关系

- **15 风格素材库**(`archive/legal-skills-brand-card/`):独立项目名片素材,**单独发布用**(静态,star 手动更新),15 个固定风格挑选
- **brand 页(本设计)**:嵌入 skill 卡组最后一页,**统一风格用**(动态,star 实时,风格跟 skill preset)
- 两者并存,职责不同:独立素材库 = 项目名片单发;brand 页 = skill 卡组统一收尾
