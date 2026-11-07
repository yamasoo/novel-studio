/* 反推設定頁（轉移計畫 §8.2.7）：從 app.js 的 viewReverse 搬過來（原本 181-241）。
   三個原生 confirm 改 await FE.confirm（文字一字不差）；動作做完一律 FE.route()（同一頁重載），
   不再自己遞迴呼叫 viewReverse；草稿清單不再用偽協定的假連結。
   Panel／S／B() 仍是 app.js 全域。 */
(function () {
  "use strict";

  const { h } = FE;
  const { fmtNum, unitCh, unitOfBook } = nsShared;
  const enc = encodeURIComponent;
  const bookPath = (rest) => "#/b/" + encodeURIComponent(S.book) + rest;

  async function resetRun(signal) {
    if (!(await FE.confirm("清掉已抽取的資料和草稿，重新開始？（會先移到 .studio/備份）"))) return;
    try {
      await FE.api(B("/reverse/reset"), { method: "POST", body: {}, signal });
      await FE.route();
    } catch (e) { FE.fail(e); }
  }

  async function adoptGroup(g, signal) {
    if (!(await FE.confirm("採用「" + g + "」的草稿？已有的同名檔案會先備份再覆蓋。"))) return;
    try {
      const res = await FE.api(B("/reverse/adopt"), { method: "POST", body: { group: g }, signal });
      FE.toast("已採用 " + res.adopted + " 份" + (res.backed_up ? "（備份 " + res.backed_up + " 份原檔）" : ""));
      await FE.route();
    } catch (e) { FE.fail(e); }
  }

  async function discardGroup(g, signal) {
    if (!(await FE.confirm("捨棄「" + g + "」的草稿？"))) return;
    try {
      await FE.api(B("/reverse/discard"), { method: "POST", body: { group: g }, signal });
      await FE.route();
    } catch (e) { FE.fail(e); }
  }

  function draftLink(x, docEl) {
    // 舊版是 href 指向偽協定的假連結；改成真的節點事件，不留假連結。
    const open = () => docView(docEl, x.draft);
    return h("div", {},
      h("a", {
        "data-view": x.draft,
        role: "button",
        tabindex: "0",
        // 舊版是 href 假連結（瀏覽器預設 cursor:pointer）；這裡補回游標，不動共用 CSS。
        style: "cursor:pointer",
        onclick: open,
        onkeydown: (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); open(); } },
      }, x.rel),
      x.exists ? [" ", h("span", { class: "badge b-warn" }, "覆蓋")] : null);
  }

  function groupCard([g, desc], items, docEl, signal) {
    const exists = items.filter((x) => x.exists).length;
    return h("div", { class: "card", style: "margin:10px 0;padding:12px 14px" },
      h("div", { class: "row" },
        h("b", {}, g),
        h("span", { class: "muted small", style: "margin-left:8px" },
          desc + "　·　" + items.length + " 份" + (exists ? "，其中 " + exists + " 份會覆蓋現有檔案（先備份）" : "")),
        h("span", { class: "grow" }),
        h("button", { class: "sm primary", "data-adopt": g, onclick: () => adoptGroup(g, signal) }, "採用" + g),
        h("button", { class: "sm danger", "data-discard": g, onclick: () => discardGroup(g, signal) }, "捨棄")),
      h("details", { style: "margin-top:6px" },
        h("summary", { class: "small" }, "看清單"),
        h("div", { class: "small", style: "columns:2;margin-top:6px" }, items.map((x) => draftLink(x, docEl)))));
  }

  async function render(ctx) {
    const signal = ctx.signal;
    const upto = ctx.query.upto || "";
    const r = await FE.api(B("/reverse?provider=" + enc(Panel.prov()) + (upto ? "&upto=" + enc(upto) : "")), { signal });
    const st = r.state, est = r.estimate, dr = st.drafts || {};
    const processed = (st.processed || []).length;
    const busy = !!(S.job && S.job.status === "running");
    const cost = est.cost != null ? "約 US$" + est.cost.toFixed(2) : (Panel.isClaude() ? "用 Claude 訂閱額度" : "依你設定的價格（沒填價格就不顯示）");
    const groups = [
      ["設定", "角色、勢力、世界觀、故事核心、名詞表"],
      ["大綱", "全書大綱、卷綱"],
      ["章綱", "每章的章綱（反向整理，狀態「已寫」）"],
      ["追蹤", "章節摘要、伏筆、時間線、讀者認知、角色關係、角色狀態、狀態卡"],
    ];
    const nDraft = groups.reduce((a, [g]) => a + (dr[g] || []).length, 0);

    const uptoInput = h("input", {
      type: "number", id: "rv-upto", min: "1", value: upto,
      placeholder: String(est.total_chapters || ""), style: "width:140px",
    });
    const docEl = h("div", { id: "doc", style: "margin-top:12px" });

    ctx.view(
      h("div", { class: "page-head" },
        h("div", {},
          h("h1", {}, "從正文建立設定"),
          h("div", { class: "sub" }, "已經寫好的書，不用開書訪談：AI 照章節順序分批讀正文，反推出設定、大綱、章綱與追蹤資料。全部先存成草稿，你核對後再分組採用。"))),
      r.has_settings
        ? h("div", { class: "alert warn", style: "margin-bottom:12px" },
          h("span", { class: "t" }, "這本書已經有角色或伏筆資料。採用草稿時，同名檔案會先備份再覆蓋。"))
        : null,
      h("div", { class: "card", style: "margin-bottom:14px" },
        h("div", { class: "card-title" },
          h("h2", {}, "1. 估算"),
          h("span", { class: "muted small" }, "執行者：" + Panel.provName() + "（右側面板上方可以切換）")),
        h("div", { class: "grid g3", style: "margin-bottom:10px" },
          h("div", {},
            h("div", { class: "muted small" }, "要讀的章節"),
            h("div", { class: "big" }, (est.chapters || 0) + " 章"),
            h("div", { class: "muted small" }, fmtNum(est.chars || 0) + " " + unitCh(unitOfBook()) + "，共 " + (est.total_chapters || 0) + " 章")),
          h("div", {},
            h("div", { class: "muted small" }, "分批"),
            h("div", { class: "big" }, (est.batches || 0) + " 批"),
            h("div", { class: "muted small" }, "依執行者的上下文長度，每批 1～3 章")),
          h("div", {},
            h("div", { class: "muted small" }, "預估 token"),
            h("div", { class: "big" }, fmtNum(est.tokens_in || 0)),
            h("div", { class: "muted small" }, "輸出約 " + fmtNum(est.tokens_out || 0) + "；" + cost))),
        h("div", { class: "row", style: "gap:10px;flex-wrap:wrap" },
          h("label", { class: "f", style: "margin:0" },
            h("span", {}, "先跑到第幾章（空白＝全部）"),
            uptoInput),
          h("button", {
            class: "ghost", id: "rv-est",
            onclick: () => FE.go(bookPath("/reverse" + (uptoInput.value ? "?upto=" + enc(uptoInput.value) : ""))),
          }, "重新估算"))),
      h("div", { class: "card", style: "margin-bottom:14px" },
        h("div", { class: "card-title" },
          h("h2", {}, "2. 執行"),
          h("span", { class: "muted small" },
            (processed ? "已抽取 " + processed + " 章（到第 " + Math.max(...st.processed) + " 章）" : "還沒開始") + (st.done ? "，已產生草稿" : ""))),
        h("div", { class: "muted small", style: "margin-bottom:10px" },
          "中途停止或失敗都沒關係，下次按「繼續」會從斷的地方接著跑，已完成的章節不會重跑。想換範圍或正文改過很多，按「重新開始」（暫存會先備份）。"),
        h("div", { class: "row", style: "gap:8px" },
          h("button", {
            class: "primary", id: "rv-run", disabled: busy,
            onclick: () => Panel.run("reverse", uptoInput.value ? { upto: parseInt(uptoInput.value, 10) } : {}),
          }, processed ? (st.done ? "加跑新章節並重新整理" : "繼續") : "開始"),
          processed
            ? h("button", { class: "ghost danger", id: "rv-reset", disabled: busy, onclick: () => resetRun(signal) }, "重新開始")
            : null)),
      h("div", { class: "card" },
        h("div", { class: "card-title" },
          h("h2", {}, "3. 核對草稿"),
          h("span", { class: "muted small" }, nDraft ? nDraft + " 份草稿" : "跑完之後草稿會出現在這裡")),
        groups.map(([g, desc]) => {
          const items = dr[g] || [];
          return items.length ? groupCard([g, desc], items, docEl, signal) : null;
        }),
        docEl));
  }

  nsPage("b/:book/reverse", "reverse", { book: true }, render);
})();
