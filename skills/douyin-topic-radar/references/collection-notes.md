# 采集实现与排障

本文记录抖音 PC 搜索页的可观测结构，供采集器失效时定位。页面改版很频繁，遇到不一致先重新探测，不要照抄旧选择器。

## 数据来源

卡片 `div.search-result-card` 的 DOM 里**没有**作品链接和作品 ID（`a[href*="/video/"]` 为 0 个）。作品 ID、点赞、发布时间等完整字段在 React 组件的 `memoizedProps.awemeInfo` 上。

采集器对每张卡片做一次有界遍历（最多访问 240 个 fiber 节点），取到 `awemeInfo` 后直接读：

遍历有两条边界，缺一不可：

- **不跟随根节点的 `sibling`**。卡片 fiber 的 `sibling` 是下一张卡片，跟过去就会把邻居的 ID 贴到当前卡片上。子树内部的 `sibling` 才是同层元素。
- **元素节点必须仍在本卡片内**（`card.contains(stateNode)`）。这是结构变化时的第二道防线。

读不到 `awemeInfo` 时该卡片留空（`aweme_id: null`），不猜测、不借用邻居数据。

| 字段 | 含义 |
|---|---|
| `awemeId` | 作品 ID，拼 `https://www.douyin.com/video/<id>` |
| `desc` | 文案 |
| `authorInfo.nickname/uid/followerCount/totalFavorited` | 作者信息 |
| `stats.diggCount/commentCount/shareCount/collectCount` | 互动数 |
| `video.duration` | 时长，毫秒 |
| `createTime` | 发布时间，Unix 秒 |
| `textExtra[].hashtagName` | 话题标签 |
| `isAds` / `isSlides` | 广告、图集标记 |

读不到 `awemeInfo` 时回退到解析可见文本（时长、点赞、作者、发布时间、文案），但**拿不到作品 ID**，这类记录只参与聚合。

## 相关搜索

“相关搜索”是页面底部的一个区块：标签节点文本为 `相关搜索`，其父节点内第二个 `div` 的每个子节点是一个词条。采集器按这个结构取词，不依赖 `li[data-text]`（当前版本已不存在该属性）。

## 筛选面板

“筛选”按钮的可点击元素是带 `tabindex="0"` 的 `div`，内层 `span` 只渲染文字。点击内层 `span` 不会展开面板。

面板内的选项是 `span`，选中项会追加一个高亮类（`classList.length >= 2`），未选中项只有一个类名。选项文本存在重复（“不限”出现多次），所以按文本定位时只用唯一文本（“最新发布”“一周内”“最多点赞”）。

**首次点击被吞**：`goto` 之后页面会吞掉第一下点击，需要点击后校验、未生效再点。采集器对打开面板和选中选项各做了最多 3 次重试。

## 滚动

结果区用鼠标滚轮加载：先把鼠标移到视口中部，再 `wheel(0, 2800)`，等 1.8 秒。每轮约新增 10–20 条。连续两轮卡片数不变视为到底。

## 导航超时

抖音搜索页常在 `load` 事件之前就完成渲染，`page.goto()` 会抛 `PageNavigationTimeoutError`，但导航已提交。采集器捕获该错误后继续在当前页操作；其他导航错误照常抛出。

## 排障顺序

1. `document.querySelectorAll("div.search-result-card").length` 是否大于 0——为 0 说明没进结果页或被登录墙拦住。
2. 任取一张卡片，检查其 React fiber 上是否还有 `awemeInfo`——没有说明结构变了，需要重新探测。
3. 检查“筛选”按钮是否还存在、`tabindex` 是否为 0。
4. 检查 `page.url()` 是否仍是搜索页，而不是被跳到登录或风控页。
