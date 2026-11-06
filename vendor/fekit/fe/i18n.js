/* fekit i18n.js — 介面多語系（執行期翻譯）。介面與合約見 docs/02_API合約.md 第 9.1 節。
 *
 * 做法：程式裡的介面文字維持中文原文，當作「索引」；語言檔（<base>/<語言>.json）把中文原文對到該語言。
 * 找不到對應就原樣顯示中文，所以翻譯可以一批一批補，不會壞掉。
 * 只加上 FE.i18n 與 FE.t；載入本身不動 DOM，呼叫 FE.i18n.init() 才開始。 */
(function () {
  "use strict";

  const FE = window.FE;
  if (!FE) {
    console.error("fekit：i18n.js 要在 core.js 之後載入");
    return;
  }
  if (FE.i18n) {
    console.warn("fekit：i18n.js 被載入了兩次，第二次已略過");
    return;
  }

  const DEFAULT_LANGS = [["zh-TW", "繁體中文"], ["en", "English"], ["ja", "日本語"]];
  const SAME = "==";                                  // 語言檔的值填這個＝各語言同形，直接用原文
  const CJK = /[぀-ヿ㐀-鿿]/;                          // 含日文假名與中日韓漢字；沒有這些字就不翻
  const SKIP_TAGS = new Set(["SCRIPT", "STYLE", "TEXTAREA", "PRE", "INPUT", "SVG", "svg"]);
  const ATTRS = ["title", "placeholder", "aria-label"];
  const PLACEHOLDER = /\{(\d+)\}/;

  let langs = DEFAULT_LANGS;
  let lang = DEFAULT_LANGS[0][0];
  let exact = {};
  let patterns = [];                                  // [{re, groups, to}]
  let observer = null;
  let initPromise = null;
  let busy = false;                                   // 我們自己改節點時，不要被觀察器再觸發

  const missing = new Set();
  const originals = new WeakMap();                    // 節點／元素 → 原文，切換語言或內容被改寫時用

  const source = () => langs[0][0];
  const escapeRe = (text) => text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

  /* ──────────────── 語言檔 ──────────────── */

  function compile(key, value) {
    // 把 "共 {0} 章" 變成 /^共 ([\s\S]*?) 章$/；同一個變數出現兩次時，第二次要求和第一次相同。
    const parts = key.split(/(\{\d+\})/);
    const first = {};
    let groups = 0;
    let pattern = "^";
    for (const part of parts) {
      const match = /^\{(\d+)\}$/.exec(part);
      if (!match) {
        pattern += escapeRe(part);
        continue;
      }
      const id = match[1];
      if (id in first) {
        pattern += `\\${first[id]}`;
      } else {
        groups += 1;
        first[id] = groups;
        pattern += "([\\s\\S]*?)";
      }
    }
    return { re: new RegExp(pattern + "$"), groups: first, to: value };
  }

  function build(table) {
    exact = {};
    patterns = [];
    for (const [key, value] of Object.entries(table)) {
      if (key.charAt(0) === "_" || value === SAME || typeof value !== "string") continue;
      if (PLACEHOLDER.test(key)) patterns.push(compile(key, value));
      else exact[key] = value;
    }
    // 長的樣式先比，避免被短的搶走。
    patterns.sort((a, b) => b.re.source.length - a.re.source.length);
  }

  async function loadTable(base, code) {
    const url = new URL(`${base.replace(/\/+$/, "")}/${encodeURIComponent(code)}.json`, document.baseURI);
    try {
      const response = await fetch(url, { cache: "no-store" });
      if (!response.ok) {
        console.warn(`fekit：找不到語言檔 ${url.pathname}（HTTP ${response.status}），維持原文`);
        return {};
      }
      const data = await response.json();
      return data && typeof data === "object" && !Array.isArray(data) ? data : {};
    } catch (error) {
      console.warn("fekit：語言檔載入失敗，維持原文", error);
      return {};
    }
  }

  /* ──────────────── 翻譯 ──────────────── */

  function viaPattern(core) {
    for (const entry of patterns) {
      const hit = entry.re.exec(core);
      if (hit) {
        // 變數本身若是介面詞也一起翻。
        return entry.to.replace(/\{(\d+)\}/g, (all, id) => (id in entry.groups ? tr(hit[entry.groups[id]]) : all));
      }
    }
    return null;
  }

  function quiet(text) {
    // 翻不出來回傳 null，也不記入 missing。
    const core = text.trim();
    if (exact[core] !== undefined) return text.replace(core, exact[core]);
    const out = viaPattern(core);
    return out === null ? null : text.replace(core, out);
  }

  function tr(text) {
    if (lang === source() || !text || !CJK.test(text)) return text;
    const split = /^(\s*)([\s\S]*?)(\s*)$/.exec(text);
    const core = split[2];
    if (!core) return text;
    let out = exact[core];
    if (out === undefined && core.indexOf("、") > 0) {
      // 「、」串起來的清單：每一項都翻得出來才逐項翻。
      const got = core.split("、").map(quiet);
      if (got.every((item) => item !== null)) out = got.join(exact["、"] !== undefined ? exact["、"] : "、");
    }
    if (out === undefined) {
      const hit = viaPattern(core);
      if (hit !== null) out = hit;
    }
    if (out === undefined) {
      missing.add(core);
      return text;
    }
    return split[1] + out + split[3];
  }

  function t(text, ...args) {
    const out = tr(String(text));
    return out.replace(/\{(\d+)\}/g, (all, id) => (args[+id] !== undefined && args[+id] !== null ? args[+id] : all));
  }

  /* ──────────────── 套用到 DOM ──────────────── */

  function skipped(el) {
    for (let node = el; node && node.nodeType === 1; node = node.parentElement) {
      if (SKIP_TAGS.has(node.tagName) || node.hasAttribute("data-i18n-skip") || node.isContentEditable) return true;
    }
    return false;
  }

  function skippedAttr(el) {
    // 屬性：輸入框的 placeholder 要翻，但標了 data-i18n-skip 的不動。
    for (let node = el; node && node.nodeType === 1; node = node.parentElement) {
      if (node.hasAttribute("data-i18n-skip")) return true;
    }
    return false;
  }

  function doText(node) {
    if (skipped(node.parentElement)) return;
    let seen = originals.get(node);
    // 目前的內容既不是我們翻出來的、也不是原文：被別人改寫了，重新記原文。
    if (seen === undefined || (node.nodeValue !== seen.shown && node.nodeValue !== seen.src)) {
      seen = { src: node.nodeValue, shown: node.nodeValue };
      originals.set(node, seen);
    }
    const next = tr(seen.src);
    if (next !== node.nodeValue) node.nodeValue = next;
    seen.shown = node.nodeValue;
  }

  function doAttrs(el) {
    if (el.nodeType !== 1 || skippedAttr(el)) return;
    for (const name of ATTRS) {
      if (!el.hasAttribute(name)) continue;
      let record = originals.get(el);
      if (!record) {
        record = {};
        originals.set(el, record);
      }
      const current = el.getAttribute(name);
      if (!record[name] || (current !== record[name].shown && current !== record[name].src)) {
        record[name] = { src: current, shown: current };
      }
      const next = tr(record[name].src);
      if (next !== current) el.setAttribute(name, next);
      record[name].shown = next;
    }
  }

  function walk(root) {
    if (!root) return;
    if (root.nodeType === 3) {
      doText(root);
      return;
    }
    if (root.nodeType !== 1 || root.hasAttribute("data-i18n-skip")) return;
    doAttrs(root);
    if (SKIP_TAGS.has(root.tagName) || root.isContentEditable) return;
    for (let child = root.firstChild; child; child = child.nextSibling) walk(child);
  }

  function apply(root) {
    busy = true;
    try {
      if (!root) document.title = tr(document.title);
      walk(root || document.body);
    } finally {
      busy = false;
    }
  }

  function onMutations(records) {
    if (busy || lang === source()) return;
    busy = true;
    try {
      for (const record of records) {
        if (record.type === "childList") record.addedNodes.forEach((node) => walk(node));
        else if (record.type === "characterData") doText(record.target);
        else if (record.type === "attributes") doAttrs(record.target);
      }
    } finally {
      busy = false;
    }
  }

  function domReady() {
    if (document.readyState !== "loading") return Promise.resolve();
    return new Promise((done) => document.addEventListener("DOMContentLoaded", done, { once: true }));
  }

  /* ──────────────── 公開介面 ──────────────── */

  function init(options = {}) {
    if (initPromise) {
      console.warn("fekit：FE.i18n.init() 只需要呼叫一次，第二次已略過");
      return initPromise;
    }
    initPromise = (async () => {
      if (Array.isArray(options.langs) && options.langs.length) langs = options.langs.map((item) => [String(item[0]), String(item[1])]);
      const wanted = options.lang !== undefined ? options.lang : FE.store.get("lang", source());
      lang = langs.some((item) => item[0] === wanted) ? wanted : source();

      const table = lang === source() ? {} : await loadTable(options.base || "locales", lang);
      build(table);
      await domReady();

      document.documentElement.lang = lang;
      if (lang !== source()) {
        apply();
        observer = new MutationObserver(onMutations);
        observer.observe(document.body, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ATTRS });
      }
    })();
    return initPromise;
  }

  function set(code) {
    if (!langs.some((item) => item[0] === code)) throw new RangeError(`FE.i18n.set()：沒有這個語言 ${code}`);
    FE.store.set("lang", code);
    location.reload();
  }

  function select(props = {}) {
    return FE.h("select", {
      "aria-label": "語言",
      ...props,
      value: lang,
      onchange: (event) => set(event.target.value),
    }, langs.map(([code, name]) => FE.h("option", { value: code }, name)));
  }

  FE.i18n = {
    init, tr, apply, set, select, missing,
    get lang() { return lang; },
    get langs() { return langs.map((item) => item.slice()); },
  };
  FE.t = t;
})();
