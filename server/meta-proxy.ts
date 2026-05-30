/**
 * 链客宝 SEO Meta 代理服务器
 * =============================
 * 轻量级 Express 服务，仅在 /app/card/:token 路由上注入 SEO meta 标签。
 * 不做 React SSR，仅做字符串级别的 HTML 模板修改。
 *
 * 工作原理:
 *   1. 拦截 /app/card/:token 请求
 *   2. 调用后端 API 获取名片数据 (GET /api/card/token/{token})
 *   3. 读取 dist/index.html 模板
 *   4. 在 <head> 中注入 og:title, og:description, og:image 等 meta 标签
 *   5. 返回完整 HTML（SPA JS 依然加载并正常 hydrate）
 *
 * 使用方式:
 *   DEV:   npx tsx server/meta-proxy.ts
 *   PROD:  NODE_ENV=production npx tsx server/meta-proxy.ts
 *
 * 配合 nginx 使用:
 *   location ~ ^/app/card/(.+)$ {
 *       proxy_pass http://127.0.0.1:3002;  # meta-proxy 端口
 *   }
 */

import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';

// ---- Polyfill __dirname for ESM ----
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const ROOT = path.resolve(__dirname, '..');
const DIST = path.resolve(ROOT, 'dist');

const API_BASE = process.env.API_BASE || 'http://localhost:8001';
const PORT = parseInt(process.env.META_PROXY_PORT || '3002', 10);
const HOST = process.env.HOST || '0.0.0.0';
const SITE_URL = process.env.SITE_URL || 'https://liankebao.top';

// ============================================================
// 后端 API 调用：获取名片数据
// ============================================================

interface CardFields {
  name?: string;
  position?: string;
  company?: string;
  phone?: string;
  email?: string;
  wechat?: string;
  address?: string;
  website?: string;
  cover_image?: string;
}

interface CardData {
  id: number;
  share_token: string;
  share_url: string;
  name: string;
  fields: CardFields;
  cover_image?: string;
  album_meta: any;
  created_at: string;
  view_count: number;
}

async function fetchCardData(token: string): Promise<CardData | null> {
  try {
    const res = await fetch(`${API_BASE}/api/card/token/${token}`, {
      // @ts-ignore
      signal: AbortSignal.timeout(5000),
    });
    if (!res.ok) return null;
    const json = await res.json() as any;
    if (json.code !== 200 || !json.data) return null;
    return json.data as CardData;
  } catch (err) {
    console.error(`[MetaProxy] 获取名片数据失败 (token=${token}):`, err);
    return null;
  }
}

// ============================================================
// Meta 标签生成
// ============================================================

function escapeHtml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

const DEFAULT_TITLE = '链客宝 - 数字名片';
const DEFAULT_DESC = '链客宝 — 一站式AI营销增长引擎，企业家的AI营销朋友圈。';
const DEFAULT_IMAGE = `${SITE_URL}/app/og-image.png`;

function buildMetaTags(cardData: CardData | null, token: string): { title: string; metaHtml: string } {
  if (!cardData) {
    return {
      title: DEFAULT_TITLE,
      metaHtml: `
    <meta property="og:title" content="${escapeHtml(DEFAULT_TITLE)}" />
    <meta property="og:description" content="${escapeHtml(DEFAULT_DESC)}" />
    <meta property="og:image" content="${escapeHtml(DEFAULT_IMAGE)}" />
    <meta property="og:url" content="${escapeHtml(SITE_URL)}/app/card/${escapeHtml(token)}" />
    <meta property="og:type" content="website" />
    <meta property="og:site_name" content="链客宝" />
    <meta property="og:locale" content="zh_CN" />
    <meta name="twitter:card" content="summary_large_image" />
    <meta name="twitter:title" content="${escapeHtml(DEFAULT_TITLE)}" />
    <meta name="twitter:description" content="${escapeHtml(DEFAULT_DESC)}" />
    <meta name="twitter:image" content="${escapeHtml(DEFAULT_IMAGE)}" />
    <title>${escapeHtml(DEFAULT_TITLE)}</title>
`,
    };
  }

  const name = cardData.name || '数字名片';
  const title = `${name} 的数字名片 | 链客宝`;
  const fields = cardData.fields || {};
  const company = fields.company || '';
  const position = fields.position || '';
  const description = [position, company].filter(Boolean).join(' · ') || DEFAULT_DESC;
  const image = cardData.cover_image || fields.cover_image || DEFAULT_IMAGE;
  const url = `${SITE_URL}/app/card/${escapeHtml(token)}`;

  const metaHtml = `
    <meta property="og:title" content="${escapeHtml(title)}" />
    <meta property="og:description" content="${escapeHtml(description)}" />
    <meta property="og:image" content="${escapeHtml(image)}" />
    <meta property="og:url" content="${escapeHtml(url)}" />
    <meta property="og:type" content="website" />
    <meta property="og:site_name" content="链客宝" />
    <meta property="og:locale" content="zh_CN" />
    <meta name="twitter:card" content="summary_large_image" />
    <meta name="twitter:title" content="${escapeHtml(title)}" />
    <meta name="twitter:description" content="${escapeHtml(description)}" />
    <meta name="twitter:image" content="${escapeHtml(image)}" />
    <title>${escapeHtml(title)}</title>
`;

  return { title, metaHtml };
}

// ============================================================
// 在 HTML 的 <head> 中注入 meta 标签
// ============================================================

function injectMetaIntoHtml(html: string, metaHtml: string): string {
  // 在 <head> 标签之后、第一个子节点之前插入 meta 标签
  const headEndIndex = html.indexOf('</head>');
  if (headEndIndex === -1) return html;

  // 找到 <title> 或 <meta charset> 之后的位置
  // 在 meta description 之后、link rel="icon" 之前插入
  const insertAfter = html.lastIndexOf('/>', headEndIndex);
  const insertPos = insertAfter !== -1 ? insertAfter + 2 : html.indexOf('>') + 1;

  return html.slice(0, insertPos) + '\n' + metaHtml + html.slice(insertPos);
}

// ============================================================
// 读取 dist/index.html 模板
// ============================================================

let cachedIndexHtml: string | null = null;

function getIndexHtml(): string | null {
  if (cachedIndexHtml) return cachedIndexHtml;

  // 尝试多个可能的路径
  const paths = [
    path.resolve(DIST, 'index.html'),
    path.resolve(ROOT, 'dist', 'index.html'),
  ];

  for (const p of paths) {
    if (fs.existsSync(p)) {
      const content = fs.readFileSync(p, 'utf-8');
      // 缓存（生产模式下）
      if (process.env.NODE_ENV === 'production') {
        cachedIndexHtml = content;
      }
      return content;
    }
  }

  return null;
}

// ============================================================
// 启动服务器
// ============================================================

async function startServer() {
  // 动态导入 express（ESM 兼容）
  const { default: express } = await import('express');
  const app = express();

  // ---- 健康检查 ----
  app.get('/health', (_req, res) => {
    res.json({ status: 'ok', service: 'meta-proxy' });
  });

  // ---- SEO Meta 代理：/app/card/:token ----
  app.get('/app/card/:token', async (req, res) => {
    const startTime = Date.now();
    const { token } = req.params;

    try {
      // 1. 获取名片数据
      const cardData = await fetchCardData(token);

      // 2. 生成 meta 标签
      const { title, metaHtml } = buildMetaTags(cardData, token);

      // 3. 读取 index.html 模板
      const indexHtml = getIndexHtml();
      if (!indexHtml) {
        console.error('[MetaProxy] 未找到 dist/index.html');
        res.status(500).send('Server Error: index.html not found');
        return;
      }

      // 4. 注入 meta 标签
      const fullHtml = injectMetaIntoHtml(indexHtml, metaHtml);

      const elapsed = Date.now() - startTime;
      console.log(`[MetaProxy] ✅ ${title} (${elapsed}ms)`);

      res.status(200).set({ 'Content-Type': 'text/html; charset=utf-8' });
      res.send(fullHtml);
    } catch (err) {
      console.error(`[MetaProxy] 处理失败: /app/card/${token}`, err);
      // 回退：返回原始 index.html
      const fallback = getIndexHtml();
      if (fallback) {
        res.status(200).set({ 'Content-Type': 'text/html; charset=utf-8' });
        res.send(fallback);
      } else {
        res.status(500).send('Server Error');
      }
    }
  });

  // ---- 非卡片路由：简单回应（nginx 应先拦截） ----
  app.get('*', (_req, res) => {
    res.status(404).send('Not found — this is the meta-proxy service for /app/card/:token only');
  });

  // ---- 启动 ----
  app.listen(PORT, HOST, () => {
    console.log(`\n  🔖 链客宝 SEO Meta Proxy 启动`);
    console.log(`  🌐 地址: http://${HOST}:${PORT}`);
    console.log(`  📇 路由: /app/card/:token (SEO meta 注入)`);
    console.log(`  ⚡ API 后端: ${API_BASE}`);
    console.log(`  📂 静态模板: ${DIST}`);
    console.log(`  🌍 站点 URL: ${SITE_URL}\n`);
  });
}

startServer().catch((err) => {
  console.error('[MetaProxy] 启动失败:', err);
  process.exit(1);
});
