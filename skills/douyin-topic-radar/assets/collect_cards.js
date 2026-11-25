// 在抖音搜索结果页内执行，返回当前已渲染卡片的结构化数据。
// 由 assets/collect_driver.mjs 读取后经 page.evaluate() 注入，不单独运行。
(() => {
  const DURATION_RE = /^(?:\d{1,2}:)?\d{1,2}:\d{2}$/;
  const COUNT_RE = /^[\d.]+[万亿]?$/;
  const TIME_RE =
    /^(?:·\s*)?(?:\d{4}-\d{1,2}-\d{1,2}|\d{1,2}-\d{1,2}|\d{1,2}月\d{1,2}日|.+前|刚刚)$/;

  const toCount = (value) => {
    if (typeof value === "number") return Number.isFinite(value) ? value : null;
    if (typeof value !== "string") return null;
    const text = value.replace(/,/g, "").trim();
    if (!text) return null;
    if (text.endsWith("万")) return Math.round(parseFloat(text) * 1e4);
    if (text.endsWith("亿")) return Math.round(parseFloat(text) * 1e8);
    const parsed = Number(text);
    return Number.isFinite(parsed) ? parsed : null;
  };

  const leafTexts = (node) => {
    const texts = [];
    const walk = (current) => {
      if (current.children && current.children.length) {
        for (const child of current.children) walk(child);
        return;
      }
      const text = (current.textContent || "").trim();
      if (text) texts.push(text);
    };
    walk(node);
    return texts;
  };

  // 抖音不在卡片 DOM 里输出作品 ID，只在 React 组件属性中保留 awemeInfo。
  const findAwemeInfo = (card) => {
    const fiberKey = Object.keys(card).find((key) => key.startsWith("__reactFiber"));
    if (!fiberKey) return null;
    const queue = [card[fiberKey]];
    let visited = 0;
    while (queue.length && visited < 240) {
      const fiber = queue.shift();
      visited += 1;
      const props = fiber && fiber.memoizedProps;
      if (props && props.awemeInfo && props.awemeInfo.awemeId) {
        return props.awemeInfo;
      }
      if (fiber && fiber.child) queue.push(fiber.child);
      if (fiber && fiber.sibling) queue.push(fiber.sibling);
    }
    return null;
  };

  // 兜底：读不到 awemeInfo 时仍从可见文本还原可观测字段，但没有作品 ID。
  const parseVisibleCard = (card) => {
    const texts = leafTexts(card);
    const record = {
      desc: null,
      authorName: null,
      durationMs: null,
      diggCount: null,
      createTimeText: null,
    };
    let atTextIndex = -1;
    texts.forEach((text, index) => {
      if (atTextIndex < 0 && text === "@") atTextIndex = index;
    });
    const rest = [];
    for (let index = 0; index < texts.length; index += 1) {
      const text = texts[index];
      if (text === "@") continue;
      if (atTextIndex >= 0 && index === atTextIndex + 1) {
        record.authorName = text;
        continue;
      }
      if (record.durationMs === null && DURATION_RE.test(text)) {
        const parts = text.split(":").map(Number);
        record.durationMs =
          parts.length === 3
            ? (parts[0] * 3600 + parts[1] * 60 + parts[2]) * 1000
            : (parts[0] * 60 + parts[1]) * 1000;
        continue;
      }
      if (record.diggCount === null && COUNT_RE.test(text)) {
        record.diggCount = toCount(text);
        continue;
      }
      if (record.createTimeText === null && TIME_RE.test(text)) {
        record.createTimeText = text.replace(/^·\s*/, "");
        continue;
      }
      rest.push(text);
    }
    record.desc = rest.sort((a, b) => b.length - a.length)[0] || null;
    return record;
  };

  const cards = [...document.querySelectorAll("div.search-result-card")].map(
    (card, position) => {
      const aweme = findAwemeInfo(card);
      const visible = parseVisibleCard(card);
      const info = aweme || {};
      const author = info.authorInfo || {};
      const stats = info.stats || {};
      const video = info.video || {};
      const durationMs =
        typeof video.duration === "number" ? video.duration : visible.durationMs;
      const hashtags = Array.isArray(info.textExtra)
        ? info.textExtra
            .filter((item) => item && item.hashtagName)
            .map((item) => item.hashtagName)
        : [];
      const awemeId = info.awemeId || null;

      return {
        aweme_id: awemeId,
        url: awemeId ? "https://www.douyin.com/video/" + awemeId : null,
        desc: String(info.desc || visible.desc || "").trim(),
        author: {
          nickname: author.nickname || visible.authorName || null,
          uid: author.uid || null,
          follower_count:
            typeof author.followerCount === "number" ? author.followerCount : null,
          total_favorited:
            typeof author.totalFavorited === "number" ? author.totalFavorited : null,
        },
        stats: {
          digg:
            typeof stats.diggCount === "number" ? stats.diggCount : visible.diggCount,
          comment: typeof stats.commentCount === "number" ? stats.commentCount : null,
          share: typeof stats.shareCount === "number" ? stats.shareCount : null,
          collect: typeof stats.collectCount === "number" ? stats.collectCount : null,
          play: typeof stats.playCount === "number" ? stats.playCount : null,
        },
        duration_s:
          durationMs === null || durationMs === undefined
            ? null
            : Math.round(durationMs / 1000),
        create_time: typeof info.createTime === "number" ? info.createTime : null,
        create_time_text: visible.createTimeText,
        hashtags,
        is_ads: Boolean(info.isAds),
        is_slides: Boolean(info.isSlides),
        source: aweme ? "aweme_info" : "dom_fallback",
        position,
      };
    },
  );

  const relatedSearches = (() => {
    const labels = [...document.querySelectorAll("p, span, div")].filter(
      (node) => (node.textContent || "").trim() === "相关搜索",
    );
    if (!labels.length) return [];
    const label = labels[labels.length - 1];
    const box = label.parentElement ? label.parentElement.querySelector("div") : null;
    if (!box) return [];
    return [...box.children]
      .map((child) => (child.textContent || "").trim())
      .filter(Boolean);
  })();

  return {
    cards,
    related_searches: relatedSearches,
    card_count: document.querySelectorAll("div.search-result-card").length,
    page_url: location.href,
  };
})()
