import { jsxs, jsx } from "react/jsx-runtime";
import { renderToString } from "react-dom/server";
function SSRCoverPage(page) {
  return /* @__PURE__ */ jsx(
    "div",
    {
      className: "ssr-page ssr-cover",
      style: {
        background: page.style.background,
        color: page.style.textColor
      },
      children: /* @__PURE__ */ jsxs("div", { className: "ssr-cover-content", children: [
        /* @__PURE__ */ jsx(
          "div",
          {
            className: "ssr-avatar",
            style: { backgroundColor: page.style.accentColor + "33" },
            children: /* @__PURE__ */ jsxs("svg", { width: "40", height: "40", viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: "2", children: [
              /* @__PURE__ */ jsx("path", { d: "M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" }),
              /* @__PURE__ */ jsx("circle", { cx: "12", cy: "7", r: "4" })
            ] })
          }
        ),
        /* @__PURE__ */ jsx("h3", { className: "ssr-title", children: page.title }),
        page.subtitle && /* @__PURE__ */ jsx("p", { className: "ssr-subtitle", children: page.subtitle }),
        /* @__PURE__ */ jsx(
          "div",
          {
            className: "ssr-badge",
            style: { backgroundColor: page.style.accentColor },
            children: "Powered by 链客宝 AI"
          }
        )
      ] })
    }
  );
}
function SSRContactPage(page) {
  return /* @__PURE__ */ jsxs(
    "div",
    {
      className: "ssr-page ssr-contact",
      style: {
        background: page.style.background,
        color: page.style.textColor
      },
      children: [
        /* @__PURE__ */ jsx("h3", { className: "ssr-section-title", style: { color: page.style.accentColor }, children: page.title }),
        /* @__PURE__ */ jsxs("div", { className: "ssr-contact-list", children: [
          (page.fields || []).map((f, i) => /* @__PURE__ */ jsxs("div", { className: "ssr-contact-item", children: [
            /* @__PURE__ */ jsx("span", { className: "ssr-contact-label", children: f.label.split(" ")[0] }),
            /* @__PURE__ */ jsx("span", { className: "ssr-contact-value", children: f.value })
          ] }, i)),
          (!page.fields || page.fields.length === 0) && /* @__PURE__ */ jsx("p", { className: "ssr-empty-text", children: "暂无联系方式" })
        ] })
      ]
    }
  );
}
function SSRCompanyPage(page) {
  var _a, _b, _c, _d;
  return /* @__PURE__ */ jsxs(
    "div",
    {
      className: "ssr-page ssr-company",
      style: {
        background: page.style.background,
        color: page.style.textColor
      },
      children: [
        /* @__PURE__ */ jsx("h3", { className: "ssr-section-title", style: { color: page.style.accentColor }, children: page.title }),
        /* @__PURE__ */ jsxs("div", { className: "ssr-company-list", children: [
          ((_a = page.content) == null ? void 0 : _a.company) && /* @__PURE__ */ jsxs("div", { className: "ssr-company-item", children: [
            /* @__PURE__ */ jsx("p", { className: "ssr-field-label", children: "公司" }),
            /* @__PURE__ */ jsx("p", { className: "ssr-field-value", children: page.content.company })
          ] }),
          ((_b = page.content) == null ? void 0 : _b.position) && /* @__PURE__ */ jsxs("div", { className: "ssr-company-item", children: [
            /* @__PURE__ */ jsx("p", { className: "ssr-field-label", children: "职位" }),
            /* @__PURE__ */ jsx("p", { className: "ssr-field-value", children: page.content.position })
          ] }),
          ((_c = page.content) == null ? void 0 : _c.address) && /* @__PURE__ */ jsxs("div", { className: "ssr-company-item", children: [
            /* @__PURE__ */ jsx("p", { className: "ssr-field-label", children: "地址" }),
            /* @__PURE__ */ jsx("p", { className: "ssr-field-value", children: page.content.address })
          ] }),
          ((_d = page.content) == null ? void 0 : _d.website) && /* @__PURE__ */ jsxs("div", { className: "ssr-company-item", children: [
            /* @__PURE__ */ jsx("p", { className: "ssr-field-label", children: "官网" }),
            /* @__PURE__ */ jsx("p", { className: "ssr-field-value ssr-link", children: page.content.website })
          ] })
        ] })
      ]
    }
  );
}
function SSRQRCodePage(page) {
  return /* @__PURE__ */ jsx(
    "div",
    {
      className: "ssr-page ssr-qrcode",
      style: {
        background: page.style.background,
        color: page.style.textColor
      },
      children: /* @__PURE__ */ jsxs("div", { className: "ssr-qrcode-content", children: [
        /* @__PURE__ */ jsx(
          "div",
          {
            className: "ssr-qrcode-box",
            style: { backgroundColor: page.style.accentColor + "15" },
            children: /* @__PURE__ */ jsxs(
              "svg",
              {
                width: "80",
                height: "80",
                viewBox: "0 0 24 24",
                fill: "none",
                stroke: page.style.accentColor,
                strokeWidth: "1.5",
                children: [
                  /* @__PURE__ */ jsx("rect", { x: "3", y: "3", width: "7", height: "7", rx: "1" }),
                  /* @__PURE__ */ jsx("rect", { x: "14", y: "3", width: "7", height: "7", rx: "1" }),
                  /* @__PURE__ */ jsx("rect", { x: "3", y: "14", width: "7", height: "7", rx: "1" }),
                  /* @__PURE__ */ jsx("path", { d: "M14 14h2v2h-2zM18 14h2v2h-2zM14 18h2v2h-2zM18 18h2v2h-2z" })
                ]
              }
            )
          }
        ),
        /* @__PURE__ */ jsx("h3", { className: "ssr-title", children: page.title }),
        page.subtitle && /* @__PURE__ */ jsx("p", { className: "ssr-subtitle", children: page.subtitle })
      ] })
    }
  );
}
function renderPageContent(page) {
  let element;
  switch (page.type) {
    case "cover":
      element = /* @__PURE__ */ jsx(SSRCoverPage, { ...page });
      break;
    case "contact":
      element = /* @__PURE__ */ jsx(SSRContactPage, { ...page });
      break;
    case "company":
      element = /* @__PURE__ */ jsx(SSRCompanyPage, { ...page });
      break;
    case "qrcode":
      element = /* @__PURE__ */ jsx(SSRQRCodePage, { ...page });
      break;
    default:
      element = /* @__PURE__ */ jsx(
        "div",
        {
          className: "ssr-page",
          style: {
            background: page.style.background,
            color: page.style.textColor
          },
          children: /* @__PURE__ */ jsx("div", { className: "ssr-default-content", children: /* @__PURE__ */ jsx("p", { children: page.title }) })
        }
      );
  }
  return renderToString(element);
}
function renderCardPreview(cardData) {
  var _a, _b, _c, _d;
  if (!((_b = (_a = cardData.album_meta) == null ? void 0 : _a.pages) == null ? void 0 : _b.length)) return "";
  const firstPage = cardData.album_meta.pages[0];
  const settings = cardData.album_meta.settings;
  const pageContent = renderPageContent(firstPage);
  return renderToString(
    /* @__PURE__ */ jsxs("div", { className: "ssr-card-preview", style: { width: settings.page_width }, children: [
      /* @__PURE__ */ jsxs(
        "div",
        {
          className: "ssr-card-flipbook",
          style: {
            width: settings.page_width,
            height: settings.page_height,
            borderRadius: settings.corner_radius,
            boxShadow: settings.shadow ? "0 20px 60px rgba(0,0,0,0.15), 0 8px 20px rgba(0,0,0,0.1)" : "none"
          },
          children: [
            /* @__PURE__ */ jsx("div", { dangerouslySetInnerHTML: { __html: pageContent } }),
            /* @__PURE__ */ jsx("div", { className: "ssr-card-edge" }),
            /* @__PURE__ */ jsx("div", { className: "ssr-card-curl" })
          ]
        }
      ),
      /* @__PURE__ */ jsxs("div", { className: "ssr-card-meta", children: [
        /* @__PURE__ */ jsx("div", { className: "ssr-card-name", children: cardData.name }),
        ((_c = cardData.fields) == null ? void 0 : _c.position) && /* @__PURE__ */ jsx("div", { className: "ssr-card-position", children: cardData.fields.position }),
        ((_d = cardData.fields) == null ? void 0 : _d.company) && /* @__PURE__ */ jsx("div", { className: "ssr-card-company", children: cardData.fields.company }),
        /* @__PURE__ */ jsxs("div", { className: "ssr-card-views", children: [
          cardData.view_count,
          " 次浏览"
        ] })
      ] })
    ] })
  );
}
const DEFAULT_DESC = "链客宝 — 一站式AI营销增长引擎，企业家的AI营销朋友圈。";
const DEFAULT_IMAGE = "/app/og-image.png";
function renderCardPage(cardData) {
  const name = (cardData == null ? void 0 : cardData.name) || "数字名片";
  const title = `${name} 的数字名片 | 链客宝`;
  const fields = (cardData == null ? void 0 : cardData.fields) || {};
  const company = fields.company || "";
  const position = fields.position || "";
  const description = [position, company].filter(Boolean).join(" · ") || DEFAULT_DESC;
  const image = (cardData == null ? void 0 : cardData.cover_image) || fields.cover_image || DEFAULT_IMAGE;
  const previewHtml = cardData ? renderCardPreview(cardData) : "";
  return {
    title,
    description,
    image,
    html: previewHtml
  };
}
function buildHTML(result, appHtml, cssLinks, jsScripts, cardData = null) {
  const cardDataJson = cardData ? JSON.stringify(cardData).replace(/</g, "\\u003c") : "null";
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
    
    ${cssLinks.map((href) => `    <link rel="stylesheet" href="${href}" />`).join("\n")}
  </head>
  <body>
    <div id="root">${appHtml}</div>
    ${jsScripts.map((src) => `    <script type="module" src="${src}"><\/script>`).join("\n")}
    
    <!-- SSR 状态注入：客户端 hydration 用 -->
    <script>
      window.__SSR_CARD_DATA__ = ${cardDataJson};
    <\/script>
    
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
    <\/script>
  </body>
</html>`;
}
function escapeHtml(str) {
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
}
export {
  buildHTML,
  renderCardPage
};
