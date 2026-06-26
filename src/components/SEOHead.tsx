/**
 * 链客宝 — SEO Head 组件
 * ========================
 * 在每个页面注入 JSON-LD 结构化数据（Organization / WebSite / BreadcrumbList），
 * 以及动态 OG 标签和 Twitter Card 元数据。
 *
 * 用法：
 *   <SEOHead
 *     title="页面标题"
 *     description="页面描述"
 *     breadcrumbs={[{ name: '首页', url: '/' }, { name: '当前页', url: '/current' }]}
 *   />
 */
import { useEffect } from 'react';

interface BreadcrumbItem {
  name: string;
  url: string;
}

interface SEOHeadProps {
  title?: string;
  description?: string;
  breadcrumbs?: BreadcrumbItem[];
}

const SITE_NAME = '链客宝';
const SITE_URL = 'https://liankebao.top';
const DEFAULT_DESCRIPTION = '链客宝 — 企业家供需匹配平台，帮助企业家高效匹配资源、商机和合作伙伴。';
const OG_IMAGE = `${SITE_URL}/og-image.png`;

/**
 * 获取或创建 <meta> 标签
 */
function ensureMetaTag(name: string, property?: string): HTMLMetaElement {
  const attr = property ? 'property' : 'name';
  const attrValue = property || name;
  let meta = document.querySelector(`meta[${attr}="${attrValue}"]`) as HTMLMetaElement | null;
  if (!meta) {
    meta = document.createElement('meta');
    meta.setAttribute(attr, attrValue);
    document.head.appendChild(meta);
  }
  return meta;
}

/**
 * 注入 JSON-LD script 标签到 <head>
 */
function injectJSONLD(id: string, data: Record<string, unknown>) {
  const existing = document.getElementById(id);
  if (existing) existing.remove();

  const script = document.createElement('script');
  script.id = id;
  script.type = 'application/ld+json';
  script.textContent = JSON.stringify(data, null, 2);
  document.head.appendChild(script);
}

/**
 * 更新页面所有 OG 和 Twitter Card 元标签
 */
function updateSocialMeta(title: string, description: string, url: string) {
  const fullTitle = `${title} — ${SITE_NAME}`;

  // OG tags
  ensureMetaTag('og:title', 'og:title').setAttribute('content', fullTitle);
  ensureMetaTag('og:description', 'og:description').setAttribute('content', description);
  ensureMetaTag('og:url', 'og:url').setAttribute('content', url);
  ensureMetaTag('og:image', 'og:image').setAttribute('content', OG_IMAGE);
  ensureMetaTag('og:site_name', 'og:site_name').setAttribute('content', SITE_NAME);
  ensureMetaTag('og:locale', 'og:locale').setAttribute('content', 'zh_CN');

  // Twitter Card
  ensureMetaTag('twitter:card').setAttribute('content', 'summary_large_image');
  ensureMetaTag('twitter:title').setAttribute('content', fullTitle);
  ensureMetaTag('twitter:description').setAttribute('content', description);
  ensureMetaTag('twitter:image').setAttribute('content', OG_IMAGE);

  // Canonical URL
  let link = document.querySelector('link[rel="canonical"]') as HTMLLinkElement | null;
  if (!link) {
    link = document.createElement('link');
    link.rel = 'canonical';
    document.head.appendChild(link);
  }
  link.href = url;
}

export default function SEOHead({ title, description, breadcrumbs }: SEOHeadProps) {
  useEffect(() => {
    const pageTitle = title || SITE_NAME;
    const pageDesc = description || DEFAULT_DESCRIPTION;
    const pageUrl = window.location.href;

    // ── 页面标题 ───────────────────────────────────────────────────
    if (title) {
      document.title = `${title} — ${SITE_NAME}`;
    } else {
      document.title = SITE_NAME;
    }

    // ── Meta Description ───────────────────────────────────────────
    const metaDesc = document.querySelector('meta[name="description"]');
    if (metaDesc) {
      metaDesc.setAttribute('content', pageDesc);
    }

    // ── OG / Twitter 社交元标签 ────────────────────────────────────
    updateSocialMeta(title || SITE_NAME, pageDesc, pageUrl);

    // ── JSON-LD: Organization ──────────────────────────────────────
    injectJSONLD('jsonld-organization', {
      '@context': 'https://schema.org',
      '@type': 'Organization',
      '@id': `${SITE_URL}/#organization`,
      name: SITE_NAME,
      alternateName: 'ChainKe',
      url: SITE_URL,
      description: DEFAULT_DESCRIPTION,
      foundingDate: '2024',
      areaServed: { '@type': 'Country', name: '中国' },
      logo: {
        '@type': 'ImageObject',
        url: `${SITE_URL}/icons/icon-192x192.png`,
        width: 192,
        height: 192,
      },
    });

    // ── JSON-LD: WebSite ──────────────────────────────────────────
    injectJSONLD('jsonld-website', {
      '@context': 'https://schema.org',
      '@type': 'WebSite',
      '@id': `${SITE_URL}/#website`,
      url: SITE_URL,
      name: SITE_NAME,
      alternateName: 'ChainKe',
      description: DEFAULT_DESCRIPTION,
      inLanguage: 'zh-CN',
      publisher: { '@id': `${SITE_URL}/#organization` },
    });

    // ── JSON-LD: BreadcrumbList ───────────────────────────────────
    if (breadcrumbs && breadcrumbs.length > 0) {
      injectJSONLD('jsonld-breadcrumbs', {
        '@context': 'https://schema.org',
        '@type': 'BreadcrumbList',
        itemListElement: breadcrumbs.map((item, index) => ({
          '@type': 'ListItem',
          position: index + 1,
          name: item.name,
          item: `${SITE_URL}${item.url}`,
        })),
      });
    } else {
      const existing = document.getElementById('jsonld-breadcrumbs');
      if (existing) existing.remove();
    }
  }, [title, description, breadcrumbs]);

  // 无 DOM 输出
  return null;
}
