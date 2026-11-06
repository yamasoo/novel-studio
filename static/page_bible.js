/* 設定集頁（轉移計畫 §8.2.15）：從 app.js 搬設定集整段（原 475-769）＋ renderBookStructures（原 985-1007）。
   搬進來的是只有設定集在用的：ROLE_ORDER／WORLD_CATS／entryFilterKey／loadEntryFilter／saveEntryFilter／entryMatches／
   countBy／entityFilterBar（→ entityFilterBarNode）／entityItemHtml（→ entityItemNode）／entityListHtml（→ entityListNode）／
   bindEntryFilter／BIBLE_FOLDER／dupGroupsFor／dupPanelHtml（→ dupPanelNode）／bindDupPanel／rebuildBibleIndex／
   bibleGenDialog／bibleGenPick／bibleOneDialog／viewBible／renderBookStructures。
   留在 app.js：renderChapterStructure（單章頁在用）、renderCard（視覺卡，依賴 illCfg／illProvOptions／tagAppend／waitJob）、
   renderIllust、docView（ns_doc.js）、readFiles／bookOpts。
   字串型的 entityItemHtml／entityListHtml／dupPanelHtml 全部改成節點版，沒有留字串版。 */
(function () {
  "use strict";

  const { h } = FE;
  const { statusBadgeNode } = nsShared;
  const enc = encodeURIComponent;

  const ROLE_ORDER = ["主角", "主要配角", "配角", "反派", "路人"];
  const WORLD_CATS = ["力量體系", "地理與氣候", "歷史與年表", "社會與政治", "經濟與物資", "宗教信仰", "文化與風俗", "科技原理", "載具與兵器", "生態與資源", "其他"];
  const BIBLE_FOLDER = { "角色": "角色", "勢力": "勢力", "世界觀": "世界觀" };
  const ENT_TABS = ["角色", "勢力", "世界觀"];

  const entryFilterKey = (book, t) => "studio.entityFilter." + book + "." + t;
  function loadEntryFilter(book, t) {
    try { return JSON.parse(localStorage.getItem(entryFilterKey(book, t)) || "null") || {}; } catch (e) { return {}; }
  }
  function saveEntryFilter(book, t, f) {
    try { localStorage.setItem(entryFilterKey(book, t), JSON.stringify(f)); } catch (e) { /* 無痕模式等情況：略過 */ }
  }
  function entryMatches(e, f, t) {
    const q = (f.q || "").trim().toLowerCase();
    if (q && ![e.name, ...(e.aliases || []), e.summary || ""].join(" ").toLowerCase().includes(q)) return false;
    if (t === "角色" && f.role && f.role !== "全部" && (e.role || "未設定") !== f.role) return false;
    if (t === "世界觀" && f.cat && f.cat !== "全部" && (e.category || "未分類") !== f.cat) return false;
    if (f.status && f.status !== "全部" && (e.status || "未設定") !== f.status) return false;
    if (f.tag && f.tag !== "全部" && !(e.tags || []).includes(f.tag)) return false;
    return true;
  }
  function countBy(list, fn) {
    return list.reduce((m, e) => { const k = fn(e); m[k] = (m[k] || 0) + 1; return m; }, {});
  }

  let pickSet = new Set();   // 批次移入分類：目前勾選的世界觀檔（換頁時清空）
  let pickKey = "";

  function selNode(key, label, opts, cur) {
    return h("label", { class: "ef" },
      h("span", {}, label),
      h("select", { "data-ef": key }, opts.map(([v, txt, n]) =>
        h("option", { value: v, selected: (cur || "全部") === v }, txt + "（" + n + "）"))));
  }

  function entityFilterBarNode(t, list, f) {
    const withAll = (arr) => [["全部", "全部", list.length], ...arr];
    const out = [];
    if (t === "角色") {
      const c = countBy(list, (e) => e.role || "未設定");
      out.push(selNode("role", "定位", withAll([...ROLE_ORDER, "未設定"].filter((k) => c[k]).map((k) => [k, k, c[k]])), f.role));
    }
    if (t === "世界觀") {
      const c = countBy(list, (e) => e.category || "未分類");
      const extra = Object.keys(c).filter((k) => !WORLD_CATS.includes(k) && k !== "未分類");
      const keys = [...WORLD_CATS, ...extra, "未分類"].filter((k) => WORLD_CATS.includes(k) || c[k]);
      out.push(selNode("cat", "分類", withAll(keys.map((k) => [k, k, c[k] || 0])), f.cat));
    }
    const sc = countBy(list, (e) => e.status || "未設定");
    const statusOpts = ["正式", "草稿", "未設定"].filter((k) => sc[k]);
    // 已存的篩選值若已不存在（例如草稿全部轉正式後仍選「草稿」），退回「全部」，避免列表永遠是空的
    if (f.status && f.status !== "全部" && !sc[f.status]) f.status = "全部";
    if (statusOpts.length) out.push(selNode("status", "狀態", withAll(statusOpts.map((k) => [k, k, sc[k]])), f.status));
    const tc = {};
    list.forEach((e) => (e.tags || []).forEach((x) => { tc[x] = (tc[x] || 0) + 1; }));
    const tagKeys = Object.keys(tc).sort((a, b) => tc[b] - tc[a] || a.localeCompare(b));
    if (tagKeys.length) out.push(selNode("tag", "標籤", withAll(tagKeys.map((k) => [k, k, tc[k]])), f.tag));
    const grouping = t !== "勢力"
      ? h("label", { class: "ef ef-cb" },
        h("input", { type: "checkbox", "data-ef": "group", checked: !!f.group }), " 分組顯示")
      : null;
    return h("div", { class: "ef-bar" },
      h("label", { class: "ef" },
        h("span", {}, "搜尋"),
        h("input", { type: "search", "data-ef": "q", placeholder: "名稱、別名、一句話", value: f.q || "" })),
      out,
      grouping);
  }

  function entityItemNode(t, e, file, pick) {
    // 勾選框獨立成一格（點得到就勾選），整列仍然是「看內容」
    const cb = pick
      ? h("label", {
        class: "pick-cell",
        onclick: (ev) => ev.stopPropagation(),
      }, h("input", {
        type: "checkbox", class: "pick", "data-pick": e.file, checked: pickSet.has(e.file),
        onchange: (ev) => { ev.target.checked ? pickSet.add(e.file) : pickSet.delete(e.file); },
      }))
      : null;
    const badge = t === "世界觀" ? (e.category || "未分類") : (e.role || "");
    const tagLine = (e.tags || []).length ? h("div", { class: "ds" }, e.tags.join("、")) : null;
    return h("div", {
      class: "item" + (e.file === file ? " active" : ""),
      "data-file": e.file,
      onclick: () => FE.go("#/b/" + enc(S.book) + "/bible?t=" + enc(t) + "&f=" + enc(e.file)),
    },
      h("div", { class: "row" },
        cb,
        h("span", { class: "nm" }, e.name),
        h("span", { class: "grow" }),
        badge ? h("span", { class: "badge" }, badge) : null,
        e.status === "草稿" ? statusBadgeNode("草稿") : null),
      tagLine,
      e.summary ? h("div", { class: "ds" }, e.summary) : null);
  }

  // 批次工具列的按鈕（每次重畫都重建，事件直接綁在節點上）
  function bulkBar(t, refresh) {
    const apply = async (kind) => {
      const files = [...pickSet];
      if (!files.length) { FE.toast("請先勾選要處理的項目。", "err"); return; }
      const toSel = document.querySelector("#ef-to");
      const body = kind === "promote" ? { files, status: "正式" } : { files, category: toSel ? toSel.value : "" };
      if (kind === "promote" && !(await FE.confirm("把 " + files.length + " 項轉為正式？"))) return;
      try {
        await FE.api(B("/bible/category"), { method: "POST", body });
        pickSet = new Set();
        FE.toast(kind === "promote" ? "已轉為正式 " + files.length + " 項" : "已移入 " + files.length + " 項");
        refresh();
      } catch (e) { FE.toast((e && e.message) || String(e), "err"); }
    };
    const catSel = t === "世界觀"
      ? [h("select", { id: "ef-to" }, WORLD_CATS.map((c) => h("option", { value: c }, c))),
        h("button", { id: "ef-apply", onclick: () => apply("category") }, "移入分類")]
      : null;
    return h("div", { class: "ef-bulk" },
      h("span", { id: "ef-n" }, "已選 " + pickSet.size + " 項"),
      catSel,
      h("button", {
        id: "ef-all",
        onclick: (ev) => {
          const box = ev.target.closest(".list");
          box.querySelectorAll("input[data-pick]").forEach((cb) => { cb.checked = true; pickSet.add(cb.dataset.pick); });
          document.querySelector("#ef-n").textContent = "已選 " + pickSet.size + " 項";
        },
      }, "全選"),
      h("button", {
        id: "ef-clear",
        onclick: (ev) => {
          const box = ev.target.closest(".list");
          box.querySelectorAll("input[data-pick]").forEach((cb) => { cb.checked = false; pickSet.delete(cb.dataset.pick); });
          document.querySelector("#ef-n").textContent = "已選 " + pickSet.size + " 項";
        },
      }, "清除"),
      h("button", { class: "primary", id: "ef-promote", onclick: () => apply("promote") }, "轉為正式"));
  }

  function entityListNode(t, list, f, file, refresh) {
    const shown = list.filter((e) => entryMatches(e, f, t));
    const pick = ENT_TABS.includes(t);
    const head = [h("div", { class: "muted small ef-count" }, "顯示 " + shown.length + " / " + list.length)];
    if (pick) head.push(bulkBar(t, refresh));
    if (!list.length) return h("div", {}, head, h("div", { class: "muted" }, "這裡還是空的。"));
    if (!shown.length) return h("div", {}, head, h("div", { class: "muted" }, "沒有符合條件的項目。"));
    if (f.group && t !== "勢力") {
      const keyOf = (e) => (t === "角色" ? (e.role || "未設定") : (e.category || "未分類"));
      const order = t === "角色" ? [...ROLE_ORDER, "未設定"] : [...WORLD_CATS, "未分類"];
      const groups = {};
      shown.forEach((e) => { const k = keyOf(e); (groups[k] = groups[k] || []).push(e); });
      const keys = [...order.filter((k) => groups[k]), ...Object.keys(groups).filter((k) => !order.includes(k))];
      return h("div", {}, head, keys.map((k) => h("details", { class: "grp", open: true },
        h("summary", {}, k, " ", h("span", { class: "muted small" }, String(groups[k].length))),
        groups[k].map((e) => entityItemNode(t, e, file, pick)))));
    }
    return h("div", {}, head, shown.map((e) => entityItemNode(t, e, file, pick)));
  }

  function bindEntryFilter(root, entList, t, list, file, f) {
    const paint = () => {
      entList.replaceChildren(entityListNode(t, list, f, file, () => FE.route()));
      saveEntryFilter(S.book, t, f);
    };
    paint();
    root.querySelectorAll("[data-ef]").forEach((el) => {
      const key = el.dataset.ef;
      el.addEventListener(el.type === "search" ? "input" : "change", () => {
        f[key] = el.type === "checkbox" ? el.checked : el.value;
        paint();
      });
    });
  }

  // ── 設定索引：疑似重複勾選合併 ──
  function dupGroupsFor(t, idx) {
    const prefix = "設定/" + BIBLE_FOLDER[t] + "/";
    const out = [];
    (idx.duplicates || []).forEach((g) => {
      const byFile = {};
      g.members.filter((m) => m.source === "設定檔" && m.file.startsWith(prefix)).forEach((m) => {
        (byFile[m.file] = byFile[m.file] || { file: m.file, names: new Set() }).names.add(m.name);
      });
      const files = Object.values(byFile).map((x) => ({ file: x.file, names: [...x.names] }));
      if (files.length < 2) return;
      const known = new Set(files.flatMap((x) => x.names));
      const ghosts = [...new Set(g.members.filter((m) => m.source === "名詞表" && !known.has(m.name)).map((m) => m.name))];
      const keepDefault = files.some((x) => x.file === g.suggest) ? g.suggest : files[0].file;
      out.push({ key: g.key, files, ghosts, keepDefault, loose: !!g.loose });
    });
    return out;
  }

  function dupPanelNode(t, idx, file) {
    const groups = dupGroupsFor(t, idx);
    if (!groups.length) return null;
    const mergeBtn = h("button", {
      class: "primary", id: "dup-merge-btn",
      onclick: async (ev) => {
        const box = ev.target.closest("#dup-box");
        const jobs = [];
        dupGroupsFor(t, idx).forEach((g, gi) => {
          const keep = box.querySelector('input[name="keep-' + gi + '"]:checked');
          if (!keep) return;
          const dups = [...box.querySelectorAll('input.dup-cb[data-gi="' + gi + '"]:checked')].map((c) => c.value).filter((v) => v !== keep.value);
          if (dups.length) jobs.push({ canonical: keep.value, duplicates: dups });
        });
        if (!jobs.length) { FE.toast("請先選擇保留的檔案，並勾選要併入的項目。", "err"); return; }
        const total = jobs.reduce((n, j) => n + j.duplicates.length, 0);
        if (!(await FE.confirm("要併入 " + total + " 個設定檔（" + jobs.length + " 組）嗎？舊檔會移到「設定/_已合併」，不會刪除。"))) return;
        try {
          for (const j of jobs) {
            await FE.api(B("/bible/merge"), { method: "POST", body: j });
          }
          FE.toast("已併入 " + total + " 個設定檔");
          FE.go("#/b/" + enc(S.book) + "/bible?t=" + enc(t) + "&f=" + enc(jobs[0].canonical));
        } catch (e) {
          FE.toast((e && e.message) || String(e), "err");
          FE.go("#/b/" + enc(S.book) + "/bible?t=" + enc(t) + "&f=" + enc(file));
        }
      },
    }, "合併勾選的項目");

    return h("div", { class: "card", id: "dup-box", style: "margin-bottom:12px" },
      h("div", { class: "row" }, h("b", {}, "疑似重複（" + groups.length + " 組）")),
      h("div", { class: "muted small", style: "margin:4px 0 8px" },
        "選一份「保留」，勾選要「併入」的。被併入的內容會接在保留檔後面（標示待核對），舊檔移到 設定/_已合併，不會刪除。名稱會加進保留檔的別名。"),
      groups.map((g, gi) => h("div", { class: "dup-group", style: "border-top:1px solid var(--line,#ddd);padding:6px 0" },
        h("div", { class: "small muted" },
          g.key,
          g.loose ? h("span", { class: "badge" }, "近似，請確認是不是同一個地方") : null),
        g.files.map((f) => h("div", { class: "row", style: "gap:10px;align-items:center;flex-wrap:wrap" },
          h("label", { class: "small" },
            h("input", { type: "radio", name: "keep-" + gi, value: f.file, checked: f.file === g.keepDefault }),
            " 保留"),
          h("label", { class: "small" },
            h("input", { type: "checkbox", class: "dup-cb", "data-gi": String(gi), value: f.file }),
            " 併入"),
          h("span", { class: "nm" }, f.names.join("、")),
          h("span", { class: "muted small" }, f.file.split("/").pop()))),
        g.ghosts.length
          ? h("div", { class: "muted small" }, "名詞表另有：" + g.ghosts.join("、") + "（只在名詞表出現，合併不會改動它）")
          : null)),
      h("div", { class: "row", style: "margin-top:8px" }, mergeBtn));
  }

  async function rebuildBibleIndex() {
    try {
      const r = await FE.api(B("/bible/index/rebuild"), { method: "POST" });
      FE.toast("已重建設定索引：設定檔 " + r.counts.settings + " 筆，名詞表 " + r.counts.glossary + " 筆。");
    } catch (e) { FE.toast((e && e.message) || String(e), "err"); }
  }

  function bibleGenDialog() {
    const opt = (id, title, desc) => h("div", { class: "row", style: "align-items:flex-start;gap:12px;margin:12px 0" },
      h("div", {}, h("b", {}, FE.t(title)), h("div", { class: "muted small" }, FE.t(desc))),
      h("span", { class: "grow" }),
      h("button", { class: "primary", "data-pick": id, onclick: () => bibleGenPick(id) }, FE.t("選這個")));
    const close = FE.modal({
      title: FE.t("生成設定"),
      body: [
        h("p", { class: "muted small" }, FE.t("先看你手上已經有什麼；選錯也可以再回來。")),
        opt("outline", "我已經有大綱或卷綱", "依大綱長角色、勢力、世界觀（可填參考方向與網址）"),
        opt("free", "我只有一句話或關鍵字", "自由描述要生成什麼，適合補配角或單一設定"),
        opt("intake", "我剛討論完，有一段文字", "貼對話或筆記；已定案進正式、討論中進草稿"),
        opt("one", "我只缺一個角色／勢力／世界觀", "單項補完"),
      ],
      foot: (done) => [h("button", { class: "btn", type: "button", onclick: () => done(false) }, FE.t("取消"))],
    });
    return close;
  }

  function bibleGenPick(k) {
    FE.modal.close_all();
    if (k === "outline") Panel.openForm("bible_from_outline");
    else if (k === "free") Panel.openForm("gen_drafts");
    else if (k === "intake") Panel.openForm("intake");
    else bibleOneDialog();
  }

  function bibleOneDialog() {
    const one = (v, label) => h("button", { "data-one": v }, FE.t(label));
    FE.modal({
      title: FE.t("補一個設定"),
      body: [
        h("p", { class: "muted small" }, FE.t("只補一個項目時用；完成後會進草稿或正式，視內容而定。")),
        h("div", { class: "row" },
          h("button", {
            class: "primary", "data-one": "role",
            onclick: () => { FE.modal.close_all(); Panel.openForm("character"); },
          }, FE.t("角色")),
          h("button", {
            "data-one": "faction",
            onclick: () => { FE.modal.close_all(); Panel.openForm("free", { text: "請使用 novel-bible skill 建立一個新勢力：" }); },
          }, FE.t("勢力")),
          h("button", {
            "data-one": "world",
            onclick: () => { FE.modal.close_all(); Panel.openForm("free", { text: "請使用 novel-bible skill 設計世界觀：" }); },
          }, FE.t("世界觀")),
          h("span", { class: "grow" })),
      ],
      foot: (done) => [h("button", { class: "btn", type: "button", onclick: () => done(false) }, FE.t("取消"))],
    });
  }

  // ── 本書章節結構（設定集「章節結構」分頁）──
  async function renderBookStructures(el, file, signal) {
    const r = await FE.api(B("/structures"), { signal });
    const list = r.list;
    if (!file && list.length) file = list[0].file;
    const cur = list.find((x) => x.file === file);
    const docEl = h("div", { id: "doc" });
    const actions = h("div", { id: "bs-actions" });

    el.replaceChildren(h("div", { class: "split" },
      h("div", { class: "list" }, list.length
        ? list.map((s) => h("div", {
          class: "item" + (s.file === file ? " active" : ""),
          onclick: () => FE.go("#/b/" + enc(S.book) + "/bible?t=" + enc("章節結構") + "&f=" + enc(s.file)),
        },
          h("div", { class: "row" },
            h("span", { class: "nm" }, s.name),
            h("span", { class: "grow" }),
            s.default ? h("span", { class: "badge b-ok" }, "全書預設") : null),
          s.summary ? h("div", { class: "ds" }, s.summary) : null))
        : h("div", { class: "muted" },
          "這本書還沒有章節結構。",
          h("br"),
          h("a", { href: "#/shared?t=" + enc("章節結構") }, "到共用庫套用一個 →"))),
      h("div", {}, actions,
        file ? docEl : h("div", { class: "card empty" },
          h("div", { class: "big" }, "✦"),
          "章節結構是寫章節時參考的節拍表。",
          h("br"),
          "到共用庫選一個套用到這本書。"))));

    if (!cur) return;
    const set = async (name) => {
      try {
        await FE.api(B("/structures/default"), { method: "POST", body: { name }, signal });
        FE.route();
      } catch (e) { FE.fail(e); }
    };
    actions.replaceChildren(h("div", { class: "row", style: "margin-bottom:10px" },
      cur.default
        ? h("button", { class: "sm", id: "bs-undef", onclick: () => set(null) }, "取消全書預設")
        : h("button", { class: "sm primary", id: "bs-def", onclick: () => set(cur.name) }, "設為全書預設"),
      h("span", { class: "muted small" }, "個別章節要用別的結構，到該章的「章綱」分頁選。")));
    await docView(docEl, cur.file);
  }

  async function render(ctx) {
    const signal = ctx.signal;
    const t0 = ctx.query.t;
    let file = ctx.query.f || "";
    if (pickKey !== S.book + "|" + t0) { pickSet = new Set(); pickKey = S.book + "|" + t0; }
    const b = await FE.api(B("/bible"), { signal });
    const t = t0 || "角色";
    const tabs = ["角色", "勢力", "世界觀", "核心", "章節結構", "草稿"];
    const list = b[t] || [];
    if (!file && list.length) file = list[0].file;
    const isEnt = ENT_TABS.includes(t);
    const canDel = !!file && (isEnt || t === "草稿");
    const filt = isEnt ? loadEntryFilter(S.book, t) : {};

    const btns = [];
    if (t === "核心") btns.push(h("button", { onclick: () => FE.go("#/shared?t=" + enc("文風")) }, "共用文風庫"));
    if (t === "核心") btns.push([
      h("button", { onclick: () => Panel.openForm("style") }, "分析／調整文風"),
      h("button", { onclick: () => Panel.openForm("preference") }, "記錄偏好"),
    ]);
    if (t === "草稿") btns.push(h("button", { class: "primary", onclick: () => Panel.openForm("promote_drafts") }, "草稿轉正式"));
    if (t === "章節結構") btns.push(h("button", { onclick: () => FE.go("#/shared?t=" + enc("章節結構")) }, "到共用庫選結構"));
    if (canDel) btns.push(h("button", { class: "danger", id: "bible-del" }, FE.t("刪除這份")));
    if (isEnt) btns.push(h("button", { onclick: () => rebuildBibleIndex(), title: "重新產生 設定/_索引.md，給 novel-bible 先讀" }, "重建索引"));
    btns.push(h("button", { class: "primary", onclick: () => bibleGenDialog() }, "生成設定"));
    btns.push(h("button", {
      onclick: () => FE.go("#/b/" + enc(S.book) + "/reverse"),
      title: "從正文反推設定；核對、採用草稿",
    }, "從正文建立設定"));

    const tabsNode = h("div", { class: "tabs" }, tabs.map((x) => h("button", {
      class: "tab" + (x === t ? " active" : ""),
      onclick: () => FE.go("#/b/" + enc(S.book) + "/bible?t=" + enc(x)),
    }, x, (b[x] && b[x].length) ? [" ", h("span", { class: "badge" }, String(b[x].length))] : null)));

    const head = h("div", { class: "page-head" },
      h("div", {},
        h("h1", {}, "設定集"),
        h("div", { class: "sub" }, "靜態設定。角色目前的位置、傷勢、知道什麼，在「伏筆與時間線」頁。")),
      h("div", { class: "row" }, btns));

    if (t === "章節結構") {
      const bsBox = h("div", { id: "bs-box" });
      ctx.view(head, tabsNode, bsBox);
      await renderBookStructures(bsBox, file, signal);
      return;
    }

    const idx = isEnt ? await FE.api(B("/bible/index"), { signal }).catch(() => null) : null;
    const dup = idx ? dupPanelNode(t, idx, file) : null;
    const docEl = h("div", { id: "doc" },
      file ? null : h("div", { class: "card empty" }, h("div", { class: "big" }, "✦"), "選左邊的項目查看。"));
    const entCard = h("div", { id: "ent-card", style: "margin-top:14px" });
    const entIll = h("div", { id: "ent-ill", style: "margin-top:14px" });

    let listNode, entList = null;
    if (isEnt) {
      entList = h("div", { id: "ent-list" });
      listNode = [entityFilterBarNode(t, list, filt), entList];
    } else {
      listNode = list.length
        ? list.map((e) => h("div", {
          class: "item" + (e.file === file ? " active" : ""),
          onclick: () => FE.go("#/b/" + enc(S.book) + "/bible?t=" + enc(t) + "&f=" + enc(e.file)),
        },
          h("div", { class: "row" },
            h("span", { class: "nm" }, e.name),
            h("span", { class: "grow" }),
            e.role ? h("span", { class: "badge" }, e.role) : null,
            e.status === "草稿" ? statusBadgeNode("草稿") : null),
          e.summary ? h("div", { class: "ds" }, e.summary) : null))
        : h("div", { class: "muted" }, "這裡還是空的。");
    }

    const splitNode = h("div", { class: "split" },
      h("div", { class: "list" }, dup, listNode),
      h("div", {}, docEl, entCard, entIll));
    ctx.view(head, tabsNode, splitNode);

    if (canDel) {
      document.querySelector("#bible-del").onclick = async () => {
        const ent = list.find((e) => e.file === file) || {};
        const nm = ent.name || file;
        if (!(await FE.confirm("刪除「" + nm + "」？" + String.fromCharCode(10) + "會移到 .studio/刪除，不會永久刪除；引用到它的地方（關係、伏筆、索引）可能失效。"))) return;
        try {
          const r = await FE.api(B("/bible/delete"), { method: "POST", body: { path: file }, signal });
          FE.toast(r.warning || "已移到 .studio/刪除", r.warning ? "err" : undefined);
          FE.go("#/b/" + enc(S.book) + "/bible?t=" + enc(t));
        } catch (e) { FE.fail(e); }
      };
    }
    if (isEnt) bindEntryFilter(splitNode, entList, t, list, file, filt);
    if (file) await docView(docEl, file, { signal });
    if (file && ENT_TABS.includes(t)) {
      try {
        const f = await FE.api(B("/file?path=" + enc(file)), { signal });
        await renderCard(entCard, file, f.text);
        await renderIllust(entIll, "entity:" + file, { entityText: f.text });
      } catch (e) { /* ignore */ }
    }
  }

  nsPage("b/:book/bible", "bible", { book: true }, render);
})();
