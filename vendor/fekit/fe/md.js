/* fekit md.js — Markdown 轉成「已過濾」的節點。介面與合約見 docs/02_API合約.md 第 9.2 節。
 *
 * marked 把 Markdown 轉成 HTML 字串；字串先交給不執行任何東西的 DOMParser，
 * 再用白名單把允許的標籤與屬性「重建」成新節點。原始 HTML 字串從頭到尾沒有碰到頁面。
 * 只加上 FE.md；載入本身不動 DOM。 */
(function () {
  "use strict";

  const FE = window.FE;
  if (!FE) {
    console.error("fekit：md.js 要在 core.js 之後載入");
    return;
  }
  if (FE.md) {
    console.warn("fekit：md.js 被載入了兩次，第二次已略過");
    return;
  }

  const SELF_URL = (document.currentScript && document.currentScript.src) || "";

  const ALLOWED = new Set([
    "p", "br", "hr", "h1", "h2", "h3", "h4", "h5", "h6",
    "strong", "b", "em", "i", "del", "s", "code", "pre", "blockquote", "ul", "ol", "li",
    "a", "img", "table", "thead", "tbody", "tfoot", "tr", "th", "td",
    "span", "div", "sup", "sub", "details", "summary", "input",
  ]);
  // 連內容一起丟掉；沒列在 ALLOWED 也沒列在這裡的標籤，只拿掉標籤、保留內容。
  const DROPPED = new Set([
    "script", "style", "iframe", "frame", "frameset", "object", "embed", "applet", "link", "meta", "base",
    "template", "noscript", "svg", "math", "form", "textarea", "select", "option", "button",
  ]);
  const LINK_PROTOCOLS = new Set(["http:", "https:", "mailto:"]);
  const IMAGE_PROTOCOLS = new Set(["http:", "https:"]);

  /* ──────────────── 載入 marked ──────────────── */

  let loading = null;

  function scriptUrl(path) {
    if (SELF_URL) return new URL(path, SELF_URL).href;
    const mine = Array.from(document.scripts).find((node) => /\/md\.js(\?|$)/.test(node.src));
    return new URL(path, mine ? mine.src : document.baseURI).href;
  }

  function load(options = {}) {
    if (window.marked) return Promise.resolve();
    if (loading) return loading;
    const src = options.src || scriptUrl("../vendor/marked/marked.umd.js");
    loading = new Promise((done, fail) => {
      const node = document.createElement("script");
      node.src = src;
      node.onload = () => (window.marked ? done() : fail(new Error("FE.md：marked 載入後找不到 window.marked")));
      node.onerror = () => {
        loading = null;
        fail(new Error(`FE.md：載入 marked 失敗（${src}）`));
      };
      document.head.append(node);
    });
    return loading;
  }

  function needMarked() {
    if (!window.marked) throw new Error("FE.md：還沒載入 marked，請先 await FE.md.load()");
    return window.marked;
  }

  /* ──────────────── 過濾 ──────────────── */

  function escapeHtml(text) {
    return String(text).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  function parseUrl(value) {
    // 瀏覽器解析網址時會忽略控制字元與空白，判斷前要先去掉（例如 "java\tscript:"）。
    const clean = String(value).replace(/[\x00-\x20]/g, "");
    if (!clean || clean.startsWith("#")) return null;
    try {
      return { clean, url: new URL(clean, document.baseURI) };
    } catch (_) {
      return null;
    }
  }

  function safeNumber(value, max) {
    return /^\d{1,4}$/.test(String(value)) && Number(value) <= max ? String(value) : null;
  }

  function copyAttrs(from, to, tag, opts) {
    const get = (name) => from.getAttribute(name);

    if (tag === "a") {
      const link = get("href") === null ? null : parseUrl(get("href"));
      if (link && LINK_PROTOCOLS.has(link.url.protocol)) {
        to.setAttribute("href", link.clean);
        if (link.url.protocol !== "mailto:" && link.url.origin !== location.origin && opts.links !== "same_tab") {
          to.setAttribute("target", "_blank");
          to.setAttribute("rel", "noopener noreferrer");
        }
      }
      if (get("title") !== null) to.setAttribute("title", get("title"));
    } else if (tag === "img") {
      const image = get("src") === null ? null : parseUrl(get("src"));
      const local = image && image.url.origin === location.origin;
      const ok = image && IMAGE_PROTOCOLS.has(image.url.protocol) && opts.images !== "none" && (local || opts.images === "all");
      if (ok) to.setAttribute("src", image.clean);
      if (get("alt") !== null) to.setAttribute("alt", get("alt"));
      if (get("title") !== null) to.setAttribute("title", get("title"));
      for (const name of ["width", "height"]) {
        const n = get(name) === null ? null : safeNumber(get(name), 4000);
        if (n) to.setAttribute(name, n);
      }
    } else if (tag === "th" || tag === "td") {
      const align = get("align");
      if (align && /^(left|right|center)$/i.test(align)) to.setAttribute("align", align.toLowerCase());
      for (const name of ["colspan", "rowspan"]) {
        const n = get(name) === null ? null : safeNumber(get(name), 1000);
        if (n) to.setAttribute(name, n);
      }
    } else if (tag === "ol") {
      const start = get("start") === null ? null : safeNumber(get("start"), 100000);
      if (start) to.setAttribute("start", start);
    } else if (tag === "code") {
      const cls = get("class");
      if (cls && /^language-[A-Za-z0-9_+-]+$/.test(cls)) to.setAttribute("class", cls);
    }
  }

  function clean(node, opts) {
    if (node.nodeType === 3) return [document.createTextNode(node.data)];
    if (node.nodeType !== 1) return [];                        // 註解、處理指令
    const tag = node.localName.toLowerCase();
    if (DROPPED.has(tag)) return [];

    const kids = [];
    if (tag !== "input") for (const child of node.childNodes) kids.push(...clean(child, opts));

    if (tag === "input") {
      // 只留任務清單的核取方塊，而且一律不能點。
      if ((node.getAttribute("type") || "").toLowerCase() !== "checkbox") return [];
      const box = document.createElement("input");
      box.type = "checkbox";
      box.disabled = true;
      box.checked = node.hasAttribute("checked");
      return [box];
    }
    if (!ALLOWED.has(tag)) return kids;                        // 拿掉標籤，保留內容

    const out = document.createElement(tag);
    copyAttrs(node, out, tag, opts);
    out.append(...kids);
    return [out];
  }

  function sanitize(html, options = {}) {
    // DOMParser 產生的文件是惰性的：不執行 script、不載入圖片。
    const doc = new DOMParser().parseFromString(String(html === undefined || html === null ? "" : html), "text/html");
    const fragment = document.createDocumentFragment();
    for (const child of doc.body.childNodes) fragment.append(...clean(child, options));
    return fragment;
  }

  /* ──────────────── 轉換 ──────────────── */

  let renderer = null;

  function markedOptions() {
    const marked = needMarked();
    if (!renderer) {
      renderer = new marked.Renderer();
      // 使用者在 Markdown 裡寫的原始 HTML：當文字顯示，不要默默吃掉。
      renderer.html = (token) => escapeHtml(typeof token === "string" ? token : token.text);
    }
    return { gfm: true, breaks: false, async: false, renderer };
  }

  function render(text, options = {}) {
    const marked = needMarked();
    const source = typeof text === "string" ? text : "";
    const html = marked.parse(source, markedOptions());
    return FE.h("div", { class: "md" }, sanitize(html, options));
  }

  FE.md = { load, render, sanitize };
})();
