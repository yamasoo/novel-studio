/* 反推設定頁（轉移計畫 §8.2.7）：從 app.js 的 viewReverse 搬過來（原本 181-241）。
   三個原生 confirm 改 await FE.confirm（文字一字不差）；動作做完一律 FE.route()（同一頁重載），
   不再自己遞迴呼叫 viewReverse；草稿清單不再用偽協定的假連結。
   2026-11 採用安全：章綱一律另存 大綱/章綱/反推/；其餘三組逐檔三選（預設保留現有）；
   覆蓋先備份；採用前可看新舊字數、相似度與逐段差異。
   Panel／S／B() 仍是 app.js 全域。 */
(function () {
  "use strict";

  const { h } = FE;
  const { fmtNum, unitCh, unitOfBook } = nsShared;
  const enc = encodeURIComponent;
  const bookPath = (rest) => "#/b/" + encodeURIComponent(S.book) + rest;

  // 三選的順序照計畫：保留現有（預設）／用反推版／併入缺的段落。
  const MODES = {
    設定: [["keep", "保留現有"], ["replace", "用反推版"], ["merge", "併入缺的段落"]],
    大綱: [["keep", "保留現有"], ["replace", "用反推版"], ["merge", "併入缺的段落"]],
    追蹤: [["keep", "保留現有"], ["replace", "用反推版"]],
  };
  const FALLBACK = { 設定: "merge", 大綱: "keep", 追蹤: "keep", 章綱: "copy" };

  const modeOf = (g, x) => (MODES[g] || []).some(([v]) => v === x.default_mode) ? x.default_mode : FALLBACK[g];
  const pct = (x) => Math.round((Number(x) || 0) * 100) + "%";

  async function resetRun(signal) {
    if (!(await FE.confirm("清掉已抽取的資料和草稿，重新開始？（會先移到 .studio/備份）"))) return;
    try {
      await FE.api(B("/reverse/reset"), { method: "POST", body: {}, signal });
      await FE.route();
    } catch (e) { FE.fail(e); }
  }

  function summary(g, t) {
    const parts = [];
    parts.push(g === "章綱"
      ? "已存 " + t.adopted + " 份反推章綱到 大綱/章綱/反推/"
      : "已採用 " + t.adopted + " 份");
    if (t.merged) {
      parts.push(t.merged + " 份併入既有檔"
        + (t.conflicts ? "，有 " + t.conflicts + " 段沒併入（收在檔尾「從正文反推（未併入，請核對）」）" : ""));
    }
    if (t.kept) parts.push("保留現有 " + t.kept + " 份");
    if (t.backed_up) {
      const names = t.backups.slice(0, 6).join("、")
        + (t.backups.length > 6 ? " 等 " + t.backups.length + " 份" : "");
      parts.push("備份 " + t.backed_up + " 份原檔（" + names + "）");
    }
    return parts.join("；");
  }

  async function adoptGroup(g, items, picks, signal) {
    const how = g === "章綱"
      ? "反推的章綱會存到 大綱/章綱/反推/，正式章綱一個字都不動。"
      : g === "設定"
        ? "選「保留現有」的不會被動到；「用反推版」會先備份再整份取代；「併入缺的段落」只補原檔空白的欄位與段落，有衝突的收在檔尾「從正文反推（未併入，請核對）」。"
        : "預設不覆蓋；選「用反推版」的檔案才會先備份再取代"
          + (g === "大綱" ? "；選「併入缺的段落」的只補缺的段落" : "") + "。";
    if (!(await FE.confirm("採用「" + g + "」的草稿？" + how))) return;
    try {
      // 後端一次只收一種 mode，所以照選擇把檔案分組，一組打一次（保留現有的也要送，回傳才算得到 kept）。
      const byMode = new Map();
      for (const x of items) {
        const m = g === "章綱" ? "copy" : (picks[x.rel] || modeOf(g, x));
        if (!byMode.has(m)) byMode.set(m, []);
        byMode.get(m).push(x.rel);
      }
      const total = { adopted: 0, merged: 0, kept: 0, backed_up: 0, conflicts: 0, backups: [] };
      for (const [mode, rels] of byMode) {
        const r = await FE.api(B("/reverse/adopt"), { method: "POST", body: { group: g, mode, files: rels }, signal });
        for (const k of ["adopted", "merged", "kept", "backed_up", "conflicts"]) total[k] += r[k] || 0;
        total.backups.push(...(r.backups || []));
      }
      // 摘要會列備份檔名，給比一般提示長一點的閱讀時間。
      FE.toast(summary(g, total), undefined, { duration: 8000 });
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
    return h("a", {
      "data-view": x.draft,
      role: "button",
      tabindex: "0",
      // 舊版是 href 假連結（瀏覽器預設 cursor:pointer）；這裡補回游標，不動共用 CSS。
      style: "cursor:pointer",
      onclick: open,
      onkeydown: (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); open(); } },
    }, x.rel);
  }

  function diffPara(text) { return h("p", {}, text); }

  async function showDiff(g, x, signal) {
    let d;
    try {
      d = await FE.api(B("/reverse/diff?group=" + enc(g) + "&rel=" + enc(x.rel)), { signal });
    } catch (e) { FE.fail(e); return; }
    const head = h("div", { class: "muted small", style: "margin-bottom:8px" },
      (d.old_rel ? "現有：" + d.old_rel : "沒有現有檔案可比對（採用後是新檔）")
      + "　·　舊 " + d.chars_old + " 字 / 新 " + d.chars_new + " 字（相似度 " + pct(x.similarity) + "）");
    const blocks = h("div", { class: "rv-blocks" }, (d.blocks || []).map((b) => {
      if (b.type === "same") {
        const ps = b.old.map(diffPara);
        return b.old.length > 2
          ? h("details", { class: "rv-same" },
            h("summary", { class: "muted small" }, b.old.length + " 段沒有變更（展開）"), ps)
          : h("div", { class: "rv-same" }, ps);
      }
      return h("div", { class: "rv-change" },
        h("div", { class: "rv-side old" },
          h("div", { class: "rv-tag" }, "現有"),
          b.old.length ? b.old.map(diffPara) : h("p", { class: "muted small" }, "（沒有這段）")),
        h("div", { class: "rv-side new" },
          h("div", { class: "rv-tag" }, "反推"),
          b.new.length ? b.new.map(diffPara) : h("p", { class: "muted small" }, "（反推沒有這段）")));
    }));
    FE.modal({ title: "新舊對照：" + x.rel, wide: true, body: h("div", {}, head, blocks) });
  }

  function modeNode(g, x, picks) {
    if (g === "章綱") return h("span", { class: "badge" }, "存成反推對照，正式章綱不動");
    const cur = picks[x.rel] || modeOf(g, x);
    return (MODES[g] || []).map(([v, label]) => h("label", {
      class: "small", style: "cursor:pointer;white-space:nowrap",
    },
      h("input", {
        type: "radio",
        name: "rv-" + g + "-" + x.rel,
        value: v,
        checked: cur === v,
        onchange: () => { picks[x.rel] = v; },
      }), " " + label));
  }

  function rowNode(g, x, picks, docEl, signal) {
    const meta = "舊 " + x.chars_old + " 字 / 新 " + x.chars_new + " 字"
      + (x.exists ? "（相似度 " + pct(x.similarity) + "）" : "（沒有現有檔案）");
    return h("div", { style: "padding:7px 0;border-top:1px solid var(--line,#e5e1d8)" },
      h("div", { class: "row", style: "gap:8px;align-items:baseline;flex-wrap:wrap" },
        draftLink(x, docEl),
        h("span", { class: "muted small" }, meta),
        h("span", { class: "grow" }),
        h("button", { class: "sm ghost", onclick: () => showDiff(g, x, signal) }, "看差異")),
      h("div", { class: "row", style: "gap:10px;margin-top:4px;flex-wrap:wrap;align-items:center" },
        modeNode(g, x, picks),
        g === "章綱" ? h("span", { class: "muted small" }, "→ " + x.target) : null));
  }

  function groupCard([g, desc], items, docEl, signal) {
    const picks = {};
    const existing = items.filter((x) => x.exists).length;
    const note = g === "章綱"
      ? items.length + " 份；一律存到 大綱/章綱/反推/，正式章綱不動"
        + (existing ? "（其中 " + existing + " 份對得到正式章綱，可以看差異）" : "")
      : items.length + " 份" + (existing ? "，其中 " + existing + " 份有現有檔案" : "")
        + "；預設保留現有，要動的逐檔選";
    return h("div", { class: "card", style: "margin:10px 0;padding:12px 14px" },
      h("div", { class: "row", style: "align-items:baseline;flex-wrap:wrap" },
        h("b", {}, g),
        h("span", { class: "muted small", style: "margin-left:8px" }, desc + "　·　" + note),
        h("span", { class: "grow" }),
        h("button", { class: "sm primary", "data-adopt": g, onclick: () => adoptGroup(g, items, picks, signal) }, "採用" + g),
        h("button", { class: "sm danger", "data-discard": g, onclick: () => discardGroup(g, signal) }, "捨棄")),
      h("details", { style: "margin-top:6px" },
        h("summary", { class: "small" }, "看清單與逐檔選擇"),
        h("div", { class: "small", style: "margin-top:6px" }, items.map((x) => rowNode(g, x, picks, docEl, signal)))));
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
      ["章綱", "每章的章綱（反向整理，狀態「已寫」；採用後另存反推對照）"],
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
          h("span", { class: "t" }, "這本書已經有角色或伏筆資料。採用「設定」組時同名檔案會先備份，選「併入缺的段落」只補空白欄位與新段落（有衝突的收在檔尾「從正文反推（未併入，請核對）」），選「用反推版」才整份取代；大綱／追蹤預設保留現有，逐檔選了才動；章綱一律另存 大綱/章綱/反推/，正式章綱不動。任何覆蓋都會先備份。"))
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
