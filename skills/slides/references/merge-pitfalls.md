# Slides 工程踩坑与多源合并模式

> **来源 / 缘由**: 一次真实讲课课件制作中，主题 override 完全失效；PDF 重抽仍是深蓝 `rgb(27,60,89)`，`getComputedStyle().backgroundColor` 也返原始值。九张截图反复自验都"正常"，反复核查才发现真因。**任何 multi-source HTML 合并项目**都可能踩同样坑。

## 0. 事故时间线(诊断过程)

1. 改后 `getComputedStyle(el).backgroundColor` 仍 = 原始 `--ink #1B3C59`(硬编码 `#F4F1EA!important` 没匹配上)
2. `document.styleSheets` 枚举 cssRules:我加的 `.slide.dark{background:#F4F1EA!important}` **不在**任何 stylesheet 的规则表里
3. `--paper` 解析 = `#F4F1EA`(与 override 同值巧合);`--ink` 解析 = 原始 `#1B3C59`(override 应生效但没生效)
4. 推断:多个 700 行的 `<style>` 块在 CSS 解析器中被**丢弃**(找不到 var/!important/specificity/源顺序原因)
5. **根治**: carousel + 浅色主题 override 从 `style_combined` 拎出，放进独立第二个 `<style>` 块(独立 stylesheet 各自解析)。立即生效。

## 1. 症状 + 真因模型

### 1.1 典型症状
- HTML 改完后，`getComputedStyle(el)` 返**原始** CSS 变量值(如 `--ink:#1B3C59` 而不是覆盖后的 `#1a1a22`)
- `!important` 硬编码也不匹配
- 特殊条件下(setContent 截图、`:root` 部分 var)看似"对"——*实际是巧合*，例如 `--paper:#F4F1EA` 在原始与 override 同值
- `document.styleSheets` 枚举 cssRules 时，新加的规则**不在**任何 stylesheet 的 cssRules 表里
- 浏览器 DevTools 看 `<style>` 标签内容存在但**规则不进 cascade**

### 1.2 真因模型
- 多源 HTML 合并时，`style_combined` 把所有源的 `<style>` 块内容(去 tag)拼成一个长字符串 + append carousel / override
- 源文件 style 内部如果混入 stray 内容(stray `<style>` 字面 / 中文开发备注 / 注释块),CSS 解析器在 stray 处报错,error recovery 会**跳过后续规则**直到找到一个干净的恢复点
- 大块规则丢失 → override 沉默 → 主题"该生效不生效"

### 1.3 快速诊断清单
- [ ] `getComputedStyle(el).backgroundColor` 与 `:root --ink/--paper` 值是否实际变了 → var() 是否落实
- [ ] `document.styleSheets` 枚举 cssRules，看目标规则是否在表里 → 整个块是否被丢
- [ ] DevTools 看 `<style>` 标签数量(合并后应该有 ≥2 个，其中一个是独立 override)
- [ ] `console.log` 在 override 块前后加 visible marker，看规则是否真进了 stylesheet
- [ ] 单源 HTML 打开验证: 同样的 CSS 在单源是否生效? 若生效 → 大概率合并工程的真因

## 2. 独立 `<style>` 块兜底法(根治)

模板输出 HTML 时，把 override(主题色 / 组件 CSS / carousel 等)放进**第二个独立 `<style>` 块**，与主 style_combined 完全平行:

```html
<head>
<style>{style_combined}</style>          <!-- 主:5 源合并 + dedup -->
<style>{OVERRIDE_CSS}</style>             <!-- 独立:覆盖 + 组件 + 必要时 carousel -->
</head>
```

**优势**: 独立 stylesheet 各自解析,主块 stray 内容不会带掉这块。

**模板代码**(merge.py 之类):
```python
OVERRIDE_CSS = '''
:root{--ink:#1a1a22;--paper:#F4F1EA;...}
.slide,.slide.dark{background:#F4F1EA!important;color:#1a1a22!important}
... carousel + DEC + components ...
'''

html = f'''...
<style>
{style_combined}
</style>
<style>
{OVERRIDE_CSS}
</style>
'''
```

## 3. 源文件 style 块纯净规则

源 HTML `<style>` 内部只允许合法 CSS。任何"开发备注"放 HTML 注释(`<!-- -->`)或 `<script>` 里,**不**混在 style 内部。

禁用:
- 源 `<style>` 内 stray `<style>` 字面(例如 `Part 4 <style> 与 Part 1 完全一致` 注释里的字面 `<style>` token)
- 中文开发备注作为 style 内部文本(如 `` 与 Part 1 完全一致(同 <style> 块,仅换内容)`)
- stray `</style>`、unclosed `{` 块、`@` 语法错误
- 注释放在 style 块末尾以 `<!-- 注释 -->` 形式(浏览器会保留为 CSS 文本)

合法:
- `/* CSS 注释 */` 写在 style 内部干净处
- 中文备注 / 跨文件共享提示放 HTML 注释 `<!-- -->`,紧贴 `<style>` 标签外
- 跨文件共享放 `assets/`,别写进 style

合并脚本应对 dedup by line，**不能**筛选 stray 文本。**根因层** = 源文件纯净。如果合并项目大量源文件，根治在源(本规则 §3)而非脚本。

## 4. 多源 HTML 同步主题注入模式(独立打开 = 合并版)

当一个合并版 HTML 用了同一份主题，但多个源 HTML 各自独立打开时也得是同一个主题(否则各模块独立看不一致)，用"独立 style 块注入"模式。

`/tmp/inject_light.py` 幂等模板(2026-07-16 实战):

```python
OVERRIDE_CSS = '''... 同一份 override CSS ...'''

INJECT = f"<style>\n{OVERRIDE_CSS}\n</style>\n</head>"

for f in files:  # 5 源 HTML
    src = read(f)
    if "浅色主题 override" in src:  # 幂等标记
        continue
    new = src.replace("</head>", INJECT, 1)
    write(f, new)
```

**幂等标记**: 加版本号字符串(如 `"浅色主题 override v1"`)作为注入标记,后续注入会跳过已注入文件。

**cross-source 主题一致性**: 多源独立打开 = 浅色 paper;合并版 = 浅色 paper;用户可按模块独立 review。**不要**在每个源里手改主题——必 drift。

## 5. merge.py 工程模式(dedup + 独立 style + carousel)

合并脚本(dedup by line + append override 到独立变量):

```python
# 1. dedup style_combined(去掉多源重复)
seen = set(); uniq = []
for s in all_styles:
    for line in s.split('\n'):
        l = line.strip()
        if l and l not in seen: seen.add(l); uniq.append(line)
        elif not l: uniq.append(line)
style_combined = '\n'.join(uniq)

# 2. override 进独立变量(不混入 style_combined)
OVERRIDE_CSS = '''... carousel + 主题 + 组件 ...'''

# 3. 模板输出两个 <style>
html = f'''...
<style>{style_combined}</style>
<style>{OVERRIDE_CSS}</style>
...'''
```

工程纪律:
- 主题 override 永远放 OVERRIDE_CSS,绝不追加进 style_combined
- carousel 机制(`#deck{position:fixed;...}`)放 OVERRIDE_CSS,只 merged deck 需要
- 组件 CSS(`.pipeline .step` 等)放 OVERRIDE_CSS,多源一致
- slide id 重编号 + PAGENO → 真实页码(避免听众看到 "23 / 30" 残留)

## 6. 验证 checklist(每次 fix 后跑)

- [ ] setContent 截图首屏 bg → 与目标 hex 接近(±5 RGB)
- [ ] goto file:// 同样 bg(排除 goto 路径差异)
- [ ] `document.styleSheets` 枚举 cssRules 包含 override 规则
- [ ] DevTools `<style>` 标签数 ≥ 2(主 + 独立 override)
- [ ] PDF 重抽 p1/p10/p28 中心 RGB → 浅色(不是深蓝)
- [ ] 多源 HTML 各独立打开 → 浅色一致
- [ ] 浏览器 DevTools "Computed" 面板 bg 与期望 hex 一致

## 7. 何时 NOT 用独立 `<style>` 块

- 主 style 干净已验证(`grep` 无 stray 文本)→ 不必,代码更简
- 单源 HTML 项目 → 没合并问题,直接主 style
- 主题不需要 override → 没坑

## 8. 横向关联

| 关联文件 | 用途 |
|---|---|
| `references/ppt-writing-rules.md` | 语言 / chrome / 反焦虑 / 排版层(本文件是工程层) |
| `references/browser-guide.md` | 浏览器演示模式(动画 / 视口) |
| `references/pptx-guide.md` | PPTX 转换工程 |
| `references/cn-deck-polish.md` | 中文课件去冗余与隐形坑 |
| `references/configuration.md` | 本地配置：身份 / 素材 / 偏好(讲稿层与客户判型属使用者本地资料，不在本技能内) |

## 9. 一句话总结

> 当主题"该生效不生效"——把 override 放进独立 `<style>` 块是兜底;根因在源文件 style 块不纯净,顺手清掉 stray `<style>` 字面与中文开发备注。
