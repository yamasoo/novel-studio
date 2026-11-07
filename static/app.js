/* 小說工作台 前端 */
"use strict";

const S = {
  config: null, claudeFound: null, actions: [], books: [],
  book: null,                 // 目前的書 id
  bookLang: null,             // 目前這本書的語言（zh-TW／en／ja）；書的內容用它標 lang，字形才對
  job: null,                  // 面板目前顯示的任務 {id, status, session_id}
  routeName: "",
};

/* ------------------------------------------------------------------ 工具 */
const $ = (sel, el = document) => el.querySelector(sel);
const enc = encodeURIComponent;
const fmtNum = (n) => (n || 0).toLocaleString({ en: "en-US", ja: "ja-JP" }[window.FE && FE.i18n && FE.i18n.lang] || "zh-TW");
// 字數單位：中文、日文書算「字」（chars），英文書算「詞」（words）；後端回傳 unit，這裡決定顯示哪個字
const unitCh = (unit) => (unit === "words" ? "詞" : "字");   // i18n-skip
const unitOfLang = (lang) => (lang === "en" ? "words" : "chars");
const unitOfBook = (id) => { const b = (S.books || []).find((x) => x.id === (id || S.book)); return (b && b.unit) || "chars"; };
// 書的語言：顯示書內容的容器加 lang（日文書在中文介面下用日文字形，中文書在日文介面下用繁中字形）。介面本身的 <html lang> 仍跟著介面語言
const bookLang = () => S.bookLang || ((S.books || []).find((x) => x.id === S.book) || {}).lang || "zh-TW";
function fmtTime(t) {
  if (!t) return "";
  const d = new Date(t * 1000), now = new Date();
  const hm = d.toTimeString().slice(0, 5);
  return d.toDateString() === now.toDateString() ? "今天 " + hm : `${d.getMonth() + 1}/${d.getDate()} ${hm}`;
}
function go(h) { return FE.go(h); }
window.go = go;

// 轉接：舊呼叫端 api(method, url, body) 不動，實際走 FE.api（自動帶 X-FE-Token、讀 detail）
async function api(method, url, body) {
  const opts = { method: String(method || "GET").toUpperCase() };
  if (body !== undefined) opts.body = body;
  return FE.api(url, opts);
}
const B = (path) => `/api/books/${enc(S.book)}${path}`;

// 薄別名：舊呼叫端到處都是 fail(e)／toast(msg, true)，實際走 fekit 的 FE.fail／FE.toast。
// FE.fail 會吞 AbortError，換頁中止的請求不會再跳錯誤。
function fail(e) { FE.fail(e); }
function toast(msg, err) { FE.toast(msg, err ? "err" : undefined); }

function splitFM(text) {
  if (!text.startsWith("---")) return [{}, text];
  const lines = text.split("\n");
  for (let i = 1; i < lines.length; i++) {
    if (lines[i].trim() === "---") {
      const fm = {};
      lines.slice(1, i).forEach((l) => { const m = l.match(/^([^:#\s][^:]*):\s*(.*)$/); if (m) fm[m[1].trim()] = m[2].replace(/\s+#.*$/, "").trim(); });
      return [fm, lines.slice(i + 1).join("\n")];
    }
  }
  return [{}, text];
}
/* ------------------------------------------------------------------ 路由 */
function refresh() { return FE.route(); }

async function setBook(id, keep) {
  if (id === S.book) return;
  if (!id && keep) { S.book = null; Panel.renderActions(); return; }
  S.book = id;
  S.bookLang = ((S.books || []).find((x) => x.id === id) || {}).lang || null;
  Panel.renderActions();
  // page_overview 是在 handler 內才 setBook，nsPage 的 renderNav 已經先跑過；直接開 #/b/<書> 時要補畫本書項目
  if (FE.shell.current()) renderNav();
  if (!id) return;
  // 若這本書有執行中的任務，接上（轉移計畫 §7.4：交給 Panel.resume 查 /api/fe，不再用舊的 B("/jobs")）
  if (Panel.resume) Panel.resume().catch(() => {});
}

// 導覽列本身由 shell 依 navItems() 重畫；這裡只更新左欄上方那兩塊（切換書、前文搜尋）。
function renderNav() {
  const shell = FE.shell.current();
  if (!shell) return;
  const sw = document.querySelector("#book-switch");
  if (sw) {
    const books = S.books.filter((b) => b.is_book || b.id === S.book);
    const opts = S.book ? [] : [FE.h("option", { value: "" }, "選擇一本書…")];
    for (const b of books) opts.push(FE.h("option", { value: b.id, selected: b.id === S.book }, b.name));
    sw.replaceChildren(...opts);
    sw.value = S.book || "";
    sw.onchange = (ev) => go("#/b/" + enc(ev.target.value));
  }
  // 沒有書就整塊藏起來；正在搜尋時把查詢字填回去
  const q = document.querySelector("#side-q");
  if (q) {
    const form = q.closest("form");
    if (form) form.hidden = !S.book;
    const ctx = FE.current();
    q.value = ctx && ctx.page === "b/:book/search" ? ((ctx.query || {}).q || "") : "";
  }
  shell.refresh_nav();
}

/* ------------------------------------------------------------------ 前文搜尋（本機，不用模型） */
window.sideSearch = (q) => { q = (q || "").trim(); if (q) go(`#/b/${enc(S.book)}/search?q=${enc(q)}`); };
document.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && (e.key === "k" || e.key === "K") && S.book) {
    e.preventDefault(); const i = $("#search-q") || $("#side-q"); if (i) { i.focus(); i.select(); }
  }
});

/* 在畫面裡標亮搜尋詞並捲到第一處（等內容載入，最多 3 秒） */
async function highlightTerms(root, terms) {
  terms = (terms || []).filter(Boolean);
  if (!terms.length) return;
  for (let i = 0; i < 30; i++) {
    const md = root.querySelector(".md");
    if (md && md.textContent.trim()) break;
    await new Promise((r) => setTimeout(r, 100));
  }
  const esc2 = (t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const re = new RegExp(terms.map(esc2).join("|"), "g");
  let first = null, n = 0;
  root.querySelectorAll(".md").forEach((md) => {
    const walker = document.createTreeWalker(md, NodeFilter.SHOW_TEXT);
    const nodes = []; while (walker.nextNode()) nodes.push(walker.currentNode);
    for (const node of nodes) {
      if (n > 300) return;
      const t = node.nodeValue; re.lastIndex = 0;
      if (!re.test(t)) continue;
      re.lastIndex = 0;
      const frag = document.createDocumentFragment(); let pos = 0, m;
      while ((m = re.exec(t))) {
        frag.appendChild(document.createTextNode(t.slice(pos, m.index)));
        const mk = document.createElement("mark"); mk.textContent = m[0]; frag.appendChild(mk);
        if (!first) first = mk; n++; pos = m.index + m[0].length;
      }
      frag.appendChild(document.createTextNode(t.slice(pos)));
      node.parentNode.replaceChild(frag, node);
    }
  });
  if (first) first.scrollIntoView({ block: "center" });
  else toast("這裡沒有找到完全相同的字（可能是繁簡不同）");
}

window.initFolder = async (id) => {
  go("#/b/" + enc(id));
  setTimeout(() => Panel.openForm("setup_new"), 300);
};

window.setBookLang = async (v) => {
  try {
    await api("POST", B("/lang"), { lang: v }); S.bookLang = v; toast("已改成 " + ({ "zh-TW": "繁體中文", en: "English", ja: "日本語" })[v]);
    S.books = (await api("GET", "/api/books")).books;      // 字數單位跟著語言換（字／詞）
    refresh();
  }
  catch (e) { fail(e); refresh(); }
};

/* ------------------------------------------------------------------ 恢復稿 */
window.recoverTo = async (id) => {
  try { const r = await api("POST", B(`/recoveries/${id}/candidate`)); toast("已存成候選稿"); go(`#/b/${enc(S.book)}/ch/${r.chapter}?tab=candidate`); } catch (e) { fail(e); }
};
window.recoverDiscard = async (id) => {
  if (!confirm("捨棄這份恢復稿？（會移到 .studio/備份）")) return;
  try { await api("POST", B(`/recoveries/${id}/discard`)); toast("已捨棄"); refresh(); } catch (e) { fail(e); }
};
window.recoverView = async (id) => {
  try {
    const r = await api("GET", B(`/recoveries/${id}`));
    const textArea = FE.h("textarea", { class: "editor prose", lang: bookLang(), style: "min-height:50vh", readonly: true });
    textArea.value = r.text;
    const copyBtn = FE.h("button", {}, "複製");
    const closeBtn = FE.h("button", {}, "關閉");
    const close = FE.modal({
      title: "恢復稿",
      body: [
        FE.h("div", { class: "muted small", style: "margin-bottom:8px" },
          `${r.label}　·　${r.reason}　·　${fmtNum(r.chars)} ${unitCh(unitOfBook())}`),
        textArea,
        FE.h("div", { class: "row", style: "margin-top:10px" }, FE.h("span", { class: "grow" }), copyBtn, closeBtn),
      ],
    });
    copyBtn.onclick = () => { navigator.clipboard.writeText(r.text).then(() => toast("已複製")); };
    closeBtn.onclick = () => close();
  } catch (e) { fail(e); }
};

window.openCharState = (file) => docView($("#doc"), file);


/* ------------------------------------------------------------------ 共用庫 */
const readFiles = (input) => Promise.all([...input.files].map((f) => new Promise((res, rej) => {
  const r = new FileReader();
  r.onload = () => res({ name: f.name, data: String(r.result).split(",")[1] || "" });
  r.onerror = () => rej(new Error("讀取 " + f.name + " 失敗"));
  r.readAsDataURL(f);
})));
// lang 有值時（套用共用文風、結構）：同語言的書排前面，語言不同的標「（語言不同）」，不擋，讓作者自己決定
function bookOptions(books, cur, lang) {
  const langs = S.sharedLangs || {};
  const diff = (b) => !!lang && !!langs[b] && langs[b] !== lang;
  const list = lang ? [...books.filter((b) => !diff(b)), ...books.filter(diff)] : books;
  return list.map((b) => FE.h("option", { value: b, selected: b === cur }, diff(b) ? `${b}（語言不同）` : b));
}


// 整章自動流程的步驟與面板動作的對應；面板按鈕也預設用該步驟分配的執行者
const STEP_OF_ACTION = { chapter_cards: "card", write: "write", goal_check: "goal", deslop: "deslop", review_notes: "review", revise_notes: "revise", accept: "accept" };
const AI_STEP_LABELS = [["card", "章綱"], ["write", "寫章節（候選稿）"], ["goal", "章綱核對"], ["deslop", "去 AI 味"], ["review", "審查意見"], ["revise", "依勾選意見修訂"], ["accept", "定稿並回寫追蹤"]];
/* 執行者＋模型的選項（設定裡同一個執行者可以有多個模型；id 寫成「執行者/模型」） */
function provChoices() {
  if (S.config && S.config.choices) return S.config.choices;
  return ((S.config && S.config.providers) || [{ id: "claude_code", name: "Claude Code", type: "claude_code" }])
    .map((p) => ({ id: p.id, name: p.name, type: p.type, group: p.name, label: p.name, base: p.id }));
}
function provOptions(cur, opts = {}) {
  const groups = [];
  provChoices().forEach((c) => {
    let g = groups.find((x) => x.base === c.base);
    if (!g) { g = { base: c.base, label: c.group, items: [] }; groups.push(g); }
    g.items.push(c);
  });
  const one = (c, text) => FE.h("option", { value: c.id, selected: c.id === cur },
    text + (opts.unset && c.unset ? "（未設定）" : "") + (opts.claudeNote && c.type === "claude_code" ? "（用訂閱額度）" : ""));
  return groups.map((g) => g.items.length === 1 ? one(g.items[0], g.items[0].name)
    : FE.h("optgroup", { label: g.label }, g.items.map((c) => one(c, c.label))));
}
function provName(id) { const p = provChoices().find((x) => x.id === id); return p ? p.name : id; }
function stepProv(action) {
  const m = (S.config && S.config.pipeline_providers) || {};
  const k = STEP_OF_ACTION[action];
  const ids = provChoices().map((p) => p.id);
  return k && m[k] && ids.includes(m[k]) ? m[k] : Panel.prov();
}
function provSelect(id, cur, opts) {
  return FE.h("select", { id }, ...provOptions(cur, opts));
}

async function renderChapterStructure(el, no) {
  try {
    const r = await api("GET", B("/structures?chapter=" + no));
    const ch = r.chapter || {};
    if (!ch.has_card) { el.replaceChildren(); return; }
    const def = r.list.find((s) => s.default);
    const sel = FE.h("select", { id: "cs-sel" },
      FE.h("option", { value: "" }, def ? "用全書預設（" + def.name + "）" : "不指定"),
      r.list.map((s) => FE.h("option", { value: s.name, selected: s.name === ch.assigned }, s.name)));
    sel.onchange = async (ev) => {
      try { await api("POST", B("/chapters/" + no + "/structure"), { name: ev.target.value || null }); toast("已更新本章結構"); refresh(); } catch (e) { fail(e); }
    };
    // 有章節結構就說明會參考；沒有就給「到共用庫套用」的連結
    const note = r.list.length
      ? "寫這章時會參考這個節拍表；章綱的情節點優先。"
      : ["這本書還沒有章節結構，", FE.h("a", { href: "#/shared?t=" + enc("章節結構") }, "到共用庫套用"), "。"];
    el.replaceChildren(FE.h("div", { class: "row struct-row" },
      FE.h("span", { class: "small" }, FE.h("b", {}, "本章結構")),
      sel,
      FE.h("span", { class: "muted small" }, note)));
  } catch (e) { el.replaceChildren(); }
}

/* ------------------------------------------------------------------ 插圖 */
const ILL = { cfg: null, styles: null };
async function illCfg(force) {
  if (!ILL.cfg || force) ILL.cfg = await api("GET", "/api/illust/config");
  return ILL.cfg;
}
async function waitJob(id) {
  for (;;) {
    await new Promise((r) => setTimeout(r, 1200));
    const j = await api("GET", B(`/jobs/${id}`));
    if (j.status !== "running") return j;
  }
}
const tagAppend = (cur, add) => {
  const have = (cur || "").split(/\s*,\s*/).filter(Boolean);
  add.split(/\s*,\s*/).filter(Boolean).forEach((t) => { if (!have.map((x) => x.toLowerCase()).includes(t.toLowerCase())) have.push(t); });
  return have.join(", ");
};

/* 視覺卡（角色、勢力、世界觀的「繪圖提示」） */
async function renderCard(el, file, text) {
  const cfgR = await illCfg();
  const m = (text || "").match(/^## 繪圖提示[^\n]*\n([\s\S]*?)(?=^## |$(?![\s\S]))/m);
  const sec = m ? m[1].replace(/<!--[\s\S]*?-->/g, "") : "";
  const get = (k) => ((sec.match(new RegExp("^-\\s*" + k + "\\s*[:：]\\s*(.*)$", "m")) || [])[1] || "").trim();
  const card = { tags: get("標籤"), description: get("描述") };
  const has = card.tags || card.description;
  let editing = false, zh = null;
  const render = () => {
    const kids = [
      FE.h("div", { class: "card-title" },
        FE.h("h2", {}, "視覺卡 ", has ? null : FE.h("span", { class: "badge b-warn" }, "還沒有")),
        FE.h("div", { class: "row" },
          FE.h("select", { id: "vc-prov" }),
          FE.h("button", { class: "sm", id: "vc-ai" }, "AI 從設定產生"),
          FE.h("button", { class: "sm", id: "vc-edit" }, editing ? "取消" : "手動編輯"))),
      FE.h("div", { class: "muted small", style: "margin-bottom:8px" },
        "固定不變的外觀（英文 Danbooru 標籤＋一兩句描述）。每張插圖都會自動帶入，是同一角色每次長得一樣的關鍵。"),
    ];
    if (editing) {
      kids.push(FE.h("label", { class: "f" },
        FE.h("span", {}, "標籤"),
        FE.h("textarea", { id: "vc-tags", rows: 2, placeholder: "1girl, long hair, black hair, red eyes, white hanfu", value: card.tags })));
      kids.push(FE.h("div", { class: "row", style: "margin-bottom:8px" },
        FE.h("input", { type: "text", id: "vc-zh-in", placeholder: "輸入中文外觀（例如：黑色長髮、紅色眼睛、白色漢服），本機查標籤", style: "flex:1" }),
        FE.h("button", { class: "sm", id: "vc-zh" }, "查")));
      if (zh) {
        kids.push(FE.h("div", { class: "ill-chips", style: "margin-bottom:8px" },
          zh.length ? zh.map((t) => FE.h("span", { class: "chip add", "data-tag": t.tag }, t.zh + " → " + t.tag))
            : FE.h("span", { class: "muted small" }, "沒有查到。")));
      }
      kids.push(FE.h("label", { class: "f" },
        FE.h("span", {}, "描述（英文）"),
        FE.h("textarea", { id: "vc-desc", rows: 2, value: card.description })));
      kids.push(FE.h("div", { class: "row" }, FE.h("span", { class: "grow" }),
        FE.h("button", { class: "primary sm", id: "vc-save" }, "儲存")));
    } else if (has) {
      kids.push(FE.h("div", { class: "kv" },
        FE.h("span", { class: "k" }, "標籤"), FE.h("span", {}, card.tags),
        FE.h("span", { class: "k" }, "描述"), FE.h("span", {}, card.description)));
    }
    el.replaceChildren(FE.h("div", { class: "card ill-card" }, kids));
    $("#vc-prov", el).replaceChildren(...provOptions(cfgR.config.provider || Panel.prov(), { claudeNote: true }));
    $("#vc-edit", el).onclick = () => { editing = !editing; render(); };
    $("#vc-ai", el).onclick = async () => {
      try {
        const job = await api("POST", B("/jobs"), { action: "visual_card", params: { file }, provider: $("#vc-prov", el).value });
        Panel.attach(job);
        const j = await waitJob(job.id);
        if (j.status === "done") { toast("視覺卡已寫入"); refresh(); } else toast("產生失敗，詳情看右側面板", true);
      } catch (e) { fail(e); }
    };
    if (!editing) return;
    $("#vc-zh", el).onclick = async () => {
      card.tags = $("#vc-tags", el).value; card.description = $("#vc-desc", el).value;
      try { const r = await api("POST", "/api/illust/zh", { text: $("#vc-zh-in", el).value }); if (!r.has_dict) return toast("找不到中文對照表：到「設定 → 插畫」填 Forge 資料夾", true); zh = r.tags; render(); } catch (e) { fail(e); }
    };
    el.querySelectorAll(".chip.add").forEach((c) => c.onclick = () => { card.tags = tagAppend($("#vc-tags", el).value, c.dataset.tag); card.description = $("#vc-desc", el).value; render(); });
    $("#vc-save", el).onclick = async () => {
      try { await api("POST", B("/cards"), { file, tags: $("#vc-tags", el).value, description: $("#vc-desc", el).value }); toast("已儲存視覺卡"); refresh(); } catch (e) { fail(e); }
    };
  };
  render();
}

/* 設定頁：插畫（Forge Neo／ComfyUI） */
// LoRA 列表（Forge 與 ComfyUI 共用）：可以打字搜尋；選好後讀同名 JSON 帶入觸發詞（前 3 個詞）與強度
function loraRowsEl(items, list, key, title, who) {
  const dl = "lora-dl-" + key;
  const rows = items.map((x, j) => {
    const nm = x.name || "";
    const miss = list && nm && !list.some((f) => f.name === nm);
    const row = FE.h("div", { class: "row", style: "gap:6px;margin-bottom:4px;align-items:center" },
      FE.h("input", { type: "checkbox", "data-lr": key + ":" + j, "data-lk": "on", checked: x.on !== false, title: "使用這個 LoRA" }),
      FE.h("input", { type: "text", list: dl, "data-lr": key + ":" + j, "data-lk": "name", value: nm, style: "flex:2",
        placeholder: list ? "打字搜尋 LoRA" : "LoRA 名稱（按測試連線後可以搜尋清單）",
        title: miss ? who + " 找不到這個 LoRA" : "" }),
      FE.h("input", { type: "number", "data-lr": key + ":" + j, "data-lk": "strength", value: String(x.strength ?? 1),
        step: 0.05, min: -4, max: 4, style: "width:80px", title: "強度" }),
      FE.h("input", { type: "text", "data-lr": key + ":" + j, "data-lk": "trigger", value: x.trigger || "",
        placeholder: "觸發詞（選填，接在正向提示詞後面）", style: "flex:2" }),
      FE.h("button", { class: "sm danger", "data-lrdel": key + ":" + j }, "刪除"));
    if (!miss) return row;
    return [row, FE.h("div", { class: "err small", style: "margin:-2px 0 4px 24px" }, who + " 找不到「" + nm + "」")];
  });
  return FE.h("div", { class: "f", style: "margin-top:6px" },
    FE.h("span", {}, title),
    list ? FE.h("datalist", { id: dl }, list.map((f) => FE.h("option", { value: f.name }, f.folder || ""))) : null,
    rows.length ? rows : FE.h("div", { class: "muted small" }, "沒有使用 LoRA。"),
    FE.h("div", {},
      FE.h("button", { class: "sm", "data-lradd": key }, "＋ LoRA"),
      list ? FE.h("span", { class: "muted small" }, "　共 " + list.length + " 個；選好後會讀同名 JSON 帶入觸發詞（前 3 個詞）與建議強度，沒有 JSON 就用檔名") : null));
}
function bindLoraRows(root, getList, backend, rerender) {
  root.querySelectorAll("[data-lr]").forEach((x) => {
    x.onchange = async () => {
      const [key, j] = x.dataset.lr.split(":");
      const lr = getList(key)[+j];
      const k = x.dataset.lk;
      lr[k] = k === "on" ? x.checked : k === "strength" ? (parseFloat(x.value) || 0) : x.value.trim();
      if (k === "name" && lr.name) {
        try {
          const h = await api("POST", "/api/illust/lora_hint", { backend, name: lr.name });
          lr.trigger = h.trigger; lr.strength = h.strength;
        } catch (e) { /* 讀不到就保留原值 */ }
        rerender();
      }
    };
  });
  root.querySelectorAll("[data-lradd]").forEach((b) => b.onclick = () => { getList(b.dataset.lradd).push({ name: "", strength: 1, on: true, trigger: "" }); rerender(); });
  root.querySelectorAll("[data-lrdel]").forEach((b) => b.onclick = () => { const [key, j] = b.dataset.lrdel.split(":"); getList(key).splice(+j, 1); rerender(); });
}
const COMFY_KINDS = [["anima", "Anima（標籤＋自然語言）"], ["moss", "MOSS-Image（自然語言）"]];
async function renderIllSettings(el) {
  const r = await illCfg(true);
  const c = r.config;
  const profs = JSON.parse(JSON.stringify(c.comfy_profiles || []));
  let cst = null;   // ComfyUI 測試連線結果
  const be = c.backend === "comfy" ? "comfy" : "forge";
  el.replaceChildren(
    FE.h("h2", { style: "margin-bottom:4px" }, "插畫（Forge Neo／ComfyUI）"),
    FE.h("div", { class: "f" }, FE.h("span", {}, "出圖後端")),
    FE.h("div", { class: "seg compact", id: "il-be", style: "margin-bottom:12px" },
      FE.h("label", {}, FE.h("input", { type: "radio", name: "il-be", value: "forge", checked: be === "forge" }), FE.h("span", {}, "Forge Neo")),
      FE.h("label", {}, FE.h("input", { type: "radio", name: "il-be", value: "comfy", checked: be === "comfy" }), FE.h("span", {}, "ComfyUI"))),
    FE.h("div", { "data-be": "forge" },
      FE.h("div", { class: "muted small", style: "margin-bottom:12px" },
        "Forge 要用 ", FE.h("code", {}, "--api"),
        " 啟動（加在啟動 bat 的 COMMANDLINE_ARGS）。出圖參數用 Forge「PNG Info」最後一行的格式，Forge 會自己切換模型和 VAE／文字編碼器。"),
      FE.h("div", { class: "grid g2" },
        FE.h("label", { class: "f" }, FE.h("span", {}, "Forge 網址"),
          FE.h("div", { class: "row" },
            FE.h("input", { type: "text", id: "il-url", value: c.forge_url, style: "flex:1" }),
            FE.h("button", { class: "sm", id: "il-test" }, "測試連線"))),
        FE.h("label", { class: "f" }, FE.h("span", {}, "Forge 資料夾（選填：讀最近一次的參數、找 tagcomplete 的標籤對照表）"),
          FE.h("input", { type: "text", id: "il-dir", value: c.forge_dir, placeholder: "例如 D:\\sd-webui-forge-neo" }))),
      FE.h("div", { class: "small", id: "il-status", style: "margin:-4px 0 10px" }),
      FE.h("label", { class: "f" }, FE.h("span", {}, "出圖參數（Forge PNG Info 最後一行；Seed、Size 由工作台決定）"), " ",
        FE.h("textarea", { id: "il-params", rows: 2, value: c.params })),
      FE.h("div", { class: "row", style: "margin:-6px 0 12px" },
        FE.h("button", { class: "sm", id: "il-fromforge" }, "從 Forge 讀最近一次的參數"),
        FE.h("span", { class: "muted small" }, "讀 Forge 資料夾裡的 params.txt")),
      FE.h("label", { class: "cb" },
        FE.h("input", { type: "checkbox", id: "il-save", checked: !!c.save_in_forge }),
        " 也在 Forge 的輸出資料夾存一份"),
      FE.h("div", { id: "il-loras" })),
    FE.h("div", { "data-be": "comfy" },
      FE.h("div", { class: "muted small", style: "margin-bottom:10px" },
        "工作台用 ComfyUI 的 API 出圖，只會用到 ComfyUI 內建節點。每個「出圖設定」是一份 workflow：留空就用專案附的範本（",
        FE.h("code", {}, "examples/comfy/"),
        "）； 要用自己的 workflow，請在 ComfyUI 選單用「Export (API)」匯出（沒有這個選項的話，到 ComfyUI 設定開啟開發者模式）。工作台只改正向、負向、seed、尺寸、張數，組提示詞用的自訂節點會自動略過。"),
      FE.h("label", { class: "f" }, FE.h("span", {}, "ComfyUI 網址"),
        FE.h("div", { class: "row" },
          FE.h("input", { type: "text", id: "cf-url", value: c.comfy_url, style: "flex:1" }),
          FE.h("button", { class: "sm", id: "cf-test" }, "測試連線"))),
      FE.h("div", { class: "small", id: "cf-status", style: "margin:-4px 0 10px" }),
      FE.h("div", { id: "cf-profs" }),
      FE.h("div", { class: "row", style: "margin:6px 0 10px" },
        FE.h("button", { class: "sm", id: "cf-add" }, "＋ 新增出圖設定"),
        FE.h("label", { class: "f", style: "margin:0 0 0 auto;flex-direction:row;align-items:center;gap:6px" },
          FE.h("span", {}, "預設使用"), FE.h("select", { id: "cf-def" }))),
      FE.h("label", { class: "cb" },
        FE.h("input", { type: "checkbox", id: "cf-keep", checked: !!c.comfy_keep_output }),
        " 也在 ComfyUI 的 output 資料夾存一份（不勾就只放 ComfyUI 的暫存）"),
      FE.h("label", { class: "f" }, FE.h("span", {}, "LoRA 資料夾（讀同名 JSON 的觸發詞用；留空＝問 ComfyUI）"),
        FE.h("input", { type: "text", id: "cf-loradir", value: c.comfy_lora_dir || "", placeholder: "例如 D:\\ComfyUI\\models\\loras" }))),
    FE.h("h3", { style: "margin:14px 0 8px" }, "提示詞"),
    FE.h("div", { class: "grid g4" },
      FE.h("label", { class: "f" }, FE.h("span", {}, "預設寬"), FE.h("input", { type: "number", id: "il-w", value: c.width, step: 8 })),
      FE.h("label", { class: "f" }, FE.h("span", {}, "預設高"), FE.h("input", { type: "number", id: "il-h", value: c.height, step: 8 })),
      FE.h("label", { class: "f" }, FE.h("span", {}, "分級標籤"),
        FE.h("select", { id: "il-safe" }, ["safe", "sensitive", "nsfw", "explicit", ""].map((v) => FE.h("option", { value: v, selected: c.safety === v }, v || "（不加）")))),
      FE.h("label", { class: "f" }, FE.h("span", {}, "格式"),
        FE.h("select", { id: "il-fmt" }, [["mixed", "標籤＋自然語言"], ["tags", "只有標籤"], ["natural", "自然語言為主"]].map(([v, l]) => FE.h("option", { value: v, selected: c.format === v }, l))))),
    FE.h("div", { class: "grid g2" },
      FE.h("label", { class: "f" }, FE.h("span", {}, "品質標籤（放在最前面）"), FE.h("input", { type: "text", id: "il-q", value: c.quality })),
      FE.h("label", { class: "f" }, FE.h("span", {}, "負面提示詞"), FE.h("input", { type: "text", id: "il-neg", value: c.negative })),
      FE.h("label", { class: "f" }, FE.h("span", {}, "畫風樣式表（.xlsx 或 .json，格式同 examples/styles.example.json）"),
        FE.h("input", { type: "text", id: "il-sheet", value: c.style_sheet, placeholder: "留空＝用專案附的 examples/styles.example.json" })),
      FE.h("label", { class: "f" }, FE.h("span", {}, "樣式表用哪個欄位"),
        FE.h("select", { id: "il-src" }, [["prompt", "prompt（標籤）"], ["naturl_prompt", "naturl_prompt（自然語言）"], ["both", "prompt + naturl_prompt"]].map(([v, l]) => FE.h("option", { value: v, selected: c.style_source === v }, l)))),
      FE.h("label", { class: "f" }, FE.h("span", {}, "產生畫面描述預設用的 AI"),
        FE.h("select", { id: "il-prov" },
          FE.h("option", { value: "" }, "面板目前的執行者"),
          r.providers.map((pc) => FE.h("option", { value: pc.id, selected: c.provider === pc.id }, pc.name)))),
      FE.h("div", { class: "f" }, FE.h("span", {}, "標籤對照表"),
        FE.h("div", { class: "small" },
          r.tag_csv ? "✓ " + r.tag_csv : FE.h("span", { class: "muted" }, "沒有（填 Forge 資料夾會自動找 tagcomplete 的 danbooru.csv）"),
          FE.h("br"),
          r.tag_zh_csv ? "✓ " + r.tag_zh_csv : FE.h("span", { class: "muted" }, "沒有中文對照表")))),
    FE.h("div", { class: "small muted", style: "margin:-4px 0 8px" },
      r.sheet_error ? FE.h("span", { class: "err" }, r.sheet_error)
        : r.sheet_count ? "樣式表共 " + r.sheet_count + " 個畫風" + (r.sheet_is_example ? "（目前用專案附的範例）" : "") : "",
      "　MOSS-Image 會自動改用自然語言，不加品質、分級與畫師標籤。"),
    FE.h("label", { class: "cb" },
      FE.h("input", { type: "checkbox", id: "il-nsfw", checked: !!c.show_nsfw_styles }),
      " 選畫風時預設顯示 nsfw 分類"),
    FE.h("div", { class: "row" }, FE.h("span", { class: "grow" }),
      FE.h("button", { class: "primary", id: "il-savecfg" }, "儲存插畫設定")));
  const forgeLoras = JSON.parse(JSON.stringify(c.forge_loras || []));
  let fst = null;   // Forge 測試連線結果
  const renderForgeLoras = () => {
    $("#il-loras", el).replaceChildren(loraRowsEl(forgeLoras, fst && fst.ok ? fst.loras || [] : null, "f",
      "LoRA（出圖時加進提示詞：<lora:名稱:強度> 與觸發詞；提示詞裡已經有的不重複加）", "Forge"));
    bindLoraRows($("#il-loras", el), () => forgeLoras, "forge", renderForgeLoras);
  };
  renderForgeLoras();
  const syncBe = () => {
    const v = el.querySelector('input[name="il-be"]:checked').value;
    el.querySelectorAll("[data-be]").forEach((x) => { x.hidden = x.dataset.be !== v; });
  };
  el.querySelectorAll('input[name="il-be"]').forEach((x) => x.onchange = syncBe);
  syncBe();

  const modelField = (p, i, key, label) => {
    const list = cst && cst.ok ? cst.lists[key === "upsampler_clip" ? "clip" : key] || [] : null;
    const guess = cst && cst.ok ? ((cst.profiles.find((x) => x.id === p.id) || {}).guess || {})[key] : "";
    const box = FE.h("label", { class: "f" }, FE.h("span", {}, label));
    if (!list) {
      box.append(FE.h("input", { type: "text", "data-pf": i, "data-key": key, value: p[key] || "",
        placeholder: key === "upsampler_clip" ? "例如 qwen3.5_9b_w4a8_gptq.safetensors" : "照 workflow（按測試連線後可以從清單選）" }));
      return box;
    }
    const cur = p[key] || "";
    box.append(FE.h("select", { "data-pf": i, "data-key": key },
      FE.h("option", { value: "" }, key === "upsampler_clip" ? "（請選擇）" : "照 workflow"),
      list.map((f) => FE.h("option", { value: f, selected: f === cur }, f + (f === guess && !cur ? "（建議）" : ""))),
      cur && !list.includes(cur) ? FE.h("option", { value: cur, selected: true }, cur + "（ComfyUI 找不到）") : null));
    return box;
  };
  const loraRows = (p, i) => loraRowsEl(p.loras || [], cst && cst.ok ? (cst.lists.lora || []).map((f) => ({ name: f, folder: f.replace(/\\/g, "/").split("/").slice(0, -1).join("/") })) : null,
    String(i), "LoRA（用內建的 LoraLoaderModelOnly，接在模型後面；強度 -4～4）", "ComfyUI");
  const renderProfs = () => {
    $("#cf-profs", el).replaceChildren(...profs.map((p, i) => {
      const st = cst && cst.ok ? cst.profiles.find((x) => x.id === p.id) : null;
      const sm = st && st.summary;
      const status = st ? (st.error
        ? [FE.h("span", { class: "badge b-bad" }, "workflow 有問題"), " " + st.error]
        : [FE.h("span", { class: "badge " + (sm.missing.length ? "b-bad" : "b-ok") }, sm.missing.length ? "ComfyUI 缺少節點" : "workflow 可以用"),
          " " + (sm.missing.length ? "缺：" + sm.missing.join("、") + "　" : ""),
          FE.h("span", { class: "muted" },
            "正向：" + sm.positive.join("、") + "　負向：" + (sm.negative.join("、") || "無") + "　尺寸：" + (sm.latent.join("、") || "無")
            + (sm.removed.length ? "　略過：" + sm.removed.join("、") : ""))]) : null;
      return FE.h("div", { class: "prov-box", style: "margin-bottom:10px" },
        FE.h("div", { class: "row" }, FE.h("b", {}, p.name || "未命名"), FE.h("span", { class: "grow" }),
          profs.length > 1 ? FE.h("button", { class: "sm danger", "data-del": i }, "刪除") : null),
        FE.h("div", { class: "grid g3" },
          FE.h("label", { class: "f" }, FE.h("span", {}, "名稱"),
            FE.h("input", { type: "text", "data-pf": i, "data-key": "name", value: p.name })),
          FE.h("label", { class: "f" }, FE.h("span", {}, "模型種類（決定提示詞格式）"),
            FE.h("select", { "data-pf": i, "data-key": "kind" },
              COMFY_KINDS.map(([v, l]) => FE.h("option", { value: v, selected: p.kind === v }, l)))),
          FE.h("label", { class: "f" }, FE.h("span", {}, "workflow（API 格式 .json）"),
            FE.h("input", { type: "text", "data-pf": i, "data-key": "workflow", value: p.workflow, placeholder: "留空＝專案附的範本" })),
          modelField(p, i, "unet", "模型"), modelField(p, i, "clip", "文字編碼器"), modelField(p, i, "vae", "VAE")),
        FE.h("label", { class: "f" }, FE.h("span", {}, "負面提示詞（留空＝" + (p.kind === "moss" ? "MOSS 官方建議" : "用下方「提示詞」的設定") + "）"),
          FE.h("input", { type: "text", "data-pf": i, "data-key": "negative", value: p.negative })),
        FE.h("label", { class: "cb" },
          FE.h("input", { type: "checkbox", "data-pf": i, "data-key": "upsampler", checked: !!p.upsampler }),
          " Prompt Upsampler：送出前用 LLM 把提示詞改寫成更完整的描述（多約 6 GB VRAM、每張多 10～30 秒）"),
        p.upsampler && p.kind !== "moss" ? FE.h("div", { class: "grid g3" }, modelField(p, i, "upsampler_clip", "改寫用的文字編碼器（MOSS 的 Qwen3.5 9B）")) : null,
        p.upsampler && p.kind === "moss" ? FE.h("div", { class: "muted small" }, "MOSS 直接用自己的文字編碼器改寫。") : null,
        loraRows(p, i),
        FE.h("div", { class: "small", style: "margin-top:6px" }, status));
    }));
    $("#cf-def", el).replaceChildren(...profs.map((p) => FE.h("option", { value: p.id, selected: p.id === (c.comfy_profile || profs[0].id) }, p.name)));
    el.querySelectorAll("[data-pf]").forEach((x) => {
      x.onchange = () => {
        const p = profs[+x.dataset.pf];
        p[x.dataset.key] = x.type === "checkbox" ? x.checked : x.value.trim();
        if (["kind", "upsampler"].includes(x.dataset.key)) renderProfs();
      };
    });
    el.querySelectorAll("[data-del]").forEach((b) => b.onclick = () => { profs.splice(+b.dataset.del, 1); renderProfs(); });
    bindLoraRows($("#cf-profs", el), (key) => (profs[+key].loras = profs[+key].loras || []), "comfy", renderProfs);
    el.querySelectorAll('[data-key="workflow"]').forEach((x) => attachPicker(x, { mode: "file", exts: [".json"], title: "選擇 ComfyUI workflow（API 格式）" }));
  };
  renderProfs();
  $("#cf-add", el).onclick = () => { profs.push({ id: "p" + Date.now().toString(36), name: "新的出圖設定", kind: "anima", workflow: "", unet: "", clip: "", vae: "", upsampler: false, upsampler_clip: "", negative: "", loras: [] }); renderProfs(); };

  const test = async () => {
    const st = $("#il-status", el);
    st.textContent = "連線中……";
    const s = await api("GET", "/api/illust/forge/status");
    fst = s; renderForgeLoras();
    st.replaceChildren(...(s.ok
      ? [FE.h("span", { class: "badge b-ok" }, "已連線"),
        " 模型：" + (s.model || "") + "　模組：" + (s.modules || []).join("、") + "　取樣器 " + s.samplers.length + " 種"]
      : [FE.h("span", { class: "badge b-bad" }, "連不到"), " " + s.error]));
  };
  const save = async () => {
    c.comfy_profile = $("#cf-def", el).value;
    const body = { backend: el.querySelector('input[name="il-be"]:checked').value,
      forge_url: $("#il-url", el).value.trim(), forge_dir: $("#il-dir", el).value.trim(), params: $("#il-params", el).value.trim(),
      width: parseInt($("#il-w", el).value), height: parseInt($("#il-h", el).value), safety: $("#il-safe", el).value, format: $("#il-fmt", el).value,
      quality: $("#il-q", el).value.trim(), negative: $("#il-neg", el).value.trim(), style_sheet: $("#il-sheet", el).value.trim(),
      style_source: $("#il-src", el).value, provider: $("#il-prov", el).value, show_nsfw_styles: $("#il-nsfw", el).checked, save_in_forge: $("#il-save", el).checked,
      comfy_url: $("#cf-url", el).value.trim(), comfy_profiles: profs, comfy_profile: c.comfy_profile, comfy_keep_output: $("#cf-keep", el).checked,
      comfy_lora_dir: $("#cf-loradir", el).value.trim(), forge_loras: forgeLoras };
    ILL.cfg = await api("POST", "/api/illust/config", body);
    const saved = ILL.cfg.config.comfy_profiles;
    profs.splice(0, profs.length, ...JSON.parse(JSON.stringify(saved)));
  };
  const ctest = async () => {
    const st = $("#cf-status", el);
    st.textContent = "連線中……";
    cst = await api("GET", "/api/illust/comfy/status");
    if (cst.ok) {
      // 沒選模型的，帶入建議
      let filled = 0;
      for (const p of profs) {
        const g = (cst.profiles.find((x) => x.id === p.id) || {}).guess || {};
        if (!p.workflow) for (const k of ["unet", "clip", "vae"]) if (!p[k] && g[k]) { p[k] = g[k]; filled++; }
        if (p.upsampler && p.kind !== "moss" && !p.upsampler_clip && g.upsampler_clip) { p.upsampler_clip = g.upsampler_clip; filled++; }
      }
      st.replaceChildren(
        FE.h("span", { class: "badge b-ok" }, "已連線"),
        " ComfyUI " + cst.version + "　" + (cst.device || "") + "　模型 " + cst.lists.unet.length
          + "、文字編碼器 " + cst.lists.clip.length + "、VAE " + cst.lists.vae.length + "、LoRA " + (cst.lists.lora || []).length + " 個",
        ...(filled ? ["　", FE.h("span", { class: "muted" }, "已依檔名帶入建議的模型，確認後按「儲存插畫設定」")] : []));
    } else st.replaceChildren(FE.h("span", { class: "badge b-bad" }, "連不到"), " " + cst.error);
    renderProfs();
  };
  attachPicker($("#il-dir", el), { mode: "dir", title: "選擇 Forge 資料夾" });
  attachPicker($("#il-sheet", el), { mode: "file", exts: [".xlsx", ".json"], title: "選擇畫風樣式表" });
  $("#il-test", el).onclick = async () => { try { await save(); await test(); } catch (e) { fail(e); } };
  $("#cf-test", el).onclick = async () => { try { await save(); await ctest(); } catch (e) { fail(e); } };
  $("#il-fromforge", el).onclick = async () => {
    try {
      const p = await api("POST", "/api/illust/forge/params", { forge_dir: $("#il-dir", el).value.trim() });
      $("#il-params", el).value = p.params;
      if (p.width) { $("#il-w", el).value = p.width; $("#il-h", el).value = p.height; }
      toast("已讀入，記得按「儲存插畫設定」");
    } catch (e) { fail(e); }
  };
  $("#il-savecfg", el).onclick = async () => { try { await save(); toast("已儲存插畫設定"); renderIllSettings(el); } catch (e) { fail(e); } };
}

/* ------------------------------------------------------------------ 選資料夾／檔案 */
// opts: {mode: "dir"|"file", exts: [".xlsx", ".json"], start: "路徑", title: "標題"}；選好後呼叫 onPick(路徑)
function pickPath(opts, onPick) {
  const mode = opts.mode || "dir";
  let cur = opts.start || "";
  let parent = null;
  const upBtn = FE.h("button", { class: "sm", id: "pp-up" }, "↑ 上一層");
  const pathInput = FE.h("input", { type: "text", id: "pp-path", style: "flex:1", placeholder: "輸入路徑後按 Enter" });
  const rootsBox = FE.h("div", { class: "pp-roots", id: "pp-roots" });
  const listBox = FE.h("div", { class: "pp-list", id: "pp-list" });
  const mkBtn = mode === "dir" ? FE.h("button", { class: "sm", id: "pp-mk" }, "＋ 新增資料夾") : null;
  const okBtn = mode === "dir" ? FE.h("button", { class: "primary", id: "pp-ok", disabled: true }, "選擇這個資料夾") : null;
  const close = FE.modal({
    title: opts.title || (mode === "dir" ? "選擇資料夾" : "選擇檔案"),
    body: [
      FE.h("div", { class: "row", style: "margin-bottom:8px" }, upBtn, pathInput),
      rootsBox,
      listBox,
    ],
    foot: (done) => [
      mkBtn || FE.h("span", { class: "muted small" }, opts.exts && opts.exts.length ? "只顯示 " + opts.exts.join("、") : ""),
      FE.h("span", { class: "grow" }),
      FE.h("button", { class: "btn", type: "button", onclick: () => done() }, "取消"),
      okBtn,
    ],
  });
  {
    const el = close.el;
    const load = async (p) => {
      try {
        const r = await api("GET", `/api/fs/list?mode=${mode}&exts=${enc((opts.exts || []).join(","))}&path=${enc(p || "")}`);
        cur = r.path; parent = r.parent;
        $("#pp-path", el).value = cur;
        $("#pp-roots", el).replaceChildren(...r.roots.map((x) => FE.h("span", { class: "chip", "data-p": x.path }, x.name)));
        el.querySelectorAll("#pp-roots .chip").forEach((c) => c.onclick = () => load(c.dataset.p));
        const sep = r.sep || "\\";
        const join = (n) => cur.endsWith(sep) ? cur + n : cur + sep + n;
        const items = cur
          ? [...r.dirs.map((d) => FE.h("div", { class: "pp-item dir", "data-p": join(d) }, "📁 " + d)),
            ...r.files.map((f) => FE.h("div", { class: "pp-item file", "data-p": join(f) }, "📄 " + f))]
          : [];
        $("#pp-list", el).replaceChildren(...(cur
          ? (items.length ? items : [FE.h("div", { class: "muted small", style: "padding:10px" }, "（空的）")])
          : [FE.h("div", { class: "muted small", style: "padding:10px" }, "從上面選一個起點。")]));
        el.querySelectorAll(".pp-item.dir").forEach((d) => d.onclick = () => load(d.dataset.p));
        el.querySelectorAll(".pp-item.file").forEach((f) => f.onclick = () => { close(); onPick(f.dataset.p); });
        if (okBtn) okBtn.disabled = !cur;
      } catch (e) { fail(e); }
    };
    $("#pp-up", el).onclick = () => { if (parent) load(parent); };
    $("#pp-path", el).onkeydown = (e) => { if (e.key === "Enter") load(e.target.value.trim()); };
    if (okBtn) okBtn.onclick = () => { close(); onPick(cur); };
    if (mkBtn) mkBtn.onclick = async () => {
      const name = prompt("新資料夾名稱");
      if (!name) return;
      try { const r = await api("POST", "/api/fs/mkdir", { path: cur, name }); load(r.path); } catch (e) { fail(e); }
    };
    load(cur);
  }
}
window.pickPath = pickPath;

// 在輸入框旁邊加「選擇…」按鈕；append=true 時把選到的路徑加到下一行（多行文字框）
function attachPicker(input, opts, append) {
  if (!input || input.dataset.picker) return;
  input.dataset.picker = "1";
  const btn = document.createElement("button");
  btn.type = "button"; btn.className = "sm"; btn.textContent = append ? "＋ 選擇…" : "選擇…";
  const wrap = document.createElement("div");
  wrap.className = "pick-wrap";
  input.parentNode.insertBefore(wrap, input);
  wrap.appendChild(input); wrap.appendChild(btn);
  btn.onclick = () => {
    const lines = input.value.split("\n").map((s) => s.trim()).filter(Boolean);
    const start = append ? (lines[lines.length - 1] || "") : input.value.trim();
    pickPath(Object.assign({ start }, opts), (p) => {
      input.value = append ? [...lines, p].join("\n") : p;
      input.dispatchEvent(new Event("input"));
    });
  };
}

/* ------------------------------------------------------------------ 重新啟動 */
async function restartServer(port) {
  if (!confirm("重新啟動服務？頁面會在幾秒後自動重新連上。")) return;
  let r;
  try { r = await api("POST", "/api/restart"); } catch (e) { return fail(e); }
  const target = new URL(r.url);
  const note = target.port !== location.port ? "（新的網址：" + target.origin + "）" : "";
  const msg = FE.h("p", { class: "muted" }, "等待服務重新開啟" + note);
  FE.modal({ title: "重新啟動中……", body: msg });
  const start = Date.now();
  await new Promise((res) => setTimeout(res, 1500));
  while (Date.now() - start < 40000) {
    try {
      if (target.origin === location.origin) {
        const x = await fetch("/api/config", { cache: "no-store" });
        if (x.ok) { location.reload(); return; }
      } else {
        await fetch(target.origin + "/api/config", { mode: "no-cors", cache: "no-store" });
        location.href = target.origin + "/" + location.hash; return;
      }
    } catch (e) { /* 還沒好 */ }
    await new Promise((res) => setTimeout(res, 700));
  }
  msg.replaceChildren("服務沒有在預期時間內回來。請看一下啟動工作台的黑色視窗有沒有錯誤訊息，或手動開啟 ",
    FE.h("a", { href: target.origin }, target.origin), "。");
}
window.restartServer = restartServer;

/* ------------------------------------------------------------------ Claude 面板 */
// 面板本體在 P3 換成 fekit 的 FE.jobs.panel（轉移計畫 §7.2）；Panel 只剩門面，100 多處舊呼叫不用改。
let fePanel = null;

function panelBase(job) {
  const book = (job && (job.book || job.book_id)) || S.book;
  return "/api/fe/books/" + encodeURIComponent(book) + "/jobs";
}

// render_md：串流段落的第一個字元是 U+200C 時收成「模型輸出全文」（D3-07）。
function panelRenderMd(text) {
  const collapse = text.charCodeAt(0) === 0x200c;
  const raw = collapse ? text.slice(1) : text;
  const md = FE.md.render(raw);
  if (!collapse) return md;
  return FE.h("details", { class: "ev-full" },
    FE.h("summary", {}, `模型輸出全文（${raw.length} 字）`), md);
}
const Panel = {
  // 收合交給 shell（寬螢幕記在 shell.off.panel，窄螢幕是抽屜）
  toggle(v) {
    const shell = FE.shell.current();
    if (!shell) return;
    shell.toggle("panel", v === undefined ? !shell.is_open("panel") : !!v);
  },
  renderActions() {
    const el = $("#panel-actions");
    if (!S.book) { el.replaceChildren(FE.h("div", { class: "muted small" }, "先從書架選一本書。")); return; }
    const groups = {};
    S.actions.filter((a) => !a.hidden).forEach((a) => (groups[a.group] = groups[a.group] || []).push(a));
    const collapsed = FE.store.get("actsCollapsed", false) === true;
    const head = FE.h("div", { class: "row", style: "margin-bottom:6px" },
      FE.h("span", { class: "gname muted small" }, "動作"), FE.h("span", { class: "grow" }),
      FE.h("button", { class: "ghost sm", onclick: () => Panel.collapseActs() }, collapsed ? "展開 ▾" : "收合 ▴"));
    const body = collapsed ? [] : Object.entries(groups).map(([g, list]) => FE.h("div", { class: "act-group" },
      FE.h("div", { class: "gname" }, g),
      FE.h("div", { class: "acts" }, list.map((a) => {
        const off = !Panel.isClaude() && !a.native;
        return FE.h("button", { class: off ? "sm dim-btn" : "sm", title: off ? "這個動作目前只支援 Claude Code" : null, onclick: () => Panel.openForm(a.id) }, a.label);
      }))));
    const note = !collapsed && !Panel.isClaude() && S.actions.some((a) => !a.native)
      ? FE.h("div", { class: "muted small", style: "margin-top:4px" }, "灰色按鈕目前只支援 Claude Code。") : null;
    el.replaceChildren(head, ...body, ...(note ? [note] : []));
  },
  prov() { return S.provider || (S.config && S.config.default_provider) || "claude_code"; },
  provObj() { return provChoices().find((p) => p.id === this.prov()) || { id: "claude_code", type: "claude_code", name: "Claude Code" }; },
  provName() { return this.provObj().name; },
  isClaude() { return this.provObj().type === "claude_code"; },
  renderProv() {
    const sel = document.querySelector("#prov-sel");
    if (sel) sel.replaceChildren(...provOptions(this.prov(), { unset: true }));
  },
  setProv(id) {
    S.provider = id;
    FE.store.set("provider", id);
    this.renderProv(); this.renderActions();
  },
  collapseActs() {
    FE.store.set("actsCollapsed", !FE.store.get("actsCollapsed", false));
    this.renderActions();
  },
  openForm(id, prefill = {}) {
    const a = S.actions.find((x) => x.id === id);
    if (!a) return;
    this.toggle(true);
    if (!this.isClaude() && !a.native) { toast(`「${a.label}」目前只支援 Claude Code，請在面板上方切換執行者。`, true); return; }
    if (!S.book) { toast("先選一本書", true); return; }
    const el = $("#panel-form");
    if (!a.fields.length) { this.run(id, {}); el.replaceChildren(); return; }
    const fields = a.fields.map((f) => {
      const v = prefill[f.key] ?? f.default ?? "";
      if (f.type === "textarea") return FE.h("label", { class: "f" }, FE.h("span", {}, f.label),
        FE.h("textarea", { "data-k": f.key, rows: 3, value: v }));
      if (f.type === "checkbox") return FE.h("label", { class: "cb" },
        FE.h("input", { type: "checkbox", "data-k": f.key, checked: !!v }), " " + f.label);
      if (f.type === "drafts") return FE.h("div", { class: "f" }, FE.h("span", {}, f.label),
        FE.h("div", { id: "pf-drafts", class: "muted" }, "讀取草稿中…"));
      return FE.h("label", { class: "f" }, FE.h("span", {}, f.label),
        FE.h("input", { type: f.type === "number" ? "number" : "text", "data-k": f.key, value: v }));
    });
    el.replaceChildren(
      FE.h("div", { class: "row", style: "margin-bottom:8px" },
        FE.h("b", {}, a.label), FE.h("span", { class: "grow" }),
        FE.h("button", { class: "ghost sm", onclick: () => Panel.closeForm() }, "✕")),
      ...fields,
      ...(STEP_OF_ACTION[id] ? [FE.h("label", { class: "f" },
        FE.h("span", {}, "執行者（預設＝設定裡這一步的分配）"), FE.h("select", { id: "pf-prov" }))] : []),
      FE.h("div", { class: "row" }, FE.h("span", { class: "grow" }), FE.h("button", { class: "primary", id: "pf-go" }, "執行")));
    const pfProv = el.querySelector("#pf-prov");
    if (pfProv) pfProv.replaceChildren(...provOptions(stepProv(id)));
    if (a.fields.some((f) => f.type === "drafts")) this.loadDraftPicks(el);
    const first = el.querySelector("[data-k]"); if (first) first.focus();
    $("#pf-go").onclick = () => {
      const p = {};
      el.querySelectorAll("[data-k]").forEach((i) => p[i.dataset.k] = i.type === "checkbox" ? i.checked : (i.type === "number" ? (i.value ? parseInt(i.value) : null) : i.value));
      if (el.querySelector("#pf-drafts")) p.text = [...el.querySelectorAll("[data-draft]:checked")].map((i) => i.dataset.draft).join("、");
      this.run(id, p, $("#pf-prov") ? $("#pf-prov").value : undefined);
    };
  },
  closeForm() { $("#panel-form").replaceChildren(); },
  async loadDraftPicks(el) {   // 「草稿轉正式」：列出目前的草稿讓作者勾選，不用自己打名字
    const box = el.querySelector("#pf-drafts");
    if (!box) return;
    try {
      const b = await api("GET", B("/bible"));
      const list = b["草稿"] || [];
      if (!list.length) { box.replaceChildren(FE.h("span", { class: "muted" }, "目前沒有草稿。")); return; }
      box.replaceChildren(...list.map((e) => FE.h("label", { class: "cb" },
        FE.h("input", { type: "checkbox", "data-draft": e.name }), " " + e.name,
        e.summary ? [" ", FE.h("span", { class: "muted" }, "— " + e.summary)] : null)),
        FE.h("div", { class: "muted" }, "沒勾任何一個，AI 只會列出草稿，不會定案。"));
    } catch (e) { box.textContent = "讀取草稿失敗"; }
  },
  /* ── P3：面板本體換成 fekit 的 FE.jobs.panel，這裡只剩門面（轉移計畫 §7.2） ── */
  mount(root) {
    if (fePanel) fePanel.destroy();
    fePanel = FE.jobs.panel({
      root: root,
      transport: "sse",
      base: () => panelBase(),
      render_md: panelRenderMd,
      notify: false,
      onreveal: () => Panel.toggle(true),
      onchange: (job) => {
        S.job = job;
        const running = !!job && (job.status === "running" || job.status === "queued");
        const shell = FE.shell.current();
        if (shell) shell.badge("panel", running ? "busy" : null);
      },
      onend: (job) => Panel.finish(job),
    });
  },
  attach(job, quiet, keepLog) {
    fePanel.attach(job, { base: panelBase(job), keep: !!keepLog });
  },
  async show(id) {
    const base = panelBase();
    try {
      // 只拿狀態判斷要不要 live；不要把整包 patch 傳給 attach
      // （attach 會丟掉 patch 的 log/stream，seq 卻已經是最新的，內容會消失）。
      const job = await api("GET", base + "/" + encodeURIComponent(id));
      if (job.status === "running") fePanel.attach(id, { base });
      else fePanel.show(id, { base });
    } catch (error) {
      FE.fail(error);
    }
  },
  async resume() {
    if (!fePanel || !S.book) return null;
    const book = S.book;
    const base = panelBase();
    const current = fePanel.tracker();
    // 已經在追蹤同一本書的任務（例如使用者剛按了執行）就不要被晚到的列表換掉。
    if (current && current.conn !== "closed" && current.conn !== "gone" &&
        S.job && S.job.book === S.book) return S.job;
    const found = await FE.jobs.list({ base, status: "queued,running", limit: 1 });
    if (!found.length || S.book !== book) return null;
    if (S.job && S.job.id === found[0].id && S.job.status === "running") return found[0];
    fePanel.attach({ id: found[0].id, status: found[0].status }, { base, reveal: false });
    return found[0];
  },
  async run(action, params, provider) {
    // D3-09：建立任務照舊打舊端點 POST /api/books/{book}/jobs，不用 panel.run()（它的 base 建立時就固定）。
    if ((action === "write" || action === "chapter_cards") && !(Number(params && params.from) > 0)) {
      toast(FE.t("請先填「從第幾章」。")); return;
    }
    try {
      const pid = provider || stepProv(action);
      if (pid !== this.prov()) toast(`用「${provName(pid)}」執行（設定 → 整章自動流程的步驟分配）`);
      const job = await api("POST", B("/jobs"), { action, params, provider: pid });
      this.closeForm();
      this.attach(job);
    } catch (e) { fail(e); }
  },
  async finish(job) {
    if (!job) return;
    S.books = (await api("GET", "/api/books").catch(() => ({ books: S.books }))).books;
    if (document.querySelector("textarea.editor")) {
      toast("任務完成。你正在編輯，所以頁面沒有自動重新整理。");
    } else if (job.book === "_共用") {
      if (typeof S.onSharedJob === "function") S.onSharedJob(job);
    } else if (S.book) {
      refresh();
    }
    if ((job.meta || {}).action === "volume_draft" && job.status === "done") {
      toast("卷綱草稿已產生：到大綱頁的「卷況」按「採用」才會變成正式卷綱。");
    }
  },
};
window.Panel = Panel;

/* 啟動搬到 boot.js：本檔只定義，載入後不會自己 init／route。 */
