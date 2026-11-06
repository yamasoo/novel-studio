/* 搜尋頁（轉移計畫 §8.2.8）：從 app.js 搬 viewSearch（原 255-297）、SEARCH_SCOPES（244）、searchScopes（245-248）。
   highlightTerms（原 299-330）留在 app.js 當共用函式（route() 的 finally 也要用），這裡直接呼叫全域。
   sideSearch 與 Ctrl+K 的 keydown 監聽也留在 app.js（不是頁面邏輯）。 */
(function () {
  "use strict";

  const { h } = FE;
  const enc = encodeURIComponent;
  const bookPath = (rest) => "#/b/" + encodeURIComponent(S.book) + rest;

  const SEARCH_SCOPES = [["正文", "正文"], ["候選", "候選稿"], ["章綱", "大綱與章綱"], ["設定", "設定集"], ["追蹤", "追蹤"]];

  function searchScopes() {
    try {
      const v = JSON.parse(localStorage.getItem("search-scopes") || "null");
      if (Array.isArray(v) && v.length) return v;
    } catch (e) { /* ignore */ }
    return ["正文"];
  }

  // 舊版是 SEARCH_SCOPES.find((z) => z[0] === x.scope)[1]，遇到不認識的範圍會炸；這裡查不到就退回原文。
  const scopeLabel = (scope) => {
    const hit = SEARCH_SCOPES.find((z) => z[0] === scope);
    return hit ? hit[1] : scope;
  };

  function snippetNode(sn, index) {
    // 舊版把整段交給 innerHTML，HTML 解析器會把相鄰的文字併成同一個文字節點；
    // 這裡照樣把相鄰的非高亮片段（含前後的「…」）併進同一個字串，字形整形才會一致。
    const parts = [];
    let buf = sn.pre ? "…" : "";
    for (const g of sn.segs) {
      if (g.hl) {
        if (buf) { parts.push(buf); buf = ""; }
        parts.push(h("mark", {}, g.t));
      } else {
        buf += g.t;
      }
    }
    if (sn.post) buf += "…";
    if (buf) parts.push(buf);
    return h("div", {
      class: "small",
      "data-i18n-skip": "",
      lang: bookLang(),
      style: "margin-top:6px;line-height:1.7",
      "data-more": String(index),
    }, parts);
  }

  async function render(ctx) {
    const signal = ctx.signal;
    const q = ctx.query.q || "";
    const s = ctx.query.s || "";
    const scopes = s ? s.split(",") : searchScopes();
    const docEl = h("div", { id: "doc", style: "margin-top:14px" });

    const input = h("input", {
      id: "search-q", type: "search", value: q,
      placeholder: "例如：玉珮、林遠 沈家、「三年前那場雨」",
      style: "flex:1;min-width:240px",
    });
    const form = h("form", { id: "search-form", class: "row", style: "flex-wrap:wrap;gap:10px" },
      input,
      h("button", { class: "primary" }, "搜尋"),
      h("div", { class: "row", style: "gap:12px;width:100%" },
        SEARCH_SCOPES.map(([k, l]) => h("label", { class: "cb", style: "margin:0" },
          h("input", { type: "checkbox", name: "sc", value: k, checked: scopes.includes(k) }),
          " " + l))));
    form.onsubmit = (ev) => {
      ev.preventDefault();
      const sc = Array.from(form.querySelectorAll('input[name="sc"]:checked')).map((x) => x.value);
      try { localStorage.setItem("search-scopes", JSON.stringify(sc)); } catch (err) { /* ignore */ }
      FE.go(bookPath("/search?q=" + enc(input.value.trim()) + "&s=" + enc(sc.join(","))));
    };

    const box = h("div", { id: "search-res" });
    ctx.view(
      h("div", { class: "page-head" },
        h("div", {},
          h("h1", {}, "搜尋前文"),
          h("div", { class: "sub" }, '在本機直接找，不用模型。多個詞用空白分開＝要出現在同一章；「」或 "" 包起來＝完整片語；不分繁簡。'))),
      h("div", { class: "card", style: "margin-bottom:14px" }, form),
      box,
      docEl);

    if (!q.trim()) { input.focus(); return; }

    box.replaceChildren(h("div", { class: "card muted" }, "搜尋中…"));
    const r = await FE.api(B("/search?q=" + enc(q) + "&scopes=" + enc(scopes.join(","))), { signal });
    S.searchTerms = r.terms;

    if (!r.results.length) {
      box.replaceChildren(h("div", { class: "card empty" }, "找不到「" + r.terms.join("」＋「") + "」。可以勾選更多範圍再試。"));
      return;
    }

    const openResult = async (x) => {
      const tab = x.scope === "正文" ? "text" : x.scope === "候選" ? "candidate"
        : x.no && x.path.startsWith("大綱/章綱/") ? "card"
          : x.no && x.path.startsWith("追蹤/章節摘要/") ? "summary" : null;
      if (tab) { S.hl = r.terms; FE.go(bookPath("/ch/" + x.no + "?tab=" + tab)); return; }
      await docView(docEl, x.path);
      highlightTerms(docEl, r.terms);
    };

    const cards = r.results.map((x, i) => {
      const more = x.snippets.length - 3 + (x.more || 0);
      const snippets = x.snippets.map((sn, j) => {
        const node = snippetNode(sn, i);
        if (j >= 3) node.style.display = "none";
        return node;
      });
      let expand = null;
      const card = h("div", { class: "card", style: "margin-bottom:10px;padding:12px 16px" },
        h("div", { class: "row" },
          h("a", {
            class: "nm", "data-open": String(i), role: "button", tabindex: "0",
            // 舊版是 href 假連結（瀏覽器預設 cursor:pointer）；這裡補回游標，不動共用 CSS。
            style: "cursor:pointer",
            onclick: () => openResult(x),
            onkeydown: (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); openResult(x); } },
          },
            x.scope === "正文" ? null : h("span", { class: "badge" }, scopeLabel(x.scope)),
            // 舊版是「標籤＋一個空白＋標題」的同一段文字；這裡也併成一個字串。
            (x.scope === "正文" ? "" : " ") + (x.kind === "chapter" ? "第" + x.no + "章　" + x.title : x.path)),
          h("span", { class: "grow" }),
          h("span", { class: "muted small" }, x.count + " 處")),
        snippets);
      if (x.snippets.length > 3 || x.more) {
        expand = h("button", { class: "ghost sm", style: "margin-top:4px", "data-expand": String(i) }, "展開其餘 " + more + " 處");
        expand.onclick = () => {
          card.querySelectorAll('[data-more="' + i + '"]').forEach((d) => { d.style.display = ""; });
          expand.remove();
        };
        card.append(expand);
      }
      return card;
    });

    // 舊版這整行是一個字串（innerHTML 解析後是單一文字節點），這裡也拼成一個字串。
    const summaryText =
      "「" + r.terms.join("」＋「") + "」：" +
      (r.chapters ? "出現在 " + r.chapters + " 章正文" + (r.first ? "，第一次在第 " + r.first + " 章" : "") + "；" : "") +
      "共 " + r.files + " 份檔案、" + r.hits + " 處" + (r.truncated ? "（結果太多，只列前面的）" : "");
    const summary = h("div", { class: "muted small", style: "margin:0 0 8px" }, summaryText);
    box.replaceChildren(summary, ...cards);
  }

  nsPage("b/:book/search", "search", { book: true }, render);
})();
