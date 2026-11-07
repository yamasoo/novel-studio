/* 章節頁（轉移計畫 §8.2.4）：從 app.js 的 viewChapters 搬過來（原本 723-743，含區塊標頭 722）。
   Panel.openForm 是面板門面；pipeModal／renderPipe 還在 app.js（跟 PIPE 一起在單章那批才搬），這裡直接呼叫全域。
   列用 h("tr",{onclick})，不留 inline onclick。 */
(function () {
  "use strict";

  const { h } = FE;
  const { fmtNum, unitCh, unitOfBook, statusBadgeNode } = nsShared;

  function chapterRow(c, wu) {
    return h("tr", {
      class: "click",
      onclick: () => FE.go(FE.hash("b", S.book, "ch", c.no)),
    },
      h("td", {}, "第" + c.no + "章"),
      h("td", {}, c.title),
      h("td", { class: "muted" }, c.func),
      h("td", {}, c.card_file
        ? statusBadgeNode(c.card_status || "草稿")
        : h("span", { class: "badge b-bad" }, "無")),
      h("td", { class: "num" }, c.text_file ? fmtNum(c.chars) : h("span", { class: "muted" }, "—")),
      h("td", {}, c.candidate_file
        ? h("span", { class: "badge b-accent" }, "待審 " + fmtNum(c.candidate_chars) + " " + unitCh(wu))
        : null));
  }

  async function render(ctx) {
    const chs = await FE.api(B("/chapters"), { signal: ctx.signal });
    const wu = unitOfBook();
    const nextNo = chs.length ? Math.max(...chs.map((c) => c.no)) + 1 : 1;
    // 整章自動流程的進度條由 app.js 的 renderPipe 畫進 .pipe-box（換頁後不要再畫到新頁上）。
    setTimeout(() => { if (ctx.active()) renderPipe(); }, 0);

    ctx.view(
      h("div", { class: "page-head" },
        h("div", {},
          h("h1", {}, "章節"),
          h("div", { class: "sub" }, "共 " + chs.length + " 章　·　點一列開啟")),
        h("div", { class: "row" },
          h("button", { onclick: () => Panel.openForm("chapter_cards", { from: nextNo, to: nextNo + 9 }) }, "排接下來 10 章"),
          h("button", { onclick: () => pipeModal() }, "⚡ 整章自動"),
          h("button", { class: "primary", onclick: () => Panel.openForm("write", { from: nextNo, to: nextNo }) }, "寫第" + nextNo + "章"))),
      h("div", { class: "pipe-box" }),
      h("div", { class: "card" },
        chs.length
          ? h("div", { class: "table-wrap" },
            h("table", {},
              h("thead", {}, h("tr", {},
                h("th", {}, "章"),
                h("th", {}, "章名"),
                h("th", {}, "功能"),
                h("th", {}, "章綱"),
                h("th", { style: "text-align:right" }, wu === "words" ? "正文詞數" : "正文字數"),
                h("th", {}, "候選稿"))),
              h("tbody", {}, chs.map((c) => chapterRow(c, wu)))))
          : h("div", { class: "empty" },
            h("div", { class: "big" }, "☰"),
            "還沒有任何章綱或正文。",
            h("br"),
            h("button", { class: "primary", style: "margin-top:10px", onclick: () => Panel.openForm("chapter_cards", { from: 1, to: 10 }) }, "排第一批章綱"))));
  }

  nsPage("b/:book/chapters", "chapters", { book: true }, render);
})();
