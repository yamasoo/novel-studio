/* 繪圖 Prompt 即時標籤補全（類 sd-webui-tagcomplete-neo）：
   複用後端 /api/illust/tags/suggest（由 tag_csv / tag_zh_csv 驅動），支援英文前綴／子字串、別名、中文反查與畫師 @ 優先。
   純 DOM 節點建構（FE.h），嚴禁 innerHTML。 */
(function () {
  "use strict";

  const { h } = FE;
  const cache = new Map();
  let pop = null;
  let activeEl = null;
  let activeOpts = null;
  let curItems = [];
  let curIdx = 0;
  let timer = null;
  let reqSeq = 0;

  const CAT_CLS = { "0": "tc-cat-0", "1": "tc-cat-1", "3": "tc-cat-3", "4": "tc-cat-4", "5": "tc-cat-5" };

  function fmtCount(n) {
    n = Number(n) || 0;
    if (!n) return "";
    if (n >= 1000000) return (n / 1000000).toFixed(1).replace(/\.0$/, "") + "M";
    if (n >= 1000) return (n / 1000).toFixed(1).replace(/\.0$/, "") + "K";
    return String(n);
  }

  function ensurePop() {
    if (pop && document.body.contains(pop)) return pop;
    pop = h("div", { id: "tc-pop", class: "tc-pop", style: "display:none" });
    document.body.appendChild(pop);
    return pop;
  }

  function hide() {
    curItems = [];
    curIdx = 0;
    if (pop) pop.style.display = "none";
  }

  function tokenAt(el) {
    const val = el.value || "";
    const pos = typeof el.selectionStart === "number" ? el.selectionStart : val.length;
    let s = pos;
    while (s > 0 && !/[,，\n]/.test(val[s - 1])) s--;
    let e = pos;
    while (e < val.length && !/[,，\n]/.test(val[e])) e++;
    const raw = val.slice(s, pos);
    const lead = raw.match(/^\s*/)[0].length;
    return { start: s + lead, end: e, cursor: pos, query: raw.slice(lead).trim() };
  }

  function placePop(el) {
    const p = ensurePop();
    const rect = el.getBoundingClientRect();
    const w = Math.max(260, Math.min(440, rect.width || 320));
    p.style.width = w + "px";
    const left = Math.max(8, Math.min(rect.left, window.innerWidth - w - 8));
    p.style.left = left + "px";
    p.style.display = "block";
    const ph = p.offsetHeight || 220;
    const spaceBelow = window.innerHeight - rect.bottom - 8;
    if (spaceBelow < ph && rect.top > ph + 8) {
      p.style.top = Math.max(8, rect.top - ph - 4) + "px";
    } else {
      p.style.top = Math.min(window.innerHeight - ph - 8, rect.bottom + 4) + "px";
    }
  }

  function accept(idx) {
    if (!activeEl || !curItems.length) return;
    const item = curItems[idx != null ? idx : curIdx];
    if (!item) return;
    const el = activeEl;
    const opts = activeOpts || {};
    const tok = tokenAt(el);
    const val = el.value || "";
    const before = val.slice(0, tok.start);
    const after = val.slice(tok.end);
    const sep = opts.sep !== undefined ? opts.sep : ", ";
    const hasSepAfter = /^\s*[,，\n]/.test(after);
    const ins = item.insert || item.tag || "";
    const tail = (sep && !hasSepAfter) ? sep : "";
    el.value = before + ins + tail + after;
    const nextPos = before.length + ins.length + tail.length;
    try { el.setSelectionRange(nextPos, nextPos); } catch (e) { /* ignore */ }
    el.dispatchEvent(new Event("input", { bubbles: true }));
    hide();
  }

  function renderPop() {
    if (!activeEl || !curItems.length) { hide(); return; }
    const p = ensurePop();
    p.replaceChildren(...curItems.map((it, i) => h("div", {
      class: "tc-item" + (i === curIdx ? " tc-active" : ""),
      onmousedown: (ev) => { ev.preventDefault(); accept(i); },
      onmouseenter: () => {
        curIdx = i;
        p.querySelectorAll(".tc-item").forEach((n, j) => n.classList.toggle("tc-active", j === curIdx));
      },
    },
      h("span", { class: "tc-tag " + (CAT_CLS[it.cat] || "tc-cat-0") }, it.insert || it.tag),
      it.alias ? h("span", { class: "tc-alias" }, `← ${it.alias}`) : null,
      it.zh ? h("span", { class: "tc-zh" }, it.zh) : null,
      h("span", { class: "tc-grow" }),
      it.count ? h("span", { class: "tc-cnt" }, fmtCount(it.count)) : null)));
    placePop(activeEl);
  }

  async function queryNow(el, opts) {
    const tok = tokenAt(el);
    const q = tok.query;
    const isCJK = /[\u3400-\u9fff]/.test(q);
    const minLen = isCJK ? 1 : (q.startsWith("@") ? 2 : 2);
    if (!q || q.length < minLen) { hide(); return; }
    const mode = (opts && opts.mode) || "all";
    const key = mode + "|" + q.toLowerCase();
    const mySeq = ++reqSeq;
    let res = cache.get(key);
    if (!res) {
      try {
        res = await FE.api(`/api/illust/tags/suggest?q=${encodeURIComponent(q)}&limit=15&mode=${encodeURIComponent(mode)}`);
      } catch (e) { return; }
      if (cache.size > 200) cache.clear();
      cache.set(key, res);
    }
    if (mySeq !== reqSeq || activeEl !== el) return;
    curItems = (res && res.items) || [];
    curIdx = 0;
    renderPop();
  }

  function attachTagComplete(el, opts = {}) {
    if (!el || el.dataset.tcBound) return;
    el.dataset.tcBound = "1";
    el.setAttribute("autocomplete", "off");
    el.addEventListener("input", () => {
      activeEl = el;
      activeOpts = opts;
      clearTimeout(timer);
      timer = setTimeout(() => queryNow(el, opts), 80);
    });
    el.addEventListener("keydown", (ev) => {
      if (!curItems.length || !pop || pop.style.display === "none") return;
      if (ev.key === "ArrowDown") {
        ev.preventDefault();
        curIdx = (curIdx + 1) % curItems.length;
        renderPop();
      } else if (ev.key === "ArrowUp") {
        ev.preventDefault();
        curIdx = (curIdx - 1 + curItems.length) % curItems.length;
        renderPop();
      } else if (ev.key === "Tab" || ev.key === "Enter") {
        ev.preventDefault();
        accept(curIdx);
      } else if (ev.key === "Escape") {
        ev.preventDefault();
        hide();
      }
    });
    el.addEventListener("blur", () => {
      setTimeout(() => { if (document.activeElement !== el) hide(); }, 120);
    });
  }

  window.addEventListener("fe-route", hide);
  window.addEventListener("resize", hide);
  window.attachTagComplete = attachTagComplete;
  window.clearTagCompleteCache = () => cache.clear();
})();
