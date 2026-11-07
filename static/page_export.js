/* 匯出頁（轉移計畫 §8.2.9）：從 app.js 的 viewExport（原 2903-2999）＋ fmtSize（原 2901）搬過來。
   fmtSize 只有這一頁用，所以留在本檔；sel()（用物件產生 select）也留在本檔。
   下載用 h("a",{href,download})，不用 window.open；刪除的原生 confirm 改 await FE.confirm。
   Panel／S／B() 仍是 app.js 全域。 */
(function () {
  "use strict";

  const { h } = FE;
  const { fmtNum, unitCh, fmtTime } = nsShared;
  const enc = encodeURIComponent;

  const fmtSize = (n) => (n >= 1048576 ? (n / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(n / 1024)) + " KB");
  const sel = (id, obj, cur) => h("select", { id },
    Object.entries(obj).map(([k, v]) => h("option", { value: k, selected: k === cur }, v)));

  async function render(ctx) {
    const signal = ctx.signal;
    const m = await FE.api(B("/export"), { signal });
    const p = m.prefs;
    const chs = m.chapters;
    const first = chs.length ? chs[0].no : "";
    const last = chs.length ? chs[chs.length - 1].no : "";

    // ── 格式 ──
    const radio = (value, title, note, checked) => h("label", {},
      h("input", { type: "radio", name: "x-fmt", value, checked }),
      h("span", {}, h("b", {}, title), h("small", {}, note)));
    // ── 內容 ──
    const itemBoxes = m.items.map(([k, label]) => h("label", { class: "cb" },
      h("input", { type: "checkbox", "data-item": k, checked: p.items.includes(k) }),
      " " + label,
      k === "bible" ? h("span", { class: "muted small" }, "（不含設定草稿）") : null));
    const fromInput = h("input", { type: "number", id: "x-from", class: "num-in", value: String(first), min: String(first), max: String(last) });
    const toInput = h("input", { type: "number", id: "x-to", class: "num-in", value: String(last), min: String(first), max: String(last) });

    const txtBlock = h("div", { "data-only": "txt" },
      h("label", { class: "f" }, h("span", {}, "文字編碼"), sel("x-enc", m.encodings, p.encoding)));
    const epubBlock = h("div", { "data-only": "epub" },
      h("label", { class: "cb" },
        h("input", { type: "checkbox", id: "x-vert", checked: !!p.vertical }),
        " 直排（由右往左翻頁；章名建議用「第一章」格式）"),
      h("label", { class: "cb" },
        h("input", { type: "checkbox", id: "x-cover", checked: p.use_cover !== false, disabled: !m.cover }),
        " 使用封面圖",
        h("span", { class: "muted small" }, m.cover ? "（" + m.cover + "）" : "（到「插圖 → 封面」出圖或上傳，或把 封面.jpg 放在書資料夾）")),
      h("label", { class: "cb" },
        h("input", { type: "checkbox", id: "x-ill", checked: p.include_illust !== false, disabled: !m.illust_chapters }),
        " 在章首放插圖",
        h("span", { class: "muted small" }, "（" + (m.illust_chapters ? m.illust_chapters + " 章有主圖" : "還沒有章節插圖") + "）")));

    const resultBox = h("div", { id: "x-result" });
    const listBox = h("div", { id: "x-list" });
    const goBtn = h("button", { class: "primary", id: "x-go" }, "匯出");

    ctx.view(
      h("div", { class: "page-head" },
        h("div", {},
          h("h1", {}, "匯出"),
          h("div", { class: "sub" }, "把正文和資料整理成一個檔案，存在書資料夾的 ", h("code", {}, "匯出"), " 裡"))),
      h("div", { class: "grid exp-grid" },
        h("div", { class: "card" },
          h("h2", { style: "margin-bottom:12px" }, "格式"),
          h("div", { class: "seg", id: "x-fmt" },
            radio("epub", "EPUB 電子書", "有目錄，可放進電子書閱讀器、Apple Books、Google Play 圖書", p.format !== "txt"),
            radio("txt", "TXT 純文字", "任何地方都能開，適合貼到連載平台或手機閱讀器", p.format === "txt")),
          h("h2", { style: "margin:18px 0 10px" }, "內容"),
          itemBoxes,
          h("div", { class: "row", style: "margin:4px 0 0 26px" },
            h("span", { class: "small muted" }, "章節範圍"),
            fromInput,
            " ",
            h("span", { class: "small muted" }, "到"),
            toInput,
            h("span", { class: "small muted" },
              "（正文共 " + chs.length + " 章，" + fmtNum(chs.reduce((a, c) => a + c.chars, 0)) + " " + unitCh(m.unit) + "；章綱也套用這個範圍）")),
          chs.length ? null : h("div", { class: "muted small", style: "margin:6px 0 0 26px" }, "還沒有採用的正文。候選稿要先採用才會匯出。")),
        h("div", { class: "card" },
          h("h2", { style: "margin-bottom:12px" }, "書籍資訊與排版"),
          h("div", { class: "grid g2" },
            h("label", { class: "f" }, h("span", {}, "書名"), h("input", { type: "text", id: "x-title", value: p.title || m.book_title })),
            h("label", { class: "f" }, h("span", {}, "作者（選填）"), h("input", { type: "text", id: "x-author", value: p.author || "" })),
            h("label", { class: "f" }, h("span", {}, "章名格式"), sel("x-ts", m.title_styles, p.title_style)),
            h("label", { class: "f" }, h("span", {}, "段落格式"), sel("x-ps", m.para_styles, p.para_style))),
          txtBlock,
          epubBlock,
          h("div", { class: "row", style: "margin-top:12px" }, h("span", { class: "grow" }), goBtn),
          resultBox)),
      h("div", { class: "card", style: "margin-top:14px" },
        h("div", { class: "card-title" },
          h("h2", {}, "匯出紀錄"),
          h("span", { class: "muted small" }, "檔案在書資料夾的 ", h("code", {}, "匯出"), " 裡")),
        listBox));

    const fmt = () => {
      const checked = document.querySelector('input[name="x-fmt"]:checked');
      return checked ? checked.value : "epub";
    };
    const sync = () => {
      [txtBlock, epubBlock].forEach((el) => { el.hidden = el.dataset.only !== fmt(); });
      const textOn = !!(document.querySelector('[data-item="text"]').checked || document.querySelector('[data-item="cards"]').checked);
      fromInput.disabled = !textOn;
      toInput.disabled = !textOn;
    };
    document.querySelectorAll('input[name="x-fmt"], [data-item]').forEach((el) => { el.onchange = sync; });
    sync();

    const downloadLink = (file, cls) => h("a", {
      class: cls, href: B("/exports/" + enc(file)), download: file,
    }, "下載");

    const renderList = (list) => {
      listBox.replaceChildren(list.length
        ? h("table", {}, list.map((x) => h("tr", {},
          h("td", {}, x.file),
          h("td", { class: "num" }, fmtSize(x.size)),
          h("td", { class: "muted" }, fmtTime(x.mtime)),
          h("td", { class: "num" },
            downloadLink(x.file, "btn sm"),
            " ",
            h("button", {
              class: "sm danger", "data-del": x.file,
              onclick: async () => {
                if (!(await FE.confirm("刪除 " + x.file + "？"))) return;
                try {
                  await FE.api(B("/exports/" + enc(x.file)), { method: "DELETE", signal });
                  renderList((await FE.api(B("/export"), { signal })).exports);
                } catch (e) { FE.fail(e); }
              },
            }, "刪除")))))
        : h("div", { class: "muted small" }, "還沒有匯出過。"));
    };
    renderList(m.exports);

    goBtn.onclick = async () => {
      const items = Array.from(document.querySelectorAll("[data-item]:checked")).map((el) => el.dataset.item);
      const from = parseInt(fromInput.value, 10);
      const to = parseInt(toInput.value, 10);
      if (!items.length) return FE.toast("請至少勾選一項內容", "err");
      if (from && to && from > to) return FE.toast("章節範圍的起點不能大於終點", "err");
      const body = {
        format: fmt(), items, title: document.querySelector("#x-title").value.trim(),
        author: document.querySelector("#x-author").value.trim(),
        title_style: document.querySelector("#x-ts").value, para_style: document.querySelector("#x-ps").value,
        encoding: document.querySelector("#x-enc").value,
        vertical: document.querySelector("#x-vert").checked,
        use_cover: document.querySelector("#x-cover").checked,
        include_illust: document.querySelector("#x-ill").checked,
        from: from && from !== first ? from : null,
        to: to && to !== last ? to : null,
      };
      if (body.title === m.book_title) body.title = "";
      goBtn.disabled = true; goBtn.textContent = "匯出中……";
      try {
        const r = await FE.api(B("/export"), { method: "POST", body, signal });
        const parts = [];
        if (r.chapters) parts.push(r.chapters + " 章、" + fmtNum(r.chars) + " " + unitCh(r.unit));
        if (r.docs) parts.push(r.docs + " 份資料");
        resultBox.replaceChildren(h("div", { class: "alert ok", style: "margin-top:12px" },
          h("span", { class: "k" }, "完成"),
          h("span", { class: "t" }, r.file + "（" + parts.join("，") + "，" + fmtSize(r.size) + "）"),
          downloadLink(r.file, "btn sm primary")));
        renderList((await FE.api(B("/export"), { signal })).exports);
      } catch (e) { FE.fail(e); } finally { goBtn.disabled = false; goBtn.textContent = "匯出"; }
    };
  }

  nsPage("b/:book/export", "export", { book: true }, render);
})();
