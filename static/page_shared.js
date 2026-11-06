/* 共用庫頁（轉移計畫 §8.2.12）：從 app.js 的 viewShared（原 1798-1947）搬過來，
   連同只有它在用的 styleAiModal／sampleSourceHtml／sampleSourceBind／sampleSourceValue／compareTable／STYLE_GENRES（原 1656-1796）。
   舊 route() 對 shared 沒有 setBook 也沒有 clearBook，所以 options 給 {}。
   文風任務照舊 Panel.attach(job)（job 的 book 是 _共用，base 由 panelBase 決定）；
   S.onSharedJob 改成每次 render 設定、ctx.signal abort 時清掉，避免換頁後還指到舊頁。
   bookOpts／provOpts／provSelectHtml 仍是 app.js 的字串版，這裡用 nsShared.nodesFromHtml 轉成節點。 */
(function () {
  "use strict";

  const { h } = FE;
  const { fmtNum, nodesFromHtml } = nsShared;
  const enc = encodeURIComponent;
  const BASE = "#/shared";

  const SS_LABELS = {
    none: "不附樣本", book: "某本書的正文", text: "貼上文字",
    files: "上傳檔案（.txt、.md、.docx）", copy_book: "複製某本書現有的 設定/文風.md", blank: "空白範本（自己填）",
  };
  const STYLE_GENRES = ["本格推理", "冷硬派", "心理驚悚", "恐怖怪談", "仙俠修真", "武俠", "西式奇幻", "科幻", "現代言情", "古言宮鬥",
    "都市爽文", "歷史架空", "都市寫實", "輕小說", "黑色幽默", "鄉土地域", "太空歌劇"];

  let styleJobTarget = null;   // 舊版是 S.styleJobTarget；改成頁面自己的狀態

  // 舊版 sampleSourceHtml 回傳一段 HTML 字串（呼叫端當成兄弟節點插入），這裡回傳節點陣列。
  function sampleSourceNodes(books, kinds) {
    return [
      h("div", { class: "seg compact", id: "ss-kind" },
        kinds.map((k, i) => h("label", {},
          h("input", { type: "radio", name: "ss-kind", value: k, checked: i === 0 }),
          h("span", {}, SS_LABELS[k])))),
      h("div", { "data-ss": "book copy_book", class: "row", style: "margin-top:8px" },
        h("select", { id: "ss-book" }, nodesFromHtml(bookOpts(books, S.book))),
        h("span", { "data-ss": "book", class: "row" },
          h("span", { class: "small muted" }, "章節"),
          h("input", { type: "number", id: "ss-from", class: "num-in", placeholder: "全部" }),
          h("span", { class: "small muted" }, "到"),
          h("input", { type: "number", id: "ss-to", class: "num-in", placeholder: "全部" }))),
      h("div", { "data-ss": "text", style: "margin-top:8px" },
        h("textarea", { id: "ss-text", rows: "7", placeholder: "貼上一段你想參考的文字。至少 300 字，建議 3000 字以上統計才有參考價值。" })),
      h("div", { "data-ss": "files", style: "margin-top:8px" },
        h("input", { type: "file", id: "ss-files", multiple: true, accept: ".txt,.md,.docx" })),
      h("div", { class: "muted small", style: "margin-top:6px", "data-ss": "book text files" },
        "程式會在本機統計句長、段長、對白比例、標點習慣、高頻詞組等，寫進文風檔的「文字指標」一節；不呼叫 AI。"),
    ];
  }

  function sampleSourceBind(el) {
    const sync = () => {
      const k = el.querySelector('input[name="ss-kind"]:checked').value;
      el.querySelectorAll("[data-ss]").forEach((x) => { x.hidden = !x.dataset.ss.split(" ").includes(k); });
    };
    el.querySelectorAll('input[name="ss-kind"]').forEach((x) => { x.onchange = sync; });
    sync();
  }

  async function sampleSourceValue(el) {
    const k = el.querySelector('input[name="ss-kind"]:checked').value;
    const v = { source: k === "none" ? null : k };
    if (k === "book" || k === "copy_book") {
      v.book = el.querySelector("#ss-book").value;
      v.from = parseInt(el.querySelector("#ss-from").value, 10) || null;
      v.to = parseInt(el.querySelector("#ss-to").value, 10) || null;
    }
    if (k === "text") v.text = el.querySelector("#ss-text").value;
    if (k === "files") {
      v.files = await readFiles(el.querySelector("#ss-files"));
      if (!v.files.length) throw new Error("請選擇檔案");
    }
    return v;
  }

  function compareTableNode(rows) {
    if (!rows.length) return h("div", { class: "muted small" }, "沒有可以比較的指標。");
    return h("table", {},
      h("tr", {},
        h("th", {}, "指標"),
        h("th", { class: "num" }, "文風目標"),
        h("th", { class: "num" }, "實際"),
        h("th", { class: "num" }, "差距"),
        h("th", {})),
      rows.map((r) => h("tr", {},
        h("td", {}, r["指標"]),
        h("td", { class: "num" }, r["目標"]),
        h("td", { class: "num" }, r["實際"]),
        h("td", { class: "num" }, r["差距"]),
        h("td", {}, r["偏離"] === "明顯"
          ? h("span", { class: "badge b-bad" }, "差很多")
          : r["偏離"] ? h("span", { class: "badge b-warn" }, "有點差")
            : h("span", { class: "badge b-ok" }, "接近")))));
  }

  function provSelect(id) {
    return h("select", { id }, nodesFromHtml(provOpts(Panel.prov())));
  }

  async function styleAiModal(mode, books, name, signal) {
    const titles = { design: "請 AI 設計文風", revise: "請 AI 調整「" + (name || "") + "」", test: "照「" + (name || "") + "」試寫一段" };
    let body;
    if (mode === "design") {
      const chips = h("div", { class: "chips", id: "sa-chips" },
        STYLE_GENRES.map((g) => h("button", { type: "button", class: "chip sm" }, g)));
      body = [
        h("p", { class: "muted small" }, "AI 會依照文風的十三個面向（視角距離、敘述者立場、用詞、句子、段落、描寫、修辭、對白、情緒、轉場、連載慣例……）寫出完整文風檔，含有標籤的原創範例段落。只填名稱也可以，填越多越準。"),
        h("div", { class: "grid g2" },
          h("label", { class: "f" }, h("span", {}, "名稱"), h("input", { type: "text", id: "sa-name", placeholder: "例如：冷調推理、雅致仙俠" })),
          h("label", { class: "f" }, h("span", {}, "執行者"), provSelect("sa-prov"))),
        h("label", { class: "f" }, h("span", {}, "類型（可以點下面的標籤，也可以自己寫；混合類型請寫「骨架＋調味」）"),
          h("input", { type: "text", id: "sa-genre", placeholder: "例如：本格推理＋校園" })),
        chips,
        h("label", { class: "f" }, h("span", {}, "想要的感覺"),
          h("textarea", { id: "sa-feel", rows: "2", placeholder: "例如：冷靜、克制、線索藏在日常裡；讀起來像在跟偵探一起看現場" })),
        h("div", { class: "grid g2" },
          h("label", { class: "f" }, h("span", {}, "參考作品或作者（只學特徵，不抄文字）"),
            h("input", { type: "text", id: "sa-refs", placeholder: "例如：東野圭吾的推理段落、松本清張的社會描寫" })),
          h("label", { class: "f" }, h("span", {}, "敘事視角"),
            h("input", { type: "text", id: "sa-pov", placeholder: "例如：第一人稱助手視角（不填由 AI 建議）" })),
          h("label", { class: "f" }, h("span", {}, "讀者與平台"),
            h("input", { type: "text", id: "sa-readers", placeholder: "例如：連載平台，手機閱讀，每章三千字" })),
          h("label", { class: "f" }, h("span", {}, "一定不要"),
            h("input", { type: "text", id: "sa-avoid", placeholder: "例如：不要翻譯腔、不要偵探耍帥" }))),
        h("details", { style: "margin:6px 0 10px" },
          h("summary", { class: "small" }, "附上寫作樣本（選填：AI 會從樣本歸納規則，程式會統計文字指標）"),
          h("div", { style: "margin-top:8px" }, sampleSourceNodes(books, ["none", "text", "files", "book"]))),
        h("label", { class: "cb" },
          h("input", { type: "checkbox", id: "sa-over" }),
          " 同名文風已存在時覆蓋（舊版會備份到 _共用/.備份）"),
      ];
    } else if (mode === "revise") {
      body = [
        h("p", { class: "muted small" }, "只改和你意見相關的條目，其他原樣保留；完成後會列出「舊 → 新」。舊版會備份到 ", h("code", {}, "_共用/.備份"), "。"),
        h("label", { class: "f" }, h("span", {}, "要怎麼調整"),
          h("textarea", { id: "sa-note", rows: "5", placeholder: "例如：對白再口語一點；比喻太多，一場最多一個；補一段打鬥的範例；這份太簡單了，照十三個面向補完整" })),
        h("details", { style: "margin:6px 0 10px" },
          h("summary", { class: "small" }, "附上寫作樣本（選填）"),
          h("div", { style: "margin-top:8px" }, sampleSourceNodes(books, ["none", "text", "files", "book"]))),
        h("label", { class: "f" }, h("span", {}, "執行者"), provSelect("sa-prov")),
      ];
    } else {
      body = [
        h("p", { class: "muted small" }, "照這份文風寫 200～300 字，附上自評：示範了哪些規則、哪條規則難以遵守。試寫不會改動文風檔。"),
        h("label", { class: "f" }, h("span", {}, "情境（選填）"),
          h("textarea", { id: "sa-note", rows: "3", placeholder: "例如：偵探第一次走進命案現場，和刑警有一段對話。不填由 AI 挑最能考驗文風的情境。" })),
        h("label", { class: "f" }, h("span", {}, "執行者"), provSelect("sa-prov")),
      ];
    }

    const close = FE.modal({
      title: titles[mode],
      body,
      foot: (done) => [
        h("button", { class: "btn", type: "button", onclick: () => done(false) }, "取消"),
        h("button", {
          class: "btn btn-primary", type: "button", id: "sa-go",
          onclick: () => {
            done(true);
            go();
          },
        }, mode === "test" ? "試寫" : "開始"),
      ],
    });
    const el = close.el;

    async function go() {
      try {
        const v = el.querySelector("#ss-kind") ? await sampleSourceValue(el) : {};
        v.mode = mode;
        v.provider = el.querySelector("#sa-prov").value;
        const val = (id) => (el.querySelector("#" + id) ? el.querySelector("#" + id).value.trim() : "");
        if (mode === "design") {
          v.name = val("sa-name") || val("sa-genre");
          if (!v.name) return FE.toast("請輸入名稱或類型", "err");
          Object.assign(v, {
            genre: val("sa-genre"), feel: val("sa-feel"), refs: val("sa-refs"), pov: val("sa-pov"),
            readers: val("sa-readers"), avoid: val("sa-avoid"), overwrite: el.querySelector("#sa-over").checked,
          });
        } else {
          v.name = name; v.note = val("sa-note");
          if (mode === "revise" && !v.note) return FE.toast("請寫下要怎麼調整", "err");
        }
        const job = await FE.api("/api/shared/styles/design", { method: "POST", body: v, signal });
        styleJobTarget = mode === "test" ? null : v.name;
        Panel.attach(job);
      } catch (e) { FE.fail(e); }
    }

    if (el.querySelector("#ss-kind")) sampleSourceBind(el);
    el.querySelectorAll("#sa-chips .chip").forEach((c) => {
      c.onclick = () => {
        const inp = el.querySelector("#sa-genre");
        const g = c.textContent;
        const parts = inp.value.split(/[＋+、,，]/).map((x) => x.trim()).filter(Boolean);
        inp.value = parts.includes(g) ? parts.filter((x) => x !== g).join("＋") : parts.concat(g).join("＋");
        c.classList.toggle("on", !parts.includes(g));
        if (!el.querySelector("#sa-name").value.trim()) el.querySelector("#sa-name").placeholder = inp.value || "例如：冷調推理、雅致仙俠";
      };
    });
  }

  // 在 #sh-actions 放一排按鈕（舊版是設 innerHTML，這裡建節點）
  function actionRow(buttons) {
    return h("div", { class: "row", style: "margin-bottom:10px" }, buttons);
  }

  async function render(ctx) {
    const signal = ctx.signal;
    const o = await FE.api("/api/shared", { signal });
    S.sharedBooks = o.books;
    S.sharedLangs = o.book_langs || {};
    const tab = ctx.query.t || "文風";
    let file = ctx.query.f || "";
    const tabs = ["文風", "章節結構", "共用作者偏好"];

    // 任務完成後刷新共用庫；換頁就把回呼清掉，避免指到已經不存在的頁面
    const onSharedJob = (job) => {
      if (job.status !== "done") return;
      const n = styleJobTarget;
      if (n) FE.toast("文風「" + n + "」已更新");
      if (location.hash.startsWith("#/shared")) {
        if (n) FE.go("#/shared?t=" + enc("文風") + "&f=" + enc("文風/" + n + ".md"));
        else FE.route();
      }
    };
    S.onSharedJob = onSharedJob;
    signal.addEventListener("abort", () => {
      if (S.onSharedJob === onSharedJob) S.onSharedJob = null;
    }, { once: true });

    if (!o.exists) {
      const initBtn = h("button", { class: "primary", id: "sh-init" }, "建立共用庫");
      initBtn.onclick = async () => {
        try { await FE.api("/api/shared/init", { method: "POST", signal }); await FE.route(); }
        catch (e) { FE.fail(e); }
      };
      ctx.view(
        h("div", { class: "page-head" }, h("div", {}, h("h1", {}, "共用庫"), h("div", { class: "sub" }, "所有書都能用的文風、章節結構與作者偏好"))),
        h("div", { class: "card" },
          h("p", {}, "共用庫是書庫裡的 ", h("code", {}, "_共用"), " 資料夾，跟著你的小說資料走，不在工作台的程式資料夾裡，所以不會被推上 GitHub。"),
          h("ul", { class: "muted small" },
            h("li", {}, "文風：可以重複使用、從範例文字統計出文字指標"),
            h("li", {}, "章節結構：起承轉合、壓抑爆發等節拍範本，寫章節和排章綱時參考"),
            h("li", {}, "共用作者偏好：跨書的長期偏好、常犯的毛病、禁用詞（禁用詞由程式檢查）")),
          h("p", { class: "muted small" }, "位置：", h("code", {}, o.dir)),
          initBtn));
      return;
    }

    let list = [];
    if (tab === "文風") {
      list = o.styles.map((s) => ({ file: s.file, name: s.name, desc: s.summary, lang: s.lang, badge: s.has_metrics ? "已統計 " + fmtNum(+s.sample) + " 字" : "" }));
    } else if (tab === "章節結構") {
      list = o.structures.map((s) => ({ file: s.file, name: s.name, desc: s.summary, badge: s.origin === "preset" ? "內建" : "我的", lang: s.lang, scope: s.scope, origin: s.origin }));
    } else {
      file = "作者偏好.md";
    }
    if (!file && list.length) file = list[0].file;
    const curItem = list.find((x) => x.file === file);
    const books = o.books;

    const headButtons = {
      "文風": [
        h("button", { id: "sh-ai-style" }, "✦ 請 AI 設計文風"),
        h("button", { class: "primary", id: "sh-new-style" }, "新增文風"),
      ],
      "章節結構": [h("button", { class: "primary", id: "sh-new-struct" }, "新增結構")],
      "共用作者偏好": [],
    };

    const docEl = h("div", { id: "doc" },
      file ? null : h("div", { class: "card empty" }, h("div", { class: "big" }, "✦"), "選左邊的項目查看。"));
    const actionsEl = h("div", { id: "sh-actions" });

    const tabsNode = h("div", { class: "tabs" },
      tabs.map((x) => h("button", {
        class: "tab" + (x === tab ? " active" : ""),
        onclick: () => FE.go(BASE + "?t=" + enc(x)),
      }, x, (x === "共用作者偏好" && o.prefs.active) ? [" ", h("span", { class: "badge b-ok" }, "生效中")] : null)));

    const listNode = h("div", { class: "list" },
      list.length
        ? list.map((e) => h("div", {
          class: "item" + (e.file === file ? " active" : ""),
          onclick: () => FE.go(BASE + "?t=" + enc(tab) + "&f=" + enc(e.file)),
        },
          h("div", { class: "row" },
            h("span", { class: "nm" }, e.name),
            h("span", { class: "grow" }),
            e.lang && e.lang !== "zh-TW" ? h("span", { class: "badge" }, e.lang === "en" ? "English" : "日本語") : null,
            e.badge ? h("span", { class: "badge" }, e.badge) : null),
          e.desc ? h("div", { class: "ds" }, e.desc) : null,
          e.scope ? h("div", { class: "ds" }, "適用：" + e.scope) : null))
        : h("div", { class: "muted" }, "還沒有" + tab + "。按右上角新增。"));

    ctx.view(
      h("div", { class: "page-head" },
        h("div", {}, h("h1", {}, "共用庫"),
          h("div", { class: "sub" }, "所有書都能用；放在書庫的 ", h("code", {}, "_共用"), " 資料夾，不會進 git")),
        h("div", { class: "row" }, headButtons[tab])),
      tabsNode,
      tab === "共用作者偏好"
        ? [
          h("div", { class: "alert info", style: "margin-bottom:12px" },
            h("span", { class: "k" }, "怎麼生效"),
            h("span", { class: "t" },
              "寫作、改稿、去 AI 味、審查時，Claude Code 和其他模型都會讀這份檔案（和各書的 設定/作者偏好.md 衝突時以書為準）。「禁用詞」一節由程式在「檢查用語與 AI 味」時逐字比對，目前有 ",
              h("b", {}, String(o.prefs.banned)),
              " 個。各書的 設定/作者偏好.md 也可以加「## 禁用詞」一節。")),
          docEl,
        ]
        : h("div", { class: "split" }, listNode, h("div", {}, actionsEl, docEl)));

    if (tab === "文風") {
      ctx.view; // no-op：節點已放好
      document.querySelector("#sh-ai-style").onclick = () => styleAiModal("design", books, null, signal);
      document.querySelector("#sh-new-style").onclick = () => {
        const nameInput = h("input", { type: "text", id: "ns-name", placeholder: "例如：冷調短句、古風權謀" });
        const langSel = h("select", { id: "ns-lang" },
          h("option", { value: "zh-TW" }, "繁體中文"),
          h("option", { value: "en" }, "English"),
          h("option", { value: "ja" }, "日本語"));
        const close = FE.modal({
          title: "新增文風",
          body: [
            h("label", { class: "f" }, h("span", {}, "名稱"), nameInput),
            h("label", { class: "f" }, h("span", {}, "文風語言"), langSel),
            h("div", { class: "muted small", style: "margin:-6px 0 10px" }, "從某本書的正文或設定建立時，自動用那本書的語言。"),
            h("div", { class: "f" }, h("span", {}, "從哪裡建立")),
            sampleSourceNodes(books, ["book", "text", "files", "copy_book", "blank"]),
          ],
          foot: (done) => [
            h("button", { class: "btn", type: "button", onclick: () => done(false) }, "取消"),
            h("button", {
              class: "btn btn-primary", type: "button", id: "ns-go",
              onclick: async () => {
                try {
                  const el = close.el;
                  const v = await sampleSourceValue(el);
                  v.name = nameInput.value.trim();
                  v.lang = langSel.value;
                  if (!v.name) return FE.toast("請輸入名稱", "err");
                  const r = await FE.api("/api/shared/styles", { method: "POST", body: v, signal });
                  close();
                  FE.toast("已建立文風「" + r.name + "」");
                  FE.go(BASE + "?t=" + enc("文風") + "&f=" + enc(r.file));
                } catch (e) { FE.fail(e); }
              },
            }, "建立"),
          ],
        });
        sampleSourceBind(close.el);
      };

      if (curItem) {
        const name = curItem.name;
        const applyBtn = h("button", { class: "primary sm", id: "st-apply" }, "套用到書…");
        const compareBtn = h("button", { class: "sm", id: "st-compare" }, "和某本書的正文比較");
        const restatBtn = h("button", { class: "sm", id: "st-restat" }, "重新統計文字指標");
        const aiRevBtn = h("button", { class: "sm", id: "st-ai-rev" }, "✦ 請 AI 調整");
        const aiTestBtn = h("button", { class: "sm", id: "st-ai-test" }, "✦ 試寫一段");
        const delBtn = h("button", { class: "sm danger", id: "st-del" }, "刪除");
        actionsEl.replaceChildren(actionRow([applyBtn, compareBtn, restatBtn, aiRevBtn, aiTestBtn, h("span", { class: "grow" }), delBtn]));

        aiRevBtn.onclick = () => styleAiModal("revise", books, name, signal);
        aiTestBtn.onclick = () => styleAiModal("test", books, name, signal);

        applyBtn.onclick = () => {
          const bookSel = h("select", { id: "ap-book" }, nodesFromHtml(bookOpts(books, S.book, curItem.lang)));
          const close = FE.modal({
            title: "把「" + name + "」套用到書",
            body: [
              h("p", { class: "muted small" }, "會複製成那本書的 ", h("code", {}, "設定/文風.md"), "。原本的文風檔會先備份到 ", h("code", {}, ".studio/備份"), "。之後在書裡修改不會影響共用庫。"),
              h("label", { class: "f" }, h("span", {}, "套用到"), bookSel),
            ],
            foot: (done) => [
              h("button", { class: "btn", type: "button", onclick: () => done(false) }, "取消"),
              h("button", {
                class: "btn btn-primary", type: "button", id: "ap-go",
                onclick: async () => {
                  try {
                    await FE.api("/api/shared/styles/" + enc(name) + "/apply", { method: "POST", body: { book: bookSel.value }, signal });
                    close();
                    FE.toast("已套用到《" + bookSel.value + "》");
                  } catch (e) { FE.fail(e); }
                },
              }, "套用"),
            ],
          });
        };

        compareBtn.onclick = () => {
          const bookSel = h("select", { id: "cp-book" }, nodesFromHtml(bookOpts(books, S.book, curItem.lang)));
          const fromInput = h("input", { type: "number", id: "cp-from", class: "num-in", placeholder: "全部" });
          const toInput = h("input", { type: "number", id: "cp-to", class: "num-in", placeholder: "全部" });
          const out = h("div", { id: "cp-out", style: "margin-top:12px" });
          FE.modal({
            title: "「" + name + "」和正文比較",
            body: [
              h("p", { class: "muted small" }, "在本機統計那本書的正文，和這個文風的文字指標並排比較。"),
              h("div", { class: "row" },
                bookSel,
                h("span", { class: "small muted" }, "章節"),
                fromInput,
                h("span", { class: "small muted" }, "到"),
                toInput,
                h("button", {
                  class: "primary sm", id: "cp-go",
                  onclick: async () => {
                    try {
                      const r = await FE.api("/api/shared/styles/" + enc(name) + "/compare", {
                        method: "POST",
                        body: { book: bookSel.value, from: parseInt(fromInput.value, 10) || null, to: parseInt(toInput.value, 10) || null },
                        signal,
                      });
                      out.replaceChildren(...[compareTableNode(r.rows),
                        h("div", { class: "muted small", style: "margin-top:8px" }, "正文高頻詞組：" + r.actual["高頻詞組"])]);
                    } catch (e) { FE.fail(e); }
                  },
                }, "比較")),
              out,
            ],
          });
        };

        restatBtn.onclick = () => {
          const close = FE.modal({
            title: "重新統計「" + name + "」的文字指標",
            body: [
              h("p", { class: "muted small" }, "只會更新「文字指標」一節，你寫的其他內容不動。"),
              sampleSourceNodes(books, ["book", "text", "files"]),
            ],
            foot: (done) => [
              h("button", { class: "btn", type: "button", onclick: () => done(false) }, "取消"),
              h("button", {
                class: "btn btn-primary", type: "button", id: "rs-go",
                onclick: async () => {
                  try {
                    await FE.api("/api/shared/styles/" + enc(name) + "/restat", { method: "POST", body: await sampleSourceValue(close.el), signal });
                    close();
                    FE.toast("已更新文字指標");
                    await FE.route();
                  } catch (e) { FE.fail(e); }
                },
              }, "統計"),
            ],
          });
          sampleSourceBind(close.el);
        };

        delBtn.onclick = async () => {
          if (!(await FE.confirm("刪除文風「" + name + "」？（會移到 _共用/.刪除，不會永久刪除）"))) return;
          try {
            await FE.api("/api/shared/styles/" + enc(name), { method: "DELETE", signal });
            FE.go(BASE + "?t=" + enc("文風"));
          } catch (e) { FE.fail(e); }
        };
      }
    }

    if (tab === "章節結構") {
      document.querySelector("#sh-new-struct").onclick = () => {
        const nameInput = h("input", { type: "text", id: "nt-name", placeholder: "例如：雙線交錯" });
        const close = FE.modal({
          title: "新增章節結構",
          body: [
            h("label", { class: "f" }, h("span", {}, "名稱"), nameInput),
            h("p", { class: "muted small" }, "會建立一份節拍表範本，之後直接編輯。也可以選左邊的內建結構，按「複製到我的結構」再修改。"),
          ],
          foot: (done) => [
            h("button", { class: "btn", type: "button", onclick: () => done(false) }, "取消"),
            h("button", {
              class: "btn btn-primary", type: "button", id: "nt-go",
              onclick: async () => {
                try {
                  const r = await FE.api("/api/shared/structures", {
                    method: "POST",
                    body: { name: nameInput.value.trim(), lang: (S.sharedLangs || {})[S.book] },
                    signal,
                  });
                  close();
                  FE.go(BASE + "?t=" + enc("章節結構") + "&f=" + enc("結構/" + r.name + ".md"));
                } catch (e) { FE.fail(e); }
              },
            }, "建立"),
          ],
        });
      };

      if (curItem) {
        const name = curItem.name, origin = curItem.origin;
        const applyBtn = h("button", { class: "primary sm", id: "sc-apply" }, "套用到書…");
        const copyBtn = origin === "preset" ? h("button", { class: "sm", id: "sc-copy" }, "複製到我的結構") : null;
        const delBtn = origin === "mine" ? h("button", { class: "sm danger", id: "sc-del" }, "刪除") : null;
        actionsEl.replaceChildren(actionRow([
          applyBtn,
          copyBtn,
          h("span", { class: "grow" }),
          delBtn || h("span", { class: "muted small" }, "內建結構不能直接修改"),
        ]));

        applyBtn.onclick = () => {
          const bookSel = h("select", { id: "sa-book" }, nodesFromHtml(bookOpts(books, S.book, curItem.lang)));
          const defBox = h("input", { type: "checkbox", id: "sa-def", checked: !(curItem.scope && curItem.scope.includes("卷")) });
          const close = FE.modal({
            title: "把「" + name + "」套用到書",
            body: [
              h("p", { class: "muted small" }, "會複製到那本書的 ", h("code", {}, "設定/章節結構/"), "。設為全書預設後，每章寫稿都會參考這個節拍；個別章節可以在章節頁改用別的結構。"),
              h("label", { class: "f" }, h("span", {}, "套用到"), bookSel),
              h("label", { class: "cb" }, defBox, " 設為全書預設"),
            ],
            foot: (done) => [
              h("button", { class: "btn", type: "button", onclick: () => done(false) }, "取消"),
              h("button", {
                class: "btn btn-primary", type: "button", id: "sa-go",
                onclick: async () => {
                  try {
                    await FE.api("/api/shared/structures/" + enc(name) + "/apply", {
                      method: "POST",
                      body: { book: bookSel.value, origin, default: defBox.checked },
                      signal,
                    });
                    close();
                    FE.toast("已套用到《" + bookSel.value + "》");
                  } catch (e) { FE.fail(e); }
                },
              }, "套用"),
            ],
          });
        };

        if (copyBtn) {
          copyBtn.onclick = () => {
            const input = h("input", { type: "text", value: name });
            FE.modal({
              title: "複製到我的結構",
              body: [h("label", { class: "f" }, h("span", {}, "新的名稱"), input)],
              foot: (done) => [
                h("button", { class: "btn", type: "button", onclick: () => done(false) }, "取消"),
                h("button", { class: "btn btn-primary", type: "button", onclick: () => done(input.value) }, "確定"),
              ],
            }).closed.then(async (nn) => {
              if (!nn) return;
              try {
                const r = await FE.api("/api/shared/structures", { method: "POST", body: { copy_preset: name, name: nn }, signal });
                FE.go(BASE + "?t=" + enc("章節結構") + "&f=" + enc("結構/" + r.name + ".md"));
              } catch (e) { FE.fail(e); }
            });
          };
        }
        if (delBtn) {
          delBtn.onclick = async () => {
            if (!(await FE.confirm("刪除結構「" + name + "」？（會移到 _共用/.刪除；已套用到書裡的複本不受影響）"))) return;
            try {
              await FE.api("/api/shared/structures/" + enc(name), { method: "DELETE", signal });
              FE.go(BASE + "?t=" + enc("章節結構"));
            } catch (e) { FE.fail(e); }
          };
        }
      }
    }

    if (file) await docView(docEl, file.startsWith("preset:") ? file : file, { base: "/api/shared", readonly: file.startsWith("preset:") });
  }

  nsPage("shared", "shared", {}, render);
})();
