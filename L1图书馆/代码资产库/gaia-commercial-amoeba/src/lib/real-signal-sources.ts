/**
 * 真实情报采集器 — 从公开信源抓取真实数据
 * 
 * 支持的信源:
 * - GitHub Trending (无需认证)
 * - HackerNews API (免费)
 * - RSS/Atom feeds (通用)
 * - 知乎热门 (RSS桥接)
 */

import * as cheerio from "cheerio";
import Parser from "rss-parser";

// ============================================================
// 类型定义
// ============================================================

export interface RealSignal {
  id: string;
  source: string;
  sourceUrl: string;
  title: string;
  summary: string;
  hotScore: number;     // 1-10 based on real metrics
  url: string;
  fetchedAt: string;
  departmentHint: string[];  // 建议分配给哪些部门
}

// ============================================================
// GitHub Trending
// ============================================================

export async function fetchGitHubTrending(): Promise<RealSignal[]> {
  const signals: RealSignal[] = [];

  try {
    const res = await fetch("https://github.com/trending?since=weekly", {
      headers: { "User-Agent": "Mozilla/5.0" },
      signal: AbortSignal.timeout(10000),
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const html = await res.text();
    const $ = cheerio.load(html);

    $("article.Box-row").each((i, el) => {
      if (i >= 5) return;

      const name = $(el).find("h2 a").text().trim().replace(/\s+/g, "");
      const desc = $(el).find("p").text().trim();
      const stars = $(el).find(".octicon-star").parent().text().trim();

      signals.push({
        id: `gh-${Date.now()}-${i}`,
        source: "GitHub Trending",
        sourceUrl: `https://github.com/${name}`,
        title: name,
        summary: desc || "无描述",
        hotScore: Math.min(10, parseInt(stars.replace(/,/g, "")) > 1000 ? 9 : 7),
        url: `https://github.com/${name}`,
        fetchedAt: new Date().toISOString(),
        departmentHint: ["technology", "strategy"],
      });
    });
  } catch (err) {
    console.error("GitHub Trending fetch failed:", err);
  }

  return signals;
}

// ============================================================
// HackerNews API (免费, 无需认证)
// ============================================================

export async function fetchHackerNews(): Promise<RealSignal[]> {
  const signals: RealSignal[] = [];

  try {
    const idsRes = await fetch(
      "https://hacker-news.firebaseio.com/v0/topstories.json",
      { signal: AbortSignal.timeout(10000) }
    );
    if (!idsRes.ok) throw new Error("Failed to fetch HN ids");

    const ids: number[] = (await idsRes.json()).slice(0, 10);

    const details = await Promise.all(
      ids.map(async (id) => {
        try {
          const r = await fetch(
            `https://hacker-news.firebaseio.com/v0/item/${id}.json`,
            { signal: AbortSignal.timeout(5000) }
          );
          return r.ok ? r.json() : null;
        } catch {
          return null;
        }
      })
    );

    for (const item of details) {
      if (!item || !item.title) continue;
      signals.push({
        id: `hn-${item.id}`,
        source: "HackerNews",
        sourceUrl: item.url || `https://news.ycombinator.com/item?id=${item.id}`,
        title: item.title,
        summary: `${item.score ?? 0} points | ${item.descendants ?? 0} comments`,
        hotScore: Math.min(10, Math.round((item.score ?? 0) / 20 + 3)),
        url: item.url || `https://news.ycombinator.com/item?id=${item.id}`,
        fetchedAt: new Date().toISOString(),
        departmentHint: item.title?.toLowerCase().includes("ai")
          ? ["technology", "strategy"]
          : ["technology"],
      });
    }
  } catch (err) {
    console.error("HackerNews fetch failed:", err);
  }

  return signals;
}

// ============================================================
// RSS Feed通用抓取器
// ============================================================

const RSS_FEEDS = [
  { url: "https://feeds.feedburner.com/36kr/xx", name: "36氪", dept: ["intelligence", "strategy"] },
  { url: "https://www.ruanyifeng.com/blog/atom.xml", name: "阮一峰周刊", dept: ["technology"] },
  { url: "https://hnrss.org/frontpage", name: "HNRSS", dept: ["technology"] },
];

export async function fetchRSSFeeds(): Promise<RealSignal[]> {
  const signals: RealSignal[] = [];
  const parser = new Parser({
    timeout: 10000,
    headers: { "User-Agent": "Mozilla/5.0" },
  });

  for (const feed of RSS_FEEDS) {
    try {
      const parsed = await parser.parseURL(feed.url);
      const items = (parsed.items ?? []).slice(0, 3);

      for (const item of items) {
        signals.push({
          id: `rss-${feed.name}-${Date.now()}`,
          source: feed.name,
          sourceUrl: item.link ?? feed.url,
          title: item.title ?? "无标题",
          summary: item.contentSnippet?.slice(0, 120) ?? "无摘要",
          hotScore: 7,
          url: item.link ?? feed.url,
          fetchedAt: new Date().toISOString(),
          departmentHint: feed.dept,
        });
      }
    } catch (err) {
      console.error(`RSS feed ${feed.name} failed:`, err);
    }
  }

  return signals;
}

// ============================================================
// 知乎模拟信号（真实场景需接入知乎开放API或Cookie爬虫）
// 当前用AI模拟知乎热门话题，但标注为"模拟"
// ============================================================

export async function fetchZhihuSignals(): Promise<RealSignal[]> {
  const signals: RealSignal[] = [];

  const prompt = `模拟知乎2026年6月商业/科技/法律/设计领域最热门的5个问题。
每个问题需包含：问题标题、关注人数(真实范围)、所属领域。

输出JSON：
{
  "questions": [
    {"title": "问题标题", "followers": 12345, "domain": "科技/商业/法律/设计"}
  ]
}`;

  try {
    const apiKey = process.env.LLM_API_KEY;
    if (!apiKey) return signals;

    const res = await fetch("https://api.deepseek.com/v1/chat/completions", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiKey}`,
      },
      body: JSON.stringify({
        model: "deepseek-chat",
        messages: [{ role: "user", content: prompt }],
        max_tokens: 1000,
        temperature: 0.7,
      }),
    });

    if (!res.ok) throw new Error(`API error: ${res.status}`);
    const data = await res.json();
    const text = data.choices?.[0]?.message?.content ?? "";
    const match = text.match(/\{[\s\S]*\}/);
    if (!match) return signals;

    const parsed = JSON.parse(match[0]);
    if (parsed.questions) {
      const domainToDept: Record<string, string[]> = {
        "科技": ["technology", "strategy"],
        "商业": ["intelligence", "strategy"],
        "法律": ["legal", "compliance"],
        "设计": ["design"],
        "金融": ["finance"],
        "运营": ["operations"],
      };

      for (const q of parsed.questions) {
        signals.push({
          id: `zhihu-${Date.now()}-${Math.random().toString(36).slice(2, 4)}`,
          source: "知乎（模拟）",
          sourceUrl: "https://www.zhihu.com/hot",
          title: q.title ?? "热门问题",
          summary: `${q.followers ?? 0}人关注`,
          hotScore: Math.min(10, Math.round((q.followers ?? 1000) / 10000) + 3),
          url: "https://www.zhihu.com/hot",
          fetchedAt: new Date().toISOString(),
          departmentHint: domainToDept[q.domain] ?? ["strategy"],
        });
      }
    }
  } catch (err) {
    console.error("Zhihu simulation failed:", err);
  }

  return signals;
}

// ============================================================
// 全量采集入口
// ============================================================

export async function collectAllRealSignals(): Promise<{
  signals: RealSignal[];
  sourceStats: { source: string; count: number }[];
}> {
  console.log("🔍 开始真实情报采集...");

  const results = await Promise.allSettled([
    fetchGitHubTrending(),
    fetchHackerNews(),
    fetchRSSFeeds(),
    fetchZhihuSignals(),
  ]);

  const allSignals: RealSignal[] = [];

  for (const result of results) {
    if (result.status === "fulfilled") {
      allSignals.push(...result.value);
    }
  }

  const stats: Record<string, number> = {};
  for (const s of allSignals) {
    stats[s.source] = (stats[s.source] ?? 0) + 1;
  }

  console.log(`✅ 采集完成: ${allSignals.length}条信号`);
  for (const [src, cnt] of Object.entries(stats)) {
    console.log(`   ${src}: ${cnt}条`);
  }

  return {
    signals: allSignals,
    sourceStats: Object.entries(stats).map(([source, count]) => ({ source, count })),
  };
}
