#!/usr/bin/env node
/**
 * 链客宝 — 轻量级预渲染脚本
 * =============================================================================
 * 功能: 使用 Puppeteer 将 SPA 的关键页面渲染为静态 HTML,
 *       供爬虫/搜索引擎索引, 提升 SEO.
 *
 * 前置条件:
 *   1. 先执行 npm run build 完成生产构建
 *   2. Node.js >= 18, Puppeteer 会自行下载 Chromium
 *
 * 使用方式:
 *   node scripts/pre-render.js
 *
 * 输出目录:
 *   deploy/docker/dist/prerendered/
 *   (构建产物所在目录下的 prerendered/ 子目录)
 *
 * 可配置项:
 *   - PRERENDER_BASE: 构建输出目录 (默认 deploy/docker/dist)
 *   - PRERENDER_PORT: 预览服务端口 (默认 4173)
 * =============================================================================
 */

import { launch } from 'puppeteer';
import { createServer } from 'http';
import { readFileSync, existsSync, mkdirSync, writeFileSync } from 'fs';
import { resolve, dirname, extname, join } from 'path';
import { fileURLToPath } from 'url';

// ── 路径配置 ─────────────────────────────────────────────────────────────────
const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
const PROJECT_ROOT = resolve(__dirname, '..');

// 构建输出目录 (与 vite.config.ts 中的 outDir 一致)
const BUILD_DIR = resolve(PROJECT_ROOT, 'deploy/docker/dist');

// 预渲染输出目录
const PRERENDER_DIR = resolve(BUILD_DIR, 'prerendered');

// ── 待预渲染页面 ──────────────────────────────────────────────────────────────
// 格式: { route, outputFile, title }
// route       → 浏览器访问路径
// outputFile  → 相对于 PRERENDER_DIR 的输出文件路径
// title       → 页面标题 (用于日志)
const PAGES = [
  { route: '/',              outputFile: 'index.html',            title: '首页' },
  { route: '/business-card', outputFile: 'business-card.html',    title: '数字名片' },
  { route: '/trust',         outputFile: 'trust.html',            title: '信任评分' },
  { route: '/pricing',       outputFile: 'pricing.html',          title: '价格方案' },
  { route: '/about',         outputFile: 'about.html',            title: '关于我们' },
  { route: '/login',         outputFile: 'login.html',            title: '登录' },
  { route: '/onboarding',    outputFile: 'onboarding.html',       title: '冷启动引导' },
];

// ── 配置 ──────────────────────────────────────────────────────────────────────
const PORT = parseInt(process.env.PRERENDER_PORT || '4173', 10);
const BASE_URL = `http://127.0.0.1:${PORT}`;
const RENDER_TIMEOUT = 30_000;       // 单页渲染超时 (ms)
const NAVIGATION_TIMEOUT = 15_000;   // 导航超时 (ms)

// ── 简单静态文件服务器 ─────────────────────────────────────────────────────────
function createStaticServer(buildDir) {
  const mimeTypes = {
    '.html': 'text/html; charset=utf-8',
    '.js':   'application/javascript; charset=utf-8',
    '.css':  'text/css; charset=utf-8',
    '.json': 'application/json; charset=utf-8',
    '.png':  'image/png',
    '.jpg':  'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.gif':  'image/gif',
    '.svg':  'image/svg+xml',
    '.ico':  'image/x-icon',
    '.woff': 'font/woff',
    '.woff2':'font/woff2',
    '.ttf':  'font/ttf',
  };

  return createServer((req, res) => {
    let urlPath = new URL(req.url, 'http://127.0.0.1').pathname;

    // SPA 回退: 非静态资源路径 → index.html
    const ext = extname(urlPath);
    if (!ext || ext === '.html') {
      const filePath = join(buildDir, urlPath === '/' ? 'index.html' : urlPath);
      if (existsSync(filePath) && ext === '.html') {
        // 精确匹配到 HTML 文件 → 直接返回
        serveFile(res, filePath, mimeTypes);
        return;
      }
      // SPA 回退
      serveFile(res, join(buildDir, 'index.html'), mimeTypes);
      return;
    }

    const filePath = join(buildDir, urlPath);
    serveFile(res, filePath, mimeTypes);
  });
}

function serveFile(res, filePath, mimeTypes) {
  try {
    if (!existsSync(filePath)) {
      res.writeHead(404);
      res.end('Not Found');
      return;
    }
    const ext = extname(filePath);
    const contentType = mimeTypes[ext] || 'application/octet-stream';
    const content = readFileSync(filePath);
    res.writeHead(200, { 'Content-Type': contentType });
    res.end(content);
  } catch (err) {
    res.writeHead(500);
    res.end('Internal Server Error');
  }
}

// ── 提取页面元数据 ────────────────────────────────────────────────────────────
function extractMeta($html) {
  const title = $html.match(/<title>([^<]*)<\/title>/)?.[1] || '';
  const desc = $html.match(/<meta\s+name=["']description["']\s+content=["']([^"']*)["']/)?.[1] || '';
  const ogTitle = $html.match(/<meta\s+property=["']og:title["']\s+content=["']([^"']*)["']/)?.[1] || '';
  return { title, desc, ogTitle };
}

// ── 主逻辑 ────────────────────────────────────────────────────────────────────
async function main() {
  console.log('='.repeat(60));
  console.log('  链客宝 — 轻量级预渲染脚本');
  console.log('='.repeat(60));

  // 检查构建产物
  const indexHtml = resolve(BUILD_DIR, 'index.html');
  if (!existsSync(indexHtml)) {
    console.error(`\n❌ 未找到构建产物: ${indexHtml}`);
    console.error('   请先执行 npm run build');
    process.exit(1);
  }
  console.log(`\n📁 构建目录: ${BUILD_DIR}`);

  // 准备输出目录
  if (!existsSync(PRERENDER_DIR)) {
    mkdirSync(PRERENDER_DIR, { recursive: true });
  }
  console.log(`📁 输出目录: ${PRERENDER_DIR}\n`);

  // 启动静态文件服务器
  const server = createStaticServer(BUILD_DIR);
  await new Promise((resolve) => server.listen(PORT, '127.0.0.1', resolve));
  console.log(`🌐 预览服务已启动: http://127.0.0.1:${PORT}\n`);

  let browser;
  try {
    // 启动 Puppeteer
    browser = await launch({
      headless: true,
      args: [
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-dev-shm-usage',
        '--disable-gpu',
      ],
    });

    const page = await browser.newPage();
    await page.setViewport({ width: 1280, height: 720 });

    // 模拟 Googlebot User-Agent, 让 SPA 按 SEO 模式渲染
    await page.setUserAgent(
      'Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)'
    );

    const results = [];

    for (const { route, outputFile, title } of PAGES) {
      const url = `${BASE_URL}${route}`;
      process.stdout.write(`  🔄 渲染: ${title.padEnd(12)} ${url} ... `);

      try {
        await page.goto(url, {
          waitUntil: 'networkidle0',
          timeout: NAVIGATION_TIMEOUT,
        });

        // 额外等待: 确保动态内容完成渲染
        await new Promise((r) => setTimeout(r, 2000));

        // 获取页面完整 HTML
        const html = await page.content();
        const sizeKB = (Buffer.byteLength(html, 'utf-8') / 1024).toFixed(1);

        // 提取元数据
        const meta = extractMeta(html);

        // 写入文件
        const outputPath = resolve(PRERENDER_DIR, outputFile);
        writeFileSync(outputPath, html, 'utf-8');

        console.log(`✅ ${sizeKB}KB`);
        results.push({ route, outputFile, sizeKB, ...meta });
      } catch (err) {
        console.log(`❌ ${err.message}`);
        results.push({ route, outputFile, error: err.message });
      }
    }

    // ── 输出汇总 ──────────────────────────────────────────────────────────
    console.log('\n' + '='.repeat(60));
    console.log('  预渲染结果汇总');
    console.log('='.repeat(60));
    console.log('  路由'.padEnd(20) + '文件'.padEnd(22) + '大小');
    console.log('  ' + '-'.repeat(56));
    for (const r of results) {
      const status = r.error ? '❌' : '✅';
      const size = r.sizeKB ? `${r.sizeKB} KB` : r.error?.slice(0, 30) || '';
      console.log(`  ${status} ${r.route.padEnd(18)} ${r.outputFile.padEnd(20)} ${size}`);
    }

    // ── 生成索引文件 (方便调试) ──────────────────────────────────────────
    const indexMd = [
      '# 预渲染页面索引',
      '',
      `生成时间: ${new Date().toISOString()}`,
      `构建目录: ${BUILD_DIR}`,
      `输出目录: ${PRERENDER_DIR}`,
      '',
      '| 路由 | 文件 | 大小 | 标题 | 描述 |',
      '|------|------|------|------|------|',
    ];
    for (const r of results) {
      const metaTitle = (r.title || '').replace(/\|/g, '\\|');
      const metaDesc = (r.desc || '').replace(/\|/g, '\\|');
      const size = r.sizeKB ? `${r.sizeKB} KB` : '❌';
      indexMd.push(`| ${r.route} | ${r.outputFile} | ${size} | ${metaTitle} | ${metaDesc} |`);
    }
    writeFileSync(resolve(PRERENDER_DIR, 'INDEX.md'), indexMd.join('\n'), 'utf-8');

    console.log(`\n📄 索引文件: ${PRERENDER_DIR}/INDEX.md`);
    console.log(`\n✅ 预渲染完成! 共 ${results.length} 个页面\n`);

  } finally {
    if (browser) await browser.close();
    await new Promise((resolve) => server.close(resolve));
  }
}

main().catch((err) => {
  console.error('\n❌ 预渲染失败:', err.message);
  process.exit(1);
});
