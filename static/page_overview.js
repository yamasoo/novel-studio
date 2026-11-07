/* 總覽頁（轉移計畫 §8.2.5）：從 app.js 的 viewOverview（原 628-697，含區塊標頭 627）與 alertHtml（原 706-719）搬過來。
   註冊兩個 PAGES key：
     "b/:book"          → #/b/<book>（無子路徑）與尾斜線都畫總覽；有殘餘段（沒登記的頁）時畫 404（不再回舊 route()）。
                          留著這個 key 是因為 matchPage 取最長命中：刪掉它，#/b/<book> 會直接掉到 not_found。
     "b/:book/overview" → #/b/<book>/overview。
   renderPipe／pipeModal／setBookLang／splitFM／docView／spinoffDialog 仍是 app.js 全域（PIPE 那批才搬）。 */
(function () {
  "use strict";

  const { h } = FE;
  const { fmtNum, unitCh, statusBadgeNode } = nsShared;

  // 舊版的 go('#/b/' + enc(S.book) + …) 等價寫法
  const bookPath = (rest) => "#/b/" + encodeURIComponent(S.book) + rest;

  function alertNode(a) {
    let btn = null;
    if (a.chapter) {
      btn = h("button", {
        class: "sm",
        onclick: () => FE.go(bookPath("/ch/" + a.chapter + "?tab=" + (a.tab || "candidate"))),
      }, a.tab === "revision" ? "確認" : "審閱");
    } else if (a.action === "recoveries") {
      btn = h("button", { class: "sm", onclick: () => FE.go(bookPath("/jobs")) }, "查看");
    } else if (a.action === "sync_tracking") {
      btn = h("button", { class: "sm", onclick: () => Panel.run("sync_tracking", {}) }, "補齊");
    } else if (a.action === "rewriteback") {
      btn = h("button", {
        class: "sm",
        onclick: async () => {
          const ok = await FE.confirm(FE.t("重跑第" + a.chapter_no + "章的回寫追蹤？會依正文重新整理這章的摘要、伏筆、時間線、角色狀態等。"));
          if (ok) Panel.run("accept", { chapter: a.chapter_no, path: a.path || "" });
        },
      }, "重跑回寫");
    } else if (a.action === "reverse") {
      btn = h("button", { class: "sm primary", onclick: () => FE.go(bookPath("/reverse")) }, "前往");
    } else if (a.kind === "懸念久未回收") {
      btn = h("button", { class: "sm", onclick: () => FE.go(bookPath("/tracking?t=reader")) }, "查看");
    } else if (a.kind === "設定草稿") {
      btn = h("button", { class: "sm", onclick: () => FE.go(bookPath("/bible?t=草稿")) }, "查看");
    } else if ((a.kind || "").startsWith("伏筆")) {
      btn = h("button", { class: "sm", onclick: () => FE.go(bookPath("/tracking")) }, "查看");
    }
    const more = a.details && a.details.length > 1
      ? h("details", { class: "small", style: "margin-top:4px" },
        h("summary", {}, "展開 " + a.details.length + " 項"),
        a.details.map((x) => h("div", {}, x)))
      : null;
    return h("div", { class: "alert " + a.level },
      h("span", { class: "k" }, a.kind),
      h("span", { class: "t" }, a.text, more),
      btn);
  }

  // 資料夾還不是小說專案（沒有 CLAUDE.md）
  async function renderNonBook(ctx) {
    const draftPath = "候選/新書草稿/骨架.md";
    let hasDraft = false;
    try {
      await FE.api(B("/file?path=" + encodeURIComponent(draftPath)), { signal: ctx.signal });
      hasDraft = true;
    } catch (e) {
      if (e && e.name === "AbortError") throw e;
    }

    const draftBody = h("div", { id: "ov-draft-body" });
    const draftCard = h("div", { class: "card", id: "ov-draft-card", style: "display:none" },
      h("div", { class: "card-title" },
        h("h2", {}, "參考書骨架草稿"),
        h("span", { class: "muted small" }, draftPath)),
      h("p", { class: "muted small" }, "這是模型依參考書產生的草稿，還不是這本書的設定；不會自動套用。"),
      draftBody);
    const draftBtn = h("button", {
      id: "ov-draft",
      onclick: () => {
        draftCard.style.display = "";
        draftBtn.disabled = true;
        docView(draftBody, draftPath);
      },
    }, "查看參考書骨架草稿");

    ctx.view(
      h("div", { class: "page-head" },
        h("div", {}, h("h1", {}, S.book), h("div", { class: "sub" }, "這個資料夾還不是小說專案"))),
      h("div", { class: "card" },
        h("p", {}, "還沒有 CLAUDE.md。開書訪談完成後，這裡就會出現進度與資料。"),
        h("div", { class: "row" },
          h("button", { class: "primary", onclick: () => Panel.openForm("setup_new") }, "開始開書訪談"),
          h("button", { id: "ov-spin", onclick: () => spinoffDialog() }, "用參考書產生故事骨架"),
          hasDraft ? draftBtn : null)),
      hasDraft ? draftCard : null);
  }

  async function render(ctx) {
    const ov = await FE.api(B("/overview"), { signal: ctx.signal });
    if (!S.books.length) S.books = (await FE.api("/api/books", { signal: ctx.signal })).books;
    if (!ov.is_book) return renderNonBook(ctx);

    const sc = ov.status_count, total = Math.max(ov.chapters, 1);
    const seg = (n, cls) => (n ? h("div", { class: cls, style: "width:" + (n / total) * 100 + "%" }) : null);
    S.bookLang = ov.lang || S.bookLang;
    const [, stateBody] = splitFM(ov.state_card || "");
    const next = ov.next;
    // 整章自動流程的進度條由 app.js 的 renderPipe 畫進 .pipe-box（換頁後不要再畫到新頁上）。
    setTimeout(() => { if (ctx.active()) renderPipe(); }, 0);

    const langSel = h("select", {
      id: "book-lang",
      onchange: (ev) => setBookLang(ev.target.value),
      value: ov.lang || "zh-TW",
    },
      h("option", { value: "zh-TW" }, "繁體中文"),
      h("option", { value: "en" }, "English"),
      h("option", { value: "ja" }, "日本語"));

    const stateText = stateBody.trim();
    const stateEl = stateText
      ? FE.md.render(stateBody)
      : h("div", { class: "md" }, h("span", { class: "muted" }, "還沒有狀態卡。寫完第一章後會自動產生。"));
    stateEl.setAttribute("lang", ov.lang || "zh-TW");

    ctx.view(
      h("div", { class: "page-head" },
        h("div", {},
          h("h1", {}, S.book),
          h("div", { class: "sub" }, ov.hook || ""),
          h("div", { class: "sub small" }, h("label", {}, "寫作語言：", langSel))),
        h("div", { class: "row" },
          next.has_card
            ? h("button", { class: "primary", onclick: () => Panel.openForm("write", { from: next.no, to: next.no }) },
              "寫第" + next.no + "章" + (next.title ? "《" + next.title + "》" : ""))
            : h("button", { class: "primary", onclick: () => Panel.openForm("chapter_cards", { from: next.no, to: next.no + 9 }) },
              "排第" + next.no + "–" + (next.no + 9) + "章的章綱"),
          h("button", { onclick: () => pipeModal(next.no) }, "⚡ 整章自動"),
          h("button", { onclick: () => Panel.openForm("review", { from: Math.max(1, ov.latest - 4), to: Math.max(1, ov.latest) }) }, "審查最近章節"),
          h("button", { onclick: () => FE.go(bookPath("/drift")) }, "卷末體檢"))),
      h("div", { class: "pipe-box" }),
      h("div", { class: "grid g4" },
        h("div", { class: "card stat" }, h("div", { class: "num" }, ov.written), h("div", { class: "lbl" }, "已寫章數")),
        h("div", { class: "card stat" }, h("div", { class: "num" }, fmtNum(ov.chars)), h("div", { class: "lbl" }, ov.unit === "words" ? "正文詞數" : "正文字數")),
        h("div", { class: "card stat" }, h("div", { class: "num" }, ov.chapters), h("div", { class: "lbl" }, "已規劃章數（含章綱）")),
        h("div", { class: "card stat" }, h("div", { class: "num" }, next.no),
          h("div", { class: "lbl" }, "下一章 ", next.has_card ? statusBadgeNode(next.card_status) : h("span", { class: "badge b-bad" }, "沒有章綱")))),
      h("div", { class: "card", style: "margin-top:14px" },
        h("div", { class: "card-title" },
          h("h2", {}, "章綱進度"),
          h("a", { href: bookPath("/chapters") }, "看全部章節 →")),
        h("div", { class: "progress" },
          seg(sc["已寫"], "c-written"), seg(sc["已確認"], "c-confirmed"), seg(sc["草稿"], "c-draft"), seg(sc["無章綱"], "c-none")),
        h("div", { class: "legend" },
          h("span", {}, h("i", { class: "c-written" }), "已寫 " + (sc["已寫"] || 0)),
          h("span", {}, h("i", { class: "c-confirmed" }), "章綱已確認 " + (sc["已確認"] || 0)),
          h("span", {}, h("i", { class: "c-draft" }), "章綱草稿 " + (sc["草稿"] || 0)),
          sc["無章綱"] ? h("span", {}, h("i", { class: "c-none" }), "有正文無章綱 " + sc["無章綱"]) : null)),
      h("div", { class: "grid g2", style: "margin-top:14px" },
        h("div", { class: "card" },
          h("div", { class: "card-title" },
            h("h2", {}, "需要注意"),
            h("span", { class: "badge" }, String(ov.alerts.length))),
          ov.alerts.length ? ov.alerts.map(alertNode) : h("div", { class: "muted" }, "一切正常。")),
        h("div", { class: "card state" },
          h("div", { class: "card-title" },
            h("h2", {}, "狀態卡"),
            h("a", { href: bookPath("/tracking?t=state") }, "開啟 →")),
          stateEl)),
      ov.recent.length
        ? h("div", { class: "card", style: "margin-top:14px" },
          h("div", { class: "card-title" }, h("h2", {}, "最近章節")),
          h("table", {}, ov.recent.map((c) => h("tr", {
            class: "click",
            onclick: () => FE.go(bookPath("/ch/" + c.no)),
          },
            h("td", {}, "第" + c.no + "章"),
            h("td", {}, c.title),
            h("td", { class: "num" }, fmtNum(c.chars) + " " + unitCh(ov.unit))))))
        : null);
  }

  // #/b/<book>：0 個殘餘段就是總覽。有殘餘段（沒有登記的頁）或書不存在時只畫 404，不再呼叫舊 route()。
  // 不能直接刪掉這個 key：matchPage 是「最長的 key 勝出」，刪了 #/b/<book> 反而會落到 not_found。
  // 這裡的節點刻意與 fekit core.js 的 notFoundView 一致（div.empty「找不到這個頁面。回首頁」）。
  const notFound = () => h("div", { class: "empty" }, "找不到這個頁面。", " ", h("a", { href: "#/" }, "回首頁"));

  // 書不在 S.books 裡就先重抓一次目錄再判斷（外建目錄的情況），免得上來就對不存在的書發請求
  async function knownBook(id) {
    if (!id) return false;
    if ((S.books || []).some((b) => b.id === id)) return true;
    try { S.books = (await FE.api("/api/books")).books; } catch (e) { /* 目錄讀不到就當作不認識 */ }
    return (S.books || []).some((b) => b.id === id);
  }

  // 不用 nsPage 的 book 選項：它會在 handler 之前就 setBook（對不存在的書會讓面板去輪詢一個 404 的任務端點）。
  nsPage("b/:book", "overview", {}, async (ctx) => {
    const id = ctx.params.book;
    const known = await knownBook(id);
    if (known) await setBook(id);
    else await setBook(null, true);
    if (ctx.args.length || !known) { ctx.view(notFound()); return; }
    await render(ctx);
  });
  nsPage("b/:book/overview", "overview", { book: true }, render);
})();
