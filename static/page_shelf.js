/* 書架頁（轉移計畫 §8.2.1）：從 app.js 搬 viewShelf（原 212-270）＋ DEMO_LANGS／DEMO_INTRO／renderDemoCard（272-288）
   ＋ newBookDialog（290-351）＋ spinoffDialog（353-371）＋ spinoffGenerate（373-437）。
   註冊 key 用 "home"：fekit 的 matchPage 對空路徑會用 router.home（預設 "home"）去比對
   （core.js:574「const wanted = parts.length ? parts : [router.home]」），所以 #/、#、直接開網址都落在這裡。
   **spinoffDialog 保留 window 全域**：page_outline.js:155 與 page_overview.js:89 在呼叫它（與 docView／pipeModal 同一種模式）。
   initFolder 仍留在 app.js 的 window.initFolder（書庫裡「不是小說專案」的資料夾用它開書）。
   新書對話框、骨架進度視窗全部改 FE.modal＋h 表單；attachPicker／pickPath 照舊呼叫全域（P5 才換 FE.filepicker）。 */
(function () {
  "use strict";

  const { h } = FE;
  const { fmtNum, fmtTime } = nsShared;
  const enc = encodeURIComponent;

  const DEMO_LANGS = { "zh-TW": "繁體中文", en: "English", ja: "日本語" };   // i18n-skip
  const DEMO_INTRO = {
    "zh-TW": "可以先放一本示範書《退婚之後》進書架，看看各頁面長什麼樣子。示範書只是資料夾，隨時可以刪掉。",
    en: "可以先放一本示範書《The Lantern Road》進書架，看看各頁面長什麼樣子。示範書只是資料夾，隨時可以刪掉。",
    ja: "可以先放一本示範書《辺境の薬師と竜の約束》進書架，看看各頁面長什麼樣子。示範書只是資料夾，隨時可以刪掉。",
  };

  function renderDemoCard(card) {
    if (!card) return;
    let lang = (FE.i18n && FE.i18n.lang) || "zh-TW";
    if (!DEMO_INTRO[lang]) lang = "zh-TW";
    const langSel = h("select", { id: "demo-lang" }, Object.keys(DEMO_INTRO).map((l) =>
      h("option", { value: l, selected: l === lang }, DEMO_LANGS[l])));
    const addBtn = h("button", { id: "add-demo" }, "加入示範書");
    card.replaceChildren(
      h("h3", {}, "第一次使用？"),
      h("p", { class: "muted" }, DEMO_INTRO[lang]),
      h("div", { class: "row" }, langSel, addBtn));
    langSel.onchange = (ev) => {
      lang = ev.target.value;
      renderDemoCard(card);
    };
    addBtn.onclick = async () => {
      try {
        await FE.api("/api/demo", { method: "POST", body: { lang } });
        FE.toast("已加入示範書");
        FE.route();
      } catch (e) { FE.fail(e); }
    };
  }

  function newBookDialog() {
    const others = (S.books || []).map((b) => h("option", { value: b.name }, b.title || b.name));
    const nameInput = h("input", { type: "text", id: "nb-name", placeholder: "例如：退婚之後" });
    const langSel = h("select", { id: "nb-lang" },
      h("option", { value: "zh-TW" }, "繁體中文"), h("option", { value: "en" }, "English"), h("option", { value: "ja" }, "日本語"));
    const ideaArea = h("textarea", { id: "nb-idea", rows: "4", placeholder: "一句話、一段簡介，或幾個關鍵字" });
    const refSel = h("select", { id: "nb-ref" }, h("option", { value: "" }, "（不參考）"), others);
    const genBox = h("input", { type: "checkbox", id: "nb-gen" });
    const hint = h("p", { class: "muted small", id: "nb-mode-hint" });
    const genRow = h("label", { class: "f", id: "nb-gen-row" }, genBox, " 順便產生故事骨架草稿（用上面的參考書，1–2 分鐘；不會自動套用）");
    const goBtn = h("button", { class: "primary", id: "nb-go" }, "建立並開始訪談");

    const close = FE.modal({
      title: "開新書",
      body: [
        h("p", { class: "muted small" }, "先在書庫建立資料夾，再選開書方式。開書訪談會先問兩輪再建立專案；用參考書骨架直接開書會先產生骨架，然後直接寫入設定與大綱，跳過訪談。執行者可以在右側面板上方切換。"),
        h("label", { class: "f" }, h("span", {}, "書名（也是資料夾名稱）"), nameInput),
        h("label", { class: "f" }, h("span", {}, "寫作語言"), langSel),
        h("p", { class: "muted small" }, "決定這本書的提示詞和模型輸出的語言。介面語言是另外的設定（右下角）。"),
        h("label", { class: "f" }, h("span", {}, "初步構想（選填）"), ideaArea),
        h("label", { class: "f" }, h("span", {}, "參考書（選填；用骨架直接開書時必選）"), refSel),
        h("p", { class: "muted small" }, "只沿用它的", h("b", {}, "文風指標"), "與", h("b", {}, "章節結構"), "（數字），不會帶入任何名字或情節。"),
        h("label", { class: "f" }, h("span", {}, "開書方式")),
        h("div", { class: "seg compact", id: "nb-mode" },
          h("label", {}, h("input", { type: "radio", name: "nb-mode", value: "interview", checked: true }), h("span", {}, "開書訪談（推薦）")),
          h("label", {}, h("input", { type: "radio", name: "nb-mode", value: "skeleton" }), h("span", {}, "用參考書骨架直接開書"))),
        hint,
        genRow,
      ],
      foot: (done) => [
        h("span", { class: "grow" }),
        h("button", { class: "btn", type: "button", onclick: () => done(false) }, "取消"),
        goBtn,
      ],
    });

    // P5 起改讀 FE.i18n，不再寫入舊的 ns_lang 偏好。
    const ul = FE.i18n && FE.i18n.lang;
    if (ul) langSel.value = ul;
    nameInput.focus();
    const syncMode = () => {
      const mode = close.el.querySelector('input[name="nb-mode"]:checked').value;
      const skeleton = mode === "skeleton";
      genRow.style.display = skeleton ? "none" : "";
      hint.textContent = skeleton
        ? FE.t("需要選一本參考書。會先產生骨架（約 1–2 分鐘），然後直接寫入 CLAUDE.md、故事核心、全書大綱與卷綱，跳過開書訪談；骨架沒提到的欄位會標「待補」。")
        : FE.t("先問兩輪再建立專案。下面可以順便產生一份骨架草稿，但草稿不會自動套用。");
      goBtn.textContent = skeleton ? FE.t("建立並用骨架開書") : FE.t("建立並開始訪談");
    };
    close.el.querySelectorAll('input[name="nb-mode"]').forEach((r) => { r.onchange = syncMode; });
    syncMode();

    goBtn.onclick = async () => {
      const name = nameInput.value;
      const lang = langSel.value;
      const ref = refSel.value;
      const mode = close.el.querySelector('input[name="nb-mode"]:checked').value;
      const gen = mode !== "skeleton" && genBox.checked;
      const idea = ideaArea.value;
      if (mode === "skeleton" && !ref) return FE.toast("用骨架直接開書要先選一本參考書", "err");
      close();
      const busy = FE.modal({
        title: "建立中…",
        body: [h("p", { class: "muted small" }, "正在量參考書的文風指標與結構 DNA（大書約 20–30 秒），完成後" + (mode === "skeleton" ? "會開始產生骨架。" : "會開始開書訪談。"))],
        foot: () => [],
      });
      try {
        const r = await FE.api("/api/books", { method: "POST", body: { name, idea, lang, provider: Panel.prov(), ref, mode } });
        S.books = (await FE.api("/api/books")).books;
        if (mode === "skeleton") {
          // 不要先跳書頁：那會短暫顯示「不是小說專案」的兩個按鈕，看起來像又要開一次訪談。
          busy();
          spinoffGenerate(r.id, ref, idea, { apply: true });
          return;
        }
        busy();
        FE.go("#/b/" + enc(r.id));
        if (r.job) Panel.attach(r.job);
        if (r.seeded && r.seeded.length) FE.toast("已沿用參考書的文風指標與章節結構");
        if (gen && ref) spinoffGenerate(r.id, ref, idea);
        else if (gen && !ref) FE.toast("要先選一本參考書", "err");
      } catch (e) { busy(); FE.fail(e); }
    };
  }

  function spinoffDialog() {
    if (!S.book) return;
    const others = (S.books || []).filter((b) => b.name !== S.book);
    if (!others.length) { FE.toast("書庫裡沒有其他書可以參考", "err"); return; }
    const refSel = h("select", { id: "sp-ref" }, others.map((b) => h("option", { value: b.name }, b.title || b.name)));
    const noteArea = h("textarea", { id: "sp-note", rows: "2", placeholder: "例如：換成校園背景、主角改成女性" });
    const goBtn = h("button", { class: "primary", id: "sp-go" }, "產生骨架");
    const close = FE.modal({
      title: "用參考書產生故事骨架",
      body: [
        h("p", { class: "muted small" }, "只沿用參考書的抽象特徵（文風、結構、視角、章節節奏），不會帶入名字或情節。請只用你自有或公有領域的作品。"),
        h("label", { class: "f" }, h("span", {}, "參考書"), refSel),
        h("label", { class: "f" }, h("span", {}, "補充要求（選填）"), noteArea),
        h("p", { class: "muted small" }, "用右側目前的執行者生（約 3 次呼叫、1–2 分鐘）。Claude Code 不行，要先切成 API 執行者。"),
      ],
      foot: (done) => [
        h("span", { class: "grow" }),
        h("button", { class: "btn", type: "button", onclick: () => done(false) }, "取消"),
        goBtn,
      ],
    });
    goBtn.onclick = () => {
      const ref = refSel.value, note = noteArea.value;
      close();
      spinoffGenerate(S.book, ref, note);
    };
  }

  async function spinoffGenerate(id, source, note, opts) {
    const o = opts || {};
    const applyMode = !!o.apply;
    const t0 = Date.now();
    let background = false;
    const stageEl = h("b", { id: "sp-stage" }, "排隊中…");
    const elapsedEl = h("span", { class: "muted small", id: "sp-elapsed" }, FE.t("已 {0} 秒", 0));
    const bgBtn = applyMode ? null : h("button", { id: "sp-bg" }, "背景執行");
    const close = FE.modal({
      title: "正在產生故事骨架",
      body: [
        h("p", { class: "muted small" }, "用《" + source + "》的文風指紋與結構 DNA 產生；約 1–2 分鐘（大書量指紋會久一點）。"),
        h("p", {}, stageEl, " ", elapsedEl),
        h("p", { class: "muted small" }, applyMode
          ? "正在建立專案，請稍待…完成後會直接寫入設定與大綱。"
          : ["這個視窗可以留著看進度；草稿會寫到 ", h("code", {}, "候選/新書草稿/"), "，不會自動套用。"]),
        bgBtn ? h("div", { class: "row" }, h("span", { class: "grow" }), bgBtn) : null,
      ],
      foot: () => [],
    });
    if (bgBtn) bgBtn.onclick = () => { background = true; close(); };
    const alive = () => !!document.querySelector("#sp-stage");
    const setStage = (s) => { const el = document.querySelector("#sp-stage"); if (el) el.textContent = s; };
    const tick = setInterval(() => {
      const el = document.querySelector("#sp-elapsed");
      if (el) el.textContent = FE.t("已 {0} 秒", Math.floor((Date.now() - t0) / 1000));
    }, 500);
    try {
      const start = await FE.api("/api/books/" + enc(id) + "/spinoff", {
        method: "POST", body: { source, note, provider: Panel.prov(), apply: applyMode },
      });
      setStage(start.stage || "執行中…");
      let st = { status: "running" };
      while (st.status === "running") {
        await new Promise((r) => setTimeout(r, 1200));
        if (!alive()) background = true;   // 視窗被關掉（按背景或點外面）就不要再彈結果視窗
        st = await FE.api("/api/books/" + enc(id) + "/spinoff/" + enc(start.task));
        setStage(st.stage || "執行中…");
      }
      clearInterval(tick);
      if (!alive()) background = true;
      if (background) {
        if (st.status === "error") FE.toast("骨架沒有產生：" + (st.error || "未知錯誤"), "err");
        else if (applyMode) { if (S.book === id) FE.route(); FE.toast("已用骨架開書"); }
        else { FE.route(); FE.toast("骨架草稿已產生"); }
        return;
      }
      const r = st.result || {};
      const bad = (r.guard && r.guard["撞到名字"]) || [];
      if (st.status === "error") {
        const retryBtn = h("button", { class: "primary", id: "sp-retry" }, "重試");
        const c2 = FE.modal({
          title: "產生失敗",
          body: [
            h("p", { style: "color:#b45309" }, st.error || "未知錯誤"),
            h("p", { class: "muted small" }, "可以按「重試」再跑一次；一直失敗的話，把右側執行者換成另一個 API 模型再試。"),
          ],
          foot: (done) => [
            h("span", { class: "grow" }),
            h("button", { class: "btn", type: "button", onclick: () => done(false) }, "知道了"),
            retryBtn,
          ],
        });
        retryBtn.onclick = () => { c2(); spinoffGenerate(id, source, note, opts); };
        FE.toast("骨架沒有產生", "err");
        return;
      }
      if (applyMode) {
        const files = (r.applied && r.applied.files) || [];
        FE.go("#/b/" + enc(id));
        FE.modal({
          title: "已用骨架開書",
          body: [
            h("p", { class: "muted small" }, files.length
              ? "已寫入 " + files.length + " 個檔案：" + files.join("、") + "。"
              : "已寫入設定與大綱。"),
            bad.length ? h("p", { class: "muted small", style: "color:#b45309" }, "護欄：有名字和參考書重複（" + bad.join("、") + "），請手動改掉。") : null,
            h("p", { class: "muted small" }, "目標讀者、平台、篇幅、讀者契約等骨架沒提到的欄位已標「待補」，可在「設定 → 故事核心」補；章綱請用「卷先行 → 排這一卷的章綱」。"),
          ],
          foot: (done) => [
            h("span", { class: "grow" }),
            h("button", { class: "btn btn-primary", type: "button", onclick: () => { done(true); FE.route(); } }, "進入這本書"),
          ],
        });
        FE.route();
        FE.toast("已用骨架開書");
        return;
      }
      const previewMd = FE.md.render(r.preview || "");
      FE.modal({
        title: "故事骨架草稿",
        body: [
          h("p", { class: "muted small" }, ["已寫到 ", h("code", {}, r.draft || ""), "。這只是草稿，不會改動設定或大綱；滿意再手動貼進「設定」與「大綱」。"]),
          bad.length ? h("p", { class: "muted small", style: "color:#b45309" }, "護欄：有名字和參考書重複（" + bad.join("、") + "），請手動改掉。") : null,
          previewMd,
        ],
        foot: (done) => [
          h("span", { class: "grow" }),
          h("button", { class: "btn btn-primary", type: "button", onclick: () => { done(true); FE.route(); } }, "知道了"),
        ],
      });
      FE.route();
      FE.toast(bad.length ? "骨架生成了，但有撞名要處理" : "骨架草稿已產生", bad.length > 0 ? "err" : undefined);
    } catch (e) { clearInterval(tick); FE.fail(e); }
  }

  async function render(ctx) {
    const signal = ctx.signal;
    const data = await FE.api("/api/books", { signal });
    S.books = data.books;

    if (!data.library) {
      const libInput = h("input", { type: "text", id: "lib-path", value: data.suggested || "" });
      const okBtn = h("button", { class: "primary", id: "lib-ok" }, "使用這個資料夾");
      ctx.view(
        h("div", { class: "page-head" },
          h("div", {}, h("h1", {}, "歡迎使用小說工作台"), h("div", { class: "sub" }, "先選一個資料夾當「書庫」"))),
        h("div", { class: "card" },
          h("p", {}, "書庫是放所有小說專案的資料夾，每本書是裡面的一個子資料夾；共用庫和插圖也會放在這裡。工作台程式和書庫是分開的，更新或重新下載工作台都不會動到你的書。"),
          h("label", { class: "f" }, h("span", {}, "書庫資料夾"), libInput),
          h("div", { class: "muted small", style: "margin:-6px 0 12px" },
            data.suggested_exists ? "這個資料夾已經存在，裡面的書會出現在書架上。" : "資料夾不存在時會自動建立。",
            "之後可以在「設定」改。"),
          h("div", { class: "row" }, okBtn)));
      attachPicker(libInput, { mode: "dir", title: "選擇書庫資料夾" });
      okBtn.onclick = async () => {
        const p = libInput.value.trim();
        if (!p) return FE.toast("請選擇資料夾", "err");
        try { await FE.api("/api/config", { method: "POST", body: { library: p, create_library: true } }); FE.route(); } catch (e) { FE.fail(e); }
      };
      return;
    }

    if (!data.exists) {
      const mkBtn = h("button", { class: "primary", id: "mk-lib" }, "建立這個資料夾");
      ctx.view(
        h("div", { class: "page-head" }, h("div", {}, h("h1", {}, "書架"), h("div", { class: "sub" }, "還沒有書庫資料夾"))),
        h("div", { class: "card" },
          h("p", {}, "書庫是放所有小說專案的資料夾，每本書是裡面的一個子資料夾。目前設定的位置："),
          h("p", {}, h("code", {}, data.library || "（未設定）")),
          h("div", { class: "row" },
            mkBtn,
            h("button", { onclick: () => FE.go("#/settings") }, "改用其他位置"))));
      mkBtn.onclick = async () => {
        try { await FE.api("/api/config", { method: "POST", body: { create_library: true } }); FE.route(); } catch (e) { FE.fail(e); }
      };
      return;
    }

    const books = data.books.filter((b) => b.is_book);
    const others = data.books.filter((b) => !b.is_book);
    const newCard = h("div", { class: "card book new", id: "new-book" },
      h("div", { class: "plus" }, "＋"), h("div", {}, "開新書"), h("div", { class: "muted small" }, "可參考另一本書"));
    const importCard = h("div", { class: "card book new", onclick: () => FE.go("#/import") },
      h("div", { class: "plus" }, "⇪"), h("div", {}, "匯入舊稿"));
    const demoCard = books.length ? null : h("div", { class: "card", style: "margin-top:16px", id: "demo-card" });

    const shelves = h("div", { class: "shelf" },
      books.map((b) => h("div", { class: "card book", onclick: () => FE.go("#/b/" + enc(b.id)) },
        h("div", { class: "title" }, b.name),
        h("div", { class: "hook" }, b.hook || "（還沒有一句話鉤子）"),
        h("div", { class: "meta" },
          h("span", {}, "已寫 " + b.chapters_written + " 章"),
          h("span", {}, fmtNum(b.chars) + " " + unitCh(b.unit)),
          b.pending_candidates ? h("span", { class: "badge b-accent" }, b.pending_candidates + " 份候選稿") : null),
        h("div", { class: "meta" }, "更新於 " + (fmtTime(b.updated) || "—")))),
      newCard,
      importCard);

    const othersNode = others.length
      ? [h("hr", { class: "sep" }),
        h("div", { class: "muted small" }, "書庫裡還有這些資料夾（沒有 CLAUDE.md，不是小說專案）："),
        h("div", { class: "row", style: "margin-top:6px" },
          others.map((o) => [
            h("span", { class: "badge" }, o.name),
            h("button", { class: "sm", onclick: () => initFolder(o.id) }, "在這裡開書"),
          ]))]
      : null;

    ctx.view(
      h("div", { class: "page-head" },
        h("div", {},
          h("h1", {}, "書架"),
          h("div", { class: "sub" }, books.length + " 本書　·　書庫：", h("code", {}, data.library))),
        h("div", { class: "row" }, h("button", { onclick: () => FE.go("#/guide") }, "使用說明"))),
      S.claudeFound
        ? null
        : h("div", { class: "alert warn", style: "margin-bottom:14px" },
          h("span", { class: "k" }, "找不到 Claude Code"),
          h("span", { class: "t" }, "按鈕會無法執行。請安裝 Claude Code，或到設定填入 claude 的路徑。"),
          h("button", { class: "sm", onclick: () => FE.go("#/settings") }, "設定")),
      shelves,
      demoCard,
      othersNode);

    newCard.onclick = newBookDialog;
    if (demoCard) renderDemoCard(demoCard);
  }

  window.spinoffDialog = spinoffDialog;
  nsPage("home", "shelf", { clearBook: true }, render);
})();
