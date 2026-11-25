// 由 scripts/radar.py driver 生成后交给 ego-browser 执行；占位符由生成器替换。
const SPACE_ID = __SPACE_ID__;
const KEYWORD = __KEYWORD__;
const MODE = __MODE__;
const ROUNDS = __ROUNDS__;
const SCROLL_STEP = __SCROLL_STEP__;
const OUT_PATH = __OUT__;
const PAGE_LABEL = __PAGE__;
const SHOULD_FINISH = __FINISH__;
const COLLECTOR_SOURCE = __COLLECTOR__;

const FILTER_OPTIONS = {
  comprehensive: [],
  latest: ["最新发布", "一周内"],
  top: ["最多点赞"],
};

const options = FILTER_OPTIONS[MODE];
if (!options) throw new Error("未知采集模式: " + MODE);

const resolveTask = async () => {
  if (Number.isInteger(SPACE_ID) && SPACE_ID > 0) {
    const entry = (await listTaskSpaces()).find((space) => space.id === SPACE_ID);
    if (entry) return taskSpace(SPACE_ID);
  }
  return taskSpace("douyin-topic-radar");
};

const task = await resolveTask();
const pages = await task.pages();
const page = PAGE_LABEL && pages.some((item) => item.label === PAGE_LABEL)
  ? task.page(PAGE_LABEL)
  : pages.length
    ? pages[0]
    : await task.adopt((await task.tabs())[0].page);

const url = "https://www.douyin.com/search/" + encodeURIComponent(KEYWORD);
try {
  await page.goto(url, { timeout: 30000 });
} catch (error) {
  // 抖音搜索页常在 load 事件前完成渲染；导航超时后继续在已提交的页面上操作。
  if (!String(error).includes("PageNavigationTimeoutError")) throw error;
}
await page.waitForSelector("div.search-result-card", { timeout: 30000 });

const panelOpen = () =>
  page.evaluate(() =>
    [...document.querySelectorAll("span")].some(
      (span) => (span.textContent || "").trim() === "最新发布",
    ),
  );

// 首次导航后页面会吞掉第一下点击，因此每次点击后都校验结果，未生效就重试。
const openPanel = async () => {
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    const tagged = await page.evaluate(() => {
      document
        .querySelectorAll("[data-radar-filter]")
        .forEach((node) => node.removeAttribute("data-radar-filter"));
      // 真正接收点击的是带 tabindex 的容器，内层 span 只渲染文字。
      const target = [...document.querySelectorAll("div[tabindex='0']")].find(
        (node) => (node.textContent || "").trim() === "筛选",
      );
      if (target) target.setAttribute("data-radar-filter", "open");
      return document.querySelectorAll('[data-radar-filter="open"]').length;
    });
    if (tagged !== 1) throw new Error("未找到唯一的筛选按钮，实际命中 " + tagged);
    await page.click('[data-radar-filter="open"]', { label: "打开筛选面板" });
    await page.waitForTimeout(1500);
    if (await panelOpen()) return;
  }
  throw new Error("筛选面板三次点击后仍未展开");
};

const optionSelected = (text) =>
  page.evaluate((optionText) => {
    const span = [...document.querySelectorAll("span")].find(
      (node) => (node.textContent || "").trim() === optionText,
    );
    if (!span) return false;
    // 未选中项只有一个类名，选中项会追加高亮类。
    return span.classList.length >= 2;
  }, text);

const clickOption = async (text) => {
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    if (!(await panelOpen())) await openPanel();
    const tagged = await page.evaluate((optionText) => {
      document
        .querySelectorAll("[data-radar-option]")
        .forEach((node) => node.removeAttribute("data-radar-option"));
      const spans = [...document.querySelectorAll("span")].filter(
        (span) => (span.textContent || "").trim() === optionText,
      );
      if (!spans.length) return false;
      spans[0].setAttribute("data-radar-option", "1");
      return true;
    }, text);
    if (!tagged) throw new Error("筛选项不存在: " + text);
    await page.click('[data-radar-option="1"]', { label: "选择" + text });
    await page.waitForTimeout(1500);
    if (await optionSelected(text)) return;
  }
  throw new Error("筛选项三次点击后仍未选中: " + text);
};

for (const option of options) await clickOption(option);

if (options.length) {
  await page.waitForFunction(
    () => document.querySelectorAll("div.search-result-card").length > 0,
    undefined,
    { timeout: 20000 },
  );
}

const viewport = await page.evaluate(() => ({
  width: window.innerWidth,
  height: window.innerHeight,
}));

const mergeSnapshot = (snapshot, round, collected) => {
  for (const card of snapshot.cards) {
    if (!card.aweme_id) continue;
    if (!collected.has(card.aweme_id)) {
      collected.set(card.aweme_id, { ...card, first_seen_round: round });
    }
  }
};

const collected = new Map();
const rounds = [];
let lastCount = -1;
let stagnant = 0;

for (let round = 1; round <= ROUNDS; round += 1) {
  const snapshot = await page.evaluate(COLLECTOR_SOURCE);
  mergeSnapshot(snapshot, round, collected);
  rounds.push({
    round,
    card_count: snapshot.card_count,
    unique_so_far: collected.size,
  });
  if (snapshot.card_count === lastCount) stagnant += 1;
  else stagnant = 0;
  lastCount = snapshot.card_count;
  if (stagnant >= 2) break;

  await page.mouse.move(Math.round(viewport.width / 2), Math.round(viewport.height * 0.6), {
    label: "移动到结果区",
  });
  await page.mouse.wheel(0, SCROLL_STEP, { label: "滚动加载更多结果" });
  await page.waitForTimeout(1800);
}

const finalSnapshot = await page.evaluate(COLLECTOR_SOURCE);
mergeSnapshot(finalSnapshot, rounds.length + 1, collected);

const payload = {
  schema: "douyin-topic-radar/raw/1",
  keyword: KEYWORD,
  mode: MODE,
  collected_at: new Date().toISOString(),
  collected_at_local: new Date().toString(),
  page_url: await page.url(),
  viewport,
  rounds,
  cards: [...collected.values()],
  related_searches: finalSnapshot.related_searches,
  card_count: finalSnapshot.card_count,
  truncated: rounds.length >= ROUNDS,
};

const fs = await import("node:fs/promises");
const path = await import("node:path");
await fs.mkdir(path.dirname(OUT_PATH), { recursive: true });
await fs.writeFile(OUT_PATH, JSON.stringify(payload, null, 2), "utf8");

console.log(
  JSON.stringify({
    ok: true,
    keyword: KEYWORD,
    mode: MODE,
    cards: payload.cards.length,
    related: payload.related_searches.length,
    out: OUT_PATH,
    spaceId: task.spaceId,
    page: page.label,
  }),
);

if (SHOULD_FINISH) await task.finish({ keep: [] });
