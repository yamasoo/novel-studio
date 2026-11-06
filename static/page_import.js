/* 匯入頁（轉移計畫 §8.2.11）：從 app.js 搬 viewImport（原 2015-2067）、renderImportPreview（原 2069-2127）與 IMP 狀態（原 2014）。
   import 不碰 S.book（舊 route() 對它沒有 setBook／clearBook）。
   readFiles／bookOpts／unitOfLang 留在 app.js（設定集與插圖也在用），這裡直接呼叫全域；
   bookOpts 回傳的是 HTML 字串（全站唯一實作），這裡用惰性 DOMParser 轉成 option 節點，不碰 innerHTML。
   檔案選擇沿用 <input type="file" multiple> ＋ readFiles（不是資料夾選擇的 pickPath／attachPicker）。 */
(function () {
  "use strict";

  const { h } = FE;
  const { fmtNum, unitCh } = nsShared;
  const enc = encodeURIComponent;

  const IMP = { files: [], preview: null };

  function bookOptions(books, cur) {
    // bookOpts → "&lt;option value=… selected&gt;書名&lt;/option&gt;"；DOMParser 產生的文件是惰性的（不執行、不載入）。
    const doc = new DOMParser().parseFromString(bookOpts(books, cur), "text/html");
    return Array.from(doc.body.querySelectorAll("option")).map((o) =>
      h("option", { value: o.value, selected: o.getAttribute("selected") !== null }, o.textContent));
  }

  async function render(ctx) {
    const signal = ctx.signal;
    const info = await FE.api("/api/import/info", { signal });
    IMP.files = [];
    IMP.preview = null;

    const langSel = h("select", { id: "im-lang" },
      h("option", { value: "zh-TW" }, "繁體中文"),
      h("option", { value: "en" }, "English"),
      h("option", { value: "ja" }, "日本語"));
    const filesInput = h("input", { type: "file", id: "im-files", multiple: true, accept: ".txt,.md,.markdown,.docx" });
    const textArea = h("textarea", {
      id: "im-text", rows: "6",
      placeholder: "第一章 ……" + String.fromCharCode(10) + "正文……" + String.fromCharCode(10, 10) + "第二章 ……",
    });
    const modeSel = h("select", { id: "im-mode" },
      h("option", { value: "auto" }, "自動（第X章、Chapter N、楔子、番外；找不到再用 # 標題）"),
      h("option", { value: "chapter" }, "只認「第X章／第X回」這類標題"),
      h("option", { value: "markdown" }, "只認 Markdown 的 # 標題"));
    const numSel = h("select", { id: "im-num" },
      h("option", { value: "auto" }, "照標題上的章號（不連續時自動改成依順序）"),
      h("option", { value: "sequential" }, "依順序重新編號"));
    const startInput = h("input", { type: "number", id: "im-start", value: "1", min: "1" });
    const convBox = h("input", { type: "checkbox", id: "im-conv", disabled: !info.has_opencc });
    const convWrap = h("label", { class: "cb", id: "im-conv-wrap" },
      convBox,
      " 簡體轉成台灣繁體（含用語，例如「軟件」→「軟體」）",
      info.has_opencc ? null : h("span", { class: "badge b-warn" }, "需要 OpenCC：關閉工作台後重新執行 start.bat 會自動安裝"));
    const preBox = h("input", { type: "checkbox", id: "im-pre" });
    const punctBox = h("input", { type: "checkbox", id: "im-punct", checked: true });
    const previewBtn = h("button", { class: "primary", id: "im-preview" }, "預覽拆章結果");
    const out = h("div", { id: "im-out" });

    ctx.view(
      h("div", { class: "page-head" },
        h("div", {},
          h("h1", {}, "匯入舊稿"),
          h("div", { class: "sub" }, "把已經寫好的 TXT、Markdown、Word（.docx）拆成章節放進書裡；全部在本機處理，不呼叫 AI"))),
      h("div", { class: "grid exp-grid" },
        h("div", { class: "card" },
          h("h2", { style: "margin-bottom:10px" }, "1. 選擇稿子"),
          h("label", { class: "f" }, h("span", {}, "稿子的語言"), langSel),
          h("label", { class: "f" }, h("span", {}, "檔案（可以一次選多個；一個檔案一章也可以）"), filesInput),
          h("label", { class: "f" }, h("span", {}, "或直接貼上"), textArea),
          h("div", { class: "muted small" }, "編碼會自動判斷（UTF-8、Big5、GB18030）。舊版 .doc 請先在 Word 另存成 .docx。")),
        h("div", { class: "card" },
          h("h2", { style: "margin-bottom:10px" }, "2. 怎麼拆章"),
          h("div", { class: "grid g2" },
            h("label", { class: "f" }, h("span", {}, "章節標題"), modeSel),
            h("label", { class: "f" }, h("span", {}, "章號"), numSel),
            h("label", { class: "f" }, h("span", {}, "依順序編號時從第幾章開始"), startInput)),
          convWrap,
          h("label", { class: "cb" }, preBox, " 把第一個章節標題之前的文字當成一章（例如楔子）"),
          h("label", { class: "cb" }, punctBox, " 修正標點（西式引號改「」、半形逗號改全形等）"),
          h("div", { class: "row" }, h("span", { class: "grow" }), previewBtn))),
      out);

    const opts = () => ({
      mode: modeSel.value, numbering: numSel.value, start: parseInt(startInput.value, 10) || 1,
      convert: IMP.lang === "zh-TW" && convBox.checked, lang: IMP.lang,
      preface_as_chapter: preBox.checked, fix_punct: punctBox.checked,
    });
    const payload = () => ({ files: IMP.files, text: textArea.value });
    // 英文、日文稿子不需要簡轉繁，簡體相關的選項與對照一起收起來
    const syncLang = () => {
      IMP.lang = langSel.value;
      convWrap.style.display = IMP.lang === "zh-TW" ? "" : "none";
    };
    langSel.onchange = syncLang;
    syncLang();
    filesInput.onchange = async (ev) => {
      try { IMP.files = await readFiles(ev.target); } catch (e) { FE.fail(e); }
    };
    previewBtn.onclick = async () => {
      previewBtn.disabled = true;
      previewBtn.textContent = "處理中……";
      try {
        const r = await FE.api("/api/import/preview", { method: "POST", body: { payload: payload(), opts: opts() }, signal });
        IMP.preview = r;
        renderPreview(r, info, payload, opts);
      } catch (e) { FE.fail(e); } finally {
        previewBtn.disabled = false;
        previewBtn.textContent = "預覽拆章結果";
      }
    };

    function renderPreview(r, info, payload, opts) {
      const total = r.chapters.reduce((a, c) => a + c.chars, 0);
      const zhOn = IMP.lang === "zh-TW";   // 只有繁體中文稿才顯示簡體相關的檢查與對照
      const wu = unitOfLang(IMP.lang);
      const flagsOf = (c) => (c.flags || []).filter((f) => zhOn || !/簡體/.test(f));
      const guessName = (IMP.files[0] && IMP.files[0].name.replace(/\.[^.]+$/, "").replace(/^\d+[\s._\-、]*/, "")) || "";
      const flagged = r.chapters.filter((c) => flagsOf(c).length).length;

      const table = h("div", { class: "table-wrap", style: "max-height:360px" },
        h("table", {},
          h("tr", {},
            h("th", { class: "num" }, "章"),
            h("th", {}, "章名"),
            h("th", { class: "num" }, wu === "words" ? "詞數" : "字數"),
            h("th", {}, "檢查"),
            h("th", {}, "開頭")),
          r.chapters.map((c) => h("tr", { class: flagsOf(c).length ? "hl" : "" },
            h("td", { class: "num" }, String(c.no)),
            h("td", {}, c.title || h("span", { class: "muted" }, "（無章名）")),
            h("td", { class: "num" }, fmtNum(c.chars)),
            h("td", {}, flagsOf(c).flatMap((f, i) => {
              const badge = h("span", { class: /空章|重複|倒退|簡體/.test(f) ? "badge b-bad" : "badge b-warn" }, f);
              return i ? [" ", badge] : [badge];
            })),
            h("td", { class: "muted small" }, c.head)))));

      const radioNew = h("input", { type: "radio", name: "im-dest", value: "new", checked: !info.books.length });
      const radioOld = h("input", { type: "radio", name: "im-dest", value: "old", checked: info.books.length > 0, disabled: !info.books.length });
      const goBtn = h("button", { class: "primary", id: "im-go" }, "匯入 " + r.chapters.length + " 章");
      const resultBox = h("div", { id: "im-result" });

      out.replaceChildren(
        h("div", { class: "card", style: "margin-top:14px" },
          h("div", { class: "card-title" },
            h("h2", {}, "拆章結果：" + r.chapters.length + " 章，" + fmtNum(total) + " " + unitCh(wu),
              h("span", { class: flagged ? "badge b-warn" : "badge b-ok", style: "margin-left:8px" },
                flagged ? flagged + " 章要檢查" : "沒有發現問題")),
            h("span", { class: "muted small" }, r.numbered_by_title ? "章號照標題" : "章號依順序")),
          h("div", { class: "row small muted", style: "margin-bottom:8px" },
            r.sources.map((s) => h("span", { class: "badge" },
              s.name + "：" + s.encoding + (zhOn && s.simplified ? "，簡體字約 " + s.simplified : "")))),
          r.warnings.map((w) => h("div", { class: "alert warn" }, h("span", { class: "t" }, w))),
          r.preface.map((p) => h("div", { class: "muted small", style: "margin:6px 0" },
            "開頭文字（" + p.name + "，" + p.chars + " " + unitCh(wu) + "）：" + p.preview + "……")),
          table),
        h("div", { class: "card", style: "margin-top:14px" },
          h("h2", { style: "margin-bottom:10px" }, "3. 放到哪裡"),
          h("div", { class: "seg compact" },
            h("label", {}, radioNew, h("span", {}, "建立新書")),
            h("label", {}, radioOld, h("span", {}, "放進現有的書"))),
          h("div", { class: "grid g2", style: "margin-top:10px" },
            h("label", { class: "f", "data-dest": "new" },
              h("span", {}, "書名"), h("input", { type: "text", id: "im-name", value: guessName })),
            h("label", { class: "f", "data-dest": "old" },
              h("span", {}, "書"), h("select", { id: "im-book" }, bookOptions(info.books, S.book))),
            h("label", { class: "f" },
              h("span", {}, "放進"), h("select", { id: "im-target" },
                h("option", { value: "正文" }, "正文（直接當成定稿）"),
                h("option", { value: "候選" }, "候選稿（逐章審閱後再採用）"))),
            h("label", { class: "f", "data-dest": "old" },
              h("span", {}, "書裡已經有同一章時"), h("select", { id: "im-conflict" },
                h("option", { value: "skip" }, "跳過，保留書裡的"),
                h("option", { value: "overwrite" }, "覆蓋（原檔先備份）")))),
          h("div", { class: "row" }, h("span", { class: "grow" }), goBtn),
          resultBox));

      const sync = () => {
        const d = document.querySelector('input[name="im-dest"]:checked').value;
        document.querySelectorAll("[data-dest]").forEach((x) => { x.hidden = x.dataset.dest !== d; });
      };
      document.querySelectorAll('input[name="im-dest"]').forEach((x) => { x.onchange = sync; });
      sync();

      goBtn.onclick = async () => {
        const isNew = document.querySelector('input[name="im-dest"]:checked').value === "new";
        const body = {
          payload: payload(),
          opts: Object.assign(opts(), {
            target: document.querySelector("#im-target").value,
            conflict: document.querySelector("#im-conflict").value,
          }),
        };
        if (isNew) {
          body.new_book = document.querySelector("#im-name").value.trim();
          if (!body.new_book) return FE.toast("請輸入書名", "err");
        } else {
          body.book = document.querySelector("#im-book").value;
        }
        goBtn.disabled = true;
        try {
          const res = await FE.api("/api/import/commit", { method: "POST", body, signal });
          S.books = (await FE.api("/api/books", { signal })).books;
          const nextStep = res.target === "正文"
            ? ["已經寫好的書，可以用 ",
              h("a", { href: "#/b/" + enc(res.book) + "/reverse" }, "從正文建立設定"),
              " 讓 AI 從正文反推角色、世界觀、名詞表、大綱、章綱、伏筆與時間線（先存成草稿，不需要開書訪談）；文風可以到「共用庫 → 文風」用這本書的正文分析。"]
            : ["到章節頁逐章審閱候選稿，按「採用」移入正文並回寫追蹤。"];
          resultBox.replaceChildren(
            h("div", { class: "alert ok", style: "margin-top:12px" },
              h("span", { class: "k" }, "完成"),
              h("span", { class: "t" },
                "匯入 " + res.written.length + " 章（" + fmtNum(res.chars) + " " + unitCh(unitOfLang(IMP.lang)) + "）到《" + res.book + "》的" + res.target + "。" +
                (res.skipped.length ? "跳過已存在的第 " + res.skipped.join("、") + " 章。" : "") +
                (res.replaced.length ? "覆蓋了第 " + res.replaced.join("、") + " 章（原檔已備份）。" : "")),
              h("button", { class: "sm primary", onclick: () => FE.go("#/b/" + enc(res.book)) }, "開啟這本書")),
            h("div", { class: "muted small", style: "margin-top:8px" }, "下一步建議：", nextStep));
          renderNav();
        } catch (e) { FE.fail(e); } finally { goBtn.disabled = false; }
      };
    }
  }

  nsPage("import", "import", {}, render);
})();
