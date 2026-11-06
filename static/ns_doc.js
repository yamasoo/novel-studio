/* 文件檢視／編輯（轉移計畫 §8.3 的 ns_doc.js）：從 app.js 的 docView（原 708-783）＋ localizeLabels（原 694-706）搬過來。
   對外仍然叫 window.docView(el, path, opts)：頁面檔（outline／reverse／search／shared／import 之外）與還沒搬的
   bible／tracking／illust 都是直接呼叫全域，改名會一次踩碎很多頁。
   全部改成 h() 節點；Markdown 用 FE.md.render；編輯中的未存檔狀態走 FE.dirty（換頁會跳「還沒存檔」）；
   Ctrl+S 存檔；textarea 的 keydown／input 監聽用 AbortController 綁，重畫或換頁就 abort，不留 leak。 */
(function () {
  "use strict";

  const { h } = FE;
  const { fmtNum, unitCh, unitOfBook } = nsShared;
  const enc = encodeURIComponent;

  // 設定檔裡的「欄位標籤」（例如「想要：」）和正文同一個文字節點，整段對不上鍵，所以要切開來翻。
  // 只改顯示，檔案內容不動；中文介面直接略過。
  function localizeLabels(root) {
    if (!root || !window.I18N || I18N.lang === "zh-TW") return;
    const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const nodes = [];
    while (w.nextNode()) nodes.push(w.currentNode);
    for (const n of nodes) {
      const m = n.nodeValue.match(/^(\s*)([^：:\n]{1,30}[：:])([\s\S]*)$/);
      if (!m) continue;
      const label = I18N.tr(m[2]), rest = I18N.tr(m[3]);
      const next = m[1] + label + rest;
      if (next !== n.nodeValue) n.nodeValue = next;
    }
  }

  async function docView(el, path, opts = {}) {
    const signal = opts.signal;
    const fbase = opts.base || B("");
    let f;
    try {
      f = await FE.api(fbase + "/file?path=" + enc(path), { signal });
    } catch (e) {
      el.replaceChildren(h("div", { class: "card empty" }, (e && e.message) || String(e)));
      return;
    }
    let editing = false, findings = null, editorCtrl = null;
    let fm, body;
    [fm, body] = splitFM(f.text);

    const setDirty = (on) => FE.dirty.set(on);
    const stopEditor = () => { if (editorCtrl) { editorCtrl.abort(); editorCtrl = null; } };
    // 換頁時把未存檔狀態與編輯器監聽收乾淨
    if (signal) signal.addEventListener("abort", () => { stopEditor(); setDirty(false); }, { once: true });

    const findingsCard = () => {
      if (!findings) return null;
      const items = findings["問題"] || [];
      return h("div", { class: "card" },
        h("div", { class: "card-title" },
          h("h3", {}, "檢查結果"),
          h("button", { class: "ghost sm", "data-a": "closecheck" }, "✕")),
        h("div", { class: "small muted" }, "中文字數 " + fmtNum(findings["中文字數"])),
        h("div", { class: "findings" }, items.length
          ? items.map((x, i) => h("div", { class: "finding", "data-i": String(i) },
            h("span", { class: "ln" }, x["行"] ? "第" + x["行"] + "行" : "全章"),
            h("span", {},
              h("span", { class: "badge " + (x["等級"] === "必須修" ? "b-bad" : x["等級"] === "建議修" ? "b-warn" : "") }, x["等級"]),
              " ",
              x["類型"] + "：" + x["片段"],
              h("div", { class: "muted small" }, x["建議"]))))
          : h("div", { class: "muted" }, "沒有發現問題。")),
        items.length
          ? h("button", {
            class: "sm",
            style: "margin-top:8px",
            onclick: () => Panel.openForm("deslop", {
              chapter: parseInt((f.path.match(/第0*(\d+)章/) || [])[1], 10) || 1,
              candidate: f.path.startsWith("候選"),
            }),
          }, "請 Claude 處理")
          : null);
    };

    const render = () => {
      stopEditor();
      const prose = !!opts.prose;
      const lang = bookLang();

      const bar = h("div", { class: "doc-bar" },
        h("span", { class: "path" }, f.path),
        prose ? h("span", { class: "badge" }, fmtNum(f.chars) + " " + unitCh(unitOfBook())) : null,
        h("span", { class: "grow" }),
        opts.checkable ? h("button", { class: "sm", "data-a": "check" }, "檢查用語與 AI 味") : null,
        (f.readonly || opts.readonly)
          ? null
          : (editing
            ? [h("button", { class: "sm", "data-a": "cancel" }, "取消"), h("button", { class: "sm primary", "data-a": "save" }, "儲存")]
            : h("button", { class: "sm", "data-a": "edit" }, "編輯")));

      const fmRow = Object.keys(fm).length
        ? h("div", { class: "fm" },
          Object.entries(fm).filter(([, v]) => v !== "" && v !== "[]")
            .map(([k, v]) => h("span", { class: "badge" }, FE.t(String(k)) + "：" + FE.t(String(v)))))
        : null;

      const ta = h("textarea", {
        class: "editor" + (prose ? " prose" : ""), lang, spellcheck: "false",
      }, f.text);

      let content;
      if (editing) {
        content = ta;
      } else {
        const mdNode = FE.md.render(body);
        if (prose) mdNode.classList.add("prose");
        mdNode.setAttribute("lang", lang);
        if (prose) mdNode.setAttribute("data-i18n-skip", "");
        content = [fmRow, mdNode];
      }

      el.replaceChildren(h("div", { class: "doc-wrap" + (findings ? " with-side" : "") },
        h("div", { class: "card" }, bar, content),
        findingsCard()));

      if (!prose && !editing) localizeLabels(el.querySelector(".md"));
      el.querySelectorAll("[data-a]").forEach((b) => { b.onclick = () => act(b.dataset.a); });
      el.querySelectorAll(".finding").forEach((d) => {
        d.onclick = () => jump(findings["問題"][d.dataset.i]["行"]);
      });
      if (editing) {
        editorCtrl = new AbortController();
        const ctrlSignal = editorCtrl.signal;
        ta.addEventListener("keydown", (e) => {
          if ((e.ctrlKey || e.metaKey) && e.key === "s") { e.preventDefault(); act("save"); }
        }, { signal: ctrlSignal });
        ta.addEventListener("input", () => { setDirty(ta.value !== f.text); }, { signal: ctrlSignal });
        setDirty(ta.value !== f.text);
      }
    };

    const jump = (line) => {
      if (!line) return;
      if (!editing) { editing = true; render(); }
      const ta = el.querySelector("textarea.editor");
      const lines = ta.value.split(String.fromCharCode(10));
      let start = 0;
      for (let i = 0; i < line - 1 && i < lines.length; i++) start += lines[i].length + 1;
      ta.focus();
      ta.setSelectionRange(start, start + (lines[line - 1] || "").length);
      const lh = parseFloat(getComputedStyle(ta).lineHeight) || 24;
      ta.scrollTop = Math.max(0, (line - 4) * lh);
    };

    const act = async (a) => {
      if (a === "edit") { editing = true; render(); }
      else if (a === "cancel") { editing = false; setDirty(false); render(); }
      else if (a === "closecheck") { findings = null; render(); }
      else if (a === "check") {
        try {
          findings = await FE.api(B("/check"), { method: "POST", body: { path: f.path }, signal });
          render();
        } catch (e) { FE.fail(e); }
      } else if (a === "save") {
        const text = el.querySelector("textarea.editor").value;
        try {
          const r = await FE.api(fbase + "/file", { method: "PUT", body: { path: f.path, text, mtime: f.mtime }, signal });
          FE.toast("已儲存");
          f = await FE.api(fbase + "/file?path=" + enc(path), { signal });
          [fm, body] = splitFM(f.text);
          editing = false;
          setDirty(false);
          if (findings) findings = await FE.api(B("/check"), { method: "POST", body: { path: f.path }, signal });
          render();
          if (opts.onSaved) opts.onSaved(r);
        } catch (e) { FE.fail(e); }
      }
    };

    render();
  }

  window.docView = docView;
})();
