/* 大綱頁（轉移計畫 §8.2.6）：從 app.js 搬 viewOutline（原 1196-1220）、volCard（1099-1120）、
   bindVol（1148-1195）、showRevision（1121-1135）、applyRevision（1137-1146）。
   這五個只有大綱頁在用，所以整組留在本檔；bindVol 的綁定改在 volCard 建節點時直接掛 onclick，
   data-* 屬性照留（語意與舊版相同）。
   docView／Panel／S／B() 仍是 app.js 全域（docView 那批還沒搬），這裡直接呼叫並傳節點。 */
(function () {
  "use strict";

  const { h } = FE;

  const outlineHash = (file) => "#/b/" + encodeURIComponent(S.book) + "/outline?f=" + encodeURIComponent(file);
  // 舊版的 .catch(() => null)／.catch(() => [])：換頁中止時照樣往上拋。
  const soft = (promise, fallback) => promise.catch((e) => {
    if (e && e.name === "AbortError") throw e;
    return fallback;
  });

  async function outlineSync(no, signal) {
    try {
      const r = await FE.api(B("/volumes/outline-sync"), { method: "POST", body: { volume: no }, signal });
      const warn = (r && r.warnings) || [];
      if (warn.length) FE.toast(warn.join("；"), "err");
      else FE.toast(FE.t("已同步全書大綱"));
      await FE.route();
    } catch (e) { FE.fail(e); }
  }

  async function adoptVolume(no, signal) {
    try {
      const r = await FE.api(B("/volumes/adopt"), { method: "POST", body: { volume: no }, signal });
      const warn = (r && r.warnings) || [];
      if (warn.length) FE.toast(warn.join("；"), "err");
      else FE.toast(FE.t("已採用第 {0} 卷卷綱", no));
      await FE.route();
    } catch (e) { FE.fail(e); }
  }

  async function cardCheck(a, z, signal) {
    try {
      const r = await FE.api(B("/card-check?from=" + a + "&to=" + z), { signal });
      const rows = r.findings || [];
      FE.modal({
        title: FE.t("章綱體檢") + "（第 " + a + "–" + z + " 章）",
        body: rows.length
          ? h("div", { class: "card" },
            h("div", { class: "small muted" }, FE.t("把設定和章綱對照：提前登場（劇透風險）與久別重逢（設定說已退場）。")),
            rows.map((f) => h("div", { class: "row", style: "align-items:flex-start" },
              h("span", { class: "badge" }, f.kind),
              h("span", {}, FE.t("第 {0} 章", f.chapter) + "「" + f.name + "」：" + f.detail))))
          : h("div", { class: "card" }, h("p", {}, FE.t("章綱沒有發現衝突。"))),
        foot: (done) => [h("button", { class: "btn btn-primary", type: "button", onclick: () => done(true) }, FE.t("知道了"))],
      });
    } catch (e) { FE.fail(e); }
  }

  async function applyRevision(no, signal, close) {
    if (!(await FE.confirm(FE.t("套用後會覆蓋正式卷綱（會先備份），確定嗎？")))) return;
    try {
      const r = await FE.api(B("/volumes/revision/apply"), { method: "POST", body: { volume: no }, signal });
      const warn = (r && r.warnings) || [];
      if (close) close();
      FE.toast(warn.length ? warn.join("；") : FE.t("已套用卷綱修訂"), warn.length ? "err" : undefined);
      await FE.route();
    } catch (e) { FE.fail(e); }
  }

  async function showRevision(no, signal) {
    try {
      const r = await FE.api(B("/volumes/revision/" + no), { signal });
      const lines = (r.diff || "").split("\n").map((line) => {
        const plus = line.charAt(0) === "+" && !line.startsWith("+++");
        const minus = line.charAt(0) === "-" && !line.startsWith("---");
        const color = plus ? "#1a7f37" : minus ? "#b42318" : "#666";
        return h("div", { style: "color:" + color + ";white-space:pre-wrap" }, line);
      });
      let close = null;
      close = FE.modal({
        title: FE.t("卷綱修訂差異") + "（第 " + no + " 卷）",
        body: [
          h("p", { class: "muted small" }, FE.t("紅色是正式卷綱被拿掉的行，綠色是修訂後新增或改寫的行。按「套用修訂」才會覆蓋正式檔（會先備份）。")),
          h("div", { style: "max-height:55vh;overflow:auto;font-family:ui-monospace,monospace;font-size:12px;line-height:1.5;background:#faf8f4;padding:8px;border-radius:6px" },
            lines.length ? lines : FE.t("沒有差異。")),
        ],
        foot: (done) => [
          h("button", { class: "btn", type: "button", onclick: () => done(false) }, FE.t("取消")),
          h("button", {
            class: "btn btn-primary", type: "button",
            onclick: () => { done(true); applyRevision(no, signal, close); },
          }, FE.t("套用修訂")),
        ],
      });
    } catch (e) { FE.fail(e); }
  }

  function volCard(v, signal) {
    const dim = (x) => h("span", { class: "muted small" }, FE.t("第 {0}–{1} 章", x.lo, x.hi) + (x.status ? "（" + x.status + "）" : ""));
    const vols = (v.volumes || []).map((x) => h("div", { class: "row" },
      h("span", {}, x.name, " ", dim(x)),
      h("span", { class: "grow" }),
      x.kind === "卷" ? [
        h("button", { class: "sm", "data-revise": String(x.no), onclick: () => Panel.openForm("volume_revise", { volume: String(x.no) }) }, FE.t("修訂")),
        h("button", { class: "sm", "data-sync": String(x.no), onclick: () => outlineSync(Number(x.no), signal) }, FE.t("同步大綱")),
      ] : null,
      h("button", { class: "sm", "data-check": x.lo + "-" + x.hi, onclick: () => cardCheck(Number(x.lo), Number(x.hi), signal) }, FE.t("章綱體檢")),
      h("button", { class: "sm", "data-card": x.lo + "-" + x.hi, onclick: () => Panel.openForm("chapter_cards", { from: Number(x.lo), to: Number(x.hi) }) }, FE.t("排這一卷的章綱"))));
    const drafts = (v.drafts || []).map((x) => h("div", { class: "row" },
      h("span", {}, FE.t("草稿") + "：" + x.name + " ", dim(x)),
      h("span", { class: "grow" }),
      h("button", { class: "sm", "data-open": x.rel, onclick: () => FE.go(outlineHash(x.rel)) }, FE.t("編輯")),
      h("button", { class: "sm primary", "data-adopt": String(x.no), onclick: () => adoptVolume(Number(x.no), signal) }, FE.t("採用"))));
    const revs = (v.revisions || []).map((x) => h("div", { class: "row" },
      h("span", {}, FE.t("卷綱修訂草稿") + "：" + x.name + " ", dim(x)),
      h("span", { class: "grow" }),
      h("button", { class: "sm", "data-open": x.rel, onclick: () => FE.go(outlineHash(x.rel)) }, FE.t("編輯")),
      h("button", { class: "sm", "data-diff": String(x.no), onclick: () => showRevision(Number(x.no), signal) }, FE.t("看差異")),
      h("button", { class: "sm primary", "data-revapply": String(x.no), onclick: () => applyRevision(Number(x.no), signal, null) }, FE.t("套用修訂"))));
    const plans = (v.plans || []).map((x) => h("div", { class: "row" },
      h("span", {}, FE.t("卷綱更新草稿") + "：" + x.name + " ", dim(x)),
      h("span", { class: "grow" }),
      h("button", { class: "sm", "data-open": x.rel, onclick: () => FE.go(outlineHash(x.rel)) }, FE.t("編輯"))));

    return h("div", { class: "card", id: "vol-card" },
      h("div", { class: "row" },
        h("b", {}, FE.t("卷況")),
        h("span", { class: "grow" }),
        h("button", { class: "primary", id: "vol-new", onclick: () => Panel.openForm("volume_draft", { volume: v.next, from: v.from, to: v.from + 19 }) }, FE.t("開新卷"))),
      h("div", { class: "muted small" }, FE.t("卷綱決定這一卷的邊界；不在任何卷綱範圍內的章節，整章自動流程會拒絕。")),
      h("div", { style: "margin-top:8px" },
        vols.length ? vols : h("div", { class: "muted" }, FE.t("還沒有卷綱。")),
        drafts, revs, plans),
      drafts.length ? h("div", { class: "muted small" }, FE.t("採用後會寫到正式卷綱（狀態改成「已確認」），草稿會被移除。")) : null,
      revs.length ? h("div", { class: "muted small" }, FE.t("修訂會先產生草稿；看過差異按「套用修訂」才覆蓋正式卷綱（會先備份）。")) : null);
  }

  async function render(ctx) {
    const signal = ctx.signal;
    const files = await FE.api(B("/outline"), { signal });
    const vol = await soft(FE.api(B("/volumes"), { signal }), null);
    const chs = await soft(FE.api(B("/chapters"), { signal }), []);
    const nextNo = chs.length ? Math.max(...chs.map((c) => c.no)) + 1 : 1;
    // 卷綱草稿／更新草稿也列進左邊的清單，點開就能看／改（存檔走 /file 的 PUT）
    const drafts = ((vol && vol.drafts) || []).map((x) => ({ name: x.name + "（" + FE.t("草稿") + "）", file: x.rel }));
    const plans = ((vol && vol.plans) || []).map((x) => ({ name: x.name, file: x.rel }));
    const all = files.concat(drafts).concat(plans);
    const file = ctx.query.f || (all.length ? all[0].file : "");
    const docEl = h("div", { id: "doc" });

    ctx.view(
      h("div", { class: "page-head" },
        h("div", {}, h("h1", {}, "大綱"), h("div", { class: "sub" }, "全書大綱與卷綱。章綱在「章節」頁。")),
        h("div", { class: "row" },
          h("button", { onclick: () => Panel.openForm("concept") }, "故事核心診斷"),
          h("button", { onclick: () => Panel.openForm("master_outline") }, "全書大綱"),
          h("button", { onclick: () => spinoffDialog() }, "參考書骨架"))),
      vol ? volCard(vol, signal) : null,
      h("div", { class: "split" },
        h("div", { class: "list" },
          all.length
            ? all.map((x) => h("div", {
              class: "item" + (x.file === file ? " active" : ""),
              onclick: () => FE.go(outlineHash(x.file)),
            }, h("div", { class: "nm" }, x.name)))
            : h("div", { class: "muted" }, "還沒有大綱。"),
          h("div", {
            class: "item",
            onclick: () => FE.go("#/b/" + encodeURIComponent(S.book) + "/bible?t=" + encodeURIComponent("核心") + "&f=" + encodeURIComponent("設定/故事核心.md")),
          },
            h("div", { class: "nm" }, "故事核心"),
            h("div", { class: "ds" }, "設定/故事核心.md"))),
        file
          ? docEl
          : h("div", { class: "card empty" }, h("div", { class: "big" }, "⌘"), "還沒有大綱。可以先做「故事核心診斷」，再規劃全書大綱。")));

    if (file) await docView(docEl, file);
  }

  nsPage("b/:book/outline", "outline", { book: true }, render);
})();
