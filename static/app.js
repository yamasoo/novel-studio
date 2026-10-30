/* 小說工作台 前端 */
"use strict";

const S = {
  config: null, claudeFound: null, actions: [], books: [],
  book: null,                 // 目前的書 id
  bookLang: null,             // 目前這本書的語言（zh-TW／en／ja）；書的內容用它標 lang，字形才對
  job: null,                  // 面板目前顯示的任務 {id, status, session_id}
  es: null,                   // EventSource
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
function go(h) { if (location.hash === h) route(); else location.hash = h; }
window.go = go;

async function api(method, url, body) {
  const opt = { method, headers: {} };
  if (body !== undefined) { opt.headers["Content-Type"] = "application/json"; opt.body = JSON.stringify(body); }
  const r = await fetch(url, opt);
  let data = null;
  try { data = await r.json(); } catch (e) { /* ignore */ }
  if (!r.ok) throw new Error((data && (data.error || data.detail)) || ("HTTP " + r.status));
  return data;
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
function statusBadge(s) {
  const m = { "已寫": "b-ok", "已確認": "b-info", "草稿": "b-warn", "正式": "b-ok", "已回收": "b-ok", "推進中": "b-info", "已埋": "b-warn", "廢棄": "" };
  return s ? `<span class="badge ${m[s] || ""}">${esc(s)}</span>` : "";
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

async function route() {
  if (!$("#modal").hidden) closeModal();
  const { parts, q } = parseHash();
  const view = $("#view");
  try {
    if (parts[0] === "settings") { S.routeName = "settings"; await setBook(null, true); return await viewSettings(view); }
    if (parts[0] === "shared") { S.routeName = "shared"; return await viewShared(view, q.t, q.f); }
    if (parts[0] === "import") { S.routeName = "import"; return await viewImport(view); }
    if (parts[0] === "guide") { S.routeName = "guide"; await setBook(null, true); return await viewGuide(view); }
    if (parts[0] === "about") { S.routeName = "about"; return await viewAbout(view); }
    if (parts[0] === "b" && parts[1]) {
      await setBook(parts[1]);
      const sub = parts[2] || "overview";
      S.routeName = sub;
      renderNav();
      if (sub === "overview") return await viewOverview(view);
      if (sub === "chapters") return await viewChapters(view);
      if (sub === "ch") return await viewChapter(view, parseInt(parts[3]), q.tab);
      if (sub === "outline") return await viewOutline(view, q.f);
      if (sub === "bible") return await viewBible(view, q.t, q.f);
      if (sub === "tracking") return await viewTracking(view, q.t);
      if (sub === "jobs") return await viewJobs(view);
      if (sub === "export") return await viewExport(view);
      if (sub === "illust") return await viewIllust(view, q.t);
      if (sub === "search") return await viewSearch(view, q.q || "", q.s);
      if (sub === "reverse") return await viewReverse(view, q.upto);
      if (sub === "drift") return await viewDrift(view, q.from, q.to);
    }
    S.routeName = "shelf";
    await setBook(null, true);
    await viewShelf(view);
  } catch (e) {
    view.innerHTML = `<div class="card"><h2>出了點問題</h2><p class="muted">${esc(e.message)}</p><button onclick="go('#/')">回書架</button></div>`;
  } finally {
    renderNav();
    if (S.hl) { const t = S.hl; S.hl = null; highlightTerms(view, t); }
  }
}
window.addEventListener("hashchange", route);
function refresh() { route(); }

async function setBook(id, keep) {
  if (id === S.book) return;
  if (!id && keep) { S.book = null; Panel.renderActions(); return; }
  S.book = id;
  S.bookLang = ((S.books || []).find((x) => x.id === id) || {}).lang || null;
  Panel.renderActions();
  if (!id) return;
  // 若這本書有執行中的任務，接上
  try {
    const hist = await api("GET", B("/jobs"));
    if (hist[0] && hist[0].status === "running" && !(S.job && S.job.id === hist[0].id)) Panel.attach(hist[0], true);
  } catch (e) { /* ignore */ }
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

/* ------------------------------------------------------------------ 從正文建立設定（反推） */
async function viewReverse(view, upto) {
  const r = await api("GET", B(`/reverse?provider=${enc(Panel.prov())}${upto ? "&upto=" + enc(upto) : ""}`));
  const st = r.state, est = r.estimate, dr = st.drafts || {};
  const processed = (st.processed || []).length;
  const busy = S.job && S.job.status === "running";
  const cost = est.cost != null ? `約 US$${est.cost.toFixed(2)}` : (Panel.isClaude() ? "用 Claude 訂閱額度" : "依你設定的價格（沒填價格就不顯示）");
  const groups = [["設定", "角色、勢力、世界觀、故事核心、名詞表"], ["大綱", "全書大綱、卷綱"], ["章綱", "每章的章綱（反向整理，狀態「已寫」）"],
    ["追蹤", "章節摘要、伏筆、時間線、讀者認知、角色關係、角色狀態、狀態卡"]];
  const nDraft = groups.reduce((a, [g]) => a + (dr[g] || []).length, 0);
  view.innerHTML = `
    <div class="page-head"><div><h1>從正文建立設定</h1><div class="sub">已經寫好的書，不用開書訪談：AI 照章節順序分批讀正文，反推出設定、大綱、章綱與追蹤資料。全部先存成草稿，你核對後再分組採用。</div></div></div>
    ${r.has_settings ? `<div class="alert warn" style="margin-bottom:12px"><span class="t">這本書已經有角色或伏筆資料。採用草稿時，同名檔案會先備份再覆蓋。</span></div>` : ""}
    <div class="card" style="margin-bottom:14px">
      <div class="card-title"><h2>1. 估算</h2><span class="muted small">執行者：${esc(Panel.provName())}（右側面板上方可以切換）</span></div>
      <div class="grid g3" style="margin-bottom:10px">
        <div><div class="muted small">要讀的章節</div><div class="big">${est.chapters || 0} 章</div><div class="muted small">${fmtNum(est.chars || 0)} ${unitCh(unitOfBook())}，共 ${est.total_chapters || 0} 章</div></div>
        <div><div class="muted small">分批</div><div class="big">${est.batches || 0} 批</div><div class="muted small">依執行者的上下文長度，每批 1～3 章</div></div>
        <div><div class="muted small">預估 token</div><div class="big">${fmtNum(est.tokens_in || 0)}</div><div class="muted small">輸出約 ${fmtNum(est.tokens_out || 0)}；${esc(cost)}</div></div>
      </div>
      <div class="row" style="gap:10px;flex-wrap:wrap">
        <label class="f" style="margin:0"><span>先跑到第幾章（空白＝全部）</span><input type="number" id="rv-upto" min="1" value="${esc(upto || "")}" placeholder="${est.total_chapters || ""}" style="width:140px"></label>
        <button class="ghost" id="rv-est">重新估算</button>
      </div>
    </div>
    <div class="card" style="margin-bottom:14px">
      <div class="card-title"><h2>2. 執行</h2><span class="muted small">${processed ? `已抽取 ${processed} 章（到第 ${Math.max(...st.processed)} 章）` : "還沒開始"}${st.done ? "，已產生草稿" : ""}</span></div>
      <div class="muted small" style="margin-bottom:10px">中途停止或失敗都沒關係，下次按「繼續」會從斷的地方接著跑，已完成的章節不會重跑。想換範圍或正文改過很多，按「重新開始」（暫存會先備份）。</div>
      <div class="row" style="gap:8px">
        <button class="primary" id="rv-run" ${busy ? "disabled" : ""}>${processed ? (st.done ? "加跑新章節並重新整理" : "繼續") : "開始"}</button>
        ${processed ? `<button class="ghost danger" id="rv-reset" ${busy ? "disabled" : ""}>重新開始</button>` : ""}
      </div>
    </div>
    <div class="card">
      <div class="card-title"><h2>3. 核對草稿</h2><span class="muted small">${nDraft ? `${nDraft} 份草稿` : "跑完之後草稿會出現在這裡"}</span></div>
      ${groups.map(([g, desc]) => { const items = dr[g] || []; return items.length ? `<div class="card" style="margin:10px 0;padding:12px 14px">
        <div class="row"><b>${g}</b><span class="muted small" style="margin-left:8px">${desc}　·　${items.length} 份${items.some((x) => x.exists) ? `，其中 ${items.filter((x) => x.exists).length} 份會覆蓋現有檔案（先備份）` : ""}</span>
          <span class="grow"></span><button class="sm primary" data-adopt="${g}">採用${g}</button><button class="sm danger" data-discard="${g}">捨棄</button></div>
        <details style="margin-top:6px"><summary class="small">看清單</summary><div class="small" style="columns:2;margin-top:6px">${items.map((x) =>
          `<div><a href="javascript:void 0" data-view="${esc(x.draft)}">${esc(x.rel)}</a>${x.exists ? ' <span class="badge b-warn">覆蓋</span>' : ""}</div>`).join("")}</div></details>
      </div>` : ""; }).join("")}
      <div id="doc" style="margin-top:12px"></div>
    </div>`;
  $("#rv-est").onclick = () => go(`#/b/${enc(S.book)}/reverse${$("#rv-upto").value ? "?upto=" + enc($("#rv-upto").value) : ""}`);
  $("#rv-run").onclick = () => Panel.run("reverse", $("#rv-upto").value ? { upto: parseInt($("#rv-upto").value) } : {});
  if ($("#rv-reset")) $("#rv-reset").onclick = async () => {
    if (!confirm("清掉已抽取的資料和草稿，重新開始？（會先移到 .studio/備份）")) return;
    await api("POST", B("/reverse/reset"), {}); viewReverse(view, upto);
  };
  view.querySelectorAll("[data-adopt]").forEach((b) => b.onclick = async () => {
    const g = b.dataset.adopt;
    if (!confirm(`採用「${g}」的草稿？已有的同名檔案會先備份再覆蓋。`)) return;
    const res = await api("POST", B("/reverse/adopt"), { group: g });
    toast(`已採用 ${res.adopted} 份${res.backed_up ? `（備份 ${res.backed_up} 份原檔）` : ""}`); viewReverse(view, upto);
  });
  view.querySelectorAll("[data-discard]").forEach((b) => b.onclick = async () => {
    if (!confirm(`捨棄「${b.dataset.discard}」的草稿？`)) return;
    await api("POST", B("/reverse/discard"), { group: b.dataset.discard }); viewReverse(view, upto);
  });
  view.querySelectorAll("[data-view]").forEach((a) => a.onclick = () => docView($("#doc"), a.dataset.view));
}

/* ------------------------------------------------------------------ 前文搜尋（本機，不用模型） */
const SEARCH_SCOPES = [["正文", "正文"], ["候選", "候選稿"], ["章綱", "大綱與章綱"], ["設定", "設定集"], ["追蹤", "追蹤"]];
function searchScopes() {
  try { const v = JSON.parse(localStorage.getItem("search-scopes") || "null"); if (Array.isArray(v) && v.length) return v; } catch (e) { /* ignore */ }
  return ["正文"];
}
window.sideSearch = (q) => { q = (q || "").trim(); if (q) go(`#/b/${enc(S.book)}/search?q=${enc(q)}`); };
document.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && (e.key === "k" || e.key === "K") && S.book) {
    e.preventDefault(); const i = $("#search-q") || $("#side-q"); if (i) { i.focus(); i.select(); }
  }
});
async function viewSearch(view, q, s) {
  const scopes = s ? s.split(",") : searchScopes();
  view.innerHTML = `
    <div class="page-head"><div><h1>搜尋前文</h1><div class="sub">在本機直接找，不用模型。多個詞用空白分開＝要出現在同一章；「」或 "" 包起來＝完整片語；不分繁簡。</div></div></div>
    <div class="card" style="margin-bottom:14px"><form id="search-form" class="row" style="flex-wrap:wrap;gap:10px">
      <input id="search-q" type="search" value="${esc(q)}" placeholder="例如：玉珮、林遠 沈家、「三年前那場雨」" style="flex:1;min-width:240px">
      <button class="primary">搜尋</button>
      <div class="row" style="gap:12px;width:100%">${SEARCH_SCOPES.map(([k, l]) => `<label class="cb" style="margin:0"><input type="checkbox" name="sc" value="${k}" ${scopes.includes(k) ? "checked" : ""}> ${l}</label>`).join("")}</div>
    </form></div>
    <div id="search-res"></div><div id="doc" style="margin-top:14px"></div>`;
  $("#search-form").onsubmit = (e) => {
    e.preventDefault();
    const sc = [...document.querySelectorAll('#search-form input[name="sc"]:checked')].map((x) => x.value);
    try { localStorage.setItem("search-scopes", JSON.stringify(sc)); } catch (err) { /* ignore */ }
    go(`#/b/${enc(S.book)}/search?q=${enc($("#search-q").value.trim())}&s=${enc(sc.join(","))}`);
  };
  if (!q.trim()) { $("#search-q").focus(); return; }
  const box = $("#search-res");
  box.innerHTML = `<div class="card muted">搜尋中…</div>`;
  const r = await api("GET", B(`/search?q=${enc(q)}&scopes=${enc(scopes.join(","))}`));
  S.searchTerms = r.terms;
  if (!r.results.length) { box.innerHTML = `<div class="card empty">找不到「${esc(r.terms.join("」＋「"))}」。可以勾選更多範圍再試。</div>`; return; }
  const segs = (sn) => (sn.pre ? "…" : "") + sn.segs.map((g) => g.hl ? `<mark>${esc(g.t)}</mark>` : esc(g.t)).join("") + (sn.post ? "…" : "");
  const label = (x) => x.kind === "chapter" ? `第${x.no}章　${esc(x.title)}` : esc(x.path);
  const tag = (x) => x.scope === "正文" ? "" : `<span class="badge">${esc(SEARCH_SCOPES.find((z) => z[0] === x.scope)[1])}</span> `;
  box.innerHTML = `<div class="muted small" style="margin:0 0 8px">「${esc(r.terms.join("」＋「"))}」：${r.chapters ? `出現在 ${r.chapters} 章正文${r.first ? `，第一次在第 ${r.first} 章` : ""}；` : ""}共 ${r.files} 份檔案、${r.hits} 處${r.truncated ? "（結果太多，只列前面的）" : ""}</div>
    ${r.results.map((x, i) => `<div class="card" style="margin-bottom:10px;padding:12px 16px">
      <div class="row"><a href="javascript:void 0" class="nm" data-open="${i}">${tag(x)}${label(x)}</a><span class="grow"></span><span class="muted small">${x.count} 處</span></div>
      ${x.snippets.map((sn, j) => `<div class="small"${LP()} style="margin-top:6px;line-height:1.7${j >= 3 ? ";display:none" : ""}" data-more="${i}">${segs(sn)}</div>`).join("")}
      ${x.snippets.length > 3 || x.more ? `<button class="ghost sm" style="margin-top:4px" data-expand="${i}">展開其餘 ${x.snippets.length - 3 + x.more} 處</button>` : ""}
    </div>`).join("")}`;
  box.querySelectorAll("[data-expand]").forEach((b) => b.onclick = () => {
    box.querySelectorAll(`[data-more="${b.dataset.expand}"]`).forEach((d) => d.style.display = ""); b.remove();
  });
  box.querySelectorAll("[data-open]").forEach((a) => a.onclick = async () => {
    const x = r.results[+a.dataset.open];
    const tab = x.scope === "正文" ? "text" : x.scope === "候選" ? "candidate"
      : x.no && x.path.startsWith("大綱/章綱/") ? "card" : x.no && x.path.startsWith("追蹤/章節摘要/") ? "summary" : null;
    if (tab) { S.hl = r.terms; go(`#/b/${enc(S.book)}/ch/${x.no}?tab=${tab}`); return; }
    await docView($("#doc"), x.path);
    highlightTerms($("#doc"), r.terms);
  });
}
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

/* ------------------------------------------------------------------ 書架 */
async function viewShelf(view) {
  const data = await api("GET", "/api/books");
  S.books = data.books;
  if (!data.library) {
    view.innerHTML = `
      <div class="page-head"><div><h1>歡迎使用小說工作台</h1><div class="sub">先選一個資料夾當「書庫」</div></div></div>
      <div class="card">
        <p>書庫是放所有小說專案的資料夾，每本書是裡面的一個子資料夾；共用庫和插圖也會放在這裡。工作台程式和書庫是分開的，更新或重新下載工作台都不會動到你的書。</p>
        <label class="f"><span>書庫資料夾</span><input type="text" id="lib-path" value="${esc(data.suggested)}"></label>
        <div class="muted small" style="margin:-6px 0 12px">${data.suggested_exists ? "這個資料夾已經存在，裡面的書會出現在書架上。" : "資料夾不存在時會自動建立。"}之後可以在「設定」改。</div>
        <div class="row"><button class="primary" id="lib-ok">使用這個資料夾</button></div>
      </div>`;
    attachPicker($("#lib-path"), { mode: "dir", title: "選擇書庫資料夾" });
    $("#lib-ok").onclick = async () => {
      const p = $("#lib-path").value.trim();
      if (!p) return toast("請選擇資料夾", true);
      try { await api("POST", "/api/config", { library: p, create_library: true }); refresh(); } catch (e) { fail(e); }
    };
    return;
  }
  if (!data.exists) {
    view.innerHTML = `
      <div class="page-head"><div><h1>書架</h1><div class="sub">還沒有書庫資料夾</div></div></div>
      <div class="card">
        <p>書庫是放所有小說專案的資料夾，每本書是裡面的一個子資料夾。目前設定的位置：</p>
        <p><code>${esc(data.library || "（未設定）")}</code></p>
        <div class="row"><button class="primary" id="mk-lib">建立這個資料夾</button><button onclick="go('#/settings')">改用其他位置</button></div>
      </div>`;
    $("#mk-lib").onclick = async () => { await api("POST", "/api/config", { create_library: true }); refresh(); };
    return;
  }
  const books = data.books.filter((b) => b.is_book);
  const others = data.books.filter((b) => !b.is_book);
  view.innerHTML = `
    <div class="page-head">
      <div><h1>書架</h1><div class="sub">${books.length} 本書　·　書庫：<code>${esc(data.library)}</code></div></div>
      <div class="row"><button onclick="go('#/guide')">使用說明</button></div>
    </div>
    ${S.claudeFound ? "" : `<div class="alert warn" style="margin-bottom:14px"><span class="k">找不到 Claude Code</span><span class="t">按鈕會無法執行。請安裝 Claude Code，或到設定填入 claude 的路徑。</span><button class="sm" onclick="go('#/settings')">設定</button></div>`}
    <div class="shelf">
      ${books.map((b) => `
        <div class="card book" onclick="go('#/b/${enc(b.id)}')">
          <div class="title">${esc(b.name)}</div>
          <div class="hook">${esc(b.hook || "（還沒有一句話鉤子）")}</div>
          <div class="meta"><span>已寫 ${b.chapters_written} 章</span><span>${fmtNum(b.chars)} ${unitCh(b.unit)}</span>
          ${b.pending_candidates ? `<span class="badge b-accent">${b.pending_candidates} 份候選稿</span>` : ""}</div>
          <div class="meta">更新於 ${fmtTime(b.updated) || "—"}</div>
        </div>`).join("")}
      <div class="card book new" id="new-book"><div class="plus">＋</div><div>開新書</div><div class="muted small">可參考另一本書</div></div>
      <div class="card book new" onclick="go('#/import')"><div class="plus">⇪</div><div>匯入舊稿</div></div>
    </div>
    ${books.length ? "" : `<div class="card" style="margin-top:16px" id="demo-card"></div>`}
    ${others.length ? `<hr class="sep"><div class="muted small">書庫裡還有這些資料夾（沒有 CLAUDE.md，不是小說專案）：</div>
      <div class="row" style="margin-top:6px">${others.map((o) => `<span class="badge">${esc(o.name)}</span>
      <button class="sm" onclick="initFolder('${esc(o.id)}')">在這裡開書</button>`).join("")}</div>` : ""}`;
  $("#new-book").onclick = newBookDialog;
  renderDemoCard();
  renderNav();
}

// 書架的「第一次使用？」卡片：預設帶目前介面語言的示範書，可改選另外兩種語言
const DEMO_LANGS = { "zh-TW": "繁體中文", en: "English", ja: "日本語" };   // i18n-skip
const DEMO_INTRO = {   // 三句各自一個翻譯 key（書名不翻成別的語言，三語的示範書各用自己的書名）
  "zh-TW": "可以先放一本示範書《退婚之後》進書架，看看各頁面長什麼樣子。示範書只是資料夾，隨時可以刪掉。",
  en: "可以先放一本示範書《The Lantern Road》進書架，看看各頁面長什麼樣子。示範書只是資料夾，隨時可以刪掉。",
  ja: "可以先放一本示範書《辺境の薬師と竜の約束》進書架，看看各頁面長什麼樣子。示範書只是資料夾，隨時可以刪掉。",
};
function renderDemoCard(lang) {
  const card = $("#demo-card");
  if (!card) return;
  lang = lang || ((window.I18N && I18N.lang) || "zh-TW");
  if (!DEMO_INTRO[lang]) lang = "zh-TW";
  card.innerHTML = `<h3>第一次使用？</h3><p class="muted">${DEMO_INTRO[lang]}</p>
    <div class="row"><select id="demo-lang">${Object.keys(DEMO_INTRO).map((l) => `<option value="${l}"${l === lang ? " selected" : ""}>${DEMO_LANGS[l]}</option>`).join("")}</select><button id="add-demo">加入示範書</button></div>`;
  $("#demo-lang").onchange = (e) => renderDemoCard(e.target.value);
  $("#add-demo").onclick = async () => { try { await api("POST", "/api/demo", { lang }); toast("已加入示範書"); refresh(); } catch (e) { fail(e); } };
}

function newBookDialog() {
  const others = (S.books || []).map((b) => `<option value="${esc(b.name)}">${esc(b.title || b.name)}</option>`).join("");
  modal(`
    <h2>開新書</h2>
    <p class="muted small">會在書庫建立資料夾，然後請 ${esc(Panel.provName())} 跟你做開書訪談（可以在右側面板上方切換執行者）。訪談問題會出現在右側面板，直接在下方回覆即可。</p>
    <label class="f"><span>書名（也是資料夾名稱）</span><input type="text" id="nb-name" placeholder="例如：退婚之後"></label>
    <label class="f"><span>寫作語言</span><select id="nb-lang"><option value="zh-TW">繁體中文</option><option value="en">English</option><option value="ja">日本語</option></select></label>
    <p class="muted small">決定這本書的提示詞和模型輸出的語言。介面語言是另外的設定（右下角）。</p>
    <label class="f"><span>初步構想（選填）</span><textarea id="nb-idea" rows="4" placeholder="一句話、一段簡介，或幾個關鍵字"></textarea></label>
    <label class="f"><span>參考書（選填）</span><select id="nb-ref"><option value="">（不參考）</option>${others}</select></label>
    <p class="muted small">只沿用它的<b>文風指標</b>與<b>章節結構</b>（數字），不會帶入任何名字或情節。勾選下面的選項才會請模型另外生故事骨架（約 3 次呼叫）。</p>
    <label class="f"><span><input type="checkbox" id="nb-gen"> 順便產生故事骨架（用上面的參考書，1–2 分鐘）</span></label>
    <div class="row"><span class="grow"></span><button onclick="closeModal()">取消</button><button class="primary" id="nb-go">建立並開始訪談</button></div>`,
  (el) => {
    try { const ul = localStorage.getItem("ns_lang"); if (ul) $("#nb-lang", el).value = ul; } catch (e) {}
    $("#nb-name", el).focus();
    $("#nb-go", el).onclick = async () => {
      // 先讀完表單再跳「建立中…」：那個視窗會把表單換掉，之後再讀就會拿到 null
      const name = $("#nb-name", el).value;
      const lang = $("#nb-lang", el).value;
      const ref = $("#nb-ref", el).value;
      const gen = $("#nb-gen", el).checked;
      const idea = $("#nb-idea", el).value;
      if (ref) modal(`<h2>建立中…</h2><p class="muted small">正在量參考書的文風指標與結構 DNA（大書約 20–30 秒），完成後會開始開書訪談。</p>`);
      try {
        const r = await api("POST", "/api/books", { name, idea, lang, provider: Panel.prov(), ref });
        closeModal();
        S.books = (await api("GET", "/api/books")).books;
        go("#/b/" + enc(r.id));
        if (r.job) Panel.attach(r.job);
        if (r.seeded && r.seeded.length) toast("已沿用參考書的文風指標與章節結構");
        if (gen && ref) spinoffGenerate(r.id, ref, idea);
        else if (gen && !ref) toast("要先選一本參考書", true);
      } catch (e) { closeModal(); fail(e); }
    };
  });
}

function spinoffDialog() {
  if (!S.book) return;
  const others = (S.books || []).filter((b) => b.name !== S.book);
  if (!others.length) { toast("書庫裡沒有其他書可以參考", true); return; }
  const opts = others.map((b) => `<option value="${esc(b.name)}">${esc(b.title || b.name)}</option>`).join("");
  modal(`<h2>用參考書產生故事骨架</h2>
    <p class="muted small">只沿用參考書的抽象特徵（文風、結構、視角、章節節奏），不會帶入名字或情節。請只用你自有或公有領域的作品。</p>
    <label class="f"><span>參考書</span><select id="sp-ref">${opts}</select></label>
    <label class="f"><span>補充要求（選填）</span><textarea id="sp-note" rows="2" placeholder="例如：換成校園背景、主角改成女性"></textarea></label>
    <p class="muted small">用右側目前的執行者生（約 3 次呼叫、1–2 分鐘）。Claude Code 不行，要先切成 API 執行者。</p>
    <div class="row"><span class="grow"></span><button onclick="closeModal()">取消</button><button class="primary" id="sp-go">產生骨架</button></div>`,
  (el) => {
    $("#sp-go", el).onclick = () => {
      const ref = $("#sp-ref", el).value, note = $("#sp-note", el).value;
      closeModal();
      spinoffGenerate(S.book, ref, note);
    };
  });
}

async function spinoffGenerate(id, source, note) {
  const t0 = Date.now();
  modal(`<h2>正在產生故事骨架</h2>
    <p class="muted small">用《${esc(source)}》的文風指紋與結構 DNA 產生；約 1–2 分鐘（大書量指紋會久一點）。</p>
    <p><b id="sp-stage">排隊中…</b> <span class="muted small" id="sp-elapsed">${t("已 {0} 秒", 0)}</span></p>
    <p class="muted small">這個視窗可以留著看進度；草稿會寫到 <code>候選/新書草稿/</code>，不會自動套用。</p>`);
  const setStage = (s) => { const el = $("#sp-stage"); if (el) el.textContent = s; };
  const tick = setInterval(() => {
    const el = $("#sp-elapsed");
    if (el) el.textContent = t("已 {0} 秒", Math.floor((Date.now() - t0) / 1000));
  }, 500);
  try {
    const start = await api("POST", `/api/books/${enc(id)}/spinoff`, { source, note, provider: Panel.prov() });
    setStage(start.stage || "執行中…");
    let st = { status: "running" };
    while (st.status === "running") {
      await new Promise((r) => setTimeout(r, 1200));
      st = await api("GET", `/api/books/${enc(id)}/spinoff/${enc(start.task)}`);
      setStage(st.stage || "執行中…");
    }
    clearInterval(tick);
    if (st.status === "error") {
      modal(`<h2>產生失敗</h2><p style="color:#b45309">${esc(st.error || "未知錯誤")}</p>
        <div class="row"><span class="grow"></span><button class="primary" onclick="closeModal()">知道了</button></div>`);
      toast("骨架沒有產生", true);
      return;
    }
    const r = st.result || {};
    const bad = (r.guard && r.guard["撞到名字"]) || [];
    modal(`<h2>故事骨架草稿</h2>
      <p class="muted small">已寫到 <code>${esc(r.draft || "")}</code>。看完滿意再貼進「設定」與「大綱」——工作台不會自動套用。</p>
      ${bad.length ? `<p class="muted small" style="color:#b45309">護欄：有名字和參考書重複（${esc(bad.join("、"))}），請手動改掉。</p>` : ""}
      <div class="md">${md(r.preview || "")}</div>
      <div class="row"><span class="grow"></span><button class="primary" onclick="closeModal()">知道了</button></div>`);
    toast(bad.length ? "骨架生成了，但有撞名要處理" : "骨架草稿已產生", bad.length > 0);
  } catch (e) { clearInterval(tick); fail(e); }
}
/* ------------------------------------------------------------------ 卷末體檢（漂移報告） */
async function viewDrift(view, fromQ, toQ) {
  const ov = await api("GET", B("/overview")).catch(() => ({}));
  const latest = ov.latest || 1;
  const from = parseInt(fromQ || Math.max(1, latest - 9));
  const to = parseInt(toQ || latest);
  view.innerHTML = `
    <div class="page-head"><div><h1>卷末體檢</h1>
      <div class="sub">拿設定回頭對正文：哪幾章沒寫到章綱、哪些角色久未登場、哪些伏筆欠帳、哪些章文風偏了。本機計算，不花錢。</div></div></div>
    <div class="card">
      <div class="row" style="align-items:flex-end">
        <label class="f" style="width:120px"><span>從第幾章</span><input type="number" id="dr-from" value="${from}"></label>
        <label class="f" style="width:120px"><span>到第幾章</span><input type="number" id="dr-to" value="${to}"></label>
        <span class="grow muted small">第一次掃一本長書約 2–10 秒（之後會快取）；掃描期間這個頁面可以切走。</span>
        <button class="primary" id="dr-go">開始檢查</button>
      </div>
    </div>
    <div id="dr-out"></div>`;
  $("#dr-go").onclick = async () => {
    const a = parseInt($("#dr-from").value) || 1, b = parseInt($("#dr-to").value) || a;
    const out = $("#dr-out");
    const t0 = Date.now();
    out.innerHTML = `<div class="card"><p class="muted">檢查第 ${a}–${b} 章…（<span id="dr-sec">0</span> 秒）</p></div>`;
    const tick = setInterval(() => { const el = $("#dr-sec"); if (el) el.textContent = ((Date.now() - t0) / 1000).toFixed(0); }, 500);
    try {
      const r = await api("GET", `${B("/drift")}?from=${a}&to=${b}`);
      clearInterval(tick);
      out.innerHTML = `<div class="card"><div class="md">${md(r.report)}</div>
        <div class="row" style="margin-top:10px">
          <span class="grow"></span>
          <button id="dr-plan">產生卷綱更新草稿（用 ${esc(Panel.provName())}）</button>
        </div>
        <div id="dr-plan-out"></div></div>`;
      $("#dr-plan").onclick = async () => {
        const box = $("#dr-plan-out");
        const t1 = Date.now();
        box.innerHTML = `<p class="muted">產生中…（通常 30–90 秒，推理模型會久一點；<span id="dr-sec2">0</span> 秒）</p>`;
        const tick2 = setInterval(() => { const el = $("#dr-sec2"); if (el) el.textContent = ((Date.now() - t1) / 1000).toFixed(0); }, 500);
        try {
          const p = await api("POST", B("/drift/plan"), { from: a, to: b, provider: Panel.prov() });
          clearInterval(tick2);
          if (p.error) {
            box.innerHTML = `<p class="muted small" style="color:#b45309">產生失敗：${esc(p.error)}</p>
              <p class="muted small">沒有存任何草稿，卷綱也沒動。可以再試一次，或換一個執行者。</p>`;
            return;
          }
          box.innerHTML = `<div class="md">${md(p.plan_md)}</div>
            <div class="row"><span class="grow"></span><button id="dr-apply">附加到卷綱</button></div>
            <p class="muted small">附加＝在 <code>${esc(p.volume_file)}</code> 末尾加一節，不會覆蓋原本的卷綱。</p>`;
          $("#dr-apply").onclick = async () => {
            try {
              const res = await api("POST", B("/drift/apply"), { from: a, to: b, draft: p.draft });
              toast("已附加到 " + res.volume_file);
              box.innerHTML = `<p class="muted">已附加到 <code>${esc(res.volume_file)}</code>（原本的內容沒動）。</p>`;
            } catch (e) { fail(e); }
          };
        } catch (e) { clearInterval(tick2); fail(e); }
      };
    } catch (e) { clearInterval(tick); fail(e); }
  };
}

window.initFolder = async (id) => {
  go("#/b/" + enc(id));
  setTimeout(() => Panel.openForm("setup_new"), 300);
};

/* ------------------------------------------------------------------ 總覽 */
async function viewOverview(view) {
  const ov = await api("GET", B("/overview"));
  if (!S.books.length) S.books = (await api("GET", "/api/books")).books;
  if (!ov.is_book) {
    view.innerHTML = `<div class="page-head"><div><h1>${esc(S.book)}</h1><div class="sub">這個資料夾還不是小說專案</div></div></div>
      <div class="card"><p>還沒有 CLAUDE.md。開書訪談完成後，這裡就會出現進度與資料。</p>
      <div class="row"><button class="primary" onclick="Panel.openForm('setup_new')">開始開書訪談</button></div></div>`;
    return;
  }
  const sc = ov.status_count, total = Math.max(ov.chapters, 1);
  const seg = (n, cls) => n ? `<div class="${cls}" style="width:${(n / total) * 100}%"></div>` : "";
  S.bookLang = ov.lang || S.bookLang;
  const [, stateBody] = splitFM(ov.state_card || "");
  const next = ov.next;
  setTimeout(() => { const sel = $("#book-lang"); if (sel) sel.value = ov.lang || "zh-TW"; }, 0);
  setTimeout(() => renderPipe(), 0);
  view.innerHTML = `
    <div class="page-head">
      <div><h1>${esc(S.book)}</h1><div class="sub">${esc(ov.hook || "")}</div>
        <div class="sub small"><label>寫作語言：<select id="book-lang" onchange="setBookLang(this.value)"><option value="zh-TW">繁體中文</option><option value="en">English</option><option value="ja">日本語</option></select></label></div></div>
      <div class="row">
        ${next.has_card
          ? `<button class="primary" onclick="Panel.openForm('write',{from:${next.no},to:${next.no}})">寫第${next.no}章${next.title ? "《" + esc(next.title) + "》" : ""}</button>`
          : `<button class="primary" onclick="Panel.openForm('chapter_cards',{from:${next.no},to:${next.no + 9}})">排第${next.no}–${next.no + 9}章的章綱</button>`}
        <button onclick="pipeModal(${next.no})">⚡ 整章自動</button>
        <button onclick="Panel.openForm('review',{from:${Math.max(1, ov.latest - 4)},to:${Math.max(1, ov.latest)}})">審查最近章節</button>
        <button onclick="go('#/b/' + enc(S.book) + '/drift')">卷末體檢</button>
      </div>
    </div>
    <div class="pipe-box"></div>
    <div class="grid g4">
      <div class="card stat"><div class="num">${ov.written}</div><div class="lbl">已寫章數</div></div>
      <div class="card stat"><div class="num">${fmtNum(ov.chars)}</div><div class="lbl">${ov.unit === "words" ? "正文詞數" : "正文字數"}</div></div>
      <div class="card stat"><div class="num">${ov.chapters}</div><div class="lbl">已規劃章數（含章綱）</div></div>
      <div class="card stat"><div class="num">${next.no}</div><div class="lbl">下一章 ${next.has_card ? statusBadge(next.card_status) : '<span class="badge b-bad">沒有章綱</span>'}</div></div>
    </div>
    <div class="card" style="margin-top:14px">
      <div class="card-title"><h2>章綱進度</h2><a href="#/b/${enc(S.book)}/chapters">看全部章節 →</a></div>
      <div class="progress">${seg(sc["已寫"], "c-written")}${seg(sc["已確認"], "c-confirmed")}${seg(sc["草稿"], "c-draft")}${seg(sc["無章綱"], "c-none")}</div>
      <div class="legend"><span><i class="c-written"></i>已寫 ${sc["已寫"] || 0}</span><span><i class="c-confirmed"></i>章綱已確認 ${sc["已確認"] || 0}</span>
        <span><i class="c-draft"></i>章綱草稿 ${sc["草稿"] || 0}</span>${sc["無章綱"] ? `<span><i class="c-none"></i>有正文無章綱 ${sc["無章綱"]}</span>` : ""}</div>
    </div>
    <div class="grid g2" style="margin-top:14px">
      <div class="card">
        <div class="card-title"><h2>需要注意</h2><span class="badge">${ov.alerts.length}</span></div>
        ${ov.alerts.length ? ov.alerts.map(alertHtml).join("") : '<div class="muted">一切正常。</div>'}
      </div>
      <div class="card state">
        <div class="card-title"><h2>狀態卡</h2><a href="#/b/${enc(S.book)}/tracking?t=state">開啟 →</a></div>
        <div class="md"${LA()}>${stateBody.trim() ? md(stateBody) : '<span class="muted">還沒有狀態卡。寫完第一章後會自動產生。</span>'}</div>
      </div>
    </div>
    ${ov.recent.length ? `<div class="card" style="margin-top:14px"><div class="card-title"><h2>最近章節</h2></div>
      <table>${ov.recent.map((c) => `<tr class="click" onclick="go('#/b/${enc(S.book)}/ch/${c.no}')"><td>第${c.no}章</td><td>${esc(c.title)}</td><td class="num">${fmtNum(c.chars)} ${unitCh(ov.unit)}</td></tr>`).join("")}</table></div>` : ""}`;
}
window.setBookLang = async (v) => {
  try {
    await api("POST", B("/lang"), { lang: v }); S.bookLang = v; toast("已改成 " + ({ "zh-TW": "繁體中文", en: "English", ja: "日本語" })[v]);
    S.books = (await api("GET", "/api/books")).books;      // 字數單位跟著語言換（字／詞）
    route && route();
  }
  catch (e) { fail(e); route && route(); }
};
function alertHtml(a) {
  let btn = "";
  if (a.chapter) btn = `<button class="sm" onclick="go('#/b/${enc(S.book)}/ch/${a.chapter}?tab=${a.tab || "candidate"}')">${a.tab === "revision" ? "確認" : "審閱"}</button>`;
  else if (a.action === "recoveries") btn = `<button class="sm" onclick="go('#/b/${enc(S.book)}/jobs')">查看</button>`;
  else if (a.action === "sync_tracking") btn = `<button class="sm" onclick="Panel.run('sync_tracking',{})">補齊</button>`;
  else if (a.action === "rewriteback") btn = `<button class="sm" onclick="if(confirm('重跑第${a.chapter_no}章的回寫追蹤？會依正文重新整理這章的摘要、伏筆、時間線、角色狀態等。'))Panel.run('accept',{chapter:${a.chapter_no},path:'${esc(a.path || "")}'})">重跑回寫</button>`;
  else if (a.action === "reverse") btn = `<button class="sm primary" onclick="go('#/b/${enc(S.book)}/reverse')">前往</button>`;
  else if (a.kind === "懸念久未回收") btn = `<button class="sm" onclick="go('#/b/${enc(S.book)}/tracking?t=reader')">查看</button>`;
  else if (a.kind === "設定草稿") btn = `<button class="sm" onclick="go('#/b/${enc(S.book)}/bible?t=草稿')">查看</button>`;
  else if (a.kind.startsWith("伏筆")) btn = `<button class="sm" onclick="go('#/b/${enc(S.book)}/tracking')">查看</button>`;
  const more = a.details && a.details.length > 1
    ? `<details class="small" style="margin-top:4px"><summary>展開 ${a.details.length} 項</summary>${a.details.map((x) => `<div>${esc(x)}</div>`).join("")}</details>` : "";
  return `<div class="alert ${a.level}"><span class="k">${esc(a.kind)}</span><span class="t">${esc(a.text)}${more}</span>${btn}</div>`;
}

/* ------------------------------------------------------------------ 章節列表 */
async function viewChapters(view) {
  const chs = await api("GET", B("/chapters"));
  const wu = unitOfBook();
  const nextNo = chs.length ? Math.max(...chs.map((c) => c.no)) + 1 : 1;
  setTimeout(() => renderPipe(), 0);
  view.innerHTML = `
    <div class="page-head"><div><h1>章節</h1><div class="sub">共 ${chs.length} 章　·　點一列開啟</div></div>
      <div class="row"><button onclick="Panel.openForm('chapter_cards',{from:${nextNo},to:${nextNo + 9}})">排接下來 10 章</button><button onclick="pipeModal()">⚡ 整章自動</button><button class="primary" onclick="Panel.openForm('write',{from:${nextNo},to:${nextNo}})">寫第${nextNo}章</button></div></div>
    <div class="pipe-box"></div>
    <div class="card">
      ${chs.length ? `<div class="table-wrap"><table>
        <thead><tr><th>章</th><th>章名</th><th>功能</th><th>章綱</th><th style="text-align:right">${wu === "words" ? "正文詞數" : "正文字數"}</th><th>候選稿</th></tr></thead>
        <tbody>${chs.map((c) => `<tr class="click" onclick="go('#/b/${enc(S.book)}/ch/${c.no}')">
          <td>第${c.no}章</td><td>${esc(c.title)}</td><td class="muted">${esc(c.func)}</td>
          <td>${c.card_file ? statusBadge(c.card_status || "草稿") : '<span class="badge b-bad">無</span>'}</td>
          <td class="num">${c.text_file ? fmtNum(c.chars) : '<span class="muted">—</span>'}</td>
          <td>${c.candidate_file ? `<span class="badge b-accent">待審 ${fmtNum(c.candidate_chars)} ${unitCh(wu)}</span>` : ""}</td></tr>`).join("")}
        </tbody></table></div>`
        : `<div class="empty"><div class="big">☰</div>還沒有任何章綱或正文。<br><button class="primary" style="margin-top:10px" onclick="Panel.openForm('chapter_cards',{from:1,to:10})">排第一批章綱</button></div>`}
    </div>`;
}

/* ------------------------------------------------------------------ 單章 */
async function viewChapter(view, no, tab) {
  const [chs, rvRes, recs] = await Promise.all([api("GET", B("/chapters")), api("GET", B(`/revision/${no}`)).catch(() => ({})),
    api("GET", B("/recoveries")).catch(() => [])]);
  const c = chs.find((x) => x.no === no) || { no, title: "" };
  const rv = rvRes.revision;
  const myRecs = recs.filter((r) => Number(r.chapter) === no);
  const idx = chs.findIndex((x) => x.no === no);
  const prev = chs[idx - 1], next = chs[idx + 1];
  const tabs = [];
  if (c.card_file) tabs.push(["card", "章綱", c.card_file]);
  if (c.text_file) tabs.push(["text", "正文", c.text_file]);
  if (c.candidate_file) tabs.push(["candidate", "候選稿", c.candidate_file]);
  if (c.summary_file) tabs.push(["summary", "摘要", c.summary_file]);
  if (rv) tabs.push(["revision", "修訂對照", null]);
  if (c.text_file || c.candidate_file) tabs.push(["illust", "插圖", null]);
  if (!tab || !tabs.find((t) => t[0] === tab)) tab = (tabs.find((t) => t[0] === "candidate") || tabs.find((t) => t[0] === "text") || tabs[0] || [])[0];
  const cur = tabs.find((t) => t[0] === tab);
  const base = `#/b/${enc(S.book)}/ch/${no}`;
  view.innerHTML = `
    <div class="page-head">
      <div><div class="muted small"><a href="#/b/${enc(S.book)}/chapters">章節</a> ／ 第${no}章</div>
        <h1>第${no}章　${esc(c.title)}</h1></div>
      <div class="row">
        ${prev ? `<button class="ghost" onclick="go('#/b/${enc(S.book)}/ch/${prev.no}')">← 第${prev.no}章</button>` : ""}
        ${next ? `<button class="ghost" onclick="go('#/b/${enc(S.book)}/ch/${next.no}')">第${next.no}章 →</button>` : ""}
      </div>
    </div>
    <div class="row" style="margin-bottom:12px">
      ${!c.text_file && !c.candidate_file && c.card_file ? `<button class="primary" onclick="Panel.openForm('write',{from:${no},to:${no}})">寫這章</button>` : ""}
      ${!c.card_file ? `<button onclick="Panel.openForm('chapter_cards',{from:${no},to:${no}})">補這一章的章綱</button>` : ""}
      ${!c.text_file || c.candidate_file ? `<button onclick="pipeModal(${no})">⚡ 整章自動${c.candidate_file ? "（從核對開始）" : ""}</button>` : ""}
      ${c.text_file ? `<button onclick="Panel.openForm('revise',{chapter:${no}})">改稿</button>
        <button onclick="Panel.run('review_notes',{chapter:${no}})">審查</button>
        <button onclick="Panel.openForm('deslop',{chapter:${no}})">去 AI 味</button>` : ""}
    </div>
    ${tabs.length ? `<div class="tabs">${tabs.map(([k, l]) => `<button class="tab ${k === tab ? "active" : ""}" onclick="go('${base}?tab=${k}')">${l}</button>`).join("")}</div>` : ""}
    ${tab === "candidate" ? `<div class="alert info" style="margin-bottom:12px"><span class="k">候選稿</span><span class="t">審閱後按「採用」移入正文並回寫追蹤；不滿意就「退回」並寫下意見，AI 會改寫。</span>
        <button class="ok sm" id="cand-accept">採用</button><button class="sm" id="cand-reject">退回重寫</button>
        <button class="sm" onclick="Panel.openForm('deslop',{chapter:${no},candidate:true})">去 AI 味</button>
        <button class="sm danger" id="cand-discard">捨棄</button></div>` : ""}
    ${myRecs.map((r) => `<div class="alert warn" style="margin-bottom:10px"><span class="k">恢復稿</span>
        <span class="t">${esc(r.label)}中斷（${esc(r.reason)}），保留了 ${fmtNum(r.chars)} 字。</span>
        <button class="sm primary" onclick="Panel.run('recover_continue',{id:'${esc(r.id)}'})">接著寫完</button>
        <button class="sm" onclick="recoverTo('${esc(r.id)}')">直接存成候選稿</button>
        <button class="sm" onclick="recoverView('${esc(r.id)}')">查看</button>
        <button class="sm danger" onclick="recoverDiscard('${esc(r.id)}')">捨棄</button></div>`).join("")}
    ${rv && tab !== "revision" ? `<div class="alert info" style="margin-bottom:10px"><span class="k">待確認修訂</span><span class="t">有一份修訂（${rv.changes} 處變更）等你逐段確認。</span><button class="sm" onclick="go('${base}?tab=revision')">開啟</button></div>` : ""}
    <div class="pipe-box"></div>
    <div id="struct-box"></div>
    <div id="goal-box"></div>
    <div id="review-box"></div>
    <div id="doc"></div>`;
  renderPipe();
  if (tab === "card") renderChapterStructure($("#struct-box"), no);
  if (tab === "revision") return renderRevision($("#doc"), no, rv);
  if (tab === "illust") return renderIllust($("#doc"), "chapter:" + no, { chapter: no });
  if (c.card_file && (tab === "text" || tab === "candidate")) renderGoals($("#goal-box"), no, tab === "candidate", cur && cur[2]);
  if (tab === "text" || tab === "candidate") renderReview($("#review-box"), no, tab === "candidate", cur && cur[2]);
  if (cur) await docView($("#doc"), cur[2], { prose: tab === "text" || tab === "candidate", checkable: tab === "text" || tab === "candidate" });
  else $("#doc").innerHTML = `<div class="card empty">這章還沒有任何檔案。</div>`;
  if (tab === "candidate") {
    $("#cand-accept").onclick = async () => {
      if (!confirm(`採用第${no}章？候選稿會移到正文，並請 ${Panel.provName()} 回寫追蹤資料。`)) return;
      try { const r = await api("POST", B(`/candidate/${no}/accept?provider=${enc(stepProv("accept"))}`)); Panel.attach(r.job); go(`${base}?tab=text`); } catch (e) { fail(e); }
    };
    $("#cand-reject").onclick = () => modal(`<h2>退回第${no}章候選稿</h2>
      <label class="f"><span>要怎麼改？寫得越具體越好</span><textarea id="rj-note" rows="5" placeholder="例如：林晚太早亮出底牌了，改成先讓掌櫃說漏嘴"></textarea></label>
      <div class="row"><span class="grow"></span><button onclick="closeModal()">取消</button><button class="primary" id="rj-go">退回重寫</button></div>`, (el) => {
      $("#rj-go", el).onclick = async () => {
        try { const r = await api("POST", B(`/candidate/${no}/reject`), { note: $("#rj-note", el).value, provider: Panel.prov() }); closeModal(); Panel.attach(r.job); } catch (e) { fail(e); }
      };
    });
    $("#cand-discard").onclick = async () => {
      if (!confirm("捨棄這份候選稿？（會移到 .studio/備份，不會永久刪除）")) return;
      try { await api("POST", B(`/candidate/${no}/discard`)); toast("已捨棄"); go(base); } catch (e) { fail(e); }
    };
  }
}

/* ------------------------------------------------------------------ 整章自動流程 */
const PIPE = { data: null, timer: null, book: null, lastJob: null, lastStatus: null };
const PIPE_ICON = { done: "✓", skipped: "–", running: "●", failed: "✗", pending: "○" };
const PIPE_STATUS = { running: ["執行中", "b-accent"], paused: ["這章完成，等你繼續", "b-ok"], done: ["全部完成", "b-ok"],
  failed: ["停在失敗的步驟", "b-bad"], stopped: ["已停止", "b-warn"] };

async function pipeFetch() {
  if (!S.book) return null;
  const book = S.book;
  try {
    const r = await api("GET", B("/pipeline"));
    if (book !== S.book) return null;
    PIPE.meta = r; PIPE.data = r.pipeline; PIPE.book = book;
    PIPE.rw = null;
    if (r.pipeline && ["failed", "stopped"].includes(r.pipeline.status)) {
      try { PIPE.rw = await api("GET", B("/pipeline/rewind_check")); } catch (e) { PIPE.rw = null; }
    }
  } catch (e) { PIPE.data = null; }
  return PIPE.data;
}
async function renderPipe() {
  const boxes = document.querySelectorAll(".pipe-box");
  if (!boxes.length || !S.book) return;
  const p = PIPE.book === S.book && PIPE.data && PIPE.data.status === "running" ? PIPE.data : await pipeFetch();
  boxes.forEach((el) => { el.innerHTML = p ? pipeHtml(p) : ""; });
  pipeWatch(p);
}
function pipeHtml(p) {
  const [label, cls] = PIPE_STATUS[p.status] || [p.status, ""];
  const rng = p.from === p.to ? `第${p.from}章` : `第${p.from}～${p.to}章`;
  const steps = p.steps.map((s) => `<div class="pstep ${s.status}" title="${esc(s.note || "")}">
      <span class="pi">${PIPE_ICON[s.status] || "○"}</span><span class="pl">${esc(s.label)}${s.provider || (p.step_providers || {})[s.key] ? `<span class="muted small">（${esc(provName(s.provider || p.step_providers[s.key]))}）</span>` : ""}</span>
      ${s.note ? `<span class="pn">${esc(s.note)}</span>` : ""}
      ${PIPE.rw && PIPE.rw.steps[s.key] && PIPE.rw.steps[s.key].ok ? `<button class="sm ghost" style="white-space:nowrap;align-self:flex-start;margin-top:4px" title="還原到這一步開始前的候選稿，從這裡重跑" onclick="pipeRewind('${s.key}')">↺ 重跑</button>` : ""}</div>`).join("");
  const btns = [];
  if (p.status === "running") {
    if (p.job) btns.push(`<button class="sm" onclick="pipeShowJob('${esc(p.job)}')">看目前這一步</button>`);
    btns.push(`<button class="sm danger" onclick="pipeStop()">停止</button>`);
  } else {
    if (p.status === "failed" || p.status === "stopped") btns.push(`<button class="sm primary" onclick="pipeResume()">從這一步繼續</button>`);
    if (p.status === "paused") btns.push(`<button class="sm primary" onclick="pipeResume()">繼續下一章（第${p.chapter}章）</button>`);
    btns.push(`<button class="sm ghost" onclick="pipeClear()">關閉</button>`);
  }
  return `<div class="card pipe ${p.status}">
    <div class="row"><b>⚡ 整章自動流程</b><span class="muted small">${rng}${p.status === "running" || p.status === "failed" || p.status === "stopped" ? `　·　目前第${p.chapter}章` : ""}　·　${p.mode === "continue" ? "連續寫" : "寫一章停一章"}　·　自動勾選：${esc((p.severities || []).join("、") || "無")}</span>
      <span class="badge ${cls}">${label}</span><span class="grow"></span>${btns.join("")}</div>
    ${p.status === "paused" || p.status === "done" ? `<div class="muted small" style="margin-top:6px">${esc(p.message || "")}${p.done_chapters && p.done_chapters.length ? `　已定稿：${p.done_chapters.map((n) => `<a href="#/b/${enc(S.book)}/ch/${n}?tab=text">第${n}章</a>`).join("、")}` : ""}</div>` : ""}
    ${p.status === "failed" ? `<div class="alert bad" style="margin:8px 0 0"><span class="k">失敗</span><span class="t">${esc(p.error)}</span></div>` : ""}
    ${p.status === "stopped" && p.message ? `<div class="muted small" style="margin-top:6px">${esc(p.message)}</div>` : ""}
    ${p.status === "paused" || p.status === "done" ? "" : `<div class="psteps">${steps}</div>`}
  </div>`;
}
function pipeWatch(p) {
  const running = p && p.status === "running";
  if (running && !PIPE.timer) PIPE.timer = setInterval(pipeTick, 1500);
  if (!running && PIPE.timer) { clearInterval(PIPE.timer); PIPE.timer = null; }
  if (p && running && p.job && p.job !== PIPE.lastJob) {
    PIPE.lastJob = p.job;
    if (!S.job || S.job.id !== p.job || S.job.status !== "running") pipeShowJob(p.job, true);
  }
}
async function pipeTick() {
  const before = PIPE.data && PIPE.data.status;
  const p = await pipeFetch();
  document.querySelectorAll(".pipe-box").forEach((el) => { el.innerHTML = p ? pipeHtml(p) : ""; });
  pipeWatch(p);
  if (before === "running" && (!p || p.status !== "running")) {
    if (p && p.status === "failed") toast("整章自動流程停住了：" + p.error, true);
    else if (p && (p.status === "paused" || p.status === "done")) toast(p.message || "完成");
    if (!document.querySelector("textarea.editor")) refresh();
  }
}
async function pipeShowJob(id, quiet) {
  try {
    const j = await api("GET", B("/jobs/" + id));
    if (j.status === "running") Panel.attach(j, quiet, !!quiet);
    else if (!quiet || !S.job || S.job.status !== "running") Panel.show(id);
  } catch (e) { /* ignore */ }
}
async function pipeStop() {
  if (!confirm("停止整章自動流程？目前這一步會中斷，之後可以從這一步繼續。")) return;
  try { await api("POST", B("/pipeline/stop")); toast("正在停止……"); } catch (e) { fail(e); }
}
async function pipeResume() {
  try { const r = await api("POST", B("/pipeline/resume"), { provider: Panel.prov() }); PIPE.data = r.pipeline; renderPipe(); } catch (e) { fail(e); }
}
async function pipeClear() {
  try { await api("POST", B("/pipeline/clear")); PIPE.data = null; renderPipe(); } catch (e) { fail(e); }
}
function pipeRewind(key) {
  const p = PIPE.data;
  if (!p) return;
  const st = p.steps.find((x) => x.key === key);
  const later = p.steps.slice(p.steps.findIndex((x) => x.key === key)).map((x) => x.label);
  const canNote = PIPE.rw && (PIPE.rw.note_steps || []).includes(key);
  const what = key === "card" ? "第" + p.chapter + "章的章綱和候選稿會先備份再移開，請 AI 重寫章綱"
    : key === "write" ? "第" + p.chapter + "章的候選稿會先備份再移開，請 AI 重新寫一份"
    : "候選稿會還原成「" + st.label + "」開始前的版本（目前的候選稿先備份）";
  modal(`<h2>↺ 從「${esc(st.label)}」重跑</h2>
    <p class="small">${esc(what)}。</p>
    <p class="small muted">之後這幾步的結果會先備份到 .studio/備份/ 再清掉，然後重新執行：${later.map(esc).join(" → ")}</p>
    ${canNote ? `<label class="f"><span>這次的要求（選填，只用在「${esc(st.label)}」這一步）</span><textarea id="rw-note" rows="2" placeholder="例如：保留更多對白；這次節奏放慢"></textarea></label>` : ""}
    <div class="row" style="margin-top:12px"><span class="grow"></span><button onclick="closeModal()">取消</button><button class="primary" id="rw-go">重跑</button></div>`, (el) => {
    $("#rw-go", el).onclick = async () => {
      try {
        const r = await api("POST", B("/pipeline/rewind"), { step: key, note: canNote ? $("#rw-note", el).value : "" });
        closeModal();
        PIPE.data = r.pipeline; PIPE.rw = null; PIPE.lastJob = null;
        toast("從「" + st.label + "」重跑");
        renderPipe();
      } catch (e) { fail(e); }
    };
  });
}
async function pipeModal(no) {
  const [r, chs] = await Promise.all([api("GET", B("/pipeline")), api("GET", B("/chapters"))]);
  if (r.pipeline && r.pipeline.status === "running") return toast("已經有整章自動流程在執行", true);
  const firstOpen = (chs.find((c) => !c.text_file || c.candidate_file) || { no: (chs.length ? chs[chs.length - 1].no + 1 : 1) }).no;
  no = no || firstOpen;
  const lastCard = Math.max(no, ...chs.filter((c) => c.card_file).map((c) => c.no));
  const d = r.defaults;
  modal(`<h2>⚡ 整章自動流程</h2>
    <p class="muted small">每章依序：${r.steps.map((s) => esc(s.label)).join(" → ")}。<br>已有章綱就不重寫；已有候選稿就從核對開始。每一步各自呼叫一次 AI；任何一步失敗都會停在那一步，修正後可以從那一步繼續。</p>
    <div class="row"><span class="small muted">從第</span><input type="number" id="pp-from" class="num-in" value="${no}" min="1"><span class="small muted">章到第</span>
      <input type="number" id="pp-to" class="num-in" value="${no}" min="1"><span class="small muted">章</span>
      <span class="muted small">（章綱寫到第${lastCard}章）</span></div>
    <div class="f" style="margin-top:12px"><span>跑法</span></div>
    <div class="seg compact" id="pp-mode">
      <label><input type="radio" name="pp-mode" value="stop" ${d.mode !== "continue" ? "checked" : ""}><span>寫一章停一章</span></label>
      <label><input type="radio" name="pp-mode" value="continue" ${d.mode === "continue" ? "checked" : ""}><span>連續寫到最後一章</span></label>
    </div>
    <div class="f" style="margin-top:12px"><span>自動勾選哪些等級的審查意見（交給修訂）</span></div>
    <div class="row" id="pp-sev">${r.severities.map((x) => `<label class="cb"><input type="checkbox" value="${x}" ${d.severities.includes(x) ? "checked" : ""}> ${x}</label>`).join("")}</div>
    <label class="f" style="margin-top:8px"><span>對整個流程的要求（選填，每一步都會帶上）</span><textarea id="pp-note" rows="2" placeholder="例如：這幾章節奏要快；不要新增角色"></textarea></label>
    <label class="f"><span>執行者</span>${provSelectHtml("pp-prov")}</label>
    ${Object.keys(d.step_providers || {}).length ? `<div class="muted small">各步驟另外指定：${AI_STEP_LABELS.filter(([k]) => (d.step_providers || {})[k]).map(([k, l]) => `${esc(l)} → ${esc(provName(d.step_providers[k]))}`).join("、")}；其他步驟用上面選的執行者。（設定 → 整章自動流程）</div>` : ""}
    <div class="row" style="margin-top:14px"><span class="grow"></span><button onclick="closeModal()">取消</button><button class="primary" id="pp-go">開始</button></div>`, (el) => {
    $("#pp-go", el).onclick = async () => {
      try {
        const body = { from: parseInt($("#pp-from", el).value), to: parseInt($("#pp-to", el).value) || parseInt($("#pp-from", el).value),
          mode: el.querySelector('input[name="pp-mode"]:checked').value,
          severities: [...el.querySelectorAll("#pp-sev input:checked")].map((x) => x.value),
          note: $("#pp-note", el).value, provider: $("#pp-prov", el).value };
        if (!body.from) return toast("請輸入章號", true);
        const res = await api("POST", B("/pipeline"), body);
        closeModal();
        PIPE.data = res.pipeline; PIPE.book = S.book; PIPE.lastJob = null;
        toast("開始整章自動流程");
        if (!document.querySelector(".pipe-box")) go(`#/b/${enc(S.book)}/ch/${body.from}`); else renderPipe();
      } catch (e) { fail(e); }
    };
  });
}
window.pipeModal = pipeModal; window.pipeStop = pipeStop; window.pipeResume = pipeResume; window.pipeClear = pipeClear; window.pipeShowJob = pipeShowJob;

/* ------------------------------------------------------------------ 文件檢視／編輯 */
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
  const fbase = opts.base || B("");
  let f;
  try { f = await api("GET", fbase + "/file?path=" + enc(path)); }
  catch (e) { el.innerHTML = `<div class="card empty">${esc(e.message)}</div>`; return; }
  let editing = false, findings = null;
  let fm, body;
  [fm, body] = splitFM(f.text);
  const render = () => {
    const fmHtml = Object.keys(fm).length ? `<div class="fm">${Object.entries(fm).filter(([, v]) => v !== "" && v !== "[]")
      .map(([k, v]) => `<span class="badge">${esc(I18N.t(String(k)))}：${esc(I18N.t(String(v)))}</span>`).join("")}</div>` : "";
    el.innerHTML = `
      <div class="doc-wrap ${findings ? "with-side" : ""}">
        <div class="card">
          <div class="doc-bar">
            <span class="path">${esc(f.path)}</span>${opts.prose ? `<span class="badge">${fmtNum(f.chars)} ${unitCh(unitOfBook())}</span>` : ""}
            <span class="grow"></span>
            ${opts.checkable ? `<button class="sm" data-a="check">檢查用語與 AI 味</button>` : ""}
            ${f.readonly || opts.readonly ? "" : editing ? `<button class="sm" data-a="cancel">取消</button><button class="sm primary" data-a="save">儲存</button>`
              : `<button class="sm" data-a="edit">編輯</button>`}
          </div>
          ${editing ? `<textarea class="editor ${opts.prose ? "prose" : ""}"${LA()} spellcheck="false">${esc(f.text)}</textarea>`
            : `${fmHtml}<div class="md ${opts.prose ? "prose" : ""}"${opts.prose ? LP() : LA()}>${md(body)}</div>`}
        </div>
        ${findings ? `<div class="card"><div class="card-title"><h3>檢查結果</h3><button class="ghost sm" data-a="closecheck">✕</button></div>
          <div class="small muted">中文字數 ${fmtNum(findings["中文字數"])}</div>
          <div class="findings">${findings["問題"].length ? findings["問題"].map((x, i) => `
            <div class="finding" data-i="${i}"><span class="ln">${x["行"] ? "第" + x["行"] + "行" : "全章"}</span>
            <span><span class="badge ${x["等級"] === "必須修" ? "b-bad" : x["等級"] === "建議修" ? "b-warn" : ""}">${esc(x["等級"])}</span>
            ${esc(x["類型"])}：${esc(x["片段"])}<div class="muted small">${esc(x["建議"])}</div></span></div>`).join("")
            : '<div class="muted">沒有發現問題。</div>'}</div>
          ${findings["問題"].length ? `<button class="sm" style="margin-top:8px" onclick="Panel.openForm('deslop',{chapter:${parseInt((f.path.match(/第0*(\d+)章/) || [])[1]) || 1},candidate:${f.path.startsWith("候選")}})">請 Claude 處理</button>` : ""}
        </div>` : ""}
      </div>`;
    if (!opts.prose && !editing) localizeLabels(el.querySelector(".md"));
    el.querySelectorAll("[data-a]").forEach((b) => b.onclick = () => act(b.dataset.a));
    el.querySelectorAll(".finding").forEach((d) => d.onclick = () => jump(findings["問題"][d.dataset.i]["行"]));
    if (editing) {
      const ta = $("textarea.editor", el);
      ta.addEventListener("keydown", (e) => { if ((e.ctrlKey || e.metaKey) && e.key === "s") { e.preventDefault(); act("save"); } });
    }
  };
  const jump = (line) => {
    if (!line) return;
    if (!editing) { editing = true; render(); }
    const ta = $("textarea.editor", el);
    const lines = ta.value.split("\n");
    let start = 0;
    for (let i = 0; i < line - 1 && i < lines.length; i++) start += lines[i].length + 1;
    ta.focus();
    ta.setSelectionRange(start, start + (lines[line - 1] || "").length);
    const lh = parseFloat(getComputedStyle(ta).lineHeight) || 24;
    ta.scrollTop = Math.max(0, (line - 4) * lh);
  };
  const act = async (a) => {
    if (a === "edit") { editing = true; render(); }
    else if (a === "cancel") { editing = false; render(); }
    else if (a === "closecheck") { findings = null; render(); }
    else if (a === "check") {
      try { findings = await api("POST", B("/check"), { path: f.path }); render(); } catch (e) { fail(e); }
    } else if (a === "save") {
      const text = $("textarea.editor", el).value;
      try {
        const r = await api("PUT", fbase + "/file", { path: f.path, text, mtime: f.mtime });
        toast("已儲存");
        f = await api("GET", fbase + "/file?path=" + enc(path));
        [fm, body] = splitFM(f.text);
        editing = false;
        if (findings) findings = await api("POST", B("/check"), { path: f.path });
        render();
        if (opts.onSaved) opts.onSaved(r);
      } catch (e) { fail(e); }
    }
  };
  render();
}


/* ------------------------------------------------------------------ 章綱核對 */
async function renderGoals(el, no, candidate, path) {
  let d;
  try { d = await api("GET", B(`/goals/${no}`)); } catch (e) { return; }
  if (!d.goals.length) return;
  const r = d.result && d.result.path === path ? d.result : null;
  const icon = { completed: ["✓", "b-ok"], unmet: ["✗", "b-bad"], unverified: ["？", "b-warn"], unknown: ["－", ""] };
  const lbl = { completed: "已寫到", unmet: "沒寫到", unverified: "引文對不上", unknown: "無法判斷" };
  const sm = r ? r.summary : null;
  el.innerHTML = `<details class="card goal-card" ${r && (sm.unmet || sm.unverified) ? "open" : ""} style="margin-bottom:14px">
    <summary class="row"><b>章綱核對</b>
      ${r ? `<span class="badge b-ok">已寫到 ${sm.completed}</span>${sm.unmet ? `<span class="badge b-bad">沒寫到 ${sm.unmet}</span>` : ""}${sm.unverified ? `<span class="badge b-warn">引文對不上 ${sm.unverified}</span>` : ""}${sm.unknown ? `<span class="badge">無法判斷 ${sm.unknown}</span>` : ""}
        <span class="muted small">${fmtTime(r.checked_at)}${r.stale ? "　稿子之後改過，結果可能過時" : ""}</span>`
        : `<span class="muted small">這份稿子還沒核對（${d.goals.length} 項）</span>`}
      <span class="grow"></span><button class="sm" onclick="event.preventDefault();Panel.run('goal_check',{chapter:${no},candidate:${candidate}})">${r ? "重新核對" : "核對章綱"}</button>
    </summary>
    <div class="goal-list">${(r ? r.items : d.goals).map((g) => {
      const st = g.status ? icon[g.status] : ["·", ""];
      return `<div class="goal-item"><span class="badge ${st[1]}" title="${g.status ? lbl[g.status] : ""}">${st[0]}</span>
        <div class="grow"><div>${esc(g.id)}　${esc(g.text)}</div>
        ${g.note && g.status !== "completed" ? `<div class="small" style="color:var(--ink-2)">→ ${esc(g.note)}</div>` : ""}
        ${(g.evidence || []).map((q) => `<div class="quote ${q.found ? "" : "bad"}" title="${q.found ? "已在正文中找到" : "正文裡找不到這句"}">${q.found ? "" : "✗ "}「${esc(q.quote)}」</div>`).join("")}</div></div>`;
    }).join("")}</div></details>`;
}

/* ------------------------------------------------------------------ 審查意見 */
async function renderReview(el, no, candidate, path) {
  let rec;
  try { rec = (await api("GET", B(`/review/${no}`))).review; } catch (e) { return; }
  if (rec && rec.path !== path) rec = null;
  const sevCls = { "必須修": "b-bad", "建議修": "b-warn", "提醒": "" };
  if (!rec) {
    el.innerHTML = `<div class="card review-card" style="margin-bottom:14px"><div class="row"><b>審查意見</b>
      <span class="muted small">審查後可以勾選要處理的意見，修訂結果會逐段讓你選擇。</span><span class="grow"></span>
      <button class="sm" onclick="Panel.run('review_notes',{chapter:${no},candidate:${candidate}})">審查這份稿子</button></div></div>`;
    return;
  }
  el.innerHTML = `<details class="card review-card" open style="margin-bottom:14px">
    <summary class="row"><b>審查意見</b><span class="muted small">${esc(rec.summary || "")}</span>
      <span class="muted small">${fmtTime(rec.checked_at)}${rec.stale ? "　稿子之後改過，意見可能過時" : ""}</span>
      <span class="grow"></span><button class="sm" onclick="event.preventDefault();Panel.run('review_notes',{chapter:${no},candidate:${candidate}})">重新審查</button></summary>
    <div class="rv-list">${rec.items.length ? rec.items.map((x) => `
      <label class="rv-item"><input type="checkbox" data-id="${esc(x.id)}" ${x.severity !== "提醒" ? "checked" : ""}>
        <div class="grow"><div><span class="badge ${sevCls[x.severity]}">${esc(x.severity)}</span> ${x.category ? `<span class="badge">${esc(x.category)}</span>` : ""} ${esc(x.issue)}</div>
          ${x.quote ? `<div class="quote ${x.located ? "" : "bad"}" title="${x.located ? "已在正文中找到" : "正文裡找不到這句"}">${x.located ? "" : "✗ "}「${esc(x.quote)}」</div>` : ""}
          ${x.suggestion ? `<div class="small" style="color:var(--ink-2)">修法：${esc(x.suggestion)}</div>` : ""}</div></label>`).join("")
      : '<div class="muted">沒有發現問題。</div>'}</div>
    <label class="f" style="margin-top:10px"><span>你自己的修改意見（選填）</span><textarea id="rv-extra" rows="2" placeholder="例如：第二場對話太長，砍一半"></textarea></label>
    <div class="row"><span class="grow"></span><button class="primary sm" id="rv-go">依勾選意見修訂</button></div>
  </details>`;
  $("#rv-go", el).onclick = () => {
    const ids = [...el.querySelectorAll("input[data-id]:checked")].map((i) => i.dataset.id);
    const extra = $("#rv-extra", el).value;
    if (!ids.length && !extra.trim()) { toast("請至少勾選一條意見，或寫下自己的意見", true); return; }
    Panel.run("revise_notes", { chapter: no, ids, extra });
  };
}

/* ------------------------------------------------------------------ 逐段對照 */
function inlineHtml(segs, side) {
  return segs.map(([op, s]) => op === "eq" ? esc(s) : (op === (side === "old" ? "del" : "ins") ? `<mark class="${op}">${esc(s)}</mark>` : "")).join("");
}
function renderRevision(el, no, rv) {
  if (!rv) { el.innerHTML = '<div class="card empty">沒有待確認的修訂。</div>'; return; }
  const choice = {};
  const ds = rv.kind === "deslop";
  const reasonsHtml = (b) => (b.reasons || []).length ? `<div class="rv-why small">${b.reasons.map((r) =>
    `<div><span class="badge b-warn">${esc(r.why || "")}</span> ${esc(r.old)} → ${esc(r.new)}</div>`).join("")}</div>` : "";
  const draw = () => {
    let n = 0;
    el.innerHTML = `
      <div class="card" style="margin-bottom:14px">
        <div class="row"><b>${ds ? "去 AI 味對照" : "修訂對照"}</b><span class="badge">${rv.changes} 處變更</span>${ds && (rv.items || []).length ? `<span class="badge">逐處清單 ${rv.items.length} 條</span>` : ""}<span class="muted small">原稿：${esc(rv.base_path)}　·　${fmtTime(rv.created)}</span>
          <span class="grow"></span><button class="sm" id="rv-all-new">全部採用修訂</button><button class="sm" id="rv-all-old">全部保留原文</button></div>
        ${rv.stale ? '<div class="alert warn" style="margin-top:8px"><span class="k">對不上</span><span class="t">原稿在修訂之後被改過了，這份修訂不能套用，請捨棄後重新修訂。</span></div>' : ""}
        <details style="margin-top:8px"${ds ? " open" : ""}><summary class="small">${ds ? "AI 的逐處清單與說明" : "處理的意見與 AI 的說明"}</summary><div class="md small"${LA()} style="margin-top:6px">${md(ds ? (rv.report || "") : "**意見**\n\n" + (rv.notes || "") + "\n\n**說明**\n\n" + (rv.report || ""))}</div></details>
        ${ds && (rv.unmatched || []).length ? `<div class="muted small" style="margin-top:6px">清單裡有 ${rv.unmatched.length} 條對不到段落（AI 抄的原句和原稿不完全一樣），只列在上面的清單裡。</div>` : ""}
      </div>
      <div class="rv-blocks">${rv.blocks.map((b) => {
        if (b.type === "same") {
          return b.old.length > 2
            ? `<details class="rv-same"><summary class="muted small">${b.old.length} 段沒有變更（展開）</summary>${b.old.map((x) => `<p${LP()}>${esc(x)}</p>`).join("")}</details>`
            : `<div class="rv-same">${b.old.map((x) => `<p${LP()}>${esc(x)}</p>`).join("")}</div>`;
        }
        const k = String(b.index); const useNew = (choice[k] || "new") === "new"; n++;
        const oldHtml = b.old.length ? b.old.map((x, i) => `<p${LP()}>${b.inline ? inlineHtml(b.inline[i], "old") : esc(x)}</p>`).join("") : '<p class="muted small">（原文沒有這段）</p>';
        const newHtml = b.new.length ? b.new.map((x, i) => `<p${LP()}>${b.inline ? inlineHtml(b.inline[i], "new") : esc(x)}</p>`).join("") : '<p class="muted small">（修訂刪掉了這段）</p>';
        return `<div class="rv-change">
          <div class="rv-side old ${useNew ? "" : "chosen"}" data-k="${k}" data-v="old"><div class="rv-tag">原文</div>${oldHtml}</div>
          <div class="rv-side new ${useNew ? "chosen" : ""}" data-k="${k}" data-v="new"><div class="rv-tag">修訂</div>${newHtml}${reasonsHtml(b)}</div>
        </div>`;
      }).join("")}</div>
      <div class="card row" style="margin-top:14px;position:sticky;bottom:10px">
        <span class="muted small">點左右兩邊選擇要的版本。${ds ? `套用後寫回 ${esc(rv.base_path)}（原檔先備份${rv.base_path.startsWith("正文") ? "；去 AI 味不改劇情，不用重跑回寫追蹤" : ""}），並跑一次保真檢查。`
          : `套用後會存成候選稿${rv.base_path.startsWith("正文") ? "（原本的正文不動，採用候選稿時才覆蓋並回寫追蹤）" : ""}。`}</span>
        <span class="grow"></span><button class="sm danger" id="rv-discard">捨棄這份${ds ? "去 AI 味結果" : "修訂"}</button>
        <button class="primary" id="rv-apply" ${rv.stale ? "disabled" : ""}>${ds ? "套用" : "套用到候選稿"}</button></div>`;
    el.querySelectorAll(".rv-side").forEach((d) => d.onclick = () => { choice[d.dataset.k] = d.dataset.v; draw(); });
    $("#rv-all-new", el).onclick = () => { rv.blocks.forEach((b) => { if (b.type === "change") choice[b.index] = "new"; }); draw(); };
    $("#rv-all-old", el).onclick = () => { rv.blocks.forEach((b) => { if (b.type === "change") choice[b.index] = "old"; }); draw(); };
    $("#rv-discard", el).onclick = async () => {
      if (!confirm("捨棄這份修訂？（會移到 .studio/備份）")) return;
      await api("POST", B(`/revision/${no}/discard`)).catch(fail); go(`#/b/${enc(S.book)}/ch/${no}`);
    };
    $("#rv-apply", el).onclick = async () => {
      try {
        const r = await api("POST", B(`/revision/${no}/apply`), { choices: choice });
        toast(`已套用：採用修訂 ${r.used_new} 處、保留原文 ${r.kept_old} 處`);
        go(`#/b/${enc(S.book)}/ch/${no}?tab=${r.kind === "deslop" && r.from_text ? "text" : "candidate"}`);
        if (r.kind === "deslop" && r.fidelity) setTimeout(() => modal(`<h2>保真檢查</h2><div class="md">${md(r.fidelity)}</div><div class="row"><span class="grow"></span><button class="primary" onclick="closeModal()">知道了</button></div>`), 800);
      } catch (e) { fail(e); }
    };
  };
  draw();
}

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
/* ------------------------------------------------------------------ 大綱 */
function volCard(v) {
  const vols = (v.volumes || []).map((x) => `<div class="row"><span>${esc(x.name)} <span class="muted small">${t("第 {0}–{1} 章", x.lo, x.hi)}${x.status ? "（" + esc(x.status) + "）" : ""}</span></span><span class="grow"></span>
    ${x.kind === "卷" ? `<button class="sm" data-revise="${x.no}">${t("修訂")}</button><button class="sm" data-sync="${x.no}">${t("同步大綱")}</button>` : ""}
    <button class="sm" data-check="${x.lo}-${x.hi}">${t("章綱體檢")}</button>
    <button class="sm" data-card="${x.lo}-${x.hi}">${t("排這一卷的章綱")}</button></div>`).join("");
  const drafts = (v.drafts || []).map((x) => `<div class="row"><span>${t("草稿")}：${esc(x.name)} <span class="muted small">${t("第 {0}–{1} 章", x.lo, x.hi)}</span></span><span class="grow"></span>
    <button class="sm" data-open="${esc(x.rel)}">${t("編輯")}</button>
    <button class="sm primary" data-adopt="${x.no}">${t("採用")}</button></div>`).join("");
  const revs = (v.revisions || []).map((x) => `<div class="row"><span>${t("卷綱修訂草稿")}：${esc(x.name)} <span class="muted small">${t("第 {0}–{1} 章", x.lo, x.hi)}</span></span><span class="grow"></span>
    <button class="sm" data-open="${esc(x.rel)}">${t("編輯")}</button>
    <button class="sm" data-diff="${x.no}">${t("看差異")}</button>
    <button class="sm primary" data-revapply="${x.no}">${t("套用修訂")}</button></div>`).join("");
  const plans = (v.plans || []).map((x) => `<div class="row"><span>${t("卷綱更新草稿")}：${esc(x.name)} <span class="muted small">${t("第 {0}–{1} 章", x.lo, x.hi)}</span></span><span class="grow"></span>
    <button class="sm" data-open="${esc(x.rel)}">${t("編輯")}</button></div>`).join("");
  return `<div class="card" id="vol-card">
    <div class="row"><b>${t("卷況")}</b><span class="grow"></span><button class="primary" id="vol-new">${t("開新卷")}</button></div>
    <div class="muted small">${t("卷綱決定這一卷的邊界；不在任何卷綱範圍內的章節，整章自動流程會拒絕。")}</div>
    <div style="margin-top:8px">${vols || `<div class="muted">${t("還沒有卷綱。")}</div>`}${drafts}${revs}${plans}</div>
    ${drafts ? `<div class="muted small">${t("採用後會寫到正式卷綱（狀態改成「已確認」），草稿會被移除。")}</div>` : ""}
    ${revs ? `<div class="muted small">${t("修訂會先產生草稿；看過差異按「套用修訂」才覆蓋正式卷綱（會先備份）。")}</div>` : ""}
  </div>`;
}
async function showRevision(no) {
  try {
    const r = await api("GET", B(`/volumes/revision/${no}`));
    const body = (r.diff || "").split("\n").map((line) => {
      const plus = line.startsWith("+") && !line.startsWith("+++");
      const minus = line.startsWith("-") && !line.startsWith("---");
      const color = plus ? "#1a7f37" : minus ? "#b42318" : "#666";
      return `<div style="color:${color};white-space:pre-wrap">${esc(line)}</div>`;
    }).join("");
    modal(`<h2>${t("卷綱修訂差異")}（第 ${no} 卷）</h2>
      <p class="muted small">${t("紅色是正式卷綱被拿掉的行，綠色是修訂後新增或改寫的行。按「套用修訂」才會覆蓋正式檔（會先備份）。")}</p>
      <div style="max-height:55vh;overflow:auto;font-family:ui-monospace,monospace;font-size:12px;line-height:1.5;background:#faf8f4;padding:8px;border-radius:6px">${body || t("沒有差異。")}</div>
      <div class="row"><span class="grow"></span><button onclick="closeModal()">${t("取消")}</button><button class="primary" onclick="applyRevision(${no})">${t("套用修訂")}</button></div>`);
  } catch (e) { fail(e); }
}

async function applyRevision(no) {
  if (!confirm(t("套用後會覆蓋正式卷綱（會先備份），確定嗎？"))) return;
  try {
    const r = await api("POST", B("/volumes/revision/apply"), { volume: no });
    const warn = (r && r.warnings) || [];
    closeModal();
    toast(warn.length ? warn.join("；") : t("已套用卷綱修訂"), warn.length > 0);
    go(location.hash);
  } catch (e) { fail(e); }
}

function bindVol(v) {
  const el = $("#vol-card");
  if (!el) return;
  const nb = $("#vol-new", el);
  if (nb) nb.onclick = () => Panel.openForm("volume_draft", { volume: v.next, from: v.from, to: v.from + 19 });
  el.querySelectorAll("[data-card]").forEach((b) => { b.onclick = () => { const [a, z] = b.dataset.card.split("-").map(Number); Panel.openForm("chapter_cards", { from: a, to: z }); }; });
  el.querySelectorAll("[data-open]").forEach((b) => { b.onclick = () => go('#/b/' + enc(S.book) + '/outline?f=' + enc(b.dataset.open)); });
  el.querySelectorAll("[data-revise]").forEach((b) => { b.onclick = () => Panel.openForm("volume_revise", { volume: b.dataset.revise }); });
  el.querySelectorAll("[data-diff]").forEach((b) => { b.onclick = () => showRevision(Number(b.dataset.diff)); });
  el.querySelectorAll("[data-revapply]").forEach((b) => { b.onclick = () => applyRevision(Number(b.dataset.revapply)); });
  el.querySelectorAll("[data-sync]").forEach((b) => {
    b.onclick = async () => {
      try {
        const r = await api("POST", B("/volumes/outline-sync"), { volume: Number(b.dataset.sync) });
        const warn = (r && r.warnings) || [];
        if (warn.length) toast(warn.join("；"), true);
        else toast(t("已同步全書大綱"));
        go(location.hash);
      } catch (e) { fail(e); }
    };
  });
  el.querySelectorAll("[data-check]").forEach((b) => {
    b.onclick = async () => {
      const [a, z] = b.dataset.check.split("-").map(Number);
      try {
        const r = await api("GET", B(`/card-check?from=${a}&to=${z}`));
        const rows = r.findings || [];
        modal(`<h2>${t("章綱體檢")}（第 ${a}–${z} 章）</h2>
          ${rows.length ? `<div class="card"><div class="small muted">${t("把設定和章綱對照：提前登場（劇透風險）與久別重逢（設定說已退場）。")}</div>
            ${rows.map((f) => `<div class="row" style="align-items:flex-start"><span class="badge">${esc(f.kind)}</span>
              <span>${t("第 {0} 章", f.chapter)}「${esc(f.name)}」：${esc(f.detail)}</span></div>`).join("")}</div>`
            : `<div class="card"><p>${t("章綱沒有發現衝突。")}</p></div>`}
          <div class="row"><span class="grow"></span><button class="primary" onclick="closeModal()">${t("知道了")}</button></div>`);
      } catch (e) { fail(e); }
    };
  });
  el.querySelectorAll("[data-adopt]").forEach((b) => {
    b.onclick = async () => {
      try {
        const r = await api("POST", B("/volumes/adopt"), { volume: Number(b.dataset.adopt) });
        const warn = (r && r.warnings) || [];
        if (warn.length) toast(warn.join("；"), true);
        else toast(t("已採用第 {0} 卷卷綱", b.dataset.adopt));
        go(location.hash);
      } catch (e) { fail(e); }
    };
  });
}
async function viewOutline(view, file) {
  const files = await api("GET", B("/outline"));
  const vol = await api("GET", B("/volumes")).catch(() => null);
  const chs = await api("GET", B("/chapters")).catch(() => []);
  const nextNo = chs.length ? Math.max(...chs.map((c) => c.no)) + 1 : 1;
  // 卷綱草稿也列進左邊的清單，點開就能看／改（存檔走 /file 的 PUT）
  const drafts = ((vol && vol.drafts) || []).map((x) => ({ name: x.name + "（" + t("草稿") + "）", file: x.rel }));
  const plans = ((vol && vol.plans) || []).map((x) => ({ name: x.name, file: x.rel }));
  const all = files.concat(drafts).concat(plans);
  if (!file && all.length) file = all[0].file;
  view.innerHTML = `
    <div class="page-head"><div><h1>大綱</h1><div class="sub">全書大綱與卷綱。章綱在「章節」頁。</div></div>
      <div class="row"><button onclick="Panel.openForm('concept')">故事核心診斷</button><button onclick="Panel.openForm('master_outline')">全書大綱</button>
      <button onclick="spinoffDialog()">參考書骨架</button><button class="primary" onclick="Panel.openForm('chapter_cards',{from:${nextNo},to:${nextNo + 9}})">排接下來 10 章</button></div></div>
    ${vol ? volCard(vol) : ""}
    <div class="split">
      <div class="list">${all.length ? all.map((x) => `<div class="item ${x.file === file ? "active" : ""}" onclick="go('#/b/${enc(S.book)}/outline?f=${enc(x.file)}')"><div class="nm">${esc(x.name)}</div></div>`).join("")
        : '<div class="muted">還沒有大綱。</div>'}
        <div class="item" onclick="go('#/b/${enc(S.book)}/bible?t=核心&f=${enc("設定/故事核心.md")}')"><div class="nm">故事核心</div><div class="ds">設定/故事核心.md</div></div>
      </div>
      <div id="doc">${file ? "" : '<div class="card empty"><div class="big">⌘</div>還沒有大綱。可以先做「故事核心診斷」，再規劃全書大綱。</div>'}</div>
    </div>`;
  if (vol) bindVol(vol);
  if (file) await docView($("#doc"), file);
}

/* ------------------------------------------------------------------ 設定集 */
/* 設定集：角色、勢力、世界觀列表的篩選與分組 */
const ROLE_ORDER = ["主角", "主要配角", "配角", "反派", "路人"];
const WORLD_CATS = ["力量體系", "地理與氣候", "歷史與年表", "社會與政治", "經濟與物資", "宗教信仰", "文化與風俗", "科技原理", "載具與兵器", "生態與資源", "其他"];
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
function entityFilterBar(t, list, f) {
  const sel = (key, label, opts) => `<label class="ef"><span>${esc(label)}</span><select data-ef="${key}">${opts.map(([v, txt, n]) =>
    `<option value="${esc(v)}" ${(f[key] || "全部") === v ? "selected" : ""}>${esc(txt)}（${n}）</option>`).join("")}</select></label>`;
  const withAll = (arr) => [["全部", "全部", list.length], ...arr];
  let out = "";
  if (t === "角色") {
    const c = countBy(list, (e) => e.role || "未設定");
    out += sel("role", "定位", withAll([...ROLE_ORDER, "未設定"].filter((k) => c[k]).map((k) => [k, k, c[k]])));
  }
  if (t === "世界觀") {
    const c = countBy(list, (e) => e.category || "未分類");
    const extra = Object.keys(c).filter((k) => !WORLD_CATS.includes(k) && k !== "未分類");
    const keys = [...WORLD_CATS, ...extra, "未分類"].filter((k) => WORLD_CATS.includes(k) || c[k]);
    out += sel("cat", "分類", withAll(keys.map((k) => [k, k, c[k] || 0])));
  }
  const sc = countBy(list, (e) => e.status || "未設定");
  const statusOpts = ["正式", "草稿", "未設定"].filter((k) => sc[k]);
  // 已存的篩選值若已不存在（例如草稿全部轉正式後仍選「草稿」），退回「全部」，避免列表永遠是空的
  if (f.status && f.status !== "全部" && !sc[f.status]) f.status = "全部";
  if (statusOpts.length) out += sel("status", "狀態", withAll(statusOpts.map((k) => [k, k, sc[k]])));
  const tc = {};
  list.forEach((e) => (e.tags || []).forEach((x) => { tc[x] = (tc[x] || 0) + 1; }));
  const tagKeys = Object.keys(tc).sort((a, b) => tc[b] - tc[a] || a.localeCompare(b));
  if (tagKeys.length) out += sel("tag", "標籤", withAll(tagKeys.map((k) => [k, k, tc[k]])));
  const grouping = t !== "勢力" ? `<label class="ef ef-cb"><input type="checkbox" data-ef="group" ${f.group ? "checked" : ""}> 分組顯示</label>` : "";
  return `<div class="ef-bar"><label class="ef"><span>搜尋</span><input type="search" data-ef="q" placeholder="名稱、別名、一句話" value="${esc(f.q || "")}"></label>${out}${grouping}</div>`;
}
let pickSet = new Set();   // 批次移入分類：目前勾選的世界觀檔（換頁時清空）
function entityItemHtml(t, e, file, pick) {
  // 勾選框獨立成一格（點得到就勾選），整列仍然是「看內容」
  const cb = pick ? `<label class="pick-cell" onclick="event.stopPropagation()"><input type="checkbox" class="pick" data-pick="${esc(e.file)}" ${pickSet.has(e.file) ? "checked" : ""}></label>` : "";
  const nav = `onclick="go('#/b/${enc(S.book)}/bible?t=${enc(t)}&f=${enc(e.file)}')"`;
  const badge = t === "世界觀" ? esc(e.category || "未分類") : (e.role ? esc(e.role) : "");
  const tagLine = (e.tags || []).length ? `<div class="ds">${esc(e.tags.join("、"))}</div>` : "";
  return `
        <div class="item ${e.file === file ? "active" : ""}" data-file="${esc(e.file)}" ${nav}>
          <div class="row">${cb}<span class="nm">${esc(e.name)}</span><span class="grow"></span>${badge ? `<span class="badge">${badge}</span>` : ""}${e.status === "草稿" ? statusBadge("草稿") : ""}</div>
          ${tagLine}${e.summary ? `<div class="ds">${esc(e.summary)}</div>` : ""}</div>`;
}
function entityListHtml(t, list, f, file) {
  const shown = list.filter((e) => entryMatches(e, f, t));
  const pick = ["角色", "勢力", "世界觀"].includes(t);   // 可勾選，批次轉為正式；世界觀另可移入分類
  const catSel = t === "世界觀" ? `<select id="ef-to">${WORLD_CATS.map((c) => `<option value="${esc(c)}">${esc(c)}</option>`).join("")}</select><button id="ef-apply">移入分類</button>` : "";
  const bulk = pick ? `<div class="ef-bulk"><span id="ef-n">已選 ${pickSet.size} 項</span>${catSel}
      <button id="ef-all">全選</button><button id="ef-clear">清除</button><button class="primary" id="ef-promote">轉為正式</button></div>` : "";
  const head = `<div class="muted small ef-count">顯示 ${shown.length} / ${list.length}</div>${bulk}`;
  if (!list.length) return `<div class="muted">這裡還是空的。</div>`;
  if (!shown.length) return head + `<div class="muted">沒有符合條件的項目。</div>`;
  if (f.group && t !== "勢力") {
    const keyOf = (e) => t === "角色" ? (e.role || "未設定") : (e.category || "未分類");
    const order = t === "角色" ? [...ROLE_ORDER, "未設定"] : [...WORLD_CATS, "未分類"];
    const groups = {};
    shown.forEach((e) => { const k = keyOf(e); (groups[k] = groups[k] || []).push(e); });
    const keys = [...order.filter((k) => groups[k]), ...Object.keys(groups).filter((k) => !order.includes(k))];
    return head + keys.map((k) => `<details class="grp" open><summary>${esc(k)} <span class="muted small">${groups[k].length}</span></summary>${groups[k].map((e) => entityItemHtml(t, e, file, pick)).join("")}</details>`).join("");
  }
  return head + shown.map((e) => entityItemHtml(t, e, file, pick)).join("");
}
function bindEntryFilter(view, t, list, file, f) {
  const paint = () => {
    const box = $("#ent-list", view);
    if (box) box.innerHTML = entityListHtml(t, list, f, file);
    saveEntryFilter(S.book, t, f);
  };
  const box0 = $("#ent-list", view);
  if (box0 && ["角色", "勢力", "世界觀"].includes(t)) {
    const syncCount = () => { const n = $("#ef-n", view); if (n) n.textContent = `已選 ${pickSet.size} 項`; };
    box0.addEventListener("change", (ev) => {
      const cb = ev.target.closest && ev.target.closest("input[data-pick]");
      if (!cb) return;
      cb.checked ? pickSet.add(cb.dataset.pick) : pickSet.delete(cb.dataset.pick);
      syncCount();
    });
    box0.addEventListener("click", async (ev) => {
      const btn = ev.target.closest && ev.target.closest("#ef-all, #ef-clear, #ef-apply, #ef-promote");
      if (!btn) return;
      if (btn.id === "ef-all" || btn.id === "ef-clear") {
        const on = btn.id === "ef-all";
        box0.querySelectorAll("input[data-pick]").forEach((cb) => { cb.checked = on; on ? pickSet.add(cb.dataset.pick) : pickSet.delete(cb.dataset.pick); });
        syncCount();
        return;
      }
      const files = [...pickSet];
      if (!files.length) { toast("請先勾選要處理的項目。", true); return; }
      const body = btn.id === "ef-promote"
        ? { files, status: "正式" }
        : { files, category: $("#ef-to", view).value };
      if (btn.id === "ef-promote" && !confirm(`把 ${files.length} 項轉為正式？`)) return;
      try {
        await api("POST", B("/bible/category"), body);
        pickSet = new Set();
        toast(btn.id === "ef-promote" ? `已轉為正式 ${files.length} 項` : `已移入 ${files.length} 項`);
        await viewBible(view, t, file);
      } catch (e) { toast(e.message || String(e), true); }
    });
  }
  view.querySelectorAll("[data-ef]").forEach((el) => {
    const key = el.dataset.ef;
    el.addEventListener(el.type === "search" ? "input" : "change", () => {
      f[key] = el.type === "checkbox" ? el.checked : el.value;
      paint();
    });
  });
  paint();
}

/* ------------------------------------------------------------------ 設定索引：疑似重複勾選合併 */
const BIBLE_FOLDER = { "角色": "角色", "勢力": "勢力", "世界觀": "世界觀" };
// 只列出這一類（角色／勢力／世界觀）裡、至少涵蓋兩個設定檔的疑似重複組
function dupGroupsFor(t, idx) {
  const prefix = "設定/" + BIBLE_FOLDER[t] + "/";
  const out = [];
  (idx.duplicates || []).forEach((g) => {
    const byFile = {};
    g.members.filter((m) => m.source === "設定檔" && m.file.startsWith(prefix)).forEach((m) => {
      (byFile[m.file] = byFile[m.file] || { file: m.file, names: new Set() }).names.add(m.name);
    });
    const files = Object.values(byFile).map((f) => ({ file: f.file, names: [...f.names] }));
    if (files.length < 2) return;
    const known = new Set(files.flatMap((f) => f.names));
    const ghosts = [...new Set(g.members.filter((m) => m.source === "名詞表" && !known.has(m.name)).map((m) => m.name))];
    const keepDefault = files.some((f) => f.file === g.suggest) ? g.suggest : files[0].file;
    out.push({ key: g.key, files, ghosts, keepDefault, loose: !!g.loose });
  });
  return out;
}
function dupPanelHtml(t, idx) {
  const groups = dupGroupsFor(t, idx);
  if (!groups.length) return "";
  return `<div class="card" id="dup-box" style="margin-bottom:12px">
    <div class="row"><b>疑似重複（${groups.length} 組）</b></div>
    <div class="muted small" style="margin:4px 0 8px">選一份「保留」，勾選要「併入」的。被併入的內容會接在保留檔後面（標示待核對），舊檔移到 設定/_已合併，不會刪除。名稱會加進保留檔的別名。</div>
    ${groups.map((g, gi) => `<div class="dup-group" style="border-top:1px solid var(--line,#ddd);padding:6px 0">
      <div class="small muted">${esc(g.key)}${g.loose ? ` <span class="badge">近似，請確認是不是同一個地方</span>` : ""}</div>
      ${g.files.map((f) => `<div class="row" style="gap:10px;align-items:center;flex-wrap:wrap">
        <label class="small"><input type="radio" name="keep-${gi}" value="${esc(f.file)}" ${f.file === g.keepDefault ? "checked" : ""}> 保留</label>
        <label class="small"><input type="checkbox" class="dup-cb" data-gi="${gi}" value="${esc(f.file)}"> 併入</label>
        <span class="nm">${esc(f.names.join("、"))}</span><span class="muted small">${esc(f.file.split("/").pop())}</span></div>`).join("")}
      ${g.ghosts.length ? `<div class="muted small">名詞表另有：${esc(g.ghosts.join("、"))}（只在名詞表出現，合併不會改動它）</div>` : ""}
    </div>`).join("")}
    <div class="row" style="margin-top:8px"><button class="primary" id="dup-merge-btn">合併勾選的項目</button></div>
  </div>`;
}
function bindDupPanel(view, t, idx, file) {
  const box = $("#dup-box", view);
  if (!box) return;
  box.addEventListener("click", async (ev) => {
    if (!(ev.target.closest && ev.target.closest("#dup-merge-btn"))) return;
    const jobs = [];
    dupGroupsFor(t, idx).forEach((g, gi) => {
      const keep = box.querySelector(`input[name="keep-${gi}"]:checked`);
      if (!keep) return;
      const dups = [...box.querySelectorAll(`input.dup-cb[data-gi="${gi}"]:checked`)].map((c) => c.value).filter((v) => v !== keep.value);
      if (dups.length) jobs.push({ canonical: keep.value, duplicates: dups });
    });
    if (!jobs.length) { toast("請先選擇保留的檔案，並勾選要併入的項目。", true); return; }
    const total = jobs.reduce((n, j) => n + j.duplicates.length, 0);
    if (!confirm(`要併入 ${total} 個設定檔（${jobs.length} 組）嗎？舊檔會移到「設定/_已合併」，不會刪除。`)) return;
    try {
      for (const j of jobs) await api("POST", B("/bible/merge"), j);
      toast(`已併入 ${total} 個設定檔`);
      await viewBible(view, t, jobs[0].canonical);
    } catch (e) {
      toast(e.message || String(e), true);
      await viewBible(view, t, file);
    }
  });
}
async function rebuildBibleIndex() {
  try {
    const r = await api("POST", B("/bible/index/rebuild"));
    toast(`已重建設定索引：設定檔 ${r.counts.settings} 筆，名詞表 ${r.counts.glossary} 筆。`);
  } catch (e) { toast(e.message || String(e), true); }
}

let pickKey = "";
function bibleGenDialog() {
  const opt = (id, title, desc) => `<div class="row" style="align-items:flex-start;gap:12px;margin:12px 0">
      <div><b>${esc(t(title))}</b><div class="muted small">${esc(t(desc))}</div></div>
      <span class="grow"></span><button class="primary" data-pick="${id}">${esc(t("選這個"))}</button></div>`;
  modal(`<h2>${esc(t("生成設定"))}</h2>
    <p class="muted small">${esc(t("先看你手上已經有什麼；選錯也可以再回來。"))}</p>
    ${opt("outline", "我已經有大綱或卷綱", "依大綱長角色、勢力、世界觀（可填參考方向與網址）")}
    ${opt("free", "我只有一句話或關鍵字", "自由描述要生成什麼，適合補配角或單一設定")}
    ${opt("intake", "我剛討論完，有一段文字", "貼對話或筆記；已定案進正式、討論中進草稿")}
    ${opt("one", "我只缺一個角色／勢力／世界觀", "單項補完")}
    <div class="row"><span class="grow"></span><button onclick="closeModal()">${esc(t("取消"))}</button></div>`,
  (el) => el.querySelectorAll("[data-pick]").forEach((b) => { b.onclick = () => bibleGenPick(b.dataset.pick); }));
}

function bibleGenPick(k) {
  closeModal();
  if (k === "outline") Panel.openForm("bible_from_outline");
  else if (k === "free") Panel.openForm("gen_drafts");
  else if (k === "intake") Panel.openForm("intake");
  else bibleOneDialog();
}

function bibleOneDialog() {
  modal(`<h2>${esc(t("補一個設定"))}</h2>
    <p class="muted small">${esc(t("只補一個項目時用；完成後會進草稿或正式，視內容而定。"))}</p>
    <div class="row"><button class="primary" data-one="role">${esc(t("角色"))}</button>
      <button data-one="faction">${esc(t("勢力"))}</button><button data-one="world">${esc(t("世界觀"))}</button>
      <span class="grow"></span><button onclick="closeModal()">${esc(t("取消"))}</button></div>`,
  (el) => el.querySelectorAll("[data-one]").forEach((b) => { b.onclick = () => {
    closeModal();
    if (b.dataset.one === "role") Panel.openForm("character");
    else if (b.dataset.one === "faction") Panel.openForm("free", { text: "請使用 novel-bible skill 建立一個新勢力：" });
    else Panel.openForm("free", { text: "請使用 novel-bible skill 設計世界觀：" });
  }; }));
}

async function viewBible(view, t, file) {
  if (pickKey !== `${S.book}|${t}`) { pickSet = new Set(); pickKey = `${S.book}|${t}`; }
  const b = await api("GET", B("/bible"));
  t = t || "角色";
  const tabs = ["角色", "勢力", "世界觀", "核心", "章節結構", "草稿"];
  const list = b[t] || [];
  if (!file && list.length) file = list[0].file;
  const btns = {
    "角色": "",
    "勢力": "",
    "世界觀": "",
    "核心": `<button onclick="Panel.openForm('style')">分析／調整文風</button><button onclick="Panel.openForm('preference')">記錄偏好</button>`,
    "草稿": `<button class="primary" onclick="Panel.openForm('promote_drafts')">草稿轉正式</button>`,
    "章節結構": `<button onclick="go('#/shared?t=${enc("章節結構")}')">到共用庫選結構</button>`,
  };
  if (t === "核心") btns["核心"] = `<button onclick="go('#/shared?t=${enc("文風")}')">共用文風庫</button>` + btns["核心"];
  const isEnt = ["角色", "勢力", "世界觀"].includes(t);
  const filt = isEnt ? loadEntryFilter(S.book, t) : {};
  const plainList = list.length ? list.map((e) => `
        <div class="item ${e.file === file ? "active" : ""}" onclick="go('#/b/${enc(S.book)}/bible?t=${enc(t)}&f=${enc(e.file)}')">
          <div class="row"><span class="nm">${esc(e.name)}</span><span class="grow"></span>${e.role ? `<span class="badge">${esc(e.role)}</span>` : ""}${e.status === "草稿" ? statusBadge("草稿") : ""}</div>
          ${e.summary ? `<div class="ds">${esc(e.summary)}</div>` : ""}</div>`).join("")
        : `<div class="muted">這裡還是空的。</div>`;
  const listHtml = isEnt ? `${entityFilterBar(t, list, filt)}<div id="ent-list"></div>` : plainList;
  // 設定索引（本機計算，不用 AI）：疑似重複可勾選合併
  const idx = isEnt ? await api("GET", B("/bible/index")).catch(() => null) : null;
  const dupHtml = idx ? dupPanelHtml(t, idx) : "";
  const idxBtn = isEnt ? `<button onclick="rebuildBibleIndex()" title="重新產生 設定/_索引.md，給 novel-bible 先讀">重建索引</button>` : "";
  view.innerHTML = `
    <div class="page-head"><div><h1>設定集</h1><div class="sub">靜態設定。角色目前的位置、傷勢、知道什麼，在「伏筆與時間線」頁。</div></div>
      <div class="row">${btns[t] || ""}${idxBtn}<button class="primary" onclick="bibleGenDialog()">生成設定</button><button onclick="go('#/b/${enc(S.book)}/reverse')" title="從正文反推設定；核對、採用草稿">從正文建立設定</button></div></div>
    <div class="tabs">${tabs.map((x) => `<button class="tab ${x === t ? "active" : ""}" onclick="go('#/b/${enc(S.book)}/bible?t=${enc(x)}')">${x}${b[x] && b[x].length ? ` <span class="badge">${b[x].length}</span>` : ""}</button>`).join("")}</div>
    <div class="split">
      <div class="list">${dupHtml}${listHtml}</div>
      <div><div id="doc">${file ? "" : '<div class="card empty"><div class="big">✦</div>選左邊的項目查看。</div>'}</div>
        <div id="ent-card" style="margin-top:14px"></div><div id="ent-ill" style="margin-top:14px"></div></div>
    </div>`;
  if (isEnt) bindEntryFilter(view, t, list, file, filt);
  if (idx) bindDupPanel(view, t, idx, file);
  if (t === "章節結構") { $(".split", view).outerHTML = '<div id="bs-box"></div>'; return renderBookStructures($("#bs-box"), file); }
  if (file) await docView($("#doc"), file);
  if (file && ["角色", "勢力", "世界觀"].includes(t)) {
    try {
      const f = await api("GET", B("/file?path=" + enc(file)));
      await renderCard($("#ent-card"), file, f.text);
      await renderIllust($("#ent-ill"), "entity:" + file, { entityText: f.text });
    } catch (e) { /* ignore */ }
  }
}

/* ------------------------------------------------------------------ 伏筆與時間線 */
/* 伏筆「預計回收」→ 章號（規則同 project.due_chapter：「起推進」「呼應」「第二幕」「未排定」不算回收章） */
function dueCh(s) {
  const m = String(s || "").match(/^\s*第\s*(\d+)\s*(?:章)?(?:\s*[～~\-–至到]\s*第?\s*(\d+))?\s*章([\s\S]*)$/);
  if (!m) return null;
  const rest = m[3].trim();
  if (/^(起|開始|呼應|推進|再|埋|提及)/.test(rest)) return null;
  const n = parseInt(m[2] || m[1]);
  return /^(前後|左右)/.test(rest) ? n + 2 : n;
}
let REL_VIEW = "table";   // 角色關係：表格 / 關係圖
let REL_NOTE = "";   // 「從角色檔建立」的說明，顯示在草稿上面
async function viewTracking(view, t) {
  const d = await api("GET", B("/tracking"));
  t = t || "foreshadow";
  const tabs = [["foreshadow", "伏筆"], ["timeline", "時間線"], ["reader", "讀者認知"], ["relations", "角色關係"], ["chars", "角色狀態"], ["state", "狀態卡"], ["glossary", "名詞表"]];
  const latest = d.latest || 0;
  const chn = (s) => { const m = String(s || "").match(/(\d+)/); return m ? parseInt(m[1]) : null; };
  let body = "";
  if (t === "foreshadow") {
    const rows = d.foreshadow.rows;
    body = rows.length ? `<div class="card"><div class="row" style="margin-bottom:8px"><label class="cb" style="margin:0"><input type="checkbox" id="hide-done" checked> 隱藏已回收／廢棄</label>
      <span class="grow"></span><span class="muted small">黃底：重要度中以上、超過 ${d.stale_foreshadow} 章沒出現，或已過預計回收章（「預計回收」要寫成「第N章」才算；「起推進」「呼應」不算）</span></div>
      <div class="table-wrap"><table id="fs-table"><thead><tr>${d.foreshadow.headers.map((h) => `<th>${esc(h)}</th>`).join("")}</tr></thead><tbody>
      ${rows.map((r) => {
        const done = ["已回收", "廢棄"].includes(r["狀態"]);
        const last = chn(r["最後出現"]) || chn(r["埋設章"]);
        const due = dueCh(r["預計回收"]);
        const stale = !done && ((["高", "中"].includes(r["重要度"]) && last && latest - last > d.stale_foreshadow) || (due && latest > due));
        return `<tr class="${done ? "dim done" : ""} ${stale ? "hl" : ""}">${d.foreshadow.headers.map((h) => `<td>${h === "狀態" ? statusBadge(r[h]) : esc(r[h])}</td>`).join("")}</tr>`;
      }).join("")}</tbody></table></div></div>`
      : `<div class="card empty"><div class="big">⟲</div>還沒有伏筆紀錄。寫完章節後 Claude 會自動登記。</div>`;
  } else if (t === "timeline") {
    const rows = d.timeline.rows;
    body = rows.length ? `<div class="card"><div class="muted small" style="margin-bottom:8px">「讀者目前知道」是寫作時的資訊邊界；揭示章為「未揭示」的列以黃底標示。</div>
      <div class="table-wrap"><table><thead><tr>${d.timeline.headers.map((h) => `<th>${esc(h)}</th>`).join("")}</tr></thead><tbody>
      ${rows.map((r) => `<tr class="${/未/.test(r["揭示章"] || "") ? "hl" : ""}">${d.timeline.headers.map((h) => `<td>${esc(r[h])}</td>`).join("")}</tr>`).join("")}
      </tbody></table></div></div>` : `<div class="card empty">還沒有時間線。</div>`;
  } else if (t === "reader") {
    const rd = d.reader_draft, rl = d.reader;
    const isOpen = (r) => r["類型"] !== "已知" && !(chn(r["回收章"]) && chn(r["回收章"]) <= latest);
    const tbl = (x, id) => `<div class="table-wrap"><table id="${id}"><thead><tr>${x.headers.map((h) => `<th>${esc(h)}</th>`).join("")}</tr></thead><tbody>
      ${x.rows.map((r) => `<tr class="${isOpen(r) ? "" : "dim done"}">${x.headers.map((h) => `<td>${h === "類型" ? `<span class="badge ${r[h] === "誤認" ? "b-warn" : r[h] === "懸念" ? "b-ok" : ""}">${esc(r[h])}</span>` : esc(r[h])}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
    const intro = `<div class="muted small" style="margin-bottom:8px">讀者讀到目前的認知：<b>懸念</b>是讀者在等答案的問題，<b>誤認</b>是讀者誤以為的事，<b>已知</b>是讀者知道、但劇中角色未必知道的事。寫稿時只帶和本章有關的；還沒回收的不會被提前說破。「作者真相」選填。</div>`;
    let parts = "";
    if (rd.rows.length) {
      parts += `<div class="card" style="margin-bottom:14px;border-color:var(--warn,#c90)"><div class="card-title"><h2>草稿（${rd.rows.length} 條，尚未生效）</h2><span class="grow"></span>
        <button class="sm primary" id="rp-adopt">採用草稿</button><button class="sm" onclick="Panel.run('reader_reconcile',{})" title="拿後面的時間線與章節摘要比對，找出已經揭曉、部分揭曉、重複的條目">比對回收</button><button class="sm" onclick="openCharState('追蹤/讀者認知_草稿.md')">編輯草稿</button><button class="sm danger" id="rp-discard">捨棄</button></div>
        <div class="muted small" style="margin-bottom:8px">AI 產生的結果（從時間線轉換，或回收比對；比對的逐條理由在草稿最後，按「編輯草稿」可以看）。請檢查：有沒有把你的底牌寫成讀者已經在懷疑的懸念、有沒有漏掉你刻意埋的誤導、回收章對不對。${rl.rows.length ? "採用後會取代現在的帳本（舊的會先備份）。" : ""}</div>
        ${tbl(rd, "rp-draft")}</div>`;
    }
    if (rl.rows.length) {
      parts += `<div class="card"><div class="row" style="margin-bottom:8px"><label class="cb" style="margin:0"><input type="checkbox" id="hide-done" checked> 隱藏已回收與已知</label><span class="grow"></span>
        ${rd.rows.length ? "" : `<button class="sm" onclick="Panel.run('reader_reconcile',{})" title="拿後面的時間線與章節摘要比對，找出已經揭曉、部分揭曉、重複的條目；結果存成草稿">比對回收</button>`}<button class="sm" onclick="openCharState('追蹤/讀者認知.md')">編輯</button></div>${intro}${tbl(rl, "fs-table")}</div>`;
    } else if (!rd.rows.length) {
      parts += `<div class="card empty"><div class="big">?</div>還沒有讀者認知帳本。<br>新書寫完章節後會自動登記；已經寫了很多章的書，可以先從時間線轉換一份草稿，確認後再採用。
        ${d.timeline.rows.length ? `<div style="margin-top:12px"><button class="primary" onclick="Panel.run('reader_init',{})">從時間線建立（AI 轉換，${d.timeline.rows.length} 列）</button></div>` : ""}</div>`;
    }
    body = parts + `<div id="doc" style="margin-top:14px"></div>`;
  } else if (t === "relations") {
    const rd = d.relations_draft, rl = d.relations;
    const cols = (x) => x.headers.filter((h) => h !== "編號");
    const tbl = (x, id) => `<div class="table-wrap"><table id="${id}"><thead><tr>${cols(x).map((h) => `<th>${esc(h)}</th>`).join("")}</tr></thead><tbody>
      ${x.rows.map((r) => `<tr class="${r["結束章"] ? "dim done" : ""}">${cols(x).map((h) => `<td>${esc(r[h])}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
    const intro = `<div class="muted small" style="margin-bottom:8px">誰對誰的關係，一個方向一列（A 對 B、B 對 A 分開記）。關係改變時，舊的那列會填上「結束章」、另開一列，所以歷史都留著；淡色的列是已經結束的舊關係。寫稿時只帶在場角色之間、目前有效的關係。</div>`;
    const build = (label) => `<button class="sm rl-build" title="把各角色檔「## 關係」裡的「對象：描述」整理成表格草稿。不用模型、不花 token；確認後才會生效。">${label}</button>`;
    let parts = "";
    if (rd.rows.length) {
      parts += `<div class="card" style="margin-bottom:14px;border-color:var(--warn,#c90)"><div class="card-title"><h2>草稿（${rd.rows.length} 列，尚未生效）</h2><span class="grow"></span>
        <button class="sm primary" id="rl-adopt">採用草稿</button><button class="sm" onclick="openCharState('追蹤/關係_草稿.md')">編輯草稿</button><button class="sm danger" id="rl-discard">捨棄</button></div>
        ${REL_NOTE ? `<div class="md small" style="margin-bottom:8px">${md(REL_NOTE)}</div>` : ""}
        <div class="muted small" style="margin-bottom:8px">從角色檔的「## 關係」整理出來的，「關係」欄是角色檔那句描述原文。請檢查：對象有沒有認錯人、方向對不對、要不要把描述拆成「關係」和「態度」。${rl.rows.length ? "採用後會取代現在的關係表（舊的會先備份）。" : ""}</div>
        ${tbl(rd, "rl-draft")}</div>`;
    }
    if (rl.rows.length) {
      parts += `<div class="row" style="margin-bottom:10px"><div class="seg compact"><label><input type="radio" name="rel-view" value="table" ${REL_VIEW === "table" ? "checked" : ""}> 表格</label>
        <label><input type="radio" name="rel-view" value="graph" ${REL_VIEW === "graph" ? "checked" : ""}> 關係圖（依勢力分組）</label></div></div>`;
    }
    if (rl.rows.length && REL_VIEW === "graph") {
      parts += `<div class="card"><div id="rg-root"></div></div>`;
    } else if (rl.rows.length) {
      parts += `<div class="card"><div class="row" style="margin-bottom:8px"><label class="cb" style="margin:0"><input type="checkbox" id="hide-done" checked> 只看目前有效</label>
        <input type="text" id="rl-filter" placeholder="篩選角色或關鍵字" style="max-width:200px;margin-left:10px"><span class="grow"></span>
        ${rd.rows.length ? "" : build("從角色檔補關係草稿")}<button class="sm" onclick="openCharState('追蹤/關係.md')">編輯</button></div>${intro}${tbl(rl, "fs-table")}</div>`;
    } else if (!rd.rows.length) {
      parts += `<div class="card empty"><div class="big">⇄</div>還沒有角色關係表。<br>新書寫到前幾章時會自動登記；已經寫了很多章的書，可以從角色檔的「## 關係」轉換一份草稿，確認後再採用。
        <div style="margin-top:12px">${build("從角色檔建立草稿")}</div></div>`;
    }
    body = parts + `<div id="doc" style="margin-top:14px"></div>`;
  } else if (t === "chars") {
    body = d.characters.length ? `<div class="grid g3">${d.characters.map((c) => {
      const last = chn(c.last), gap = last ? latest - last : null;
      return `<div class="card item" style="cursor:pointer" onclick="openCharState('${esc(c.file)}')">
        <div class="row"><span class="nm" style="font-size:15px">${esc(c.name)}</span><span class="grow"></span>
        ${gap !== null && gap > 15 ? `<span class="badge b-warn">${gap} 章未登場</span>` : ""}</div>
        <div class="muted small">最後登場：${esc(c.last || "—")}　·　更新至：${esc(c.updated_to || "—")}</div></div>`;
    }).join("")}</div><div id="doc" style="margin-top:14px"></div>` : `<div class="card empty">還沒有角色狀態。</div>`;
  } else if (t === "state") {
    body = `<div id="doc"></div>`;
  } else if (t === "glossary") {
    const g = d.glossary;
    body = g.rows.length ? `<div class="card"><div class="row" style="margin-bottom:8px"><span class="muted small">${g.rows.length} 條</span><span class="grow"></span>
      <button class="sm" onclick="Panel.run('glossary_org',{})" title="AI 重新分類（地點、組織、物品、技術、制度……），把地點、船艦、武器等寫成設定集的主題檔，合併重複的勢力；名詞表留作索引。結果先存成草稿">整理進設定集</button>
      <button class="sm" onclick="go('#/b/${enc(S.book)}/bible?t=核心&f=${enc("設定/名詞表.md")}')">編輯名詞表</button></div>
      <div class="table-wrap"><table><thead><tr>${g.headers.map((h) => `<th>${esc(h)}</th>`).join("")}</tr></thead>
      <tbody>${g.rows.map((r) => `<tr>${g.headers.map((h) => `<td>${esc(r[h])}</td>`).join("")}</tr>`).join("")}</tbody></table></div></div>`
      : `<div class="card empty">名詞表是空的。</div>`;
  }
  view.innerHTML = `
    <div class="page-head"><div><h1>伏筆與時間線</h1><div class="sub">這裡是「已經發生的事實」，寫完章節後由 Claude 回寫。目前寫到第 ${latest} 章。</div></div>
      <div class="row"><button onclick="Panel.openForm('review_all')">伏筆與角色健康檢查</button></div></div>
    <div class="tabs">${tabs.map(([k, l]) => `<button class="tab ${k === t ? "active" : ""}" onclick="go('#/b/${enc(S.book)}/tracking?t=${k}')">${l}</button>`).join("")}</div>
    ${body}`;
  if (t === "reader") {
    if ($("#rp-adopt")) $("#rp-adopt").onclick = async () => {
      if (!confirm("採用這份草稿？之後寫稿、審查、回寫都會用它。")) return;
      await api("POST", B("/tracking/reader/adopt")); toast("已採用讀者認知帳本"); viewTracking(view, t);
    };
    if ($("#rp-discard")) $("#rp-discard").onclick = async () => {
      if (!confirm("捨棄這份草稿？（會移到 .studio/備份）")) return;
      await api("POST", B("/tracking/reader/discard")); viewTracking(view, t);
    };
  }
  if (t === "relations") {
    document.querySelectorAll('input[name="rel-view"]').forEach((i) => i.onchange = () => { REL_VIEW = i.value; viewTracking(view, t); });
    if ($("#rg-root")) {
      if (!d.relations_graph) $("#rg-root").innerHTML = `<div class="muted" style="padding:24px">後端還沒送出關係圖資料——工作台程式是更新前啟動的，請關掉工作台（命令列視窗）後重新啟動，再回到這一頁。</div>`;
      else if (!window.RelGraph) $("#rg-root").innerHTML = `<div class="muted" style="padding:24px">關係圖的程式檔沒載入，請按 Ctrl+F5 強制重新整理。</div>`;
      else window.RelGraph.mount($("#rg-root"), d.relations_graph);
    }
    document.querySelectorAll(".rl-build").forEach((b) => b.onclick = async () => {
      b.disabled = true;
      try { const r = await api("POST", B("/tracking/relations/build")); REL_NOTE = r.message || ""; viewTracking(view, t); }
      catch (e) { fail(e); b.disabled = false; }
    });
    if ($("#rl-adopt")) $("#rl-adopt").onclick = async () => {
      if (!confirm("採用這份草稿？之後寫稿、審查、回寫都會用它。")) return;
      try { await api("POST", B("/tracking/relations/adopt")); REL_NOTE = ""; toast("已採用角色關係表"); viewTracking(view, t); } catch (e) { fail(e); }
    };
    if ($("#rl-discard")) $("#rl-discard").onclick = async () => {
      if (!confirm("捨棄這份草稿？（會移到 .studio/備份）")) return;
      try { await api("POST", B("/tracking/relations/discard")); REL_NOTE = ""; viewTracking(view, t); } catch (e) { fail(e); }
    };
    if ($("#hide-done") && $("#rl-filter")) {
      const apply = () => {
        const q = $("#rl-filter").value.trim(), hide = $("#hide-done").checked;
        document.querySelectorAll("#fs-table tbody tr").forEach((tr) => {
          tr.style.display = ((hide && tr.classList.contains("done")) || (q && !tr.textContent.includes(q))) ? "none" : "";
        });
      };
      $("#hide-done").onchange = apply; $("#rl-filter").oninput = apply; apply();
    }
  }
  if ((t === "foreshadow" || t === "reader") && $("#hide-done")) {
    const apply = () => document.querySelectorAll("#fs-table tr.done").forEach((tr) => tr.style.display = $("#hide-done").checked ? "none" : "");
    $("#hide-done").onchange = apply; apply();
  }
  if (t === "state") await docView($("#doc"), "追蹤/狀態卡.md");
}
window.openCharState = (file) => docView($("#doc"), file);

/* ------------------------------------------------------------------ 任務紀錄 */
async function viewJobs(view) {
  const [hist, recs] = await Promise.all([api("GET", B("/jobs")), api("GET", B("/recoveries")).catch(() => [])]);
  view.innerHTML = `
    <div class="page-head"><div><h1>任務紀錄</h1><div class="sub">點一筆在右側面板查看完整過程，也可以接續那次的對話。</div></div></div>
    ${recs.length ? `<div class="card" style="margin-bottom:14px"><div class="card-title"><h2>恢復稿</h2><span class="muted small">模型中途出錯、被停止或被截斷時保留下來的文字</span></div>
      <table>${recs.map((r) => `<tr><td class="small">${fmtTime(r.created)}</td><td>${esc(r.label)}<div class="muted small">${esc(r.reason)}　·　${fmtNum(r.chars)} 字　·　…${esc(r.preview)}</div></td>
        <td style="white-space:nowrap">${r.chapter ? `<button class="sm primary" onclick="Panel.run('recover_continue',{id:'${esc(r.id)}'})">接著寫完</button>
          <button class="sm" onclick="recoverTo('${esc(r.id)}')">存成候選稿</button>` : ""}
          <button class="sm" onclick="recoverView('${esc(r.id)}')">查看</button><button class="sm danger" onclick="recoverDiscard('${esc(r.id)}')">捨棄</button></td></tr>`).join("")}</table></div>` : ""}
    <div class="card">${hist.length ? `<table><thead><tr><th>時間</th><th>任務</th><th>狀態</th><th>花費</th></tr></thead><tbody>
      ${hist.map((j) => `<tr class="click" onclick="Panel.show('${esc(j.id)}')"><td>${fmtTime(j.started)}</td><td>${esc(j.title)}</td>
        <td>${jobBadge(j.status)}</td><td class="muted small">${j.cost != null ? "$" + Number(j.cost).toFixed(3) : ""}</td></tr>`).join("")}
      </tbody></table>` : '<div class="empty">還沒有任何任務。</div>'}</div>`;
}
function jobBadge(s) {
  return { running: '<span class="badge b-ok">執行中</span>', done: '<span class="badge">完成</span>', error: '<span class="badge b-bad">失敗</span>', cancelled: '<span class="badge b-warn">已停止</span>' }[s] || esc(s);
}

/* ------------------------------------------------------------------ 設定頁 */
async function viewSettings(view) {
  const r = await api("GET", "/api/config");
  const RM = await api("GET", "/api/reasoning").catch(() => ({}));
  S.config = r.config; S.claudeFound = r.claude_found; S.keyStatus = r.key_status;
  const c = r.config;
  view.innerHTML = `
    <div class="page-head"><div><h1>設定</h1><div class="sub">小說工作台 v${esc(r.version)}</div></div></div>
    <div class="card">
      <h2 style="margin-bottom:12px">服務</h2>
      <div class="row" style="align-items:flex-end">
        <label class="f" style="margin:0;width:160px"><span>連接埠</span><input type="number" id="c-port" value="${esc(r.port)}" min="1024" max="65535"></label>
        <span class="grow muted small">目前網址 <code>${esc(location.origin)}</code>${r.port !== r.running_port && r.running_port ? `　<span class="badge b-warn">已改成 ${esc(r.port)}，重新啟動後生效</span>` : ""}</span>
        <button id="c-restart" ${r.can_restart ? "" : "disabled"}>重新啟動服務</button>
      </div>
      <div class="muted small" style="margin-top:8px">改了連接埠、更新了工作台的程式檔，或服務怪怪的時候用。有任務在執行時無法重新啟動。${r.can_restart ? "" : "<br>目前的啟動方式不支援自動重新啟動，請關閉黑色視窗後重新執行 start.bat。"}</div>
    </div>
    <div class="card">
      <h2 style="margin-bottom:12px">書庫</h2>
      <label class="f"><span>書庫資料夾（每本書是裡面的一個子資料夾）</span><input type="text" id="c-lib" value="${esc(c.library)}"></label>
      <div class="muted small">${r.library_exists ? "✓ 資料夾存在" : "✗ 資料夾不存在，儲存時會自動建立"}</div>
    </div>
    <div class="card">
      <h2 style="margin-bottom:12px">Claude Code 執行者</h2>
      <div class="kv" style="margin-bottom:12px"><span class="k">偵測結果</span><span>${r.claude_found ? `<span class="badge b-ok">找到</span> <code>${esc(r.claude_found)}</code>` : '<span class="badge b-bad">找不到 claude 指令</span>'}</span></div>
      <label class="f"><span>claude 執行檔路徑（留空＝自動尋找）</span><input type="text" id="c-cmd" value="${esc(c.claude_cmd)}" placeholder="例如 C:\\Users\\你\\.local\\bin\\claude.exe"></label>
      <label class="f"><span>模型（留空＝Claude Code 預設）</span><input type="text" id="c-model" value="${esc(c.model)}" placeholder="例如 opus、sonnet"></label>
      <label class="f"><span>權限模式</span><select id="c-perm">
        ${[["acceptEdits", "acceptEdits：可自動讀寫書目錄內的檔案（建議）"], ["default", "default：需要權限的動作會被拒絕"], ["bypassPermissions", "bypassPermissions：全部放行（風險較高）"]]
          .map(([v, l]) => `<option value="${v}" ${c.permission_mode === v ? "selected" : ""}>${l}</option>`).join("")}</select></label>
      <label class="f"><span>額外允許讀取的資料夾（一行一個）</span><textarea id="c-dirs" rows="2">${esc((c.add_dirs || []).join("\n"))}</textarea></label>
      <div class="muted small" style="margin:-6px 0 12px">novel-* skills 已內建在工作台的 <code>plugin</code> 資料夾，會自動載入，不用填。這裡只放你想讓 Claude 額外讀取的資料夾（例如參考資料）。</div>
      <label class="f"><span>額外允許的工具（一行一個）</span><textarea id="c-tools" rows="5">${esc((c.allowed_tools || []).join("\n"))}</textarea></label>
      <div class="muted small">預設允許 skill、python 檢查腳本與 git。Claude 會在書目錄裡執行，看不到書目錄以外的東西。</div>
    </div>
    <div class="card">
      <h2 style="margin-bottom:4px">AI 執行者</h2>
      <div class="muted small" style="margin-bottom:12px">Claude Code 用你的訂閱，會自己讀寫檔案，所有功能都能用。其他模型（DeepSeek、本機 llama.cpp 等 OpenAI 相容服務）由工作台組裝資料再送出，所有按鈕都能用，結果由工作台檢查後寫檔。</div>
      <label class="f"><span>預設執行者</span><select id="c-defprov">${provOpts(c.default_provider)}</select></label>
      <div id="key-store" style="margin-bottom:10px"></div>
      <div id="prov-list"></div>
      <button class="sm" id="prov-add">＋ 新增 OpenAI 相容服務</button>
    </div>
    <div class="card">
      <h2 style="margin-bottom:12px">寫稿品質（非 Claude 模型）</h2>
      <label class="cb"><input type="checkbox" id="c-recon" ${c.reconcile_before_write !== false ? "checked" : ""}> 寫章節前先做定稿對帳（多一次小呼叫，比對章綱事件和已定稿事實）</label>
      <label class="cb"><input type="checkbox" id="c-goal" ${c.goal_check_after_write !== false ? "checked" : ""}> 寫完候選稿後自動核對章綱（逐項附原文引句，由程式驗證）</label>
      <div class="muted small">用 Claude Code 寫稿時，對帳與核對寫在 novel-write skill 的流程裡；章節頁的「核對章綱」按鈕兩種執行者都能用。</div>
    </div>
    <div class="card">
      <h2 style="margin-bottom:12px">整章自動流程</h2>
      <div class="muted small" style="margin-bottom:8px">章綱 → 寫章節（候選稿）→ 章綱核對 → 去 AI 味 → 審查意見 → 自動勾選 → 依勾選意見修訂 → 全部套用 → 定稿並回寫追蹤。每一步各自呼叫一次 AI，不會一次塞太多內容。</div>
      <div class="f"><span>自動勾選哪些等級的審查意見</span></div>
      <div class="row" id="c-psev">${["必須修", "建議修", "提醒"].map((x) => `<label class="cb"><input type="checkbox" value="${x}" ${(c.pipeline_severities || ["必須修", "建議修"]).includes(x) ? "checked" : ""}> ${x}</label>`).join("")}</div>
      <div class="f" style="margin-top:8px"><span>預設跑法</span></div>
      <div class="seg compact" id="c-pmode">
        <label><input type="radio" name="c-pmode" value="stop" ${c.pipeline_mode !== "continue" ? "checked" : ""}><span>寫一章停一章</span></label>
        <label><input type="radio" name="c-pmode" value="continue" ${c.pipeline_mode === "continue" ? "checked" : ""}><span>連續寫到最後一章</span></label>
      </div>
      <div class="muted small" style="margin-top:6px">章綱核對發現沒寫到的情節點，會一併交給修訂。開始時也可以臨時改這兩項。</div>
      <div class="f" style="margin-top:12px"><span>自動駕駛：每幾章停下來檢查一次（0＝不檢查）</span></div>
      <div class="grid g3">
        <label class="f"><span>每幾章檢查</span><input type="number" id="c-ape" min="0" value="${esc(c.autopilot_every ?? 0)}"></label>
        <label class="f"><span>必須修幾項就停</span><input type="number" id="c-apsm" min="1" value="${esc(c.autopilot_stop_must ?? 1)}"></label>
        <label class="f"><span>文風偏離幾倍就停</span><input type="number" step="0.1" id="c-apss" min="1" value="${esc(c.autopilot_stop_style ?? 2.4)}"></label>
      </div>
      <div class="muted small">連續寫才有效。檢查點會看這幾章有沒有「必須修」與文風偏離，不及格就停在那一章等人（漂移線索只記錄、不停）。成本：每次檢查都是本機計算，不花錢。</div>
      <div class="f" style="margin-top:12px"><span>各步驟的執行者（面板上對應的按鈕也預設用這裡的分配）</span></div>
      <div class="grid g4" id="c-pprov">${AI_STEP_LABELS.map(([k, l]) => `<label class="f"><span>${esc(l)}</span><select data-step="${k}">
        <option value="">跟流程的執行者</option>${provOpts((c.pipeline_providers || {})[k])}</select></label>`).join("")}</div>
      <div class="muted small">建議：寫章節、去 AI 味、修訂用寫作品質最好的模型；審查可以換另一個模型交叉檢查；定稿回寫追蹤會改寫時間線與伏筆，不建議交給小型本機模型。指定的執行者連不上時，流程會停在那一步。</div>
    </div>
    <div class="card" id="ill-settings"></div>
    <div class="card">
      <h2 style="margin-bottom:12px">警示</h2>
      <div class="grid g2">
        <label class="f"><span>伏筆幾章沒出現就提醒</span><input type="number" id="c-sf" value="${esc(c.stale_foreshadow)}"></label>
        <label class="f"><span>角色幾章沒登場就提醒</span><input type="number" id="c-sc" value="${esc(c.stale_character)}"></label>
      </div>
    </div>
    <div class="row" style="margin-top:14px"><span class="grow"></span><button class="primary" id="c-save">儲存設定</button></div>`;
  renderIllSettings($("#ill-settings")).catch(fail);
  attachPicker($("#c-lib"), { mode: "dir", title: "選擇書庫資料夾" });
  attachPicker($("#c-cmd"), { mode: "file", title: "選擇 claude 執行檔" });
  attachPicker($("#c-dirs"), { mode: "dir", title: "加入允許讀取的資料夾" }, true);
  const provs = JSON.parse(JSON.stringify((c.providers || []).filter((p) => p.type !== "claude_code")));
  const keys = {};
  const renderProvs = () => {
    $("#prov-list").innerHTML = provs.map((p, i) => `
      <div class="prov-card" data-i="${i}">
        <div class="row" style="margin-bottom:8px"><b>${esc(p.name || p.id)}</b><span class="badge">${esc(p.id)}</span><span class="grow"></span>
          <button class="sm" data-a="test">測試連線／抓模型清單</button><button class="sm danger" data-a="del">刪除</button></div>
        <div class="grid g2">
          <label class="f"><span>顯示名稱</span><input type="text" data-k="name" value="${esc(p.name)}"></label>
          <label class="f"><span>網址（Base URL）</span><input type="text" data-k="base_url" value="${esc(p.base_url)}" placeholder="https://api.deepseek.com 或 http://127.0.0.1:8080/v1"></label>
          <label class="f"><span>模型名稱</span><input type="text" data-k="model" value="${esc(p.model)}" list="ml-${i}" placeholder="按「測試連線」可以選"><datalist id="ml-${i}"></datalist></label>
          <label class="f"><span>API 金鑰 ${S.keyStatus && S.keyStatus[p.id] ? `<span class="badge ${S.keyStatus[p.id].startsWith("secrets.json") ? "b-warn" : "b-ok"}">${esc(S.keyStatus[p.id])}</span>` : ""}</span>
            <input type="password" data-key="1" value="${esc(keys[p.id] || "")}" placeholder="${S.keyStatus && S.keyStatus[p.id] ? "留空＝不變更" : "本機服務可留空"}"></label>
          <label class="f"><span>或用環境變數名稱</span><input type="text" data-k="key_env" value="${esc(p.key_env || "")}" placeholder="例如 DEEPSEEK_API_KEY"></label>
          <label class="f"><span>上下文長度（tokens）</span><input type="number" data-k="context_tokens" value="${esc(p.context_tokens)}"></label>
          <label class="f"><span>最大輸出（tokens）</span><input type="number" data-k="max_output" value="${esc(p.max_output)}"></label>
          <label class="f"><span>每個中文字約幾 token（估算上下文用；空白＝自動：DeepSeek 0.6、其他 1.2）</span>
            <div class="row"><input type="number" step="0.05" min="0.2" max="3" data-k="cjk_token_ratio" value="${esc(p.cjk_token_ratio || "")}" placeholder="自動" style="flex:1"><button class="sm" data-a="calib" title="llama.cpp 用 /tokenize 實際算">校正</button></div></label>
          <label class="f"><span>溫度</span><input type="number" step="0.1" data-k="temperature" value="${esc(p.temperature)}"></label>
          <label class="f"><span>輸入價格（每百萬 tokens，美元，選填）</span><input type="number" step="0.01" data-k="price_in" value="${esc(p.price_in || 0)}"></label>
          <label class="f"><span>輸出價格（每百萬 tokens，美元，選填）</span><input type="number" step="0.01" data-k="price_out" value="${esc(p.price_out || 0)}"></label>
        </div>
        ${p.id !== "llamacpp" ? `<div class="reason-box">
          <div class="row" style="margin-bottom:4px"><b class="small">可用模型</b><span class="muted small">預設模型是上面的「模型名稱」。這裡加上其他模型後，各處的執行者選單就能選「${esc(p.name || p.id)} · 模型」；金鑰共用，空白的欄位沿用上面的設定。</span>
            <span class="grow"></span><button class="sm" data-a="addm">新增模型</button></div>
          ${(p.models || []).length ? `<div class="row muted small" style="gap:6px;margin-top:4px;flex-wrap:wrap">
            <span style="width:190px">模型代號</span><span style="width:130px">顯示名稱</span><span style="width:110px">上下文長度</span><span style="width:100px">最大輸出</span>
            <span style="width:90px">輸入價格</span><span style="width:90px">輸出價格</span><span style="width:120px">每個中文字幾 token</span></div>` : ""}
          ${(p.models || []).map((m, j) => `<div class="row" style="gap:6px;margin-top:6px;flex-wrap:wrap">
            <input type="text" data-m="${j}" data-mk="id" value="${esc(m.id || "")}" placeholder="模型代號" list="ml-${i}" style="width:190px">
            <input type="text" data-m="${j}" data-mk="name" value="${esc(m.name || "")}" placeholder="顯示名稱（選填）" style="width:130px">
            <input type="number" data-m="${j}" data-mk="context_tokens" value="${esc(m.context_tokens || "")}" placeholder="上下文長度" style="width:110px">
            <input type="number" data-m="${j}" data-mk="max_output" value="${esc(m.max_output || "")}" placeholder="最大輸出" style="width:100px">
            <input type="number" step="0.01" data-m="${j}" data-mk="price_in" value="${esc(m.price_in || "")}" placeholder="輸入價格" style="width:90px">
            <input type="number" step="0.01" data-m="${j}" data-mk="price_out" value="${esc(m.price_out || "")}" placeholder="輸出價格" style="width:90px">
            <input type="number" step="0.05" data-m="${j}" data-mk="cjk_token_ratio" value="${esc(m.cjk_token_ratio || "")}" placeholder="中文 token 比例" style="width:120px">
            <button class="sm danger" data-mdel="${j}" title="移除這個模型">✕</button></div>`).join("") || '<div class="muted small">還沒有其他模型。按「測試連線／抓模型清單」後，可以從清單點選加入。</div>'}
          <div class="small" data-mchips style="margin-top:6px"></div>
        </div>` : ""}
        <label class="cb"><input type="checkbox" data-k="json_mode" ${p.json_mode !== false ? "checked" : ""}> 支援 JSON 模式（response_format）</label>
        <div class="reason-box">
          <div class="row" style="margin-bottom:6px"><b class="small">思考強度</b><span class="muted small">推理模型的思考也算在輸出 token 裡；整理 JSON 這類格式任務通常可以關閉。</span></div>
          <label class="f"><span>控制方式</span><select data-r="adapter">${Object.entries(RM.adapters || {}).map(([k, v]) => `<option value="${k}" ${((p.reasoning || {}).adapter || "none") === k ? "selected" : ""}>${esc(v)}</option>`).join("")}</select></label>
          <div class="grid g4">${Object.entries(RM.stages || {}).map(([st, lbl]) => `<label class="f"><span>${esc(lbl)}</span><select data-r="${st}">
            ${(RM.efforts || []).map((e) => `<option value="${e}" ${((p.reasoning || {})[st] || "") === e ? "selected" : ""}>${{ off: "關閉", low: "低", medium: "中", high: "高", max: "最高" }[e]}</option>`).join("")}</select></label>`).join("")}</div>
        </div>
        <label class="f"><span>額外參數（JSON，會合併進請求，選填）</span><textarea data-k="extra" rows="2" placeholder='例如 {"top_p": 0.95}'>${esc(p.extra && Object.keys(p.extra).length ? JSON.stringify(p.extra) : "")}</textarea></label>
        <div class="small muted" data-msg></div>
      </div>`).join("") || '<div class="muted small" style="margin-bottom:8px">沒有其他服務。</div>';
    document.querySelectorAll(".prov-card").forEach((card) => {
      const i = +card.dataset.i;
      card.querySelectorAll("[data-k]").forEach((inp) => inp.oninput = inp.onchange = () => {
        const k = inp.dataset.k;
        provs[i][k] = inp.type === "checkbox" ? inp.checked : inp.value;
      });
      card.querySelector("[data-key]").oninput = (ev) => { keys[provs[i].id] = ev.target.value; };
      card.querySelectorAll("[data-mk]").forEach((inp) => inp.oninput = () => {
        const m = provs[i].models[+inp.dataset.m];
        m[inp.dataset.mk] = inp.value.trim();
      });
      card.querySelectorAll("[data-mdel]").forEach((b) => b.onclick = () => { provs[i].models.splice(+b.dataset.mdel, 1); renderProvs(); });
      if (card.querySelector('[data-a="addm"]')) card.querySelector('[data-a="addm"]').onclick = () => {
        provs[i].models = provs[i].models || []; provs[i].models.push({ id: "" }); renderProvs();
      };
      const chips = (models) => {
        const box = card.querySelector("[data-mchips]");
        if (!box) return;
        const have = new Set([provs[i].model, ...(provs[i].models || []).map((m) => m.id)]);
        const left = models.filter((m) => !have.has(m));
        box.innerHTML = left.length ? `<span class="muted">點一下加入：</span>${left.map((m) => `<button class="sm ghost" data-addm="${esc(m)}">＋ ${esc(m)}</button>`).join(" ")}` : "";
        box.querySelectorAll("[data-addm]").forEach((b) => b.onclick = () => {
          provs[i].models = provs[i].models || []; provs[i].models.push({ id: b.dataset.addm }); renderProvs();
        });
      };
      if (provs[i]._fetched) chips(provs[i]._fetched);
      card.querySelectorAll("[data-r]").forEach((sel) => sel.onchange = () => {
        provs[i].reasoning = Object.assign({}, provs[i].reasoning || {}, { [sel.dataset.r]: sel.value });
      });
      card.querySelector('[data-a="calib"]').onclick = async () => {
        const msg = card.querySelector("[data-msg]");
        msg.textContent = "校正中……";
        try {
          await saveProvs();
          const r = await api("POST", `/api/providers/${enc(provs[i].id)}/calibrate`);
          provs[i].cjk_token_ratio = r.ratio;
          card.querySelector('[data-k="cjk_token_ratio"]').value = r.ratio;
          await saveProvs();
          msg.innerHTML = `<span class="badge b-ok">已校正</span> 每個中文字約 ${esc(r.ratio)} token，已儲存`;
        } catch (e) { msg.innerHTML = `<span class="badge b-bad">無法校正</span> ${esc(e.message)}`; }
      };
      card.querySelector('[data-a="del"]').onclick = () => { if (confirm("刪除這個服務設定？")) { provs.splice(i, 1); renderProvs(); } };
      card.querySelector('[data-a="test"]').onclick = async () => {
        const msg = card.querySelector("[data-msg]");
        msg.textContent = "連線中……";
        try {
          await saveProvs();
          const r = await api("POST", `/api/providers/${enc(provs[i].id)}/models`);
          $(`#ml-${i}`).innerHTML = r.models.map((m) => `<option value="${esc(m)}">`).join("");
          msg.innerHTML = `<span class="badge b-ok">連線成功</span> 可用模型：${r.models.map(esc).join("、") || "（伺服器沒有列出）"}`;
          provs[i]._fetched = r.models; chips(r.models);
          if (!provs[i].model && r.models.length === 1) { provs[i].model = r.models[0]; card.querySelector('[data-k="model"]').value = r.models[0]; }
        } catch (e) { msg.innerHTML = `<span class="badge b-bad">失敗</span> ${esc(e.message)}`; }
      };
    });
  };
  const renderKeyStore = () => {
    const box = $("#key-store");
    if (!box) return;
    box.innerHTML = r.key_store
      ? (r.secrets_pending ? `<div class="alert warn"><span class="k">金鑰</span><span class="t">secrets.json 裡還有 ${r.secrets_pending} 個 API 金鑰。搬進${esc(r.key_store)}後，由系統加密並綁定你的登入帳號，專案資料夾裡就不會留金鑰檔。</span>
          <button class="sm primary" id="key-mig">搬進${esc(r.key_store)}</button></div>`
        : `<div class="muted small">新輸入的 API 金鑰會存進${esc(r.key_store)}（由系統加密，綁定你的登入帳號），不放在專案資料夾。</div>`)
      : `<div class="muted small">這台電腦沒有可用的系統金鑰庫，API 金鑰存在工作台資料夾的 secrets.json（不會進 git）。</div>`;
    if ($("#key-mig")) $("#key-mig").onclick = async () => {
      try {
        const m = await api("POST", "/api/secrets/migrate");
        Object.assign(r, m); S.keyStatus = m.key_status;
        toast(m.left ? `搬了 ${m.moved} 個，還有 ${m.left} 個沒搬成功` : `已搬進${m.key_store}，secrets.json 已刪除`, !!m.left);
        renderKeyStore(); renderProvs();
      } catch (e) { fail(e); }
    };
  };
  const saveProvs = async () => {
    const r = await api("POST", "/api/providers", { providers: provs, keys });
    S.config = r.config; S.keyStatus = r.key_status;
    Object.keys(keys).forEach((k) => delete keys[k]);
    Panel.renderProv();
    return r;
  };
  renderProvs();
  renderKeyStore();
  $("#prov-add").onclick = () => {
    let n = 1; while (provs.find((p) => p.id === "custom" + n)) n++;
    provs.push({ id: "custom" + n, type: "openai", name: "自訂服務 " + n, base_url: "", model: "", key_env: "", context_tokens: 32768, max_output: 4096, temperature: 0.8, json_mode: true, price_in: 0, price_out: 0, extra: {} });
    renderProvs();
  };
  $("#c-restart").onclick = async () => {
    const newPort = parseInt($("#c-port").value);
    if (newPort && newPort !== r.port) {
      try { await api("POST", "/api/config", { port: newPort }); } catch (e) { return fail(e); }
    }
    restartServer();
  };
  $("#c-save").onclick = async () => {
    try {
      await saveProvs();
      const r2 = await api("POST", "/api/config", {
        default_provider: $("#c-defprov").value,
        library: $("#c-lib").value.trim(), claude_cmd: $("#c-cmd").value.trim(), model: $("#c-model").value.trim(),
        permission_mode: $("#c-perm").value, allowed_tools: $("#c-tools").value.split("\n").map((s) => s.trim()).filter(Boolean),
        add_dirs: $("#c-dirs").value.split("\n").map((s) => s.trim()).filter(Boolean),
        reconcile_before_write: $("#c-recon").checked, goal_check_after_write: $("#c-goal").checked,
        pipeline_severities: [...document.querySelectorAll("#c-psev input:checked")].map((x) => x.value),
        pipeline_mode: document.querySelector('input[name="c-pmode"]:checked').value,
        autopilot_every: parseInt($("#c-ape").value) || 0,
        autopilot_stop_must: parseInt($("#c-apsm").value) || 1,
        autopilot_stop_style: parseFloat($("#c-apss").value) || 2.4,
        pipeline_providers: Object.fromEntries([...document.querySelectorAll("#c-pprov select")].map((x) => [x.dataset.step, x.value])),
        stale_foreshadow: parseInt($("#c-sf").value) || 10, stale_character: parseInt($("#c-sc").value) || 15, create_library: true,
        port: parseInt($("#c-port").value) || r.port,
      });
      S.config = r2.config; S.claudeFound = r2.claude_found; S.keyStatus = r2.key_status;
      S.books = (await api("GET", "/api/books")).books;
      Panel.renderProv(); Panel.renderActions();
      toast("已儲存"); refresh();
    } catch (e) { fail(e); }
  };
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

// 文風樣本來源（建立、重新統計、比較共用）
function sampleSourceHtml(books, kinds) {
  const labels = { none: "不附樣本", book: "某本書的正文", text: "貼上文字", files: "上傳檔案（.txt、.md、.docx）", copy_book: "複製某本書現有的 設定/文風.md", blank: "空白範本（自己填）" };
  return `<div class="seg compact" id="ss-kind">${kinds.map((k, i) => `<label><input type="radio" name="ss-kind" value="${k}" ${i === 0 ? "checked" : ""}><span>${labels[k]}</span></label>`).join("")}</div>
    <div data-ss="book copy_book" class="row" style="margin-top:8px">
      <select id="ss-book">${bookOpts(books, S.book)}</select>
      <span data-ss="book" class="row"><span class="small muted">章節</span><input type="number" id="ss-from" class="num-in" placeholder="全部"><span class="small muted">到</span><input type="number" id="ss-to" class="num-in" placeholder="全部"></span>
    </div>
    <div data-ss="text" style="margin-top:8px"><textarea id="ss-text" rows="7" placeholder="貼上一段你想參考的文字。至少 300 字，建議 3000 字以上統計才有參考價值。"></textarea></div>
    <div data-ss="files" style="margin-top:8px"><input type="file" id="ss-files" multiple accept=".txt,.md,.docx"></div>
    <div class="muted small" style="margin-top:6px" data-ss="book text files">程式會在本機統計句長、段長、對白比例、標點習慣、高頻詞組等，寫進文風檔的「文字指標」一節；不呼叫 AI。</div>`;
}
function sampleSourceBind(el) {
  const sync = () => {
    const k = el.querySelector('input[name="ss-kind"]:checked').value;
    el.querySelectorAll("[data-ss]").forEach((x) => { x.hidden = !x.dataset.ss.split(" ").includes(k); });
  };
  el.querySelectorAll('input[name="ss-kind"]').forEach((x) => x.onchange = sync);
  sync();
}
async function sampleSourceValue(el) {
  const k = el.querySelector('input[name="ss-kind"]:checked').value;
  const v = { source: k === "none" ? null : k };
  if (k === "book" || k === "copy_book") { v.book = $("#ss-book", el).value; v.from = parseInt($("#ss-from", el).value) || null; v.to = parseInt($("#ss-to", el).value) || null; }
  if (k === "text") v.text = $("#ss-text", el).value;
  if (k === "files") { v.files = await readFiles($("#ss-files", el)); if (!v.files.length) throw new Error("請選擇檔案"); }
  return v;
}

function compareTable(rows) {
  if (!rows.length) return '<div class="muted small">沒有可以比較的指標。</div>';
  return `<table><tr><th>指標</th><th class="num">文風目標</th><th class="num">實際</th><th class="num">差距</th><th></th></tr>
    ${rows.map((r) => `<tr><td>${esc(r["指標"])}</td><td class="num">${esc(r["目標"])}</td><td class="num">${esc(r["實際"])}</td><td class="num">${esc(r["差距"])}</td>
      <td>${r["偏離"] === "明顯" ? '<span class="badge b-bad">差很多</span>' : r["偏離"] ? '<span class="badge b-warn">有點差</span>' : '<span class="badge b-ok">接近</span>'}</td></tr>`).join("")}</table>`;
}

/* 請 AI 設計／調整／試寫文風（共用庫） */
const STYLE_GENRES = ["本格推理", "冷硬派", "心理驚悚", "恐怖怪談", "仙俠修真", "武俠", "西式奇幻", "科幻", "現代言情", "古言宮鬥",
  "都市爽文", "歷史架空", "都市寫實", "輕小說", "黑色幽默", "鄉土地域", "太空歌劇"];
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
function styleAiModal(mode, books, name) {
  const titles = { design: "請 AI 設計文風", revise: `請 AI 調整「${esc(name || "")}」`, test: `照「${esc(name || "")}」試寫一段` };
  let body = "";
  if (mode === "design") {
    body = `<p class="muted small">AI 會依照文風的十三個面向（視角距離、敘述者立場、用詞、句子、段落、描寫、修辭、對白、情緒、轉場、連載慣例……）寫出完整文風檔，含有標籤的原創範例段落。只填名稱也可以，填越多越準。</p>
      <div class="grid g2">
        <label class="f"><span>名稱</span><input type="text" id="sa-name" placeholder="例如：冷調推理、雅致仙俠"></label>
        <label class="f"><span>執行者</span>${provSelectHtml("sa-prov")}</label>
      </div>
      <label class="f"><span>類型（可以點下面的標籤，也可以自己寫；混合類型請寫「骨架＋調味」）</span><input type="text" id="sa-genre" placeholder="例如：本格推理＋校園"></label>
      <div class="chips" id="sa-chips">${STYLE_GENRES.map((g) => `<button type="button" class="chip sm">${esc(g)}</button>`).join("")}</div>
      <label class="f"><span>想要的感覺</span><textarea id="sa-feel" rows="2" placeholder="例如：冷靜、克制、線索藏在日常裡；讀起來像在跟偵探一起看現場"></textarea></label>
      <div class="grid g2">
        <label class="f"><span>參考作品或作者（只學特徵，不抄文字）</span><input type="text" id="sa-refs" placeholder="例如：東野圭吾的推理段落、松本清張的社會描寫"></label>
        <label class="f"><span>敘事視角</span><input type="text" id="sa-pov" placeholder="例如：第一人稱助手視角（不填由 AI 建議）"></label>
        <label class="f"><span>讀者與平台</span><input type="text" id="sa-readers" placeholder="例如：連載平台，手機閱讀，每章三千字"></label>
        <label class="f"><span>一定不要</span><input type="text" id="sa-avoid" placeholder="例如：不要翻譯腔、不要偵探耍帥"></label>
      </div>
      <details style="margin:6px 0 10px"><summary class="small">附上寫作樣本（選填：AI 會從樣本歸納規則，程式會統計文字指標）</summary>
        <div style="margin-top:8px">${sampleSourceHtml(books, ["none", "text", "files", "book"])}</div></details>
      <label class="cb"><input type="checkbox" id="sa-over"> 同名文風已存在時覆蓋（舊版會備份到 _共用/.備份）</label>`;
  } else if (mode === "revise") {
    body = `<p class="muted small">只改和你意見相關的條目，其他原樣保留；完成後會列出「舊 → 新」。舊版會備份到 <code>_共用/.備份</code>。</p>
      <label class="f"><span>要怎麼調整</span><textarea id="sa-note" rows="5" placeholder="例如：對白再口語一點；比喻太多，一場最多一個；補一段打鬥的範例；這份太簡單了，照十三個面向補完整"></textarea></label>
      <details style="margin:6px 0 10px"><summary class="small">附上寫作樣本（選填）</summary>
        <div style="margin-top:8px">${sampleSourceHtml(books, ["none", "text", "files", "book"])}</div></details>
      <label class="f"><span>執行者</span>${provSelectHtml("sa-prov")}</label>`;
  } else {
    body = `<p class="muted small">照這份文風寫 200～300 字，附上自評：示範了哪些規則、哪條規則難以遵守。試寫不會改動文風檔。</p>
      <label class="f"><span>情境（選填）</span><textarea id="sa-note" rows="3" placeholder="例如：偵探第一次走進命案現場，和刑警有一段對話。不填由 AI 挑最能考驗文風的情境。"></textarea></label>
      <label class="f"><span>執行者</span>${provSelectHtml("sa-prov")}</label>`;
  }
  modal(`<h2>${titles[mode]}</h2>${body}
    <div class="row" style="margin-top:14px"><span class="grow"></span><button onclick="closeModal()">取消</button><button class="primary" id="sa-go">${mode === "test" ? "試寫" : "開始"}</button></div>`, (el) => {
    if ($("#ss-kind", el)) sampleSourceBind(el);
    el.querySelectorAll("#sa-chips .chip").forEach((c) => c.onclick = () => {
      const inp = $("#sa-genre", el), g = c.textContent;
      const parts = inp.value.split(/[＋+、,，]/).map((x) => x.trim()).filter(Boolean);
      inp.value = parts.includes(g) ? parts.filter((x) => x !== g).join("＋") : parts.concat(g).join("＋");
      c.classList.toggle("on", !parts.includes(g));
      if (!$("#sa-name", el).value.trim()) $("#sa-name", el).placeholder = inp.value || "例如：冷調推理、雅致仙俠";
    });
    $("#sa-go", el).onclick = async () => {
      try {
        const v = $("#ss-kind", el) ? await sampleSourceValue(el) : {};
        v.mode = mode;
        v.provider = $("#sa-prov", el).value;
        const val = (id) => ($("#" + id, el) ? $("#" + id, el).value.trim() : "");
        if (mode === "design") {
          v.name = val("sa-name") || val("sa-genre");
          if (!v.name) return toast("請輸入名稱或類型", true);
          Object.assign(v, { genre: val("sa-genre"), feel: val("sa-feel"), refs: val("sa-refs"), pov: val("sa-pov"),
            readers: val("sa-readers"), avoid: val("sa-avoid"), overwrite: $("#sa-over", el).checked });
        } else {
          v.name = name; v.note = val("sa-note");
          if (mode === "revise" && !v.note) return toast("請寫下要怎麼調整", true);
        }
        const job = await api("POST", "/api/shared/styles/design", v);
        closeModal();
        S.styleJobTarget = mode === "test" ? null : v.name;
        Panel.attach(job);
      } catch (e) { fail(e); }
    };
  });
}
S.onSharedJob = (job) => {
  if (job.status !== "done") return;
  const n = S.styleJobTarget;
  if (n) toast("文風「" + n + "」已更新");
  if (location.hash.startsWith("#/shared")) {
    if (n) go(`#/shared?t=${enc("文風")}&f=${enc("文風/" + n + ".md")}`); else refresh();
  }
};

async function viewShared(view, t, file) {
  const o = await api("GET", "/api/shared");
  S.sharedBooks = o.books;
  S.sharedLangs = o.book_langs || {};
  t = t || "文風";
  const tabs = ["文風", "章節結構", "共用作者偏好"];
  if (!o.exists) {
    view.innerHTML = `
      <div class="page-head"><div><h1>共用庫</h1><div class="sub">所有書都能用的文風、章節結構與作者偏好</div></div></div>
      <div class="card"><p>共用庫是書庫裡的 <code>_共用</code> 資料夾，跟著你的小說資料走，不在工作台的程式資料夾裡，所以不會被推上 GitHub。</p>
        <ul class="muted small"><li>文風：可以重複使用、從範例文字統計出文字指標</li><li>章節結構：起承轉合、壓抑爆發等節拍範本，寫章節和排章綱時參考</li><li>共用作者偏好：跨書的長期偏好、常犯的毛病、禁用詞（禁用詞由程式檢查）</li></ul>
        <p class="muted small">位置：<code>${esc(o.dir)}</code></p>
        <button class="primary" id="sh-init">建立共用庫</button></div>`;
    $("#sh-init").onclick = async () => { try { await api("POST", "/api/shared/init"); refresh(); } catch (e) { fail(e); } };
    return;
  }
  const base = "#/shared";
  let list = [], side = "";
  if (t === "文風") {
    list = o.styles.map((s) => ({ file: s.file, name: s.name, desc: s.summary, lang: s.lang, badge: s.has_metrics ? `已統計 ${fmtNum(+s.sample)} 字` : "" }));
  } else if (t === "章節結構") {
    list = o.structures.map((s) => ({ file: s.file, name: s.name, desc: s.summary, badge: s.origin === "preset" ? "內建" : "我的", lang: s.lang, scope: s.scope, origin: s.origin }));
  } else {
    file = "作者偏好.md";
  }
  if (!file && list.length) file = list[0].file;
  const curItem = list.find((x) => x.file === file);
  const headBtns = {
    "文風": `<button id="sh-ai-style">✦ 請 AI 設計文風</button><button class="primary" id="sh-new-style">新增文風</button>`,
    "章節結構": `<button class="primary" id="sh-new-struct">新增結構</button>`,
    "共用作者偏好": "",
  };
  view.innerHTML = `
    <div class="page-head"><div><h1>共用庫</h1><div class="sub">所有書都能用；放在書庫的 <code>_共用</code> 資料夾，不會進 git</div></div>
      <div class="row">${headBtns[t]}</div></div>
    <div class="tabs">${tabs.map((x) => `<button class="tab ${x === t ? "active" : ""}" onclick="go('${base}?t=${enc(x)}')">${x}${x === "共用作者偏好" && o.prefs.active ? ' <span class="badge b-ok">生效中</span>' : ""}</button>`).join("")}</div>
    ${t === "共用作者偏好" ? `<div class="alert info" style="margin-bottom:12px"><span class="k">怎麼生效</span><span class="t">
        寫作、改稿、去 AI 味、審查時，Claude Code 和其他模型都會讀這份檔案（和各書的 設定/作者偏好.md 衝突時以書為準）。
        「禁用詞」一節由程式在「檢查用語與 AI 味」時逐字比對，目前有 <b>${o.prefs.banned}</b> 個。各書的 設定/作者偏好.md 也可以加「## 禁用詞」一節。</span></div>
      <div id="doc"></div>` : `
    <div class="split">
      <div class="list">${list.length ? list.map((e) => `
        <div class="item ${e.file === file ? "active" : ""}" onclick="go('${base}?t=${enc(t)}&f=${enc(e.file)}')">
          <div class="row"><span class="nm">${esc(e.name)}</span><span class="grow"></span>${e.lang && e.lang !== "zh-TW" ? `<span class="badge">${e.lang === "en" ? "English" : "日本語"}</span>` : ""}${e.badge ? `<span class="badge">${esc(e.badge)}</span>` : ""}</div>
          ${e.desc ? `<div class="ds">${esc(e.desc)}</div>` : ""}${e.scope ? `<div class="ds">適用：${esc(e.scope)}</div>` : ""}</div>`).join("")
        : `<div class="muted">還沒有${t}。按右上角新增。</div>`}</div>
      <div><div id="sh-actions"></div><div id="doc">${file ? "" : '<div class="card empty"><div class="big">✦</div>選左邊的項目查看。</div>'}</div></div>
    </div>`}`;
  const books = o.books;
  if (t === "文風") {
    $("#sh-ai-style").onclick = () => styleAiModal("design", books);
    $("#sh-new-style").onclick = () => modal(`<h2>新增文風</h2>
      <label class="f"><span>名稱</span><input type="text" id="ns-name" placeholder="例如：冷調短句、古風權謀"></label>
      <label class="f"><span>文風語言</span><select id="ns-lang"><option value="zh-TW">繁體中文</option><option value="en">English</option><option value="ja">日本語</option></select></label>
      <div class="muted small" style="margin:-6px 0 10px">從某本書的正文或設定建立時，自動用那本書的語言。</div>
      <div class="f"><span>從哪裡建立</span></div>${sampleSourceHtml(books, ["book", "text", "files", "copy_book", "blank"])}
      <div class="row" style="margin-top:14px"><span class="grow"></span><button onclick="closeModal()">取消</button><button class="primary" id="ns-go">建立</button></div>`, (el) => {
      sampleSourceBind(el);
      $("#ns-go", el).onclick = async () => {
        try {
          const v = await sampleSourceValue(el);
          v.name = $("#ns-name", el).value.trim();
          v.lang = $("#ns-lang", el).value;
          if (!v.name) return toast("請輸入名稱", true);
          const r = await api("POST", "/api/shared/styles", v);
          closeModal(); toast("已建立文風「" + r.name + "」");
          go(`${base}?t=${enc("文風")}&f=${enc(r.file)}`);
        } catch (e) { fail(e); }
      };
    });
    if (curItem) {
      const name = curItem.name;
      $("#sh-actions").innerHTML = `<div class="row" style="margin-bottom:10px">
        <button class="primary sm" id="st-apply">套用到書…</button><button class="sm" id="st-compare">和某本書的正文比較</button>
        <button class="sm" id="st-restat">重新統計文字指標</button>
        <button class="sm" id="st-ai-rev">✦ 請 AI 調整</button><button class="sm" id="st-ai-test">✦ 試寫一段</button>
        <span class="grow"></span><button class="sm danger" id="st-del">刪除</button></div>`;
      $("#st-ai-rev").onclick = () => styleAiModal("revise", books, name);
      $("#st-ai-test").onclick = () => styleAiModal("test", books, name);
      $("#st-apply").onclick = () => modal(`<h2>把「${esc(name)}」套用到書</h2>
        <p class="muted small">會複製成那本書的 <code>設定/文風.md</code>。原本的文風檔會先備份到 <code>.studio/備份</code>。之後在書裡修改不會影響共用庫。</p>
        <label class="f"><span>套用到</span><select id="ap-book">${bookOpts(books, S.book, curItem.lang)}</select></label>
        <div class="row"><span class="grow"></span><button onclick="closeModal()">取消</button><button class="primary" id="ap-go">套用</button></div>`, (el) => {
        $("#ap-go", el).onclick = async () => {
          try { await api("POST", `/api/shared/styles/${enc(name)}/apply`, { book: $("#ap-book", el).value }); closeModal(); toast("已套用到《" + $("#ap-book", el).value + "》"); } catch (e) { fail(e); }
        };
      });
      $("#st-compare").onclick = () => modal(`<h2>「${esc(name)}」和正文比較</h2>
        <p class="muted small">在本機統計那本書的正文，和這個文風的文字指標並排比較。</p>
        <div class="row"><select id="cp-book">${bookOpts(books, S.book, curItem.lang)}</select><span class="small muted">章節</span>
          <input type="number" id="cp-from" class="num-in" placeholder="全部"><span class="small muted">到</span><input type="number" id="cp-to" class="num-in" placeholder="全部">
          <button class="primary sm" id="cp-go">比較</button></div><div id="cp-out" style="margin-top:12px"></div>`, (el) => {
        $("#cp-go", el).onclick = async () => {
          try {
            const r = await api("POST", `/api/shared/styles/${enc(name)}/compare`, { book: $("#cp-book", el).value, from: parseInt($("#cp-from", el).value) || null, to: parseInt($("#cp-to", el).value) || null });
            $("#cp-out", el).innerHTML = compareTable(r.rows) + `<div class="muted small" style="margin-top:8px">正文高頻詞組：${esc(r.actual["高頻詞組"])}</div>`;
          } catch (e) { fail(e); }
        };
      });
      $("#st-restat").onclick = () => modal(`<h2>重新統計「${esc(name)}」的文字指標</h2>
        <p class="muted small">只會更新「文字指標」一節，你寫的其他內容不動。</p>${sampleSourceHtml(books, ["book", "text", "files"])}
        <div class="row" style="margin-top:14px"><span class="grow"></span><button onclick="closeModal()">取消</button><button class="primary" id="rs-go">統計</button></div>`, (el) => {
        sampleSourceBind(el);
        $("#rs-go", el).onclick = async () => {
          try { await api("POST", `/api/shared/styles/${enc(name)}/restat`, await sampleSourceValue(el)); closeModal(); toast("已更新文字指標"); refresh(); } catch (e) { fail(e); }
        };
      });
      $("#st-del").onclick = async () => {
        if (!confirm(`刪除文風「${name}」？（會移到 _共用/.刪除，不會永久刪除）`)) return;
        try { await api("DELETE", `/api/shared/styles/${enc(name)}`); go(`${base}?t=${enc("文風")}`); } catch (e) { fail(e); }
      };
    }
  }
  if (t === "章節結構") {
    $("#sh-new-struct").onclick = () => modal(`<h2>新增章節結構</h2>
      <label class="f"><span>名稱</span><input type="text" id="nt-name" placeholder="例如：雙線交錯"></label>
      <p class="muted small">會建立一份節拍表範本，之後直接編輯。也可以選左邊的內建結構，按「複製到我的結構」再修改。</p>
      <div class="row"><span class="grow"></span><button onclick="closeModal()">取消</button><button class="primary" id="nt-go">建立</button></div>`, (el) => {
      $("#nt-go", el).onclick = async () => {
        try { const r = await api("POST", "/api/shared/structures", { name: $("#nt-name", el).value.trim(), lang: (S.sharedLangs || {})[S.book] }); closeModal(); go(`${base}?t=${enc("章節結構")}&f=${enc("結構/" + r.name + ".md")}`); } catch (e) { fail(e); }
      };
    });
    if (curItem) {
      const name = curItem.name, origin = curItem.origin;
      $("#sh-actions").innerHTML = `<div class="row" style="margin-bottom:10px">
        <button class="primary sm" id="sc-apply">套用到書…</button>
        ${origin === "preset" ? '<button class="sm" id="sc-copy">複製到我的結構</button>' : ""}
        <span class="grow"></span>${origin === "mine" ? '<button class="sm danger" id="sc-del">刪除</button>' : '<span class="muted small">內建結構不能直接修改</span>'}</div>`;
      $("#sc-apply").onclick = () => modal(`<h2>把「${esc(name)}」套用到書</h2>
        <p class="muted small">會複製到那本書的 <code>設定/章節結構/</code>。設為全書預設後，每章寫稿都會參考這個節拍；個別章節可以在章節頁改用別的結構。</p>
        <label class="f"><span>套用到</span><select id="sa-book">${bookOpts(books, S.book, curItem.lang)}</select></label>
        <label class="cb"><input type="checkbox" id="sa-def" ${curItem.scope && curItem.scope.includes("卷") ? "" : "checked"}> 設為全書預設</label>
        <div class="row"><span class="grow"></span><button onclick="closeModal()">取消</button><button class="primary" id="sa-go">套用</button></div>`, (el) => {
        $("#sa-go", el).onclick = async () => {
          try { await api("POST", `/api/shared/structures/${enc(name)}/apply`, { book: $("#sa-book", el).value, origin, default: $("#sa-def", el).checked }); closeModal(); toast("已套用到《" + $("#sa-book", el).value + "》"); } catch (e) { fail(e); }
        };
      });
      if ($("#sc-copy")) $("#sc-copy").onclick = async () => {
        const nn = prompt("新的名稱", name);
        if (!nn) return;
        try { const r = await api("POST", "/api/shared/structures", { copy_preset: name, name: nn }); go(`${base}?t=${enc("章節結構")}&f=${enc("結構/" + r.name + ".md")}`); } catch (e) { fail(e); }
      };
      if ($("#sc-del")) $("#sc-del").onclick = async () => {
        if (!confirm(`刪除結構「${name}」？（會移到 _共用/.刪除；已套用到書裡的複本不受影響）`)) return;
        try { await api("DELETE", `/api/shared/structures/${enc(name)}`); go(`${base}?t=${enc("章節結構")}`); } catch (e) { fail(e); }
      };
    }
  }
  if (file) await docView($("#doc"), file.startsWith("preset:") ? file : file, { base: "/api/shared", readonly: file.startsWith("preset:") });
}

/* ------------------------------------------------------------------ 匯入舊稿 */
const IMP = { files: [], preview: null };
async function viewImport(view) {
  const info = await api("GET", "/api/import/info");
  IMP.files = []; IMP.preview = null;
  view.innerHTML = `
    <div class="page-head"><div><h1>匯入舊稿</h1><div class="sub">把已經寫好的 TXT、Markdown、Word（.docx）拆成章節放進書裡；全部在本機處理，不呼叫 AI</div></div></div>
    <div class="grid exp-grid">
      <div class="card">
        <h2 style="margin-bottom:10px">1. 選擇稿子</h2>
        <label class="f"><span>稿子的語言</span><select id="im-lang"><option value="zh-TW">繁體中文</option><option value="en">English</option><option value="ja">日本語</option></select></label>
        <label class="f"><span>檔案（可以一次選多個；一個檔案一章也可以）</span><input type="file" id="im-files" multiple accept=".txt,.md,.markdown,.docx"></label>
        <label class="f"><span>或直接貼上</span><textarea id="im-text" rows="6" placeholder="第一章 ……&#10;正文……&#10;&#10;第二章 ……"></textarea></label>
        <div class="muted small">編碼會自動判斷（UTF-8、Big5、GB18030）。舊版 .doc 請先在 Word 另存成 .docx。</div>
      </div>
      <div class="card">
        <h2 style="margin-bottom:10px">2. 怎麼拆章</h2>
        <div class="grid g2">
          <label class="f"><span>章節標題</span><select id="im-mode">
            <option value="auto">自動（第X章、Chapter N、楔子、番外；找不到再用 # 標題）</option>
            <option value="chapter">只認「第X章／第X回」這類標題</option>
            <option value="markdown">只認 Markdown 的 # 標題</option></select></label>
          <label class="f"><span>章號</span><select id="im-num">
            <option value="auto">照標題上的章號（不連續時自動改成依順序）</option>
            <option value="sequential">依順序重新編號</option></select></label>
          <label class="f"><span>依順序編號時從第幾章開始</span><input type="number" id="im-start" value="1" min="1"></label>
        </div>
        <label class="cb" id="im-conv-wrap"><input type="checkbox" id="im-conv" ${info.has_opencc ? "" : "disabled"}> 簡體轉成台灣繁體（含用語，例如「軟件」→「軟體」）
          ${info.has_opencc ? "" : '<span class="badge b-warn">需要 OpenCC：關閉工作台後重新執行 start.bat 會自動安裝</span>'}</label>
        <label class="cb"><input type="checkbox" id="im-pre"> 把第一個章節標題之前的文字當成一章（例如楔子）</label>
        <label class="cb"><input type="checkbox" id="im-punct" checked> 修正標點（西式引號改「」、半形逗號改全形等）</label>
        <div class="row"><span class="grow"></span><button class="primary" id="im-preview">預覽拆章結果</button></div>
      </div>
    </div>
    <div id="im-out"></div>`;
  const opts = () => ({ mode: $("#im-mode").value, numbering: $("#im-num").value, start: parseInt($("#im-start").value) || 1,
    convert: IMP.lang === "zh-TW" && $("#im-conv").checked, lang: IMP.lang, preface_as_chapter: $("#im-pre").checked, fix_punct: $("#im-punct").checked });
  const payload = () => ({ files: IMP.files, text: $("#im-text").value });
  // 英文、日文稿子不需要簡轉繁，簡體相關的選項與對照一起收起來
  const syncLang = () => {
    IMP.lang = $("#im-lang").value;
    $("#im-conv-wrap").style.display = IMP.lang === "zh-TW" ? "" : "none";
  };
  $("#im-lang").onchange = syncLang;
  syncLang();
  $("#im-files").onchange = async (ev) => { try { IMP.files = await readFiles(ev.target); } catch (e) { fail(e); } };
  $("#im-preview").onclick = async () => {
    const btn = $("#im-preview"); btn.disabled = true; btn.textContent = "處理中……";
    try {
      const r = await api("POST", "/api/import/preview", { payload: payload(), opts: opts() });
      IMP.preview = r;
      renderImportPreview(r, info, payload, opts);
    } catch (e) { fail(e); } finally { btn.disabled = false; btn.textContent = "預覽拆章結果"; }
  };
}

function renderImportPreview(r, info, payload, opts) {
  const total = r.chapters.reduce((a, c) => a + c.chars, 0);
  const zhOn = IMP.lang === "zh-TW";   // 只有繁體中文稿才顯示簡體相關的檢查與對照
  const wu = unitOfLang(IMP.lang);
  const flagsOf = (c) => (c.flags || []).filter((f) => zhOn || !/簡體/.test(f));
  const guessName = (IMP.files[0] && IMP.files[0].name.replace(/\.[^.]+$/, "").replace(/^\d+[\s._\-、]*/, "")) || "";
  $("#im-out").innerHTML = `
    <div class="card" style="margin-top:14px">
      <div class="card-title"><h2>拆章結果：${r.chapters.length} 章，${fmtNum(total)} ${unitCh(wu)}${(() => { const n = r.chapters.filter((c) => flagsOf(c).length).length; return n ? `<span class="badge b-warn" style="margin-left:8px">${n} 章要檢查</span>` : `<span class="badge b-ok" style="margin-left:8px">沒有發現問題</span>`; })()}</h2>
        <span class="muted small">${r.numbered_by_title ? "章號照標題" : "章號依順序"}</span></div>
      <div class="row small muted" style="margin-bottom:8px">${r.sources.map((s) => `<span class="badge">${esc(s.name)}：${esc(s.encoding)}${zhOn && s.simplified ? `，簡體字約 ${s.simplified}` : ""}</span>`).join("")}</div>
      ${r.warnings.map((w) => `<div class="alert warn"><span class="t">${esc(w)}</span></div>`).join("")}
      ${r.preface.map((p) => `<div class="muted small" style="margin:6px 0">開頭文字（${esc(p.name)}，${p.chars} ${unitCh(wu)}）：${esc(p.preview)}……</div>`).join("")}
      <div class="table-wrap" style="max-height:360px"><table>
        <tr><th class="num">章</th><th>章名</th><th class="num">${wu === "words" ? "詞數" : "字數"}</th><th>檢查</th><th>開頭</th></tr>
        ${r.chapters.map((c) => `<tr class="${flagsOf(c).length ? "hl" : ""}"><td class="num">${c.no}</td><td>${esc(c.title) || '<span class="muted">（無章名）</span>'}</td>
          <td class="num">${fmtNum(c.chars)}</td><td>${flagsOf(c).map((f) => `<span class="badge ${/空章|重複|倒退|簡體/.test(f) ? "b-bad" : "b-warn"}">${esc(f)}</span>`).join(" ")}</td>
          <td class="muted small">${esc(c.head)}</td></tr>`).join("")}
      </table></div>
    </div>
    <div class="card" style="margin-top:14px">
      <h2 style="margin-bottom:10px">3. 放到哪裡</h2>
      <div class="seg compact"><label><input type="radio" name="im-dest" value="new" ${info.books.length ? "" : "checked"}><span>建立新書</span></label>
        <label><input type="radio" name="im-dest" value="old" ${info.books.length ? "checked" : ""} ${info.books.length ? "" : "disabled"}><span>放進現有的書</span></label></div>
      <div class="grid g2" style="margin-top:10px">
        <label class="f" data-dest="new"><span>書名</span><input type="text" id="im-name" value="${esc(guessName)}"></label>
        <label class="f" data-dest="old"><span>書</span><select id="im-book">${bookOpts(info.books, S.book)}</select></label>
        <label class="f"><span>放進</span><select id="im-target"><option value="正文">正文（直接當成定稿）</option><option value="候選">候選稿（逐章審閱後再採用）</option></select></label>
        <label class="f" data-dest="old"><span>書裡已經有同一章時</span><select id="im-conflict"><option value="skip">跳過，保留書裡的</option><option value="overwrite">覆蓋（原檔先備份）</option></select></label>
      </div>
      <div class="row"><span class="grow"></span><button class="primary" id="im-go">匯入 ${r.chapters.length} 章</button></div>
      <div id="im-result"></div>
    </div>`;
  const sync = () => {
    const d = document.querySelector('input[name="im-dest"]:checked').value;
    document.querySelectorAll("[data-dest]").forEach((x) => { x.hidden = x.dataset.dest !== d; });
  };
  document.querySelectorAll('input[name="im-dest"]').forEach((x) => x.onchange = sync);
  sync();
  $("#im-go").onclick = async () => {
    const isNew = document.querySelector('input[name="im-dest"]:checked').value === "new";
    const body = { payload: payload(), opts: Object.assign(opts(), { target: $("#im-target").value, conflict: $("#im-conflict").value }) };
    if (isNew) { body.new_book = $("#im-name").value.trim(); if (!body.new_book) return toast("請輸入書名", true); }
    else body.book = $("#im-book").value;
    const btn = $("#im-go"); btn.disabled = true;
    try {
      const res = await api("POST", "/api/import/commit", body);
      S.books = (await api("GET", "/api/books")).books;
      $("#im-result").innerHTML = `<div class="alert ok" style="margin-top:12px"><span class="k">完成</span><span class="t">
        匯入 ${res.written.length} 章（${fmtNum(res.chars)} ${unitCh(unitOfLang(IMP.lang))}）到《${esc(res.book)}》的${esc(res.target)}。
        ${res.skipped.length ? `跳過已存在的第 ${res.skipped.join("、")} 章。` : ""}${res.replaced.length ? `覆蓋了第 ${res.replaced.join("、")} 章（原檔已備份）。` : ""}</span>
        <button class="sm primary" onclick="go('#/b/${enc(res.book)}')">開啟這本書</button></div>
        <div class="muted small" style="margin-top:8px">下一步建議：${res.target === "正文"
          ? `已經寫好的書，可以用 <a href="#/b/${enc(res.book)}/reverse">從正文建立設定</a> 讓 AI 從正文反推角色、世界觀、名詞表、大綱、章綱、伏筆與時間線（先存成草稿，不需要開書訪談）；文風可以到「共用庫 → 文風」用這本書的正文分析。`
          : "到章節頁逐章審閱候選稿，按「採用」移入正文並回寫追蹤。"}</div>`;
      renderNav();
    } catch (e) { fail(e); } finally { btn.disabled = false; }
  };
}

/* ------------------------------------------------------------------ 本書章節結構 */
async function renderBookStructures(el, file) {
  const r = await api("GET", B("/structures"));
  const list = r.list;
  if (!file && list.length) file = list[0].file;
  const cur = list.find((x) => x.file === file);
  el.innerHTML = `<div class="split">
      <div class="list">${list.length ? list.map((s) => `
        <div class="item ${s.file === file ? "active" : ""}" onclick="go('#/b/${enc(S.book)}/bible?t=${enc("章節結構")}&f=${enc(s.file)}')">
          <div class="row"><span class="nm">${esc(s.name)}</span><span class="grow"></span>${s.default ? '<span class="badge b-ok">全書預設</span>' : ""}</div>
          ${s.summary ? `<div class="ds">${esc(s.summary)}</div>` : ""}</div>`).join("")
        : `<div class="muted">這本書還沒有章節結構。<br><a href="#/shared?t=${enc("章節結構")}">到共用庫套用一個 →</a></div>`}</div>
      <div><div id="bs-actions"></div><div id="doc">${file ? "" : '<div class="card empty"><div class="big">✦</div>章節結構是寫章節時參考的節拍表。<br>到共用庫選一個套用到這本書。</div>'}</div></div>
    </div>`;
  if (cur) {
    $("#bs-actions").innerHTML = `<div class="row" style="margin-bottom:10px">
      ${cur.default ? '<button class="sm" id="bs-undef">取消全書預設</button>' : '<button class="sm primary" id="bs-def">設為全書預設</button>'}
      <span class="muted small">個別章節要用別的結構，到該章的「章綱」分頁選。</span></div>`;
    const set = async (name) => { try { await api("POST", B("/structures/default"), { name }); refresh(); } catch (e) { fail(e); } };
    if ($("#bs-def")) $("#bs-def").onclick = () => set(cur.name);
    if ($("#bs-undef")) $("#bs-undef").onclick = () => set(null);
    await docView($("#doc"), cur.file);
  }
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
const imgUrl = (path) => B("/illust/image?path=" + enc(path));
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

// 畫風選擇（StyleSelectorXL 樣式表）
async function pickStyles(selected, onDone) {
  let data;
  try { data = await api("GET", "/api/illust/styles"); } catch (e) { return fail(e); }
  if (data.missing) return toast("找不到畫風樣式表：到「設定 → 插畫」選一個 .xlsx 或 .json", true);
  let sel = [...(selected || [])], cat = "", q = "", nsfw = false;
  const tops = [...new Set(data.categories.map(([c]) => c.split(" > ")[0]))];
  modal(`<h2>選畫風</h2>
    <div class="row" style="margin-bottom:8px"><input type="text" id="ps-q" placeholder="搜尋名稱、中文名、提示詞" style="flex:1">
      <label class="cb" style="margin:0"><input type="checkbox" id="ps-nsfw"> 顯示 nsfw 分類</label></div>
    <div class="ps-wrap"><div class="ps-cats" id="ps-cats"></div><div class="ps-list" id="ps-list"></div></div>
    <div class="small muted" style="margin-top:8px">已選（依順序套用）：<span id="ps-sel"></span></div>
    <div class="row" style="margin-top:12px"><button class="sm" id="ps-clear">全部取消</button><span class="grow"></span><button onclick="closeModal()">取消</button><button class="primary" id="ps-ok">確定</button></div>`, async (el) => {
    const renderCats = () => {
      $("#ps-cats", el).innerHTML = [["", "全部"], ...tops.map((t) => [t, t])].map(([v, l]) => `<div class="ps-cat ${v === cat ? "on" : ""}" data-c="${esc(v)}">${esc(l)}</div>`).join("");
      el.querySelectorAll(".ps-cat").forEach((d) => d.onclick = () => { cat = d.dataset.c; renderCats(); renderList(); });
    };
    const renderList = () => {
      const ql = q.toLowerCase();
      const rows = data.styles.filter((s) => (!cat || s.categories.some((c) => c === cat || c.startsWith(cat + " >")))
        && (!ql || (s.name + s.zh + s.prompt + s.natural).toLowerCase().includes(ql))).slice(0, 300);
      $("#ps-list", el).innerHTML = rows.map((s) => `<label class="ps-item"><input type="checkbox" data-n="${esc(s.name)}" ${sel.includes(s.name) ? "checked" : ""}>
        <span><b>${esc(s.zh || s.name)}</b> <span class="muted small">${esc(s.name)}</span><br><span class="muted small">${esc(s.prompt || s.natural)}</span></span></label>`).join("")
        || '<div class="muted small">沒有符合的畫風。</div>';
      el.querySelectorAll("[data-n]").forEach((cb) => cb.onchange = () => {
        sel = cb.checked ? [...sel, cb.dataset.n] : sel.filter((x) => x !== cb.dataset.n); renderSel();
      });
    };
    const renderSel = () => { $("#ps-sel", el).textContent = sel.length ? sel.join("　＋　") : "（不套用）"; };
    $("#ps-q", el).oninput = (e) => { q = e.target.value; renderList(); };
    $("#ps-nsfw", el).onchange = async (e) => {
      nsfw = e.target.checked;
      try { data = await api("GET", "/api/illust/styles?nsfw=" + nsfw); } catch (er) { return fail(er); }
      tops.splice(0, tops.length, ...new Set(data.categories.map(([c]) => c.split(" > ")[0]))); renderCats(); renderList();
    };
    $("#ps-clear", el).onclick = () => { sel = []; renderSel(); renderList(); };
    $("#ps-ok", el).onclick = () => { closeModal(); onDone(sel); };
    renderCats(); renderList(); renderSel();
  });
}

function imageModal(target, img, reload, reuse) {
  modal(`<div class="img-view"><img src="${imgUrl(img.path)}" alt=""></div>
    <div class="row small muted" style="margin:8px 0">${esc(img.file)}　${img.width ? img.width + "×" + img.height : ""}　${img.seed ? "seed " + img.seed : ""}　${img.origin === "upload" ? "上傳" : img.origin === "comfy" ? "ComfyUI" + (img.comfy_profile ? "・" + esc(img.comfy_profile) : "") : "Forge"}</div>
    ${img.prompt ? `<details><summary class="small">提示詞</summary><pre class="pre">${esc(img.prompt)}</pre>${img.negative ? `<pre class="pre muted">負面：${esc(img.negative)}</pre>` : ""}</details>` : ""}
    <div class="row" style="margin-top:10px">
      ${img.main ? '<span class="badge b-ok">主圖</span>' : '<button class="sm primary" id="iv-main">設為主圖</button>'}
      ${img.prompt ? '<button class="sm" id="iv-copy">複製提示詞</button><button class="sm" id="iv-reuse">用這組提示詞再出圖</button>' : ""}
      <a class="btn sm" href="${imgUrl(img.path)}" download="${esc(img.file)}">下載</a>
      <span class="grow"></span><button class="sm danger" id="iv-del">刪除</button><button class="sm" onclick="closeModal()">關閉</button></div>`, (el) => {
    if ($("#iv-main", el)) $("#iv-main", el).onclick = async () => { try { await api("POST", B("/illust/main"), { target, file: img.file }); closeModal(); reload(); } catch (e) { fail(e); } };
    if ($("#iv-copy", el)) $("#iv-copy", el).onclick = () => { navigator.clipboard.writeText(img.prompt).then(() => toast("已複製")); };
    if ($("#iv-reuse", el)) $("#iv-reuse", el).onclick = () => { closeModal(); reuse(img); };
    $("#iv-del", el).onclick = async () => {
      if (!confirm("刪除這張圖？（會移到 .studio/備份/插圖）")) return;
      try { await api("POST", B("/illust/delete"), { target, file: img.file }); closeModal(); reload(); } catch (e) { fail(e); }
    };
  });
}

/* 插圖區塊：target = cover | chapter:N | entity:設定/角色/X.md */
async function renderIllust(el, target, opts = {}) {
  const cfgR = await illCfg();
  let info;
  try { info = await api("GET", B("/illust?target=" + enc(target))); } catch (e) { el.innerHTML = `<div class="card muted">${esc(e.message)}</div>`; return; }
  const cfg = cfgR.config;
  const bs = info.style || {};
  const isCh = target.startsWith("chapter:"), isEnt = target.startsWith("entity:"), isCover = target === "cover";
  const D = Object.assign({ passage: "", chars: [], places: [], action_tags: "", scene_tags: "", composition: "", sentences: "",
    extra: "", format: cfg.format, styles: bs.styles || [], artist: bs.artist || "", seed: -1, count: 1 }, info.draft || {});
  const isComfy = cfg.backend === "comfy";
  const profs = cfg.comfy_profiles || [];
  if (!profs.find((p) => p.id === D.profile)) D.profile = cfg.comfy_profile || (profs[0] || {}).id;
  const curProf = () => profs.find((p) => p.id === D.profile) || profs[0] || {};
  const genName = () => isComfy ? "ComfyUI" : "Forge";
  if (!info.draft || !info.draft.styles) D.styles = bs.styles || [];
  if (!info.draft || info.draft.artist === undefined) D.artist = bs.artist || "";
  let ents = null, picks = null, zh = null, final = null, open = opts.open || (isCh && !info.images.length);
  const sizeW = D.width || (isCover ? bs.cover_width : bs.width) || cfg.width, sizeH = D.height || (isCover ? bs.cover_height : bs.height) || cfg.height;
  D.width = sizeW; D.height = sizeH;
  const reload = () => renderIllust(el, target, Object.assign({}, opts, { open }));
  if (!Array.isArray(D.texts)) D.texts = [];
  const bookName = () => ((S.books || []).find((b) => b.id === S.book) || {}).name || "";
  const TX_KIND = [["title", "標題"], ["sign", "招牌、標語"], ["bubble", "對白氣泡"], ["caption", "說明文字"], ["other", "其他"]];
  const TX_POS = [["tl", "左上"], ["t", "上方"], ["tr", "右上"], ["l", "左側"], ["c", "中央"], ["r", "右側"], ["bl", "左下"], ["b", "下方"], ["br", "右下"]];
  const TX_SIZE = [["l", "大"], ["m", "中"], ["s", "小"]];
  const TX_FONT = [["", "字體不指定"], ["brush", "書法"], ["bold", "粗黑體"], ["serif", "襯線印刷體"], ["hand", "手寫"], ["pixel", "像素字"]];
  const txSel = (i, f, list, v) => `<select data-tx="${i}" data-tf="${f}">${list.map(([k, l]) => `<option value="${k}" ${(v || "") === k ? "selected" : ""}>${l}</option>`).join("")}</select>`;
  const textRows = () => `<h3>圖中文字</h3>
    <div class="muted small" style="margin-bottom:6px">MOSS-Image 會照引號裡的字畫出來，中文、英文都可以（英文最穩）。要換行就在文字裡打 \\n。最多 6 條；沒有加就不放文字。</div>
    ${isCover ? `<label class="chip ${D.texts.some((x) => x.book) ? "on" : ""}" style="margin-bottom:6px"><input type="checkbox" id="il-booktitle" ${D.texts.some((x) => x.book) ? "checked" : ""}>放書名</label>` : ""}
    ${D.texts.length ? `<table class="ill-chars">${D.texts.map((x, i) => `<tr>
        <td><input type="text" data-tx="${i}" data-tf="text" value="${esc(x.text || "")}" placeholder="要出現在圖上的字"></td>
        <td>${txSel(i, "kind", TX_KIND, x.kind || "title")}</td><td>${txSel(i, "pos", TX_POS, x.pos || "t")}</td>
        <td>${txSel(i, "size", TX_SIZE, x.size || "l")}</td><td>${txSel(i, "font", TX_FONT, x.font || "")}</td>
        <td><input type="text" data-tx="${i}" data-tf="color" value="${esc(x.color || "")}" placeholder="顏色（英文，例如 gold）" style="width:9em"></td>
        <td><button class="sm" data-txdel="${i}" title="刪除">✕</button></td></tr>`).join("")}</table>` : ""}
    ${D.texts.length < 6 ? '<div class="row" style="margin:6px 0 10px"><button class="sm" id="il-txadd">＋ 加一條文字</button></div>' : ""}`;

  const gallery = () => info.images.length ? `<div class="ill-gallery">${info.images.map((im, i) => `
      <div class="ill-thumb ${im.main ? "main" : ""}" data-i="${i}"><img loading="lazy" src="${imgUrl(im.path)}" alt="">
        ${im.main ? '<span class="badge b-ok">主圖</span>' : ""}</div>`).join("")}</div>`
    : `<div class="muted small">還沒有插圖。${isCh ? "可以挑一段來畫，或直接上傳。" : "可以產生提示詞送 Forge，或直接上傳。"}</div>`;

  const charRows = () => {
    if (!ents) return '<div class="muted small">載入中……</div>';
    const pool = ents.all.filter((e) => e.kind === "角色");
    const places = ents.all.filter((e) => e.kind !== "角色");
    const onChars = D.chars.map((c) => c.name), onPlaces = (D.places || []).map((p) => p.name);
    const card = (name) => (ents.cards[name] || {});
    return `<div class="ill-chips">${pool.map((e) => `<label class="chip ${onChars.includes(e.name) ? "on" : ""}" title="${esc(card(e.name).tags || "沒有視覺卡")}">
        <input type="checkbox" data-ch="${esc(e.name)}" ${onChars.includes(e.name) ? "checked" : ""}>${esc(e.name)}${e.has_card ? "" : ' <span class="warn-dot" title="沒有視覺卡">!</span>'}</label>`).join("") || '<span class="muted small">這本書還沒有角色設定檔。</span>'}</div>
      ${D.chars.length ? `<table class="ill-chars">${D.chars.map((c, i) => `<tr>
          <td class="nm">${esc(c.name)}</td>
          <td><select data-pos="${i}">${[["", "自動"], ["left", "左"], ["right", "右"], ["center", "中"], ["back", "後方"]].map(([v, l]) => `<option value="${v}" ${(c.position || "") === v ? "selected" : ""}>${l}</option>`).join("")}</select></td>
          <td><input type="text" data-act="${i}" value="${esc(c.action || "")}" placeholder="這張圖裡的動作、表情（英文標籤）"></td>
          <td class="small muted">${c.tags ? esc(c.tags.slice(0, 60)) : `<a href="#/b/${enc(S.book)}/bible?t=${enc("角色")}&f=${enc(c.file || "")}">先建立視覺卡</a>`}</td></tr>`).join("")}</table>` : ""}
      ${places.length ? `<div class="small muted" style="margin:8px 0 4px">地點、物件（有視覺卡的會帶入場景）</div><div class="ill-chips">${places.map((e) => `<label class="chip ${onPlaces.includes(e.name) ? "on" : ""}">
        <input type="checkbox" data-pl="${esc(e.name)}" ${onPlaces.includes(e.name) ? "checked" : ""}>${esc(e.name)}${e.has_card ? "" : ' <span class="warn-dot" title="沒有視覺卡">!</span>'}</label>`).join("")}</div>` : ""}`;
  };

  const render = () => {
    el.innerHTML = `<div class="card ill-card">
      <div class="card-title"><h2>插圖 <span class="badge">${info.images.length}</span></h2>
        <div class="row"><label class="btn sm">上傳圖片<input type="file" id="il-up" accept="image/png,image/jpeg,image/webp" multiple hidden></label>
          <button class="sm ${open ? "" : "primary"}" id="il-toggle">${open ? "收起出圖" : "出圖"}</button></div></div>
      ${gallery()}
      <div id="il-q" class="small" style="margin-top:6px"></div>
      ${open ? `<div class="ill-editor">
        ${isCh ? `<h3>1. 要畫哪一段</h3>
          <div class="row"><button class="sm" id="il-pick-h">挑精華段落</button><button class="sm" id="il-pick-a">挑動作最強的段落</button>
            <span class="muted small">程式在本機依動作詞、畫面詞、章綱情節點打分，不用 AI；也可以直接貼上或修改下面的文字。</span></div>
          ${picks ? `<div class="ill-picks">${picks.map((p, i) => `<div class="ill-pick" data-p="${i}"><div class="small muted">分數 ${p.score}　${esc(p.reasons)}</div>${esc(p.text.slice(0, 160))}${p.text.length > 160 ? "……" : ""}</div>`).join("")}</div>` : ""}
          <textarea id="il-passage" rows="4" placeholder="要畫的片段">${esc(D.passage)}</textarea>` : ""}
        <h3>${isCh ? "2. " : ""}出場角色與地點</h3>
        <div id="il-chars">${charRows()}</div>
        <h3>${isCh ? "3. " : ""}畫面描述</h3>
        <div class="row" style="margin-bottom:8px">
          <select id="il-prov">${illProvOptions(cfgR)}</select>
          <button class="sm primary" id="il-ai">AI 產生畫面描述</button>
          <button class="sm" id="il-zh">本機查標籤</button>
          <span class="muted small">AI 只寫下面幾欄（一小段 JSON）；角色外觀、品質、畫風由程式組裝。</span></div>
        ${zh ? `<div class="ill-chips" style="margin-bottom:8px">${zh.length ? zh.map((h) => `<span class="chip add" data-tag="${esc(h.tag)}" title="${esc(h.zh)}">${esc(h.zh)} → ${esc(h.tag)}</span>`).join("") : '<span class="muted small">對照表裡沒有查到。</span>'}</div>
          <div class="muted small" style="margin:-4px 0 8px">點一下加進「場景標籤」。對照表是 tagcomplete 附的中文翻譯，有些詞不準，請挑著用。</div>` : ""}
        <div class="grid g2">
          <label class="f"><span>動作、互動標籤</span><input type="text" data-k="action_tags" value="${esc(D.action_tags)}"></label>
          <label class="f"><span>場景標籤（地點、時間、光線）</span><input type="text" data-k="scene_tags" value="${esc(D.scene_tags)}"></label>
          <label class="f"><span>構圖、鏡頭標籤</span><input type="text" data-k="composition" value="${esc(D.composition)}" placeholder="cowboy shot, from side, close-up"></label>
          <label class="f"><span>額外標籤</span><input type="text" data-k="extra" value="${esc(D.extra)}"></label>
        </div>
        <label class="f"><span>英文描述（兩三句）</span><textarea data-k="sentences" rows="3">${esc(D.sentences)}</textarea></label>
        <h3>${isCh ? "4. " : ""}畫風與出圖</h3>
        <div class="grid g2">
          <div class="f"><span>畫風</span><div class="row"><span class="small">${D.styles.length ? D.styles.map(esc).join("　＋　") : '<span class="muted">不套用</span>'}</span>
            <button class="sm" id="il-styles">選畫風…</button></div></div>
          <label class="f"><span>畫師標籤（會自動加 @）</span><input type="text" data-k="artist" value="${esc(D.artist)}"></label>
          ${isComfy ? `<label class="f"><span>ComfyUI 出圖設定</span><select data-k="profile" id="il-prof">${profs.map((p) => `<option value="${esc(p.id)}" ${p.id === D.profile ? "selected" : ""}>${esc(p.name)}${p.upsampler ? "（Upsampler）" : ""}${(p.loras || []).some((x) => x.on !== false && x.name) ? "（LoRA）" : ""}</option>`).join("")}</select></label>` : ""}
          ${isComfy && curProf().kind === "moss" ? `<div class="f"><span>格式</span><div class="small muted">MOSS-Image 用英文自然語言，不加品質、分級與畫師標籤</div></div>`
            : `<label class="f"><span>格式</span><select data-k="format">${[["mixed", "標籤＋自然語言（Anima 建議）"], ["tags", "只有標籤"], ["natural", "自然語言為主"]].map(([v, l]) => `<option value="${v}" ${D.format === v ? "selected" : ""}>${l}</option>`).join("")}</select></label>`}
          <label class="f"><span>尺寸</span><select id="il-size">${cfgR.sizes.map(([n, w, h]) => `<option value="${w}x${h}" ${w === +D.width && h === +D.height ? "selected" : ""}>${n} ${w}×${h}</option>`).join("")}
            ${cfgR.sizes.some(([, w, h]) => w === +D.width && h === +D.height) ? "" : `<option value="${D.width}x${D.height}" selected>目前 ${D.width}×${D.height}</option>`}</select></label>
          <label class="f"><span>種子（-1＝隨機）</span><input type="number" data-k="seed" value="${esc(D.seed)}"></label>
          <label class="f"><span>張數</span><select data-k="count">${[1, 2, 3, 4].map((n) => `<option ${+D.count === n ? "selected" : ""}>${n}</option>`).join("")}</select></label>
        </div>
        ${isComfy && curProf().kind === "moss" ? textRows() : ""}
        <div class="row"><button class="sm" id="il-asm">組裝提示詞</button><span class="muted small">組裝後可以直接修改最終提示詞，或複製到 ${genName()} 自己用。</span></div>
        ${final ? `<label class="f" style="margin-top:8px"><span>正向提示詞</span><textarea id="il-pos" rows="7">${esc(final.positive)}</textarea></label>
          <label class="f"><span>負面提示詞</span><textarea id="il-neg" rows="2">${esc(final.negative)}</textarea></label>
          ${final.notes && final.notes.length ? `<div class="small muted">標籤檢查：${final.notes.map(esc).join("；")}</div>` : ""}
          <div class="row" style="margin-top:8px"><button class="sm" id="il-copy">複製正向提示詞</button><span class="grow"></span>
            <button class="primary" id="il-gen">送 ${genName()} 出圖</button></div>` : ""}
      </div>` : ""}
    </div>`;
    bind();
  };

  const collect = () => {
    el.querySelectorAll("[data-k]").forEach((i) => { D[i.dataset.k] = i.type === "number" ? parseInt(i.value) : i.value; });
    if ($("#il-passage", el)) D.passage = $("#il-passage", el).value;
    el.querySelectorAll("[data-act]").forEach((i) => { D.chars[+i.dataset.act].action = i.value; });
    el.querySelectorAll("[data-pos]").forEach((i) => { D.chars[+i.dataset.pos].position = i.value; });
    el.querySelectorAll("[data-tx]").forEach((i) => { if (D.texts[+i.dataset.tx]) D.texts[+i.dataset.tx][i.dataset.tf] = i.value; });
    if ($("#il-size", el)) { const [w, h] = $("#il-size", el).value.split("x").map(Number); D.width = w; D.height = h; }
  };

  const loadEnts = async () => {
    const text = isCh ? (D.passage || "") : "";
    const r = await api("POST", B("/illust/detect"), { text, target });
    const cards = {};
    r.entities.forEach((e) => { cards[e.name] = e.card || {}; });
    // 角色清單需要每個人的視覺卡：沒在片段裡出現的另外補
    r.all.forEach((e) => { if (!cards[e.name]) cards[e.name] = null; });
    ents = { all: r.all, cards, found: r.entities };
    const full = {};
    for (const e of r.entities) full[e.name] = e;
    ents.full = full;
    if (!D.chars.length && !info.draft.chars) {
      D.chars = r.entities.filter((e) => e.kind === "角色").slice(0, 3).map((e) => ({ name: e.name, file: e.file, tags: (e.card || {}).tags || "", description: (e.card || {}).description || "", position: "", action: "" }));
      D.places = r.entities.filter((e) => e.kind !== "角色").slice(0, 2).map((e) => ({ name: e.name, file: e.file, tags: (e.card || {}).tags || "", description: (e.card || {}).description || "" }));
    }
  };
  const cardOf = async (name) => {
    if (ents.full[name]) return ents.full[name];
    const e = ents.all.find((x) => x.name === name);
    const r = await api("POST", B("/illust/detect"), { text: name, target });
    const hit = r.entities.find((x) => x.name === name) || e;
    ents.full[name] = hit;
    return hit;
  };

  const pollQueue = async () => {
    for (;;) {
      let list;
      try { list = await api("GET", "/api/illust/queue?book=" + enc(S.book)); } catch (e) { return; }
      const mine = list.filter((x) => x.target === target);
      const active = mine.filter((x) => x.status === "queued" || x.status === "running");
      const q = $("#il-q", el);
      if (!q) return;
      const others = list.filter((x) => x.target !== target && (x.status === "queued" || x.status === "running")).length;
      q.innerHTML = active.map((x) => x.status === "running"
        ? (x.backend === "comfy"
          ? `<div class="ill-prog"><span>ComfyUI ${x.phase === "pending" ? "排隊中" : "出圖中"}（${esc(x.profile)}，${x.elapsed || 0} 秒）</span><div class="bar indet"><i></i></div><button class="sm" data-cancel="${x.id}">停止</button></div>`
          : `<div class="ill-prog"><span>Forge 出圖中 ${Math.round(x.progress * 100)}%${x.eta ? `（約 ${Math.ceil(x.eta)} 秒）` : ""}</span><div class="bar"><i style="width:${Math.round(x.progress * 100)}%"></i></div><button class="sm" data-cancel="${x.id}">停止</button></div>`)
        : `<div>排隊中（seed ${x.seed}）<button class="sm" data-cancel="${x.id}">取消</button></div>`).join("")
        + (others ? `<div class="muted">另外還有 ${others} 張在排隊</div>` : "")
        + mine.filter((x) => x.status === "error" && Date.now() / 1000 - x.created < 600).slice(-1).map((x) => `<div class="err">出圖失敗：${esc(x.error)}</div>`).join("");
      q.querySelectorAll("[data-cancel]").forEach((b) => b.onclick = () => api("POST", `/api/illust/queue/${b.dataset.cancel}/cancel`));
      if (!active.length) {
        const doneNow = mine.some((x) => x.status === "done" && x.files.some((f) => !info.images.find((im) => im.file === f)));
        if (doneNow) { info = await api("GET", B("/illust?target=" + enc(target))); collect(); render(); }
        return;
      }
      await new Promise((r) => setTimeout(r, 1200));
    }
  };

  const bind = () => {
    if ($("#il-prof", el)) $("#il-prof", el).onchange = () => { collect(); final = null; render(); };
    if ($("#il-txadd", el)) $("#il-txadd", el).onclick = () => { collect(); D.texts.push({ text: "", kind: "title", pos: "t", size: "l", font: "", color: "" }); final = null; render(); };
    el.querySelectorAll("[data-txdel]").forEach((b) => b.onclick = () => { collect(); D.texts.splice(+b.dataset.txdel, 1); final = null; render(); });
    if ($("#il-booktitle", el)) $("#il-booktitle", el).onchange = (ev) => {
      collect();
      if (ev.target.checked) D.texts.unshift({ text: bookName(), kind: "title", pos: "t", size: "l", font: "", color: "", book: true });
      else D.texts = D.texts.filter((x) => !x.book);
      D.texts = D.texts.slice(0, 6); final = null; render();
    };
    el.querySelectorAll(".ill-thumb").forEach((t) => t.onclick = () => imageModal(target, info.images[+t.dataset.i], reload, (img) => {
      open = true; final = { positive: img.prompt, negative: img.negative || "", notes: [] }; D.seed = img.seed || -1; render();
    }));
    $("#il-up", el).onchange = async (ev) => {
      try { const files = await readFiles(ev.target); await api("POST", B("/illust/upload"), { target, files }); toast("已上傳 " + files.length + " 張"); reload(); } catch (e) { fail(e); }
    };
    $("#il-toggle", el).onclick = async () => { collect(); open = !open; if (open && !ents) await loadEnts(); render(); };
    if (!open) return;
    if (!ents) { loadEnts().then(() => { const c = $("#il-chars", el); if (c) { c.innerHTML = charRows(); bindChars(); } }).catch(fail); }
    bindChars();
    const pick = async (mode) => {
      collect();
      try { const r = await api("POST", B("/illust/pick"), { chapter: opts.chapter, mode }); picks = r.passages; render(); } catch (e) { fail(e); }
    };
    if ($("#il-pick-h", el)) $("#il-pick-h", el).onclick = () => pick("highlight");
    if ($("#il-pick-a", el)) $("#il-pick-a", el).onclick = () => pick("action");
    el.querySelectorAll(".ill-pick").forEach((d) => d.onclick = async () => {
      collect(); D.passage = picks[+d.dataset.p].text; picks = null; D.chars = []; info.draft = {}; await loadEnts(); render();
    });
    $("#il-zh", el).onclick = async () => {
      collect();
      const text = isCh ? D.passage : (opts.entityText || "");
      if (!text.trim()) return toast(isCh ? "請先挑一段片段" : "沒有可以查的文字", true);
      try { const r = await api("POST", "/api/illust/zh", { text }); if (!r.has_dict) return toast("找不到中文對照表：到「設定 → 插畫」填 Forge 資料夾（會自動找 tagcomplete 的對照表）", true); zh = r.tags; render(); } catch (e) { fail(e); }
    };
    el.querySelectorAll(".chip.add").forEach((c) => c.onclick = () => { collect(); D.scene_tags = tagAppend(D.scene_tags, c.dataset.tag); render(); });
    $("#il-styles", el).onclick = () => { collect(); pickStyles(D.styles, (sel) => { D.styles = sel; render(); }); };
    $("#il-ai", el).onclick = async () => {
      collect();
      if (isCh && !D.passage.trim()) return toast("請先挑一段要畫的片段", true);
      const prov = $("#il-prov", el).value;
      const params = { target, passage: D.passage, chars: D.chars.map((c) => c.name), places: (D.places || []).map((p) => p.name) };
      try {
        await api("POST", B("/illust/draft"), { target, draft: D });
        const job = await api("POST", B("/jobs"), { action: "illust_prompt", params, provider: prov });
        Panel.attach(job);
        const btn = $("#il-ai", el); if (btn) { btn.disabled = true; btn.textContent = "AI 產生中……"; }
        const j = await waitJob(job.id);
        if (j.status !== "done") { toast("產生失敗，詳情看右側面板", true); render(); return; }
        info = await api("GET", B("/illust?target=" + enc(target)));
        Object.assign(D, info.draft || {});
        final = null; render();
      } catch (e) { fail(e); render(); }
    };
    $("#il-asm", el).onclick = async () => {
      collect();
      try {
        final = await api("POST", B("/illust/assemble"), { draft: D, profile: isComfy ? D.profile : null });
        await api("POST", B("/illust/draft"), { target, draft: D });
        render();
      } catch (e) { fail(e); }
    };
    if ($("#il-copy", el)) $("#il-copy", el).onclick = () => navigator.clipboard.writeText($("#il-pos", el).value).then(() => toast("已複製"));
    if ($("#il-gen", el)) $("#il-gen", el).onclick = async () => {
      collect();
      final.positive = $("#il-pos", el).value; final.negative = $("#il-neg", el).value;
      try {
        await api("POST", B("/illust/generate"), { target, positive: final.positive, negative: final.negative, seed: D.seed, count: +D.count,
          width: D.width, height: D.height, draft: D, profile: isComfy ? D.profile : null });
        toast("已送到 " + genName());
        pollQueue();
      } catch (e) { fail(e); }
    };
  };
  const bindChars = () => {
    el.querySelectorAll("[data-ch]").forEach((cb) => cb.onchange = async () => {
      collect();
      const name = cb.dataset.ch;
      if (cb.checked) {
        const e = await cardOf(name);
        D.chars.push({ name, file: e.file, tags: (e.card || {}).tags || "", description: (e.card || {}).description || "", position: "", action: "" });
      } else D.chars = D.chars.filter((c) => c.name !== name);
      final = null; render();
    });
    el.querySelectorAll("[data-pl]").forEach((cb) => cb.onchange = async () => {
      collect();
      const name = cb.dataset.pl;
      if (cb.checked) {
        const e = await cardOf(name);
        D.places = [...(D.places || []), { name, file: e.file, tags: (e.card || {}).tags || "", description: (e.card || {}).description || "" }];
      } else D.places = (D.places || []).filter((p) => p.name !== name);
      final = null; render();
    });
  };
  if (open) await loadEnts();
  render();
  pollQueue();
}

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

/* 書的插圖頁：封面、總覽、本書畫風 */
async function viewIllust(view, t) {
  t = t || "總覽";
  const tabs = ["總覽", "封面", "本書畫風"];
  view.innerHTML = `<div class="page-head"><div><h1>插圖</h1><div class="sub">每章、每個角色或地點都可以有插圖，全部選用。圖存在書資料夾的 <code>插圖</code> 裡（預設不進 git）</div></div></div>
    <div class="tabs">${tabs.map((x) => `<button class="tab ${x === t ? "active" : ""}" onclick="go('#/b/${enc(S.book)}/illust?t=${enc(x)}')">${x}</button>`).join("")}</div>
    <div id="il-body"></div>`;
  const body = $("#il-body");
  const cfgR = await illCfg();
  if (!cfgR.config.forge_url || cfgR.sheet_error) body.insertAdjacentHTML("beforebegin", `<div class="alert warn" style="margin-bottom:10px"><span class="t">${esc(cfgR.sheet_error || "")}</span></div>`);
  if (t === "封面") return renderIllust(body, "cover", { open: true });
  if (t === "本書畫風") {
    const bs = (await api("GET", B("/illust/overview"))).style;
    let styles = bs.styles || [];
    const draw = () => {
      body.innerHTML = `<div class="card" style="max-width:820px">
        <p class="muted small">這本書所有插圖的預設值；每張圖出圖時還可以再改。品質、分級、負面提示詞的全域預設在「設定 → 插畫」。</p>
        <div class="f"><span>畫風</span><div class="row"><span>${styles.length ? styles.map(esc).join("　＋　") : '<span class="muted">不套用</span>'}</span><button class="sm" id="bs-st">選畫風…</button></div></div>
        <div class="grid g2">
          <label class="f"><span>畫師標籤（會自動加 @）</span><input type="text" id="bs-artist" value="${esc(bs.artist || "")}"></label>
          <label class="f"><span>每張都加的標籤</span><input type="text" id="bs-extra" value="${esc(bs.extra || "")}"></label>
          <label class="f"><span>每張都加的負面提示詞</span><input type="text" id="bs-neg" value="${esc(bs.negative_extra || "")}"></label>
          <label class="f"><span>插圖尺寸</span><select id="bs-size"><option value="">用全域預設（${cfgR.config.width}×${cfgR.config.height}）</option>${cfgR.sizes.map(([n, w, h]) => `<option value="${w}x${h}" ${w === bs.width && h === bs.height ? "selected" : ""}>${n} ${w}×${h}</option>`).join("")}</select></label>
          <label class="f"><span>封面尺寸</span><select id="bs-csize">${cfgR.sizes.map(([n, w, h]) => `<option value="${w}x${h}" ${w === bs.cover_width && h === bs.cover_height ? "selected" : ""}>${n} ${w}×${h}</option>`).join("")}</select></label>
        </div>
        <div class="row"><span class="grow"></span><button class="primary" id="bs-save">儲存</button></div></div>`;
      $("#bs-st").onclick = () => pickStyles(styles, (sel) => { styles = sel; draw(); });
      $("#bs-save").onclick = async () => {
        const [w, h] = ($("#bs-size").value || "x").split("x").map((x) => parseInt(x) || null);
        const [cw, ch] = $("#bs-csize").value.split("x").map(Number);
        try {
          await api("POST", B("/illust/style"), { styles, artist: $("#bs-artist").value.trim(), extra: $("#bs-extra").value.trim(),
            negative_extra: $("#bs-neg").value.trim(), width: w, height: h, cover_width: cw, cover_height: ch });
          toast("已儲存");
        } catch (e) { fail(e); }
      };
    };
    return draw();
  }
  const o = await api("GET", B("/illust/overview"));
  const link = (it) => it.target === "cover" ? `#/b/${enc(S.book)}/illust?t=${enc("封面")}`
    : it.target.startsWith("chapter:") ? `#/b/${enc(S.book)}/ch/${it.target.split(":")[1]}?tab=illust`
      : `#/b/${enc(S.book)}/bible?t=${enc(it.target.split("/")[1])}&f=${enc(it.target.slice(7))}`;
  body.innerHTML = o.items.length ? `<div class="ill-overview">${o.items.map((it) => `<a class="ill-ov" href="${link(it)}">
      <img loading="lazy" src="${imgUrl(it.main)}" alt=""><div><b>${esc(it.label)}</b> <span class="muted small">${it.count} 張</span></div></a>`).join("")}</div>`
    : `<div class="card empty"><div class="big">✎</div>還沒有任何插圖。<br>到章節頁的「插圖」分頁、設定集的角色，或這裡的「封面」開始。</div>`;
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

/* ------------------------------------------------------------------ 關於 */
const ABOUT_LINKS = [
  ["設計參考", [
    ["oh-story-claudecode", "https://github.com/worldwonderer/oh-story-claudecode", "MIT", "novel-* skills 的部分設計概念改寫自此專案（授權全文見 plugin/THIRD_PARTY_NOTICES.md）"],
    ["Chinese-WebNovel-Skill", "https://github.com/Tomsawyerhu/Chinese-WebNovel-Skill", "", "參考中文網文寫作 skill 的流程分工（只參考概念）"],
    ["moshu 墨書", "https://github.com/huihuijiangqiang/moshu", "", "頁面分工與「AI 草稿先進候選區」的概念（未使用其程式碼）"],
    ["Pagekin（AI-Novel-Writer）", "https://github.com/EthanYoQ/AI-Novel-Writer", "GPL-3.0", "思考強度分階段、寫稿前對帳、章綱核對、審查與修訂分開、恢復稿等做法（只參考概念，未使用其程式碼）"],
    ["Novelcrafter：effective style entries", "https://www.novelcrafter.com/courses/codex-cookbook/effective-style-entries", "", "文風寫「怎麼寫」、給彈性範圍不給死數字（novel-style 參考概念）"],
    ["Sudowrite：Style", "https://docs.sudowrite.com/using-sudowrite/1ow1qkGqof9rtcyGnrWUBS/style/4gqKgVVjdN6XTKo71HChqV", "", "依場景類型給有標籤的範例段落（參考概念）"],
    ["Scriveno：STYLE-GUIDE", "https://cdn.jsdelivr.net/npm/scriveno@3.8.0/templates/STYLE-GUIDE.md", "", "文風的面向分類與 Always／Never／Consider 三分（參考概念）"],
    ["Leech & Short 文體分析清單", "https://www.lancaster.ac.uk/fass/projects/stylistics/topic10/12method.htm", "", "《Style in Fiction》的詞彙、語法、修辭、銜接分析框架（參考概念）"],
  ]],
  ["工作台使用的套件", [
    ["FastAPI", "https://github.com/fastapi/fastapi", "MIT", "網頁伺服器"],
    ["Uvicorn", "https://github.com/encode/uvicorn", "BSD-3-Clause", "網頁伺服器"],
    ["PyYAML", "https://github.com/yaml/pyyaml", "MIT", "讀取設定檔的 frontmatter"],
    ["OpenCC（opencc-python-reimplemented）", "https://github.com/yichen0831/opencc-python", "Apache-2.0", "匯入舊稿時簡體轉台灣繁體"],
    ["marked", "https://github.com/markedjs/marked", "MIT", "在網頁上顯示 Markdown（static/vendor）"],
  ]],
  ["可以連接的 AI 與工具（不隨專案附帶）", [
    ["Claude Code", "https://docs.claude.com/en/docs/claude-code/overview", "", "用 Claude 訂閱執行 novel-* skills"],
    ["DeepSeek API", "https://api-docs.deepseek.com/", "", "OpenAI 相容服務"],
    ["llama.cpp", "https://github.com/ggml-org/llama.cpp", "MIT", "本機模型（OpenAI 相容服務）"],
    ["Stable Diffusion WebUI Forge – Neo", "https://github.com/Haoming02/sd-webui-forge-classic/tree/neo", "", "插圖出圖（需用 --api 啟動）"],
    ["ComfyUI", "https://github.com/comfyanonymous/ComfyUI", "GPL-3.0", "插圖出圖的另一個後端（透過 API，只用內建節點）"],
    ["Anima", "https://huggingface.co/circlestone-labs/Anima", "", "提示詞格式依此模型的建議（標籤＋自然語言）"],
    ["a1111-sd-webui-tagcomplete", "https://github.com/DominikDoom/a1111-sd-webui-tagcomplete", "MIT", "標籤檢查與中文對照表使用它附的 tags 檔案（從 Forge 資料夾讀取，不隨專案附帶）"],
    ["StyleSelectorXL", "https://github.com/ahgsql/StyleSelectorXL", "MIT", "樣式表格式相容（範例在 examples/styles.example.json）"],
    ["EPUBCheck", "https://github.com/w3c/epubcheck", "", "匯出的 EPUB 用它驗證過"],
  ]],
];

async function viewGuide(view) {
  const lang = (window.I18N && I18N.lang) || "zh-TW";
  let text = null;
  for (const u of [`/static/guide/${lang}.md`, "/static/guide/zh-TW.md"]) {
    try {
      const r = await fetch(u, { cache: "no-cache" });
      if (r.ok) { text = await r.text(); break; }
    } catch (e) { /* 換下一個 */ }
  }
  if (!text) {
    view.innerHTML = `<div class="card empty"><div class="big">?</div>${esc(t("找不到說明文件。"))}</div>`;
    return;
  }
  view.innerHTML = `<div class="page-head"><div><h1>${esc(t("使用說明"))}</h1>
      <div class="sub">${esc(t("第一次用先看「兩個流程」；名詞看不懂再查名詞表。"))}</div></div></div>
    <div class="card"><div class="md"${LA()}>${md(text)}</div></div>`;
}

async function viewAbout(view) {
  let ver = "";
  try { ver = (await api("GET", "/api/config")).version; } catch (e) { /* ignore */ }
  view.innerHTML = `
    <div class="page-head"><div><h1>關於小說工作台</h1><div class="sub">Novel Studio v${esc(ver)}　·　MIT 授權</div></div></div>
    <div class="card about">
      <p>用 AI 寫繁體中文長篇連載小說的本機工作台。小說資料（設定、大綱、追蹤、正文）全部是純 Markdown＋YAML，存在你自己的書庫資料夾；網頁介面負責專案管理，寫作流程可以交給 Claude Code，或 DeepSeek、llama.cpp 等 OpenAI 相容模型。</p>
      <ul class="small">
        <li>只在本機執行（127.0.0.1），不會對外開放；工作台本身不會把資料傳到任何地方，只有你按下 AI 動作時，才會把需要的內容送給你選的 AI 服務。</li>
        <li>你的設定（config.json）與 API 金鑰（secrets.json）只存在工作台資料夾，不會進 git。</li>
        <li>書庫、共用庫（書庫的 <code>_共用</code>）、插圖都在你的書庫資料夾，和工作台程式分開。</li>
      </ul>
      <p class="small muted">本專案以 MIT 授權發布，全文見專案根目錄的 <code>LICENSE</code>。</p>
    </div>
    ${ABOUT_LINKS.map(([group, rows]) => `<div class="card about" style="margin-top:14px"><h2 style="margin-bottom:10px">${esc(group)}</h2>
      <table>${rows.map(([n, u, lic, d]) => `<tr><td class="nm"><a href="${esc(u)}" target="_blank" rel="noopener">${esc(n)}</a></td>
        <td>${lic ? `<span class="badge">${esc(lic)}</span>` : ""}</td><td class="small">${esc(d)}</td></tr>`).join("")}</table></div>`).join("")}`;
}

/* ------------------------------------------------------------------ 匯出 */
const fmtSize = (n) => n >= 1048576 ? (n / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(n / 1024)) + " KB";

async function viewExport(view) {
  const m = await api("GET", B("/export"));
  const p = m.prefs;
  const chs = m.chapters;
  const first = chs.length ? chs[0].no : "", last = chs.length ? chs[chs.length - 1].no : "";
  const sel = (id, obj, cur) => `<select id="${id}">${Object.entries(obj).map(([k, v]) => `<option value="${k}" ${k === cur ? "selected" : ""}>${esc(v)}</option>`).join("")}</select>`;
  view.innerHTML = `
    <div class="page-head"><div><h1>匯出</h1><div class="sub">把正文和資料整理成一個檔案，存在書資料夾的 <code>匯出</code> 裡</div></div></div>
    <div class="grid exp-grid">
      <div class="card">
        <h2 style="margin-bottom:12px">格式</h2>
        <div class="seg" id="x-fmt">
          <label><input type="radio" name="x-fmt" value="epub" ${p.format !== "txt" ? "checked" : ""}><span><b>EPUB 電子書</b><small>有目錄，可放進電子書閱讀器、Apple Books、Google Play 圖書</small></span></label>
          <label><input type="radio" name="x-fmt" value="txt" ${p.format === "txt" ? "checked" : ""}><span><b>TXT 純文字</b><small>任何地方都能開，適合貼到連載平台或手機閱讀器</small></span></label>
        </div>
        <h2 style="margin:18px 0 10px">內容</h2>
        ${m.items.map(([k, label]) => `<label class="cb"><input type="checkbox" data-item="${k}" ${p.items.includes(k) ? "checked" : ""}> ${esc(label)}${k === "bible" ? '<span class="muted small">（不含設定草稿）</span>' : ""}</label>`).join("")}
        <div class="row" style="margin:4px 0 0 26px">
          <span class="small muted">章節範圍</span>
          <input type="number" id="x-from" class="num-in" value="${esc(first)}" min="${esc(first)}" max="${esc(last)}"> <span class="small muted">到</span>
          <input type="number" id="x-to" class="num-in" value="${esc(last)}" min="${esc(first)}" max="${esc(last)}">
          <span class="small muted">（正文共 ${chs.length} 章，${fmtNum(chs.reduce((a, c) => a + c.chars, 0))} ${unitCh(m.unit)}；章綱也套用這個範圍）</span>
        </div>
        ${chs.length ? "" : '<div class="muted small" style="margin:6px 0 0 26px">還沒有採用的正文。候選稿要先採用才會匯出。</div>'}
      </div>
      <div class="card">
        <h2 style="margin-bottom:12px">書籍資訊與排版</h2>
        <div class="grid g2">
          <label class="f"><span>書名</span><input type="text" id="x-title" value="${esc(p.title || m.book_title)}"></label>
          <label class="f"><span>作者（選填）</span><input type="text" id="x-author" value="${esc(p.author)}"></label>
          <label class="f"><span>章名格式</span>${sel("x-ts", m.title_styles, p.title_style)}</label>
          <label class="f"><span>段落格式</span>${sel("x-ps", m.para_styles, p.para_style)}</label>
        </div>
        <div data-only="txt">
          <label class="f"><span>文字編碼</span>${sel("x-enc", m.encodings, p.encoding)}</label>
        </div>
        <div data-only="epub">
          <label class="cb"><input type="checkbox" id="x-vert" ${p.vertical ? "checked" : ""}> 直排（由右往左翻頁；章名建議用「第一章」格式）</label>
          <label class="cb"><input type="checkbox" id="x-cover" ${p.use_cover !== false ? "checked" : ""} ${m.cover ? "" : "disabled"}> 使用封面圖
            <span class="muted small">${m.cover ? "（" + esc(m.cover) + "）" : "（到「插圖 → 封面」出圖或上傳，或把 封面.jpg 放在書資料夾）"}</span></label>
          <label class="cb"><input type="checkbox" id="x-ill" ${p.include_illust !== false ? "checked" : ""} ${m.illust_chapters ? "" : "disabled"}> 在章首放插圖
            <span class="muted small">（${m.illust_chapters ? `${m.illust_chapters} 章有主圖` : "還沒有章節插圖"}）</span></label>
        </div>
        <div class="row" style="margin-top:12px"><span class="grow"></span><button class="primary" id="x-go">匯出</button></div>
        <div id="x-result"></div>
      </div>
    </div>
    <div class="card" style="margin-top:14px">
      <div class="card-title"><h2>匯出紀錄</h2><span class="muted small">檔案在書資料夾的 <code>匯出</code> 裡</span></div>
      <div id="x-list"></div>
    </div>`;
  const fmt = () => document.querySelector('input[name="x-fmt"]:checked').value;
  const sync = () => {
    document.querySelectorAll("[data-only]").forEach((el) => { el.hidden = el.dataset.only !== fmt(); });
    const textOn = $('[data-item="text"]').checked || $('[data-item="cards"]').checked;
    ["#x-from", "#x-to"].forEach((s) => { $(s).disabled = !textOn; });
  };
  document.querySelectorAll('input[name="x-fmt"], [data-item]').forEach((el) => el.onchange = sync);
  sync();
  const renderList = (list) => {
    $("#x-list").innerHTML = list.length ? `<table>${list.map((x) => `<tr>
        <td>${esc(x.file)}</td><td class="num">${fmtSize(x.size)}</td><td class="muted">${fmtTime(x.mtime)}</td>
        <td class="num"><a class="btn sm" href="${B("/exports/" + enc(x.file))}" download="${esc(x.file)}">下載</a>
        <button class="sm danger" data-del="${esc(x.file)}">刪除</button></td></tr>`).join("")}</table>`
      : '<div class="muted small">還沒有匯出過。</div>';
    document.querySelectorAll("[data-del]").forEach((b) => b.onclick = async () => {
      if (!confirm("刪除 " + b.dataset.del + "？")) return;
      try { await api("DELETE", B("/exports/" + enc(b.dataset.del))); renderList((await api("GET", B("/export"))).exports); } catch (e) { fail(e); }
    });
  };
  renderList(m.exports);
  $("#x-go").onclick = async () => {
    const items = [...document.querySelectorAll("[data-item]:checked")].map((el) => el.dataset.item);
    const from = parseInt($("#x-from").value), to = parseInt($("#x-to").value);
    if (!items.length) return toast("請至少勾選一項內容", true);
    if (from && to && from > to) return toast("章節範圍的起點不能大於終點", true);
    const body = {
      format: fmt(), items, title: $("#x-title").value.trim(), author: $("#x-author").value.trim(),
      title_style: $("#x-ts").value, para_style: $("#x-ps").value, encoding: $("#x-enc").value,
      vertical: $("#x-vert").checked, use_cover: $("#x-cover").checked, include_illust: $("#x-ill").checked,
      from: from && from !== first ? from : null, to: to && to !== last ? to : null,
    };
    if (body.title === m.book_title) body.title = "";
    const btn = $("#x-go");
    btn.disabled = true; btn.textContent = "匯出中……";
    try {
      const r = await api("POST", B("/export"), body);
      const parts = [];
      if (r.chapters) parts.push(`${r.chapters} 章、${fmtNum(r.chars)} ${unitCh(r.unit)}`);
      if (r.docs) parts.push(`${r.docs} 份資料`);
      $("#x-result").innerHTML = `<div class="alert ok" style="margin-top:12px"><span class="k">完成</span>
        <span class="t">${esc(r.file)}（${parts.join("，")}，${fmtSize(r.size)}）</span>
        <a class="btn sm primary" href="${B("/exports/" + enc(r.file))}" download="${esc(r.file)}">下載</a></div>`;
      renderList((await api("GET", B("/export"))).exports);
    } catch (e) { fail(e); } finally { btn.disabled = false; btn.textContent = "匯出"; }
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
  async run(action, params, provider) {
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
  async reply() {
    const text = $("#reply-text").value.trim();
    if (!text || !S.job) return;
    if (S.job.status === "running") { toast("還在執行，請等這一輪結束", true); return; }
    const sp = S.job.meta && S.job.meta.action === "style_design" && S.job.meta.params;
    if (sp && sp.name) {   // 文風任務：回覆就當成「請 AI 調整」
      try {
        const job = await api("POST", "/api/shared/styles/design", { mode: "revise", name: sp.name, note: text, provider: S.job.provider || this.prov() });
        $("#reply-text").value = "";
        S.styleJobTarget = sp.name;
        this.attach(job, false, true);
      } catch (e) { fail(e); }
      return;
    }
    try {
      const job = await api("POST", JB(S.job, "/jobs"), { action: "reply", resume: S.job.session_id, resume_provider: S.job.provider, provider: S.job.provider || this.prov(), params: { text } });
      $("#reply-text").value = "";
      this.attach(job, false, true);
    } catch (e) { fail(e); }
  },
  attach(job, quiet, keepLog) {
    if (S.es) { S.es.close(); S.es = null; }
    S.job = job; S.lastText = "";
    this.toggle(true);
    if (!keepLog) $("#panel-log").innerHTML = "";
    this.add(`<div class="ev-prompt">${esc(job.title === "回覆" ? job.prompt : job.title)}</div>`);
    this.setRunning(true);
    S.es = new EventSource(`/api/jobs/${job.id}/events`);
    S.es.onmessage = (m) => this.onEvent(JSON.parse(m.data));
    S.es.addEventListener("close", () => { S.es.close(); S.es = null; this.finish(); });
    S.es.onerror = () => { if (S.es && S.es.readyState === 2) { S.es = null; this.finish(); } };
  },
  async show(id) {
    try {
      const j = await api("GET", B("/jobs/" + id));
      if (j.status === "running") return this.attach(j);
      if (S.es) { S.es.close(); S.es = null; }
      S.job = j; S.lastText = "";
      this.toggle(true);
      $("#panel-log").innerHTML = "";
      this.add(`<div class="ev-meta">${fmtTime(j.started)}　${esc(j.title)}　${jobBadge(j.status)}</div>`);
      this.add(`<div class="ev-prompt">${esc(j.prompt)}</div>`);
      (j.events || []).forEach((e) => this.onEvent(e));
      this.setRunning(false);
    } catch (e) { fail(e); }
  },
  onEvent(e) {
    if (e.kind === "stream_start") {
      S.streamJson = !!e.json;
      this.add(`<div class="ev-stream">${e.text ? `<div class="ev-meta" style="text-align:left">${esc(e.text)}</div>` : ""}
        <details class="ev-think" hidden><summary>思考過程</summary><div class="tt"></div></details>
        <div class="ev-text st ${e.json ? "json" : ""}"></div></div>`);
      return;
    }
    const box = [...$("#panel-log").querySelectorAll(".ev-stream")].pop();
    if (e.kind === "thinking" && box) {
      const d = $(".ev-think", box); d.hidden = false; $(".tt", d).textContent += e.text; this.scroll(); return;
    }
    if (e.kind === "stream" && box) { $(".st", box).textContent += e.text; this.scroll(); return; }
    if (e.kind === "stream_end" && box) {
      const st = $(".st", box);
      if (S.streamJson) { st.outerHTML = `<details class="ev-json"><summary>結構化資料（JSON）</summary><pre>${esc(st.textContent)}</pre></details>`; }
      else { const raw = st.textContent; st.innerHTML = `<details class="ev-full"><summary>模型輸出全文（${raw.length} 字）</summary><div class="md"${LA()}>${md(raw)}</div></details>`; }
      return;
    }
    if (e.kind === "text") { S.lastText = e.text; this.add(`<div class="ev-text"><div class="md"${LA()}>${md(e.text)}</div></div>`); }
    else if (e.kind === "tool") this.add(`<div class="ev-tool">${esc(e.text)}</div>`);
    else if (e.kind === "tool_error") this.add(`<div class="ev-log">工具回報錯誤：${esc(e.text)}</div>`);
    else if (e.kind === "error") this.add(`<div class="ev-err">${esc(e.text)}</div>`);
    else if (e.kind === "log") this.add(`<div class="ev-log">${esc(e.text)}</div>`);
    else if (e.kind === "cancelled") this.add(`<div class="ev-meta">已停止</div>`);
    else if (e.kind === "result") {
      if (e.text && e.text.trim() === (S.lastText || "").trim()) {
        const last = [...$("#panel-log").querySelectorAll(".ev-text")].pop();
        if (last) { last.className = "ev-report"; last.insertAdjacentHTML("afterbegin", '<div class="rh">匯報</div>'); }
      } else if (e.text) {
        this.add(`<div class="ev-report"><div class="rh">匯報</div><div class="md"${LA()}>${md(e.text)}</div></div>`);
      }
      const u = e.usage ? `輸入 ${fmtNum(e.usage.prompt_tokens)}／輸出 ${fmtNum(e.usage.completion_tokens)} tokens` : "";
      this.add(`<div class="ev-meta">${e.turns ? e.turns + " 輪　" : ""}${u}${e.cost != null ? "　$" + Number(e.cost).toFixed(4) : ""}</div>`);
    } else if (e.kind === "end") {
      if (S.job) S.job.status = e.status;
    } else if (e.kind === "init" && S.job) { S.job.session_id = e.session_id; }
  },
  scroll() {
    const log = $("#panel-log");
    if (log.scrollHeight - log.scrollTop - log.clientHeight < 160) log.scrollTop = log.scrollHeight;
  },
  add(html) {
    const log = $("#panel-log");
    const empty = log.querySelector(".ev-empty"); if (empty) empty.remove();
    const nearBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 80;
    log.insertAdjacentHTML("beforeend", html);
    if (nearBottom) log.scrollTop = log.scrollHeight;
  },
  async finish() {
    this.setRunning(false);
    try {
      const j = await api("GET", JB(S.job, "/jobs/" + S.job.id));
      S.job.status = j.status; S.job.session_id = j.session_id;
    } catch (e) { /* ignore */ }
    S.books = (await api("GET", "/api/books").catch(() => ({ books: S.books }))).books;
    if (document.querySelector("textarea.editor")) toast("任務完成。你正在編輯，所以頁面沒有自動重新整理。");
    else if (S.job && S.job.book === "_共用") { if (typeof S.onSharedJob === "function") S.onSharedJob(S.job); }
    else if (S.book) refresh();
    if (S.job && S.job.meta && S.job.meta.action === "volume_draft" && S.job.status === "done") {
      toast("卷綱草稿已產生：到大綱頁的「卷況」按「採用」才會變成正式卷綱。");
    }
    $("#reply-text").focus();
  },
  setRunning(on) {
    $("#run-dot").className = "dot" + (on ? " run" : "");
    $("#fab-dot").className = "dot" + (on ? " run" : "");
    $("#btn-stop").hidden = !on;
    $("#reply-btn").disabled = on;
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

$("#btn-stop").onclick = async () => { if (S.job) await api("POST", `/api/jobs/${S.job.id}/cancel`).catch(fail); };
$("#reply-btn").onclick = () => Panel.reply();
$("#reply-text").addEventListener("keydown", (e) => { if ((e.ctrlKey || e.metaKey) && e.key === "Enter") Panel.reply(); });

/* ------------------------------------------------------------------ 啟動 */
(async function init() {
  try {
    const [cfg, acts, books] = await Promise.all([api("GET", "/api/config"), api("GET", "/api/actions"), api("GET", "/api/books")]);
    S.config = cfg.config; S.claudeFound = cfg.claude_found; S.actions = acts; S.books = books.books;
  } catch (e) { fail(e); }
  $("#panel-log").innerHTML = '<div class="ev-empty">從上方選一個動作，或在頁面上按按鈕。<br>Claude 的過程與匯報會顯示在這裡。</div>';
  let open = false;
  try { open = localStorage.getItem("panelOpen") === "1"; } catch (e) { /* ignore */ }
  Panel.toggle(open);
  try { S.provider = localStorage.getItem("provider") || null; } catch (e) { /* ignore */ }
  if (S.provider && !provChoices().find((p) => p.id === S.provider)) S.provider = null;
  $("#prov-sel").onchange = (ev) => Panel.setProv(ev.target.value);
  Panel.renderProv();
  Panel.renderActions();
  route();
})();
