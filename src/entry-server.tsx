/**
 * 链客宝 SSR 服务端入口
 *
 * 用于 Express SSR 服务器渲染名片分享页面。
 * 仅对 /card/:token 路由生效，其他路由保持 CSR。
 */
import React from 'react';
import { renderToString } from 'react-dom/server';

// ============================================================
// 类型定义（与 BusinessCardPage.tsx 保持一致）
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

interface AlbumPage {
  page: number;
  type: string;
  title: string;
  subtitle?: string;
  fields?: { label: string; value: string }[];
  content?: Record<string, string>;
  style: {
    background: string;
    textColor: string;
    accentColor: string;
  };
}

interface AlbumMeta {
  total_pages: number;
  pages: AlbumPage[];
  settings: {
    turn_animation: string;
    page_width: number;
    page_height: number;
    corner_radius: number;
    shadow: boolean;
  };
}

interface CardData {
  id: number;
  share_token: string;
  share_url: string;
  name: string;
  fields: CardFields;
  cover_image?: string;
  album_meta: AlbumMeta;
  created_at: string;
  view_count: number;
}

// ============================================================
// SSR 渲染：名片详情页
// ============================================================

function SSRCoverPage(page: AlbumPage) {
  return (
    <div
      className="ssr-page ssr-cover"
      style={{
        background: page.style.background,
        color: page.style.textColor,
      }}
    >
      <div className="ssr-cover-content">
        <div
          className="ssr-avatar"
          style={{ backgroundColor: page.style.accentColor + '33' }}
        >
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
            <circle cx="12" cy="7" r="4" />
          </svg>
        </div>
        <h3 className="ssr-title">{page.title}</h3>
        {page.subtitle && <p className="ssr-subtitle">{page.subtitle}</p>}
        <div
          className="ssr-badge"
          style={{ backgroundColor: page.style.accentColor }}
        >
          Powered by 链客宝 AI
        </div>
      </div>
    </div>
  );
}

function SSRContactPage(page: AlbumPage) {
  return (
    <div
      className="ssr-page ssr-contact"
      style={{
        background: page.style.background,
        color: page.style.textColor,
      }}
    >
      <h3 className="ssr-section-title" style={{ color: page.style.accentColor }}>
        {page.title}
      </h3>
      <div className="ssr-contact-list">
        {(page.fields || []).map((f, i) => (
          <div key={i} className="ssr-contact-item">
            <span className="ssr-contact-label">{f.label.split(' ')[0]}</span>
            <span className="ssr-contact-value">{f.value}</span>
          </div>
        ))}
        {(!page.fields || page.fields.length === 0) && (
          <p className="ssr-empty-text">暂无联系方式</p>
        )}
      </div>
    </div>
  );
}

function SSRCompanyPage(page: AlbumPage) {
  return (
    <div
      className="ssr-page ssr-company"
      style={{
        background: page.style.background,
        color: page.style.textColor,
      }}
    >
      <h3 className="ssr-section-title" style={{ color: page.style.accentColor }}>
        {page.title}
      </h3>
      <div className="ssr-company-list">
        {page.content?.company && (
          <div className="ssr-company-item">
            <p className="ssr-field-label">公司</p>
            <p className="ssr-field-value">{page.content.company}</p>
          </div>
        )}
        {page.content?.position && (
          <div className="ssr-company-item">
            <p className="ssr-field-label">职位</p>
            <p className="ssr-field-value">{page.content.position}</p>
          </div>
        )}
        {page.content?.address && (
          <div className="ssr-company-item">
            <p className="ssr-field-label">地址</p>
            <p className="ssr-field-value">{page.content.address}</p>
          </div>
        )}
        {page.content?.website && (
          <div className="ssr-company-item">
            <p className="ssr-field-label">官网</p>
            <p className="ssr-field-value ssr-link">{page.content.website}</p>
          </div>
        )}
      </div>
    </div>
  );
}

function SSRQRCodePage(page: AlbumPage) {
  return (
    <div
      className="ssr-page ssr-qrcode"
      style={{
        background: page.style.background,
        color: page.style.textColor,
      }}
    >
      <div className="ssr-qrcode-content">
        <div
          className="ssr-qrcode-box"
          style={{ backgroundColor: page.style.accentColor + '15' }}
        >
          <svg
            width="80" height="80" viewBox="0 0 24 24" fill="none"
            stroke={page.style.accentColor} strokeWidth="1.5"
          >
            <rect x="3" y="3" width="7" height="7" rx="1" />
            <rect x="14" y="3" width="7" height="7" rx="1" />
            <rect x="3" y="14" width="7" height="7" rx="1" />
            <path d="M14 14h2v2h-2zM18 14h2v2h-2zM14 18h2v2h-2zM18 18h2v2h-2z" />
          </svg>
        </div>
        <h3 className="ssr-title">{page.title}</h3>
        {page.subtitle && <p className="ssr-subtitle">{page.subtitle}</p>}
      </div>
    </div>
  );
}

function renderPageContent(page: AlbumPage): string {
  let element: React.ReactElement;

  switch (page.type) {
    case 'cover':
      element = <SSRCoverPage {...page} />;
      break;
    case 'contact':
      element = <SSRContactPage {...page} />;
      break;
    case 'company':
      element = <SSRCompanyPage {...page} />;
      break;
    case 'qrcode':
      element = <SSRQRCodePage {...page} />;
      break;
    default:
      element = (
        <div
          className="ssr-page"
          style={{
            background: page.style.background,
            color: page.style.textColor,
          }}
        >
          <div className="ssr-default-content">
            <p>{page.title}</p>
          </div>
        </div>
      );
  }

  return renderToString(element);
}

function renderCardPreview(cardData: CardData): string {
  if (!cardData.album_meta?.pages?.length) return '';

  const firstPage = cardData.album_meta.pages[0];
  const settings = cardData.album_meta.settings;

  const pageContent = renderPageContent(firstPage);

  return renderToString(
    <div className="ssr-card-preview" style={{ width: settings.page_width }}>
      <div
        className="ssr-card-flipbook"
        style={{
          width: settings.page_width,
          height: settings.page_height,
          borderRadius: settings.corner_radius,
          boxShadow: settings.shadow
            ? '0 20px 60px rgba(0,0,0,0.15), 0 8px 20px rgba(0,0,0,0.1)'
            : 'none',
        }}
      >
        <div dangerouslySetInnerHTML={{ __html: pageContent }} />
        <div className="ssr-card-edge" />
        <div className="ssr-card-curl" />
      </div>
      <div className="ssr-card-meta">
        <div className="ssr-card-name">{cardData.name}</div>
        {cardData.fields?.position && (
          <div className="ssr-card-position">{cardData.fields.position}</div>
        )}
        {cardData.fields?.company && (
          <div className="ssr-card-company">{cardData.fields.company}</div>
        )}
        <div className="ssr-card-views">{cardData.view_count} 次浏览</div>
      </div>
    </div>
  );
}

// ============================================================
// 主渲染函数（SSR 入口）
// ============================================================

export interface SSRRenderResult {
  html: string;
  title: string;
  description: string;
  image: string;
}

const DEFAULT_TITLE = '链客宝 - 数字名片';
const DEFAULT_DESC = '链客宝 — 一站式AI营销增长引擎，企业家的AI营销朋友圈。';
const DEFAULT_IMAGE = '/app/og-image.png';

export function renderCardPage(cardData: CardData | null): SSRRenderResult {
  const name = cardData?.name || '数字名片';
  const title = `${name} 的数字名片 | 链客宝`;
  const fields = cardData?.fields || {};
  const company = fields.company || '';
  const position = fields.position || '';
  const description = [position, company].filter(Boolean).join(' · ') || DEFAULT_DESC;
  const image = cardData?.cover_image || (fields.cover_image) || DEFAULT_IMAGE;

  const previewHtml = cardData ? renderCardPreview(cardData) : '';

  return {
    title,
    description,
    image,
    html: previewHtml,
  };
}

// ============================================================
// HTML 模板组装
// ============================================================

export function buildHTML(
  result: SSRRenderResult,
  appHtml: string,
  cssLinks: string[],
  jsScripts: string[],
  cardData: CardData | null = null,
): string {
  const cardDataJson = cardData ? JSON.stringify(cardData).replace(/</g, '\\u003c') : 'null';

  return `<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta name="description" content="${escapeHtml(result.description)}" />
    <meta name="keywords" content="链客宝, 数字名片, AI名片, ${escapeHtml(result.title)}" />
    <link rel="icon" href="data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 100 100%22><text y=%22.9em%22 font-size=%2290%22>🤝</text></svg>" />

    <!-- Open Graph / 社交分享 -->
    <meta property="og:type" content="website" />
    <meta property="og:title" content="${escapeHtml(result.title)}" />
    <meta property="og:description" content="${escapeHtml(result.description)}" />
    <meta property="og:image" content="${escapeHtml(result.image)}" />
    <meta property="og:url" content="https://liankebao.top" />
    <meta property="og:site_name" content="链客宝" />
    <meta property="og:locale" content="zh_CN" />

    <!-- Twitter Card -->
    <meta name="twitter:card" content="summary_large_image" />
    <meta name="twitter:title" content="${escapeHtml(result.title)}" />
    <meta name="twitter:description" content="${escapeHtml(result.description)}" />
    <meta name="twitter:image" content="${escapeHtml(result.image)}" />

    <!-- PWA -->
    <link rel="manifest" href="/app/manifest.json" />
    <meta name="apple-mobile-web-app-capable" content="yes" />
    <meta name="apple-mobile-web-app-status-bar-style" content="default" />
    <meta name="apple-mobile-web-app-title" content="链客宝" />

    <title>${escapeHtml(result.title)}</title>

    ${cssLinks.map(href => `    <link rel="stylesheet" href="${href}" />`).join('\n')}
  </head>
  <body>
    <div id="root">${appHtml}</div>
    ${jsScripts.map(src => `    <script type="module" src="${src}"></script>`).join('\n')}

    <!-- SSR 状态注入：客户端 hydration 用 -->
    <script>
      window.__SSR_CARD_DATA__ = ${cardDataJson};
    </script>

    <!-- Service Worker -->
    <script>
      if ('serviceWorker' in navigator) {
        window.addEventListener('load', function() {
          navigator.serviceWorker.register('/sw.js').then(function(reg) {
            console.log('[PWA] Service Worker 注册成功:', reg.scope);
          }).catch(function(err) {
            console.warn('[PWA] Service Worker 注册失败:', err);
          });
        });
      }
    </script>
  </body>
</html>`;
}

function escapeHtml(str: string): string {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
