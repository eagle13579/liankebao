/**
 * 链客宝AI SSR 服务器
 *
 * Express + Vite SSR 服务器，仅对 /app/card/:token 路由进行服务端渲染，
 * 其他路由保持 CSR（返回 SPA index.html）。
 *
 * 两种运行模式:
 *   DEV:  npm run dev:ssr   — 使用 Vite dev server (HMR)
 *   PROD: npm run build:ssr && npm run start:ssr  — 生产模式
 *
 * 运行方式: npx tsx server/ssr.ts
 */

import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';

// ---- Polyfill __dirname for ESM ----
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const ROOT = path.resolve(__dirname, '..');
const DIST = path.resolve(ROOT, 'dist');
const SSR_DIST = path.resolve(ROOT, 'dist-ssr');

const API_BASE = process.env.API_BASE || 'http://localhost:8001';
const PORT = parseInt(process.env.PORT || '3000', 10);
const HOST = process.env.HOST || '0.0.0.0';
const PROD = process.env.NODE_ENV === 'production' || process.env.IS_SSR === 'true';

// ============================================================
// 渲染函数类型
// ============================================================

interface CardData {
  id: number;
  share_token: string;
  share_url: string;
  name: string;
  fields: Record<string, any>;
  cover_image?: string;
  album_meta: {
    total_pages: number;
    pages: any[];
    settings: {
      turn_animation: string;
      page_width: number;
      page_height: number;
      corner_radius: number;
      shadow: boolean;
    };
  };
  created_at: string;
  view_count: number;
}

interface SSRRenderResult {
  html: string;
  title: string;
  description: string;
  image: string;
}

// ============================================================
// 后端 API 调用：获取名片数据
// ============================================================

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
    console.error(`[SSR] 获取名片数据失败 (token=${token}):`, err);
    return null;
  }
}

// ============================================================
// SSR 中间件
// ============================================================

interface SSRModule {
  renderCardPage: (data: CardData | null) => SSRRenderResult;
  buildHTML: (result: SSRRenderResult, appHtml: string, cssLinks: string[], jsScripts: string[], cardData?: CardData | null) => string;
}

let ssrModule: SSRModule | null = null;
let viteDevServer: any = null;

async function loadSSRModule(): Promise<SSRModule> {
  if (ssrModule) return ssrModule;

  if (PROD) {
    // 生产模式：从 dist-ssr 加载预构建的 SSR bundle
    const mod = await import(path.resolve(SSR_DIST, 'entry-server.mjs'));
    ssrModule = mod as SSRModule;
    return ssrModule;
  }

  // 开发模式：使用 Vite dev server 的 ssrLoadModule
  if (!viteDevServer) {
    const { createServer } = await import('vite');
    viteDevServer = await createServer({
      root: ROOT,
      server: { middlewareMode: true },
      appType: 'spa',
      base: '/app/',
    });
  }
  const mod = await viteDevServer.ssrLoadModule('/src/entry-server.tsx') as any;
  ssrModule = {
    renderCardPage: mod.renderCardPage,
    buildHTML: mod.buildHTML,
  } as SSRModule;
  return ssrModule;
}

// ============================================================
// 主服务器启动
// ============================================================

async function startServer() {
  const { default: express } = await import('express');
  const { default: compression } = await import('compression');

  const app = express();

  // ---- 基础中间件 ----
  app.use(compression());

  if (!PROD) {
    // 开发模式：集成 Vite 中间件
    const { createServer } = await import('vite');
    viteDevServer = await createServer({
      root: ROOT,
      server: { middlewareMode: true },
      appType: 'spa',
      base: '/app/',
    });
    app.use(viteDevServer.middlewares as any);
  } else {
    // 生产模式：静态文件服务
    const staticDir = path.resolve(DIST);
    if (fs.existsSync(staticDir)) {
      app.use('/app', express.static(staticDir, {
        maxAge: '30d',
        immutable: true,
        index: false,
      }));
    }
    // 根路径静态文件（public 目录）
    const publicDir = path.resolve(ROOT, 'public');
    if (fs.existsSync(publicDir)) {
      app.use(express.static(publicDir, { maxAge: '30d' }));
    }
  }

  // ---- SSR 路由：仅在 /app/card/:token 生效 ----
  app.get('/app/card/:token', async (req, res) => {
    const startTime = Date.now();
    try {
      const { token } = req.params;
      console.log(`[SSR] Rendering card route: /app/card/${token}`);

      // 获取名片数据
      const cardData = await fetchCardData(token);

      // 加载 SSR 渲染模块
      const mod = await loadSSRModule();

      // 渲染
      const result = mod.renderCardPage(cardData);

      let cssLinks: string[] = [];
      let jsScripts: string[] = [];

      if (PROD) {
        // 生产模式：从 dist 读取 index.html 提取资源链接
        const distIndexPath = path.resolve(DIST, 'index.html');
        if (fs.existsSync(distIndexPath)) {
          const indexContent = fs.readFileSync(distIndexPath, 'utf-8');
          const cssMatch = indexContent.match(/<link[^>]*href="([^"]*\.css)"[^>]*\/?>/g) || [];
          const jsMatch = indexContent.match(/<script[^>]*src="([^"]*\.js)"[^>]*><\/script>/g) || [];
          cssLinks = cssMatch.map((m: string) => {
            const hrefMatch = m.match(/href="([^"]+)"/);
            return hrefMatch ? hrefMatch[1] : '';
          }).filter(Boolean);
          jsScripts = jsMatch.map((m: string) => {
            const srcMatch = m.match(/src="([^"]+)"/);
            return srcMatch ? srcMatch[1] : '';
          }).filter(Boolean);
        }
      } else {
        // 开发模式：通过 Vite 转换 HTML
        const template = fs.readFileSync(path.resolve(ROOT, 'index.html'), 'utf-8');
        const transformed = await viteDevServer.transformIndexHtml(`/app/card/${token}`, template);
        const cssMatch = transformed.match(/<link[^>]*href="([^"]*\.css)"[^>]*\/?>/g) || [];
        cssLinks = cssMatch.map((m: string) => {
          const hrefMatch = m.match(/href="([^"]+)"/);
          return hrefMatch ? hrefMatch[1] : '';
        }).filter(Boolean);
        jsScripts = ['/src/main.tsx'];
      }

      // 组装完整 HTML
      const fullHtml = mod.buildHTML(result, result.html, cssLinks, jsScripts, cardData);

      const elapsed = Date.now() - startTime;
      console.log(`[SSR] ✅ 渲染完成: /app/card/${token} (${elapsed}ms)`);

      res.status(200).set({ 'Content-Type': 'text/html; charset=utf-8' });
      res.send(fullHtml);
    } catch (err: any) {
      console.error('[SSR] 渲染错误:', err);
      // 回退：返回 SPA index.html 让客户端自行处理
      try {
        const fallbackHtml = PROD
          ? fs.readFileSync(path.resolve(DIST, 'index.html'), 'utf-8')
          : await viteDevServer.transformIndexHtml(
              req.originalUrl,
              fs.readFileSync(path.resolve(ROOT, 'index.html'), 'utf-8')
            );
        res.status(200).set({ 'Content-Type': 'text/html; charset=utf-8' });
        res.send(fallbackHtml);
      } catch {
        res.status(500).send('Server Error');
      }
    }
  });

  // ---- 非 SSR 路由回退：返回 SPA index.html ----
  app.get('/app/*', async (req, res) => {
    try {
      if (PROD) {
        const indexPath = path.resolve(DIST, 'index.html');
        if (fs.existsSync(indexPath)) {
          const content = fs.readFileSync(indexPath, 'utf-8');
          res.status(200).set({ 'Content-Type': 'text/html; charset=utf-8' });
          res.send(content);
        } else {
          res.status(404).send('Not Found');
        }
      } else {
        // Vite dev 模式下由中间件处理
        res.sendStatus(404);
      }
    } catch (err) {
      console.error('[SSR] Fallback error:', err);
      res.status(500).send('Server Error');
    }
  });

  // ---- 根路径重定向 ----
  app.get('/', (_req, res) => {
    res.redirect('/app/');
  });

  // ---- 启动 ----
  app.listen(PORT, HOST, () => {
    console.log(`\n  🚀 链客宝AI SSR 服务器启动`);
    console.log(`  📡 模式: ${PROD ? 'PRODUCTION' : 'DEVELOPMENT'}`);
    console.log(`  🌐 地址: http://${HOST}:${PORT}`);
    console.log(`  📇 SSR 路由: /app/card/:token`);
    console.log(`  🔄 其他路由: SPA CSR`);
    console.log(`  ⚡ API 后端: ${API_BASE}\n`);
  });
}

startServer().catch((err) => {
  console.error('[SSR] 服务器启动失败:', err);
  process.exit(1);
});
