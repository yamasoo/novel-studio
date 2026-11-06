/* 小說工作台 前端 */
"use strict";

const S = {
  config: null, claudeFound: null, actions: [], books: [],
  book: null,                 // 目前的書 id
  bookLang: null,             // 目前這本書的語言（zh-TW／en／ja）；書的內容用它標 lang，字形才對
  job: null,                  // 面板目前顯示的任務 {id, status, session_id}
  es: null,                   // EventSource（P3 起由 FE.jobs.panel 開，這個欄位已不再使用）
  lastText: "",
  routeName: "",
};

/* ------------------------------------------------------------------ 工具 */
const $ = (sel, el = document) => el.querySelector(sel);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const enc = encodeURIComponent;
const pad3 = (n) => String(n).padStart(3, "0");
const fmtNum = (n) => (n || 0).toLocaleString({ en: "en-US", ja: "ja-JP" }[window.I18N && I18N.lang] || "zh-TW");
// 字數單位：中文、日文書算「字」（chars），英文書算「詞」（words）；後端回傳 unit，這裡決定顯示哪個字
const unitCh = (unit) => (unit === "words" ? "詞" : "字");   // i18n-skip
const unitOfLang = (lang) => (lang === "en" ? "words" : "chars");
const unitOfBook = (id) => { const b = (S.books || []).find((x) => x.id === (id || S.book)); return (b && b.unit) || "chars"; };
// 書的語言：顯示書內容的容器加 lang（日文書在中文介面下用日文字形，中文書在日文介面下用繁中字形）。介面本身的 <html lang> 仍跟著介面語言
const bookLang = () => S.bookLang || ((S.books || []).find((x) => x.id === S.book) || {}).lang || "zh-TW";
const LA = () => ` lang="${bookLang()}"`;               // 只標語言
const LP = () => ` lang="${bookLang()}" data-i18n-skip`;  // 標語言，並且不被介面翻譯動到（正文）
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
const JB = (job, path) => `/api/books/${enc((job && job.book) || S.book)}${path}`;  // 任務所屬的書（共用庫任務掛在 _共用）

function toast(msg, err) {
  const el = document.createElement("div");
  el.className = "toast" + (err ? " err" : "");
  el.textContent = msg;
  $("#toast").appendChild(el);
  setTimeout(() => el.remove(), err ? 6000 : 2600);
}
function fail(e) { console.error(e); toast(e.message || String(e), true); }

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
function md(text) {
  const html = marked.parse(text || "", { gfm: true, breaks: false });
  return html.replace(/<script[\s\S]*?<\/script>/gi, "");
}
// 對照表在 ns_shared.js（單一來源）；這裡只把節點版轉回字串，呼叫端與輸出都不變。
function statusBadge(s) {
  return nsShared.html(nsShared.statusBadgeNode(s));
}

function modal(html, onMount) {
  $("#modal-body").innerHTML = html;
  $("#modal").hidden = false;
  if (onMount) onMount($("#modal-body"));
}
function closeModal() { $("#modal").hidden = true; $("#modal-body").innerHTML = ""; }
window.closeModal = closeModal;
$("#modal").addEventListener("click", (e) => { if (e.target.id === "modal") closeModal(); });

/* ------------------------------------------------------------------ 路由 */
function parseHash() {
  const h = location.hash.replace(/^#\/?/, "");
  const [pathPart, query] = h.split("?");
  const parts = pathPart.split("/").filter(Boolean).map(decodeURIComponent);
  const q = Object.fromEntries(new URLSearchParams(query || ""));
  return { parts, q };
}

function refresh() { return FE.route(); }

async function setBook(id, keep) {
  if (id === S.book) return;
  if (!id && keep) { S.book = null; Panel.renderActions(); return; }
  S.book = id;
  S.bookLang = ((S.books || []).find((x) => x.id === id) || {}).lang || null;
  Panel.renderActions();
  if (!id) return;
  // 若這本書有執行中的任務，接上（轉移計畫 §7.4：交給 Panel.resume 查 /api/fe，不再用舊的 B("/jobs")）
  if (Panel.resume) Panel.resume().catch(() => {});
}

function renderNav() {
  const nav = $("#nav");
  const sw = $("#book-switch");
  const books = S.books.filter((b) => b.is_book || b.id === S.book);
  if (S.book && !books.find((b) => b.id === S.book)) books.push({ id: S.book, name: S.book });
  sw.innerHTML = books.length ? `<select onchange="go('#/b/'+encodeURIComponent(this.value))">
      ${S.book ? "" : '<option value="">選擇一本書…</option>'}
      ${books.map((b) => `<option value="${esc(b.id)}" ${b.id === S.book ? "selected" : ""}>${esc(b.name)}</option>`).join("")}
    </select>` : "";
  if (!S.book) { nav.innerHTML = ""; }
  else {
    const base = "#/b/" + enc(S.book);
    const items = [
      ["overview", "◉", "總覽"], ["chapters", "☰", "章節"], ["outline", "⌘", "大綱"],
      ["bible", "✦", "設定集"], ["tracking", "⟲", "伏筆與時間線"], ["jobs", "◷", "任務紀錄"], ["illust", "✎", "插圖"], ["export", "⇩", "匯出"],
    ];
    nav.innerHTML = `<form class="side-search" onsubmit="event.preventDefault();sideSearch(this.q.value)">
        <input name="q" id="side-q" type="search" placeholder="搜尋前文（Ctrl+K）" value="${esc(S.routeName === "search" ? (parseHash().q.q || "") : "")}"></form>` + items.map(([r, i, t]) =>
      `<a class="navlink ${S.routeName === r || (r === "chapters" && S.routeName === "ch") ? "active" : ""}" href="${base}/${r}"><span class="ico">${i}</span><span>${t}</span></a>`).join("");
  }
  document.querySelectorAll(".side-bottom .navlink").forEach((a) => a.classList.toggle("active", a.dataset.r === S.routeName));
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
    modal(`<h2>恢復稿</h2><div class="muted small" style="margin-bottom:8px">${esc(r.label)}　·　${esc(r.reason)}　·　${fmtNum(r.chars)} ${unitCh(unitOfBook())}</div>
      <textarea class="editor prose"${LA()} style="min-height:50vh" readonly>${esc(r.text)}</textarea>
      <div class="row" style="margin-top:10px"><span class="grow"></span><button id="rc-copy">複製</button><button onclick="closeModal()">關閉</button></div>`, (el) => {
      $("#rc-copy", el).onclick = () => { navigator.clipboard.writeText(r.text).then(() => toast("已複製")); };
    });
  } catch (e) { fail(e); }
};

window.openCharState = (file) => docView($("#doc"), file);

function jobBadge(s) {
  return nsShared.html(nsShared.jobBadgeNode(s));
}


/* ------------------------------------------------------------------ 共用庫 */
const readFiles = (input) => Promise.all([...input.files].map((f) => new Promise((res, rej) => {
  const r = new FileReader();
  r.onload = () => res({ name: f.name, data: String(r.result).split(",")[1] || "" });
  r.onerror = () => rej(new Error("讀取 " + f.name + " 失敗"));
  r.readAsDataURL(f);
})));
// lang 有值時（套用共用文風、結構）：同語言的書排前面，語言不同的標「（語言不同）」，不擋，讓作者自己決定
const bookOpts = (books, cur, lang) => {
  const langs = S.sharedLangs || {};
  const diff = (b) => !!lang && !!langs[b] && langs[b] !== lang;
  const list = lang ? [...books.filter((b) => !diff(b)), ...books.filter(diff)] : books;
  return list.map((b) => `<option value="${esc(b)}" ${b === cur ? "selected" : ""}>${diff(b) ? `${esc(b)}（語言不同）` : esc(b)}</option>`).join("");
};


// 整章自動流程的步驟與面板動作的對應；面板按鈕也預設用該步驟分配的執行者
const STEP_OF_ACTION = { chapter_cards: "card", write: "write", goal_check: "goal", deslop: "deslop", review_notes: "review", revise_notes: "revise", accept: "accept" };
const AI_STEP_LABELS = [["card", "章綱"], ["write", "寫章節（候選稿）"], ["goal", "章綱核對"], ["deslop", "去 AI 味"], ["review", "審查意見"], ["revise", "依勾選意見修訂"], ["accept", "定稿並回寫追蹤"]];
/* 執行者＋模型的選項（設定裡同一個執行者可以有多個模型；id 寫成「執行者/模型」） */
function provChoices() {
  if (S.config && S.config.choices) return S.config.choices;
  return ((S.config && S.config.providers) || [{ id: "claude_code", name: "Claude Code", type: "claude_code" }])
    .map((p) => ({ id: p.id, name: p.name, type: p.type, group: p.name, label: p.name, base: p.id }));
}
function provOpts(cur, opts = {}) {
  const groups = [];
  provChoices().forEach((c) => {
    let g = groups.find((x) => x.base === c.base);
    if (!g) { g = { base: c.base, label: c.group, items: [] }; groups.push(g); }
    g.items.push(c);
  });
  const one = (c, text) => `<option value="${esc(c.id)}" ${c.id === cur ? "selected" : ""}>${esc(text)}${opts.unset && c.unset ? "（未設定）" : ""}${opts.claudeNote && c.type === "claude_code" ? "（用訂閱額度）" : ""}</option>`;
  return groups.map((g) => g.items.length === 1 ? one(g.items[0], g.items[0].name)
    : `<optgroup label="${esc(g.label)}">${g.items.map((c) => one(c, c.label)).join("")}</optgroup>`).join("");
}
function provName(id) { const p = provChoices().find((x) => x.id === id); return p ? p.name : id; }
function stepProv(action) {
  const m = (S.config && S.config.pipeline_providers) || {};
  const k = STEP_OF_ACTION[action];
  const ids = provChoices().map((p) => p.id);
  return k && m[k] && ids.includes(m[k]) ? m[k] : Panel.prov();
}
function provSelectHtml(id) {
  return `<select id="${id}">${provOpts(Panel.prov())}</select>`;
}

async function renderChapterStructure(el, no) {
  try {
    const r = await api("GET", B(`/structures?chapter=${no}`));
    const ch = r.chapter || {};
    if (!ch.has_card) { el.innerHTML = ""; return; }
    const def = r.list.find((s) => s.default);
    el.innerHTML = `<div class="row struct-row">
      <span class="small"><b>本章結構</b></span>
      <select id="cs-sel"><option value="">${def ? `用全書預設（${esc(def.name)}）` : "不指定"}</option>
        ${r.list.map((s) => `<option value="${esc(s.name)}" ${s.name === ch.assigned ? "selected" : ""}>${esc(s.name)}</option>`).join("")}</select>
      <span class="muted small">${r.list.length ? "寫這章時會參考這個節拍表；章綱的情節點優先。" : `這本書還沒有章節結構，<a href="#/shared?t=${enc("章節結構")}">到共用庫套用</a>。`}</span>
    </div>`;
    $("#cs-sel", el).onchange = async (ev) => {
      try { await api("POST", B(`/chapters/${no}/structure`), { name: ev.target.value || null }); toast("已更新本章結構"); refresh(); } catch (e) { fail(e); }
    };
  } catch (e) { el.innerHTML = ""; }
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
function illProvOptions(cfg, cur) {
  return provOpts(cur || cfg.config.provider || Panel.prov(), { claudeNote: true });
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
    el.innerHTML = `<div class="card ill-card">
      <div class="card-title"><h2>視覺卡 ${has ? "" : '<span class="badge b-warn">還沒有</span>'}</h2>
        <div class="row"><select id="vc-prov">${illProvOptions(cfgR)}</select><button class="sm" id="vc-ai">AI 從設定產生</button>
          <button class="sm" id="vc-edit">${editing ? "取消" : "手動編輯"}</button></div></div>
      <div class="muted small" style="margin-bottom:8px">固定不變的外觀（英文 Danbooru 標籤＋一兩句描述）。每張插圖都會自動帶入，是同一角色每次長得一樣的關鍵。</div>
      ${editing ? `<label class="f"><span>標籤</span><textarea id="vc-tags" rows="2" placeholder="1girl, long hair, black hair, red eyes, white hanfu">${esc(card.tags)}</textarea></label>
        <div class="row" style="margin-bottom:8px"><input type="text" id="vc-zh-in" placeholder="輸入中文外觀（例如：黑色長髮、紅色眼睛、白色漢服），本機查標籤" style="flex:1"><button class="sm" id="vc-zh">查</button></div>
        ${zh ? `<div class="ill-chips" style="margin-bottom:8px">${zh.map((h) => `<span class="chip add" data-tag="${esc(h.tag)}">${esc(h.zh)} → ${esc(h.tag)}</span>`).join("") || '<span class="muted small">沒有查到。</span>'}</div>` : ""}
        <label class="f"><span>描述（英文）</span><textarea id="vc-desc" rows="2">${esc(card.description)}</textarea></label>
        <div class="row"><span class="grow"></span><button class="primary sm" id="vc-save">儲存</button></div>`
      : has ? `<div class="kv"><span class="k">標籤</span><span>${esc(card.tags)}</span><span class="k">描述</span><span>${esc(card.description)}</span></div>` : ""}
    </div>`;
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
function loraRowsHtml(items, list, key, title, who) {
  const dl = `lora-dl-${key}`;
  const rows = items.map((x, j) => {
    const nm = x.name || "";
    const miss = list && nm && !list.some((f) => f.name === nm);
    return `<div class="row" style="gap:6px;margin-bottom:4px;align-items:center">
      <input type="checkbox" data-lr="${key}:${j}" data-lk="on" ${x.on !== false ? "checked" : ""} title="使用這個 LoRA">
      <input type="text" list="${dl}" data-lr="${key}:${j}" data-lk="name" value="${esc(nm)}" style="flex:2" placeholder="${list ? "打字搜尋 LoRA" : "LoRA 名稱（按測試連線後可以搜尋清單）"}" title="${miss ? who + " 找不到這個 LoRA" : ""}">
      <input type="number" data-lr="${key}:${j}" data-lk="strength" value="${esc(x.strength ?? 1)}" step="0.05" min="-4" max="4" style="width:80px" title="強度">
      <input type="text" data-lr="${key}:${j}" data-lk="trigger" value="${esc(x.trigger || "")}" placeholder="觸發詞（選填，接在正向提示詞後面）" style="flex:2">
      <button class="sm danger" data-lrdel="${key}:${j}">刪除</button></div>${miss ? `<div class="err small" style="margin:-2px 0 4px 24px">${esc(who)} 找不到「${esc(nm)}」</div>` : ""}`;
  }).join("");
  return `<div class="f" style="margin-top:6px"><span>${title}</span>
    ${list ? `<datalist id="${dl}">${list.map((f) => `<option value="${esc(f.name)}">${esc(f.folder || "")}</option>`).join("")}</datalist>` : ""}
    ${rows || '<div class="muted small">沒有使用 LoRA。</div>'}
    <div><button class="sm" data-lradd="${key}">＋ LoRA</button>${list ? `<span class="muted small">　共 ${list.length} 個；選好後會讀同名 JSON 帶入觸發詞（前 3 個詞）與建議強度，沒有 JSON 就用檔名</span>` : ""}</div></div>`;
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
  el.innerHTML = `
    <h2 style="margin-bottom:4px">插畫（Forge Neo／ComfyUI）</h2>
    <div class="f"><span>出圖後端</span></div>
    <div class="seg compact" id="il-be" style="margin-bottom:12px">
      <label><input type="radio" name="il-be" value="forge" ${be === "forge" ? "checked" : ""}><span>Forge Neo</span></label>
      <label><input type="radio" name="il-be" value="comfy" ${be === "comfy" ? "checked" : ""}><span>ComfyUI</span></label>
    </div>
    <div data-be="forge">
    <div class="muted small" style="margin-bottom:12px">Forge 要用 <code>--api</code> 啟動（加在啟動 bat 的 COMMANDLINE_ARGS）。出圖參數用 Forge「PNG Info」最後一行的格式，Forge 會自己切換模型和 VAE／文字編碼器。</div>
    <div class="grid g2">
      <label class="f"><span>Forge 網址</span><div class="row"><input type="text" id="il-url" value="${esc(c.forge_url)}" style="flex:1"><button class="sm" id="il-test">測試連線</button></div></label>
      <label class="f"><span>Forge 資料夾（選填：讀最近一次的參數、找 tagcomplete 的標籤對照表）</span><input type="text" id="il-dir" value="${esc(c.forge_dir)}" placeholder="例如 D:\\sd-webui-forge-neo"></label>
    </div>
    <div class="small" id="il-status" style="margin:-4px 0 10px"></div>
    <label class="f"><span>出圖參數（Forge PNG Info 最後一行；Seed、Size 由工作台決定）</span>
      <textarea id="il-params" rows="2">${esc(c.params)}</textarea></label>
    <div class="row" style="margin:-6px 0 12px"><button class="sm" id="il-fromforge">從 Forge 讀最近一次的參數</button><span class="muted small">讀 Forge 資料夾裡的 params.txt</span></div>
    <label class="cb"><input type="checkbox" id="il-save" ${c.save_in_forge ? "checked" : ""}> 也在 Forge 的輸出資料夾存一份</label>
    <div id="il-loras"></div>
    </div>
    <div data-be="comfy">
      <div class="muted small" style="margin-bottom:10px">工作台用 ComfyUI 的 API 出圖，只會用到 ComfyUI 內建節點。每個「出圖設定」是一份 workflow：留空就用專案附的範本（<code>examples/comfy/</code>）；
        要用自己的 workflow，請在 ComfyUI 選單用「Export (API)」匯出（沒有這個選項的話，到 ComfyUI 設定開啟開發者模式）。工作台只改正向、負向、seed、尺寸、張數，組提示詞用的自訂節點會自動略過。</div>
      <label class="f"><span>ComfyUI 網址</span><div class="row"><input type="text" id="cf-url" value="${esc(c.comfy_url)}" style="flex:1"><button class="sm" id="cf-test">測試連線</button></div></label>
      <div class="small" id="cf-status" style="margin:-4px 0 10px"></div>
      <div id="cf-profs"></div>
      <div class="row" style="margin:6px 0 10px"><button class="sm" id="cf-add">＋ 新增出圖設定</button>
        <label class="f" style="margin:0 0 0 auto;flex-direction:row;align-items:center;gap:6px"><span>預設使用</span><select id="cf-def"></select></label></div>
      <label class="cb"><input type="checkbox" id="cf-keep" ${c.comfy_keep_output ? "checked" : ""}> 也在 ComfyUI 的 output 資料夾存一份（不勾就只放 ComfyUI 的暫存）</label>
      <label class="f"><span>LoRA 資料夾（讀同名 JSON 的觸發詞用；留空＝問 ComfyUI）</span><input type="text" id="cf-loradir" value="${esc(c.comfy_lora_dir || "")}" placeholder="例如 D:\\ComfyUI\\models\\loras"></label>
    </div>
    <h3 style="margin:14px 0 8px">提示詞</h3>
    <div class="grid g4">
      <label class="f"><span>預設寬</span><input type="number" id="il-w" value="${esc(c.width)}" step="8"></label>
      <label class="f"><span>預設高</span><input type="number" id="il-h" value="${esc(c.height)}" step="8"></label>
      <label class="f"><span>分級標籤</span><select id="il-safe">${["safe", "sensitive", "nsfw", "explicit", ""].map((v) => `<option value="${v}" ${c.safety === v ? "selected" : ""}>${v || "（不加）"}</option>`).join("")}</select></label>
      <label class="f"><span>格式</span><select id="il-fmt">${[["mixed", "標籤＋自然語言"], ["tags", "只有標籤"], ["natural", "自然語言為主"]].map(([v, l]) => `<option value="${v}" ${c.format === v ? "selected" : ""}>${l}</option>`).join("")}</select></label>
    </div>
    <div class="grid g2">
      <label class="f"><span>品質標籤（放在最前面）</span><input type="text" id="il-q" value="${esc(c.quality)}"></label>
      <label class="f"><span>負面提示詞</span><input type="text" id="il-neg" value="${esc(c.negative)}"></label>
      <label class="f"><span>畫風樣式表（.xlsx 或 .json，格式同 examples/styles.example.json）</span><input type="text" id="il-sheet" value="${esc(c.style_sheet)}" placeholder="留空＝用專案附的 examples/styles.example.json"></label>
      <label class="f"><span>樣式表用哪個欄位</span><select id="il-src">${[["prompt", "prompt（標籤）"], ["naturl_prompt", "naturl_prompt（自然語言）"], ["both", "prompt + naturl_prompt"]].map(([v, l]) => `<option value="${v}" ${c.style_source === v ? "selected" : ""}>${l}</option>`).join("")}</select></label>
      <label class="f"><span>產生畫面描述預設用的 AI</span><select id="il-prov"><option value="">面板目前的執行者</option>${r.providers.map((p) => `<option value="${esc(p.id)}" ${c.provider === p.id ? "selected" : ""}>${esc(p.name)}</option>`).join("")}</select></label>
      <div class="f"><span>標籤對照表</span><div class="small">${r.tag_csv ? "✓ " + esc(r.tag_csv) : '<span class="muted">沒有（填 Forge 資料夾會自動找 tagcomplete 的 danbooru.csv）</span>'}<br>${r.tag_zh_csv ? "✓ " + esc(r.tag_zh_csv) : '<span class="muted">沒有中文對照表</span>'}</div></div>
    </div>
    <div class="small muted" style="margin:-4px 0 8px">${r.sheet_error ? '<span class="err">' + esc(r.sheet_error) + "</span>" : r.sheet_count ? `樣式表共 ${r.sheet_count} 個畫風${r.sheet_is_example ? "（目前用專案附的範例）" : ""}` : ""}　MOSS-Image 會自動改用自然語言，不加品質、分級與畫師標籤。</div>
    <label class="cb"><input type="checkbox" id="il-nsfw" ${c.show_nsfw_styles ? "checked" : ""}> 選畫風時預設顯示 nsfw 分類</label>
    <div class="row"><span class="grow"></span><button class="primary" id="il-savecfg">儲存插畫設定</button></div>`;
  const forgeLoras = JSON.parse(JSON.stringify(c.forge_loras || []));
  let fst = null;   // Forge 測試連線結果
  const renderForgeLoras = () => {
    $("#il-loras", el).innerHTML = loraRowsHtml(forgeLoras, fst && fst.ok ? fst.loras || [] : null, "f",
      "LoRA（出圖時加進提示詞：&lt;lora:名稱:強度&gt; 與觸發詞；提示詞裡已經有的不重複加）", "Forge");
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
    if (!list) return `<label class="f"><span>${label}</span><input type="text" data-pf="${i}" data-key="${key}" value="${esc(p[key] || "")}" placeholder="${key === "upsampler_clip" ? "例如 qwen3.5_9b_w4a8_gptq.safetensors" : "照 workflow（按測試連線後可以從清單選）"}"></label>`;
    const cur = p[key] || "";
    return `<label class="f"><span>${label}</span><select data-pf="${i}" data-key="${key}">
      <option value="">${key === "upsampler_clip" ? "（請選擇）" : "照 workflow"}</option>
      ${list.map((f) => `<option value="${esc(f)}" ${f === cur ? "selected" : ""}>${esc(f)}${f === guess && !cur ? "（建議）" : ""}</option>`).join("")}
      ${cur && !list.includes(cur) ? `<option value="${esc(cur)}" selected>${esc(cur)}（ComfyUI 找不到）</option>` : ""}</select></label>`;
  };
  const loraRows = (p, i) => loraRowsHtml(p.loras || [], cst && cst.ok ? (cst.lists.lora || []).map((f) => ({ name: f, folder: f.replace(/\\/g, "/").split("/").slice(0, -1).join("/") })) : null,
    `${i}`, "LoRA（用內建的 LoraLoaderModelOnly，接在模型後面；強度 -4～4）", "ComfyUI");
  const renderProfs = () => {
    $("#cf-profs", el).innerHTML = profs.map((p, i) => {
      const st = cst && cst.ok ? cst.profiles.find((x) => x.id === p.id) : null;
      const sm = st && st.summary;
      return `<div class="prov-box" style="margin-bottom:10px">
        <div class="row"><b>${esc(p.name || "未命名")}</b><span class="grow"></span>${profs.length > 1 ? `<button class="sm danger" data-del="${i}">刪除</button>` : ""}</div>
        <div class="grid g3">
          <label class="f"><span>名稱</span><input type="text" data-pf="${i}" data-key="name" value="${esc(p.name)}"></label>
          <label class="f"><span>模型種類（決定提示詞格式）</span><select data-pf="${i}" data-key="kind">${COMFY_KINDS.map(([v, l]) => `<option value="${v}" ${p.kind === v ? "selected" : ""}>${l}</option>`).join("")}</select></label>
          <label class="f"><span>workflow（API 格式 .json）</span><input type="text" data-pf="${i}" data-key="workflow" value="${esc(p.workflow)}" placeholder="留空＝專案附的範本"></label>
          ${modelField(p, i, "unet", "模型")}${modelField(p, i, "clip", "文字編碼器")}${modelField(p, i, "vae", "VAE")}
        </div>
        <label class="f"><span>負面提示詞（留空＝${p.kind === "moss" ? "MOSS 官方建議" : "用下方「提示詞」的設定"}）</span><input type="text" data-pf="${i}" data-key="negative" value="${esc(p.negative)}"></label>
        <label class="cb"><input type="checkbox" data-pf="${i}" data-key="upsampler" ${p.upsampler ? "checked" : ""}> Prompt Upsampler：送出前用 LLM 把提示詞改寫成更完整的描述（多約 6 GB VRAM、每張多 10～30 秒）</label>
        ${p.upsampler && p.kind !== "moss" ? `<div class="grid g3">${modelField(p, i, "upsampler_clip", "改寫用的文字編碼器（MOSS 的 Qwen3.5 9B）")}</div>` : ""}
        ${p.upsampler && p.kind === "moss" ? '<div class="muted small">MOSS 直接用自己的文字編碼器改寫。</div>' : ""}
        ${loraRows(p, i)}
        <div class="small" style="margin-top:6px">${st ? (st.error ? `<span class="badge b-bad">workflow 有問題</span> ${esc(st.error)}`
          : `<span class="badge ${sm.missing.length ? "b-bad" : "b-ok"}">${sm.missing.length ? "ComfyUI 缺少節點" : "workflow 可以用"}</span>
             ${sm.missing.length ? "缺：" + sm.missing.map(esc).join("、") + "　" : ""}<span class="muted">正向：${sm.positive.map(esc).join("、")}　負向：${sm.negative.map(esc).join("、") || "無"}　尺寸：${sm.latent.map(esc).join("、") || "無"}${sm.removed.length ? "　略過：" + sm.removed.map(esc).join("、") : ""}</span>`) : ""}</div>
      </div>`;
    }).join("");
    $("#cf-def", el).innerHTML = profs.map((p) => `<option value="${esc(p.id)}" ${p.id === (c.comfy_profile || profs[0].id) ? "selected" : ""}>${esc(p.name)}</option>`).join("");
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
    st.innerHTML = s.ok ? `<span class="badge b-ok">已連線</span> 模型：${esc(s.model || "")}　模組：${esc((s.modules || []).join("、"))}　取樣器 ${s.samplers.length} 種`
      : `<span class="badge b-bad">連不到</span> ${esc(s.error)}`;
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
      st.innerHTML = `<span class="badge b-ok">已連線</span> ComfyUI ${esc(cst.version)}　${esc(cst.device || "")}　模型 ${cst.lists.unet.length}、文字編碼器 ${cst.lists.clip.length}、VAE ${cst.lists.vae.length}、LoRA ${(cst.lists.lora || []).length} 個`
        + (filled ? `　<span class="muted">已依檔名帶入建議的模型，確認後按「儲存插畫設定」</span>` : "");
    } else st.innerHTML = `<span class="badge b-bad">連不到</span> ${esc(cst.error)}`;
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
  modal(`<h2>${esc(opts.title || (mode === "dir" ? "選擇資料夾" : "選擇檔案"))}</h2>
    <div class="row" style="margin-bottom:8px"><button class="sm" id="pp-up">↑ 上一層</button>
      <input type="text" id="pp-path" style="flex:1" placeholder="輸入路徑後按 Enter"></div>
    <div class="pp-roots" id="pp-roots"></div>
    <div class="pp-list" id="pp-list"></div>
    <div class="row" style="margin-top:10px">
      ${mode === "dir" ? '<button class="sm" id="pp-mk">＋ 新增資料夾</button>' : `<span class="muted small">${opts.exts && opts.exts.length ? "只顯示 " + esc(opts.exts.join("、")) : ""}</span>`}
      <span class="grow"></span><button onclick="closeModal()">取消</button>
      ${mode === "dir" ? '<button class="primary" id="pp-ok">選擇這個資料夾</button>' : ""}</div>`, (el) => {
    let parent = null;
    const load = async (p) => {
      try {
        const r = await api("GET", `/api/fs/list?mode=${mode}&exts=${enc((opts.exts || []).join(","))}&path=${enc(p || "")}`);
        cur = r.path; parent = r.parent;
        $("#pp-path", el).value = cur;
        $("#pp-roots", el).innerHTML = r.roots.map((x) => `<span class="chip" data-p="${esc(x.path)}">${esc(x.name)}</span>`).join("");
        el.querySelectorAll("#pp-roots .chip").forEach((c) => c.onclick = () => load(c.dataset.p));
        const sep = r.sep || "\\";
        const join = (n) => cur.endsWith(sep) ? cur + n : cur + sep + n;
        $("#pp-list", el).innerHTML = !cur ? '<div class="muted small" style="padding:10px">從上面選一個起點。</div>'
          : (r.dirs.map((d) => `<div class="pp-item dir" data-p="${esc(join(d))}">📁 ${esc(d)}</div>`).join("")
            + r.files.map((f) => `<div class="pp-item file" data-p="${esc(join(f))}">📄 ${esc(f)}</div>`).join(""))
            || '<div class="muted small" style="padding:10px">（空的）</div>';
        el.querySelectorAll(".pp-item.dir").forEach((d) => d.onclick = () => load(d.dataset.p));
        el.querySelectorAll(".pp-item.file").forEach((f) => f.onclick = () => { closeModal(); onPick(f.dataset.p); });
        if ($("#pp-ok", el)) $("#pp-ok", el).disabled = !cur;
      } catch (e) { fail(e); }
    };
    $("#pp-up", el).onclick = () => { if (parent) load(parent); };
    $("#pp-path", el).onkeydown = (e) => { if (e.key === "Enter") load(e.target.value.trim()); };
    if ($("#pp-ok", el)) $("#pp-ok", el).onclick = () => { closeModal(); onPick(cur); };
    if ($("#pp-mk", el)) $("#pp-mk", el).onclick = async () => {
      const name = prompt("新資料夾名稱");
      if (!name) return;
      try { const r = await api("POST", "/api/fs/mkdir", { path: cur, name }); load(r.path); } catch (e) { fail(e); }
    };
    load(cur);
  });
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
  modal(`<h2>重新啟動中……</h2><p class="muted" id="rs-msg">等待服務重新開啟${target.port !== location.port ? `（新的網址：${esc(target.origin)}）` : ""}</p>`);
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
  const msg = $("#rs-msg");
  if (msg) msg.innerHTML = `服務沒有在預期時間內回來。請看一下啟動工作台的黑色視窗有沒有錯誤訊息，或手動開啟 <a href="${esc(target.origin)}">${esc(target.origin)}</a>。`;
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
  open: false,
  toggle(v) {
    this.open = v === undefined ? !this.open : v;
    $("#panel").classList.toggle("closed", !this.open);
    $("#app").classList.toggle("panel-open", this.open);
    try { localStorage.setItem("panelOpen", this.open ? "1" : ""); } catch (e) { /* ignore */ }
  },
  renderActions() {
    const el = $("#panel-actions");
    if (!S.book) { el.innerHTML = '<div class="muted small">先從書架選一本書。</div>'; return; }
    const groups = {};
    S.actions.filter((a) => !a.hidden).forEach((a) => (groups[a.group] = groups[a.group] || []).push(a));
    let collapsed = false;
    try { collapsed = localStorage.getItem("actsCollapsed") === "1"; } catch (e) { /* ignore */ }
    el.innerHTML = `<div class="row" style="margin-bottom:6px"><span class="gname muted small">動作</span><span class="grow"></span>
      <button class="ghost sm" onclick="Panel.collapseActs()">${collapsed ? "展開 ▾" : "收合 ▴"}</button></div>` +
      (collapsed ? "" : Object.entries(groups).map(([g, list]) => `<div class="act-group"><div class="gname">${esc(g)}</div>
      <div class="acts">${list.map((a) => {
        const off = !Panel.isClaude() && !a.native;
        return `<button class="sm ${off ? "dim-btn" : ""}" ${off ? 'title="這個動作目前只支援 Claude Code"' : ""} onclick="Panel.openForm('${a.id}')">${esc(a.label)}</button>`;
      }).join("")}</div></div>`).join("")) +
      (!collapsed && !Panel.isClaude() && S.actions.some((a) => !a.native) ? `<div class="muted small" style="margin-top:4px">灰色按鈕目前只支援 Claude Code。</div>` : "");
  },
  prov() { return S.provider || (S.config && S.config.default_provider) || "claude_code"; },
  provObj() { return provChoices().find((p) => p.id === this.prov()) || { id: "claude_code", type: "claude_code", name: "Claude Code" }; },
  provName() { return this.provObj().name; },
  isClaude() { return this.provObj().type === "claude_code"; },
  renderProv() {
    $("#prov-sel").innerHTML = provOpts(this.prov(), { unset: true });
    $("#fab-label").textContent = this.provName();
  },
  setProv(id) {
    S.provider = id;
    try { localStorage.setItem("provider", id); } catch (e) { /* ignore */ }
    this.renderProv(); this.renderActions();
  },
  collapseActs() {
    let c = false;
    try { c = localStorage.getItem("actsCollapsed") === "1"; localStorage.setItem("actsCollapsed", c ? "" : "1"); } catch (e) { /* ignore */ }
    this.renderActions();
  },
  openForm(id, prefill = {}) {
    const a = S.actions.find((x) => x.id === id);
    if (!a) return;
    this.toggle(true);
    if (!this.isClaude() && !a.native) { toast(`「${a.label}」目前只支援 Claude Code，請在面板上方切換執行者。`, true); return; }
    if (!S.book) { toast("先選一本書", true); return; }
    const el = $("#panel-form");
    if (!a.fields.length) { this.run(id, {}); el.innerHTML = ""; return; }
    el.innerHTML = `<div class="row" style="margin-bottom:8px"><b>${esc(a.label)}</b><span class="grow"></span><button class="ghost sm" onclick="Panel.closeForm()">✕</button></div>
      ${a.fields.map((f) => {
        const v = prefill[f.key] ?? f.default ?? "";
        if (f.type === "textarea") return `<label class="f"><span>${esc(f.label)}</span><textarea data-k="${f.key}" rows="3">${esc(v)}</textarea></label>`;
        if (f.type === "checkbox") return `<label class="cb"><input type="checkbox" data-k="${f.key}" ${v ? "checked" : ""}> ${esc(f.label)}</label>`;
        if (f.type === "drafts") return `<div class="f"><span>${esc(f.label)}</span><div id="pf-drafts" class="muted">讀取草稿中…</div></div>`;
        return `<label class="f"><span>${esc(f.label)}</span><input type="${f.type === "number" ? "number" : "text"}" data-k="${f.key}" value="${esc(v)}"></label>`;
      }).join("")}
      ${STEP_OF_ACTION[id] ? `<label class="f"><span>執行者（預設＝設定裡這一步的分配）</span><select id="pf-prov">${provOpts(stepProv(id))}</select></label>` : ""}
      <div class="row"><span class="grow"></span><button class="primary" id="pf-go">執行</button></div>`;
    if (a.fields.some((f) => f.type === "drafts")) this.loadDraftPicks(el);
    const first = el.querySelector("[data-k]"); if (first) first.focus();
    $("#pf-go").onclick = () => {
      const p = {};
      el.querySelectorAll("[data-k]").forEach((i) => p[i.dataset.k] = i.type === "checkbox" ? i.checked : (i.type === "number" ? (i.value ? parseInt(i.value) : null) : i.value));
      if (el.querySelector("#pf-drafts")) p.text = [...el.querySelectorAll("[data-draft]:checked")].map((i) => i.dataset.draft).join("、");
      this.run(id, p, $("#pf-prov") ? $("#pf-prov").value : undefined);
    };
  },
  closeForm() { $("#panel-form").innerHTML = ""; },
  async loadDraftPicks(el) {   // 「草稿轉正式」：列出目前的草稿讓作者勾選，不用自己打名字
    const box = el.querySelector("#pf-drafts");
    if (!box) return;
    try {
      const b = await api("GET", B("/bible"));
      const list = b["草稿"] || [];
      if (!list.length) { box.innerHTML = `<span class="muted">目前沒有草稿。</span>`; return; }
      box.innerHTML = list.map((e) => `<label class="cb"><input type="checkbox" data-draft="${esc(e.name)}"> ${esc(e.name)}${e.summary ? ` <span class="muted">— ${esc(e.summary)}</span>` : ""}</label>`).join("")
        + `<div class="muted">沒勾任何一個，AI 只會列出草稿，不會定案。</div>`;
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
        const runDot = document.querySelector("#run-dot");
        const fabDot = document.querySelector("#fab-dot");
        if (runDot) runDot.className = "dot" + (running ? " run" : "");
        if (fabDot) fabDot.className = "dot" + (running ? " run" : "");
        // fekit 的 drawAsk 把 null 直接傳給 replaceChildren，回覆框會多一個裸的「null」文字節點
        // （jobs.js 717-727；vendor/fekit 不可改）。每次重畫後清掉，P5 修 kit 後連這三行一起刪。
        const ask = document.querySelector("#fe-panel-host .job-ask");
        if (ask) for (const node of [...ask.childNodes]) if (node.nodeType === 3) node.remove();
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
      fail(error);
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
      toast(t("請先填「從第幾章」。")); return;
    }
    try {
      const pid = provider || stepProv(action);
      if (pid !== this.prov()) toast(`用「${provName(pid)}」執行（設定 → 整章自動流程的步驟分配）`);
      const job = await api("POST", B("/jobs"), { action, params, provider: pid });
      this.closeForm();
      this.attach(job);
    } catch (e) { fail(e); }
  },
  reply() { /* 由面板的 ask 表單處理（轉移計畫 §7.2） */ },
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
Panel.setWidth = function (w) {
  const vw = window.innerWidth;
  let px = null;
  if (w === "narrow") px = 420;
  else if (w === "half") px = Math.round(vw * 0.5);
  else if (w === "wide") px = Math.round(vw * 0.65);
  else if (typeof w === "number") px = w;
  if (px === null) {
    document.documentElement.style.removeProperty("--panel-w");
    try { localStorage.removeItem("panelW"); } catch (e) { /* ignore */ }
    return;
  }
  px = Math.max(340, Math.min(px, vw - 420));
  document.documentElement.style.setProperty("--panel-w", px + "px");
  try { localStorage.setItem("panelW", String(px)); } catch (e) { /* ignore */ }
};
(function initResizer() {
  try { const w = parseInt(localStorage.getItem("panelW")); if (w) Panel.setWidth(w); } catch (e) { /* ignore */ }
  const r = $("#panel-resizer");
  r.addEventListener("mousedown", (e) => {
    e.preventDefault();
    document.body.classList.add("resizing");
    const move = (ev) => Panel.setWidth(window.innerWidth - ev.clientX);
    const up = () => { document.body.classList.remove("resizing"); window.removeEventListener("mousemove", move); window.removeEventListener("mouseup", up); };
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
  });
  r.addEventListener("dblclick", () => Panel.setWidth(null));
})();
window.Panel = Panel;

/* 啟動搬到 boot.js：本檔只定義，載入後不會自己 init／route。 */
