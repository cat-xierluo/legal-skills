# patent-download Examples

## 快速开始

### 1. [推荐] Google Patents 下载 ⭐

```bash
cd scripts

# 安装依赖（只需一次）
pip install patent-downloader

# 用公告号下载
python cli.py google CN223081266U

# 用申请号下载（会自动匹配公告号）
python cli.py google 202421964517.8

# 指定输出目录
python cli.py google CN223081266U -o ~/Downloads/patents

# 仅查信息不下载
python cli.py google CN223081266U --info

# 批量下载
python cli.py google CN223081266U CN118198150A CN118198150B
```

### 2. 度衍专利浏览器下载

```bash
# 单个专利
python cli.py uyanip 2024214535561 -m browser

# 批量
python cli.py uyanip 2024214535561 2024222490312 -m browser

# 无头模式
python cli.py uyanip 2024214535561 -m browser --headless
```

### 3. 直接使用平台脚本（不经过 cli.py）

```bash
# Google Patents
python scripts/platforms/google_patents.py CN223081266U
python scripts/platforms/google_patents.py 202421964517.8 --info
```

## 实测案例

### 案例 1：申请号 → 公告号

```
专利号:       202421964517.8  （申请号）
对应公告号:   CN223081266U     （公告号）
标题:         一种双面装载的粉盒
申请人:       某信息科技公司
申请日:       2024-08-13
公告日:       2025-07-11
平台:         Google Patents
结果:         ✅ 下载成功（548KB PDF）
```

**为什么申请号搜不到，公告号才能搜到？**

因为 Google Patents 是用公告号（CN223081266U）索引的，不是用申请号（202421964517.8）。我们的 `google_patents.py` 模块会尝试自动匹配，但如果匹配失败，建议先用其他平台查公告号。

### 案例 2：仅查信息不下 PDF

```bash
python cli.py google CN223081266U --info
# 输出:
#   专利: 一种双面装载的粉盒
#   申请人: 某信息科技公司
#   公开日: 2025-07-11
```

## 平台对比（2026-07-11 实测）

| 平台 | 推荐度 | 方式 | 状态 |
|------|:------:|:----:|:----:|
| **Google Patents** | ⭐⭐⭐⭐⭐ | API | ✅ 实测走通 |
| **度衍专利** | ⭐⭐⭐⭐ | 浏览器 | ✅ 可用 |
| **润桐RainPat** | ⭐⭐⭐ | 浏览器/API | ⏸ 维护中至7/17 |
| **专利公布公告** | ⭐⭐ | 浏览器 | ⚠️ 有反爬 |
| **PatentStar** | ⭐ | API/浏览器 | ❌ API失效 |
| **粤港澳/PSS** | ⭐ | 浏览器 | ⏳ 待完善 |

## 申请号 vs 公告号 快速对照

| 申请号 | → | 公告号 | 类型 |
|:------:|:--:|:------:|:----:|
| `202421964517.8` | → | `CN223081266U` | 实用新型 |
| `202410619712.5` | → | `CN118198150A` | 发明公布 |
| `202410619712.5` | → | `CN118198150B` | 发明授权 |

**记住**：
- 用户给的往往是 **申请号**（带校验位）
- Google Patents 用 **公告号**（CN开头+字母结尾）
- `google_patents.py` 会尝试自动转换，但无法100%保证成功

## 批量处理

### 从文件读取

```bash
# patents.txt 内容（每行一个公告号）
CN223081266U
CN118198150A
CN118198150B

# 逐条下载
while read p; do python cli.py google "$p" -o ~/Downloads/patents; done < patents.txt
```

## 故障排除

### 1. Google Patents 报 "Could not find Google Patents page"
- 原因：输入的可能是**申请号**而不是**公告号**
- 解决：先用度衍或 PatentGuru 查公告号（如 `CN223081266U`）

### 2. 申请号自动匹配失败
- 不保证100%成功，因为申请号和公告号无直接数学关系
- 建议：先用 `python cli.py google <号> --info` 查一下

### 3. patent-downloader 未安装
```bash
pip install patent-downloader
```

## 相关文档

- `references/patent-number-formats.md` — 申请号/公告号格式详解
- `references/platform-status.md` — 各平台实测状态与详情
