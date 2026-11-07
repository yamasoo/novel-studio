/* 任務紀錄頁（轉移計畫 §8.2.3）：從 app.js 的 viewJobs 搬過來（原本 1791-1805）。
   Panel.show／Panel.run 是 P3 的門面；recoverTo／recoverView／recoverDiscard 仍是 app.js 的全域。
   兩個 GET 都走 FE.api 並帶 ctx.signal。 */
(function () {
  "use strict";

  const { h } = FE;
  const { fmtTime, fmtNum, jobBadgeNode } = nsShared;

  function recoveryRow(r) {
    const actions = [];
    if (r.chapter) {
      actions.push(h("button", { class: "sm primary", onclick: () => Panel.run("recover_continue", { id: r.id }) }, "接著寫完"));
      actions.push(h("button", { class: "sm", onclick: () => recoverTo(r.id) }, "存成候選稿"));
    }
    actions.push(h("button", { class: "sm", onclick: () => recoverView(r.id) }, "查看"));
    actions.push(h("button", { class: "sm danger", onclick: () => recoverDiscard(r.id) }, "捨棄"));
    return h("tr", {},
      h("td", { class: "small" }, fmtTime(r.created)),
      h("td", {},
        r.label,
        h("div", { class: "muted small" }, r.reason, "　·　", fmtNum(r.chars) + " 字", "　·　…", r.preview)),
      h("td", { style: "white-space:nowrap" }, actions));
  }

  function jobRow(j) {
    return h("tr", {
      class: "click",
      // 點一列 → 右側面板顯示那次的完整過程（P3 門面，行為與舊版相同）
      onclick: () => Panel.show(j.id),
    },
      h("td", {}, fmtTime(j.started)),
      h("td", {}, j.title),
      h("td", {}, jobBadgeNode(j.status)),
      h("td", { class: "muted small" }, j.cost != null ? "$" + Number(j.cost).toFixed(3) : ""));
  }

  async function render(ctx) {
    const [hist, recs] = await Promise.all([
      FE.api(B("/jobs"), { signal: ctx.signal }),
      FE.api(B("/recoveries"), { signal: ctx.signal }).catch(() => []),
    ]);

    ctx.view(
      h("div", { class: "page-head" },
        h("div", {},
          h("h1", {}, "任務紀錄"),
          h("div", { class: "sub" }, "點一筆在右側面板查看完整過程，也可以接續那次的對話。"))),
      recs.length
        ? h("div", { class: "card", style: "margin-bottom:14px" },
          h("div", { class: "card-title" },
            h("h2", {}, "恢復稿"),
            h("span", { class: "muted small" }, "模型中途出錯、被停止或被截斷時保留下來的文字")),
          h("table", {}, recs.map(recoveryRow)))
        : null,
      h("div", { class: "card" },
        hist.length
          ? h("table", {},
            h("thead", {}, h("tr", {},
              h("th", {}, "時間"), h("th", {}, "任務"), h("th", {}, "狀態"), h("th", {}, "花費"))),
            h("tbody", {}, hist.map(jobRow)))
          : h("div", { class: "empty" }, "還沒有任何任務。")));
  }

  nsPage("b/:book/jobs", "jobs", { book: true }, render);
})();
