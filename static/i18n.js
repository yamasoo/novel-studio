/* 介面多語系（執行期翻譯）
   做法：程式裡的介面文字維持中文原文，當作「索引」；語言檔（static/locales/<語言>.json）把中文原文對到該語言。
   - 找不到對應就原樣顯示中文，所以翻譯可以一批一批補，不會壞掉。
   - 文字裡有變數的，語言檔的 key 用 {0}、{1}… 表示，例如 "共 {0} 章" → "{0} chapters"。
   - 只翻譯「介面文字節點」和 title／placeholder／aria-label 屬性；輸入框內容、textarea、程式碼、
     標了 data-i18n-skip 的區塊（例如渲染出來的正文與設定內容）一律不動。
   - 換語言：右下的語言選單，記在瀏覽器；預設中文（zh-TW）。 */
(function () {
  const LANGS = [["zh-TW", "繁體中文"], ["en", "English"], ["ja", "日本語"]];
  const CJK = /[぀-ヿ㐀-鿿]/;
  const SKIP_TAG = new Set(["SCRIPT", "STYLE", "TEXTAREA", "PRE", "INPUT", "svg", "SVG"]);   // CODE 不跳過：說明文字裡常有 <code> 夾著介面詞；真正的程式碼區塊是 PRE
  const ATTRS = ["title", "placeholder", "aria-label"];
  let lang = "zh-TW", exact = {}, pats = [];
  const missing = new Set();           // 沒有翻譯的中文原文（開發時用 I18N.missing 查缺口）
  const orig = new WeakMap();          // 節點／屬性 → 原文，切回中文或換語言時用

  try { lang = localStorage.getItem("ns_lang") || "zh-TW"; } catch (e) {}
  if (!LANGS.some((l) => l[0] === lang)) lang = "zh-TW";

  function load(l) {
    exact = {}; pats = [];
    if (l === "zh-TW") return;
    try {
      const x = new XMLHttpRequest();
      x.open("GET", "/static/locales/" + l + ".json", false);   // 同步載入，避免先閃一下中文
      x.send();
      if (x.status !== 200) return;
      const d = JSON.parse(x.responseText);
      Object.keys(d).forEach((k) => {
        if (k.charAt(0) === "_") return;
        if (/\{\d+\}/.test(k)) {
          const re = new RegExp("^" + k.replace(/[.*+?^$()|[\]\\]/g, "\\$&").replace(/\{(\d+)\}/g, "(?<g$1>[\\s\\S]*?)") + "$");
          pats.push([re, d[k]]);
        } else exact[k] = d[k];
      });
      pats.sort((a, b) => b[0].source.length - a[0].source.length);   // 長的樣式先比，避免被短的搶走
    } catch (e) { console.warn("i18n load failed", e); }
  }

  function trq(x) {   // 安靜版：翻不出來回傳 null、不記入 missing
    const c = x.trim(); if (exact[c] != null) return x.replace(c, exact[c]);
    for (const [re, to] of pats) { const r = re.exec(c); if (r) return x.replace(c, to.replace(/\{(\d+)\}/g, (_, i) => tr(r.groups["g" + i]))); }
    return null;
  }
  function tr(s) {
    if (lang === "zh-TW" || !s || !CJK.test(s)) return s;
    const m = s.match(/^(\s*)([\s\S]*?)(\s*)$/), core = m[2];
    if (!core) return s;
    let out = exact[core];
    if (out == null && core.indexOf("、") > 0) {   // 「、」串起來的清單：每一項都翻得出來才逐項翻
      const parts = core.split("、"), sep = exact["、"] != null ? exact["、"] : "、";
      const got = parts.map((x) => trq(x));
      if (got.every((x) => x != null)) out = got.join(sep);
    }
    if (out == null) {
      for (const [re, to] of pats) {
        const r = re.exec(core);
        if (r) { out = to.replace(/\{(\d+)\}/g, (_, i) => tr(r.groups["g" + i]) ); break; }   // 變數本身若是介面詞也一起翻
      }
    }
    if (out == null) { missing.add(core); return s; }
    return m[1] + out + m[3];
  }

  function skipped(el) {
    for (let e = el; e && e.nodeType === 1; e = e.parentElement) {
      if (SKIP_TAG.has(e.tagName) || e.hasAttribute("data-i18n-skip") || e.isContentEditable) return true;
    }
    return false;
  }

  function doText(n) {
    if (skipped(n.parentElement)) return;
    let o = orig.get(n);
    if (o === undefined || (n.nodeValue !== o.shown && n.nodeValue !== o.src)) { o = { src: n.nodeValue, shown: n.nodeValue }; orig.set(n, o); }
    const t = tr(o.src);
    if (t !== n.nodeValue) { n.nodeValue = t; }
    o.shown = n.nodeValue;
  }
  function skippedAttr(el) {   // 屬性（title／placeholder）：輸入框的 placeholder 要翻，但標了 data-i18n-skip 的不動
    for (let e = el; e && e.nodeType === 1; e = e.parentElement) if (e.hasAttribute("data-i18n-skip")) return true;
    return false;
  }
  function doAttrs(el) {
    if (el.nodeType !== 1 || skippedAttr(el)) return;
    for (const a of ATTRS) {
      if (!el.hasAttribute(a)) continue;
      let m = orig.get(el); if (!m) { m = {}; orig.set(el, m); }
      const cur = el.getAttribute(a);
      if (!m[a] || (cur !== m[a].shown && cur !== m[a].src)) m[a] = { src: cur, shown: cur };
      const t = tr(m[a].src);
      if (t !== cur) el.setAttribute(a, t);
      m[a].shown = t;
    }
  }
  function walk(root) {
    if (!root) return;
    if (root.nodeType === 3) { doText(root); return; }
    if (root.nodeType !== 1 || root.hasAttribute("data-i18n-skip")) return;
    doAttrs(root);
    if (SKIP_TAG.has(root.tagName) || root.isContentEditable) return;
    for (let c = root.firstChild; c; c = c.nextSibling) walk(c);
  }

  let busy = false;
  const mo = new MutationObserver((muts) => {
    if (busy || lang === "zh-TW") return;
    busy = true;
    try {
      for (const m of muts) {
        if (m.type === "childList") m.addedNodes.forEach((n) => walk(n));
        else if (m.type === "characterData") doText(m.target);
        else if (m.type === "attributes") doAttrs(m.target);
      }
    } finally { busy = false; }
  });

  function applyAll() {
    busy = true;
    try {
      document.documentElement.lang = lang;
      if (lang === "zh-TW") return;
      document.title = tr(document.title);
      walk(document.body);
    } finally { busy = false; }
  }

  // 給程式碼用：t("中文原文") 或 t("共 {0} 章", 5)
  function t(s, ...args) {
    let out = lang === "zh-TW" ? s : (exact[s] != null ? exact[s] : tr(s));
    return out.replace(/\{(\d+)\}/g, (m, i) => (args[+i] != null ? args[+i] : m));
  }

  function setLang(l) {
    try { localStorage.setItem("ns_lang", l); } catch (e) {}
    location.reload();   // 最單純：整頁重畫，所有動態內容都用新語言重新產生
  }

  window.I18N = { t, tr, setLang, missing, get lang() { return lang; }, LANGS };
  window.t = t;
  load(lang);
  for (const f of ["confirm", "alert", "prompt"]) {   // 瀏覽器內建對話框的文字
    const o = window[f].bind(window); window[f] = (m, ...r) => o(tr(String(m)), ...r);
  }

  document.addEventListener("DOMContentLoaded", () => {
    const sel = document.getElementById("lang-select");
    if (sel) {
      sel.innerHTML = LANGS.map(([k, n]) => `<option value="${k}"${k === lang ? " selected" : ""}>${n}</option>`).join("");
      sel.onchange = () => setLang(sel.value);
    }
    applyAll();
    mo.observe(document.body, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ATTRS });
  });
})();
