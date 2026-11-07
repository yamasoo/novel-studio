/* 卷末體檢頁（轉移計畫 §8.2.10）：從 app.js 的 viewDrift（原 448-507）搬過來。
   報告 Markdown 用 FE.md.render（不是舊的 md()）；「檢查第 a–b 章…（N 秒）」與「產生中…（N 秒）」兩個
   本地計時器照留，但用 ctx.active() 在換頁後自動 clearInterval，不讓它繼續跑。
   Panel／S／B() 仍是 app.js 全域。 */
(function () {
  "use strict";

  const { h } = FE;
  const enc = encodeURIComponent;

  const softOv = (promise) => promise.catch((e) => {
    if (e && e.name === "AbortError") throw e;
    return {};
  });

  async function render(ctx) {
    const signal = ctx.signal;
    const ov = await softOv(FE.api(B("/overview"), { signal }));
    const latest = ov.latest || 1;
    const from = parseInt(ctx.query.from || Math.max(1, latest - 9), 10);
    const to = parseInt(ctx.query.to || latest, 10);

    const fromInput = h("input", { type: "number", id: "dr-from", value: String(from) });
    const toInput = h("input", { type: "number", id: "dr-to", value: String(to) });
    const out = h("div", { id: "dr-out" });
    const goBtn = h("button", { class: "primary", id: "dr-go" }, "開始檢查");

    ctx.view(
      h("div", { class: "page-head" },
        h("div", {},
          h("h1", {}, "卷末體檢"),
          h("div", { class: "sub" }, "拿設定回頭對正文：哪幾章沒寫到章綱、哪些角色久未登場、哪些伏筆欠帳、哪些章文風偏了。本機計算，不花錢。"))),
      h("div", { class: "card" },
        h("div", { class: "row", style: "align-items:flex-end" },
          h("label", { class: "f", style: "width:120px" }, h("span", {}, "從第幾章"), fromInput),
          h("label", { class: "f", style: "width:120px" }, h("span", {}, "到第幾章"), toInput),
          h("span", { class: "grow muted small" }, "第一次掃一本長書約 2–10 秒（之後會快取）；掃描期間這個頁面可以切走。"),
          goBtn)),
      out);

    goBtn.onclick = async () => {
      const a = parseInt(fromInput.value, 10) || 1;
      const b = parseInt(toInput.value, 10) || a;
      const t0 = Date.now();
      const sec = h("span", { id: "dr-sec" }, "0");
      out.replaceChildren(h("div", { class: "card" }, h("p", { class: "muted" }, "檢查第 " + a + "–" + b + " 章…（", sec, " 秒）")));
      const tick = setInterval(() => {
        if (!ctx.active()) { clearInterval(tick); return; }
        sec.textContent = ((Date.now() - t0) / 1000).toFixed(0);
      }, 500);
      try {
        const r = await FE.api(B("/drift?from=" + a + "&to=" + b), { signal });
        clearInterval(tick);
        const planOut = h("div", { id: "dr-plan-out" });
        const planBtn = h("button", { id: "dr-plan" }, "產生卷綱更新草稿（用 " + Panel.provName() + "）");
        out.replaceChildren(h("div", { class: "card" },
          FE.md.render(r.report || ""),
          h("div", { class: "row", style: "margin-top:10px" },
            h("span", { class: "grow" }),
            planBtn),
          planOut));

        planBtn.onclick = async () => {
          const t1 = Date.now();
          const sec2 = h("span", { id: "dr-sec2" }, "0");
          planOut.replaceChildren(h("p", { class: "muted" }, "產生中…（通常 30–90 秒，推理模型會久一點；", sec2, " 秒）"));
          const tick2 = setInterval(() => {
            if (!ctx.active()) { clearInterval(tick2); return; }
            sec2.textContent = ((Date.now() - t1) / 1000).toFixed(0);
          }, 500);
          try {
            const p = await FE.api(B("/drift/plan"), { method: "POST", body: { from: a, to: b, provider: Panel.prov() }, signal });
            clearInterval(tick2);
            if (p.error) {
              planOut.replaceChildren(
                h("p", { class: "muted small", style: "color:#b45309" }, "產生失敗：" + p.error),
                h("p", { class: "muted small" }, "沒有存任何草稿，卷綱也沒動。可以再試一次，或換一個執行者。"));
              return;
            }
            const w1 = p.warnings || [];
            if (w1.length) FE.toast(w1.join("；"), "err");
            const applyBtn = h("button", { id: "dr-apply" }, "附加到卷綱");
            planOut.replaceChildren(
              FE.md.render(p.plan_md || ""),
              h("div", { class: "row" }, h("span", { class: "grow" }), applyBtn),
              h("p", { class: "muted small" }, "附加＝在 ", h("code", {}, p.volume_file), " 末尾加一節，不會覆蓋原本的卷綱。"));
            applyBtn.onclick = async () => {
              try {
                const res = await FE.api(B("/drift/apply"), { method: "POST", body: { from: a, to: b, draft: p.draft }, signal });
                const w2 = res.warnings || [];
                if (w2.length) FE.toast(w2.join("；"), "err");
                else FE.toast("已附加到 " + res.volume_file);
                planOut.replaceChildren(h("p", { class: "muted" }, "已附加到 ", h("code", {}, res.volume_file), "（原本的內容沒動）。"));
              } catch (e) { FE.fail(e); }
            };
          } catch (e) { clearInterval(tick2); FE.fail(e); }
        };
      } catch (e) { clearInterval(tick); FE.fail(e); }
    };
  }

  nsPage("b/:book/drift", "drift", { book: true }, render);
})();
