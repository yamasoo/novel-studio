/* 小說工作台 前端 */
"use strict";

const S = {
  config: null, claudeFound: null, actions: [], books: [],
  book: null,                 // 目前的書 id
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
const fmtNum = (n) => (n || 0).toLocaleString("zh-TW");
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
  const { parts, q } = parseHash();
  const view = $("#view");
  try {
    if (parts[0] === "settings") { S.routeName = "settings"; await setBook(null, true); return await viewSettings(view); }
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
    }
    S.routeName = "shelf";
    await setBook(null, true);
    await viewShelf(view);
  } catch (e) {
    view.innerHTML = `<div class="card"><h2>出了點問題</h2><p class="muted">${esc(e.message)}</p><button onclick="go('#/')">回書架</button></div>`;
  } finally {
    renderNav();
  }
}
window.addEventListener("hashchange", route);
function refresh() { route(); }

async function setBook(id, keep) {
  if (id === S.book) return;
  if (!id && keep) { S.book = null; Panel.renderActions(); return; }
  S.book = id;
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
      ["bible", "✦", "設定集"], ["tracking", "⟲", "伏筆與時間線"], ["jobs", "◷", "任務紀錄"], ["export", "⇩", "匯出"],
    ];
    nav.innerHTML = items.map(([r, i, t]) =>
      `<a class="navlink ${S.routeName === r || (r === "chapters" && S.routeName === "ch") ? "active" : ""}" href="${base}/${r}"><span class="ico">${i}</span><span>${t}</span></a>`).join("");
  }
  document.querySelectorAll(".side-bottom .navlink").forEach((a) => a.classList.toggle("active", a.dataset.r === S.routeName));
}

/* ------------------------------------------------------------------ 書架 */
async function viewShelf(view) {
  const data = await api("GET", "/api/books");
  S.books = data.books;
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
    </div>
    ${S.claudeFound ? "" : `<div class="alert warn" style="margin-bottom:14px"><span class="k">找不到 Claude Code</span><span class="t">按鈕會無法執行。請安裝 Claude Code，或到設定填入 claude 的路徑。</span><button class="sm" onclick="go('#/settings')">設定</button></div>`}
    <div class="shelf">
      ${books.map((b) => `
        <div class="card book" onclick="go('#/b/${enc(b.id)}')">
          <div class="title">${esc(b.name)}</div>
          <div class="hook">${esc(b.hook || "（還沒有一句話鉤子）")}</div>
          <div class="meta"><span>已寫 ${b.chapters_written} 章</span><span>${fmtNum(b.chars)} 字</span>
          ${b.pending_candidates ? `<span class="badge b-accent">${b.pending_candidates} 份候選稿</span>` : ""}</div>
          <div class="meta">更新於 ${fmtTime(b.updated) || "—"}</div>
        </div>`).join("")}
      <div class="card book new" id="new-book"><div class="plus">＋</div><div>開新書</div></div>
    </div>
    ${books.length ? "" : `<div class="card" style="margin-top:16px"><h3>第一次使用？</h3><p class="muted">可以先放一本示範書《退婚之後》進書架，看看各頁面長什麼樣子。示範書只是資料夾，隨時可以刪掉。</p><button id="add-demo">加入示範書</button></div>`}
    ${others.length ? `<hr class="sep"><div class="muted small">書庫裡還有這些資料夾（沒有 CLAUDE.md，不是小說專案）：</div>
      <div class="row" style="margin-top:6px">${others.map((o) => `<span class="badge">${esc(o.name)}</span>
      <button class="sm" onclick="initFolder('${esc(o.id)}')">在這裡開書</button>`).join("")}</div>` : ""}`;
  $("#new-book").onclick = newBookDialog;
  if ($("#add-demo")) $("#add-demo").onclick = async () => { try { await api("POST", "/api/demo"); toast("已加入示範書"); refresh(); } catch (e) { fail(e); } };
  renderNav();
}

function newBookDialog() {
  modal(`
    <h2>開新書</h2>
    <p class="muted small">會在書庫建立資料夾，然後請 ${esc(Panel.provName())} 跟你做開書訪談（可以在右側面板上方切換執行者）。訪談問題會出現在右側面板，直接在下方回覆即可。</p>
    <label class="f"><span>書名（也是資料夾名稱）</span><input type="text" id="nb-name" placeholder="例如：退婚之後"></label>
    <label class="f"><span>初步構想（選填）</span><textarea id="nb-idea" rows="4" placeholder="一句話、一段簡介，或幾個關鍵字"></textarea></label>
    <div class="row"><span class="grow"></span><button onclick="closeModal()">取消</button><button class="primary" id="nb-go">建立並開始訪談</button></div>`,
  (el) => {
    $("#nb-name", el).focus();
    $("#nb-go", el).onclick = async () => {
      try {
        const r = await api("POST", "/api/books", { name: $("#nb-name", el).value, idea: $("#nb-idea", el).value, provider: Panel.prov() });
        closeModal();
        S.books = (await api("GET", "/api/books")).books;
        go("#/b/" + enc(r.id));
        if (r.job) Panel.attach(r.job);
      } catch (e) { fail(e); }
    };
  });
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
  const [, stateBody] = splitFM(ov.state_card || "");
  const next = ov.next;
  view.innerHTML = `
    <div class="page-head">
      <div><h1>${esc(S.book)}</h1><div class="sub">${esc(ov.hook || "")}</div></div>
      <div class="row">
        ${next.has_card
          ? `<button class="primary" onclick="Panel.openForm('write',{from:${next.no},to:${next.no}})">寫第${next.no}章${next.title ? "《" + esc(next.title) + "》" : ""}</button>`
          : `<button class="primary" onclick="Panel.openForm('chapter_cards',{from:${next.no},to:${next.no + 9}})">排第${next.no}章起的章綱</button>`}
        <button onclick="Panel.openForm('review',{from:${Math.max(1, ov.latest - 4)},to:${Math.max(1, ov.latest)}})">審查最近章節</button>
      </div>
    </div>
    <div class="grid g4">
      <div class="card stat"><div class="num">${ov.written}</div><div class="lbl">已寫章數</div></div>
      <div class="card stat"><div class="num">${fmtNum(ov.chars)}</div><div class="lbl">正文字數</div></div>
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
        <div class="md">${stateBody.trim() ? md(stateBody) : '<span class="muted">還沒有狀態卡。寫完第一章後會自動產生。</span>'}</div>
      </div>
    </div>
    ${ov.recent.length ? `<div class="card" style="margin-top:14px"><div class="card-title"><h2>最近章節</h2></div>
      <table>${ov.recent.map((c) => `<tr class="click" onclick="go('#/b/${enc(S.book)}/ch/${c.no}')"><td>第${c.no}章</td><td>${esc(c.title)}</td><td class="num">${fmtNum(c.chars)} 字</td></tr>`).join("")}</table></div>` : ""}`;
}
function alertHtml(a) {
  let btn = "";
  if (a.chapter) btn = `<button class="sm" onclick="go('#/b/${enc(S.book)}/ch/${a.chapter}?tab=${a.tab || "candidate"}')">${a.tab === "revision" ? "確認" : "審閱"}</button>`;
  else if (a.action === "recoveries") btn = `<button class="sm" onclick="go('#/b/${enc(S.book)}/jobs')">查看</button>`;
  else if (a.action === "sync_tracking") btn = `<button class="sm" onclick="Panel.run('sync_tracking',{})">補齊</button>`;
  else if (a.kind === "設定草稿") btn = `<button class="sm" onclick="go('#/b/${enc(S.book)}/bible?t=草稿')">查看</button>`;
  else if (a.kind.startsWith("伏筆")) btn = `<button class="sm" onclick="go('#/b/${enc(S.book)}/tracking')">查看</button>`;
  return `<div class="alert ${a.level}"><span class="k">${esc(a.kind)}</span><span class="t">${esc(a.text)}</span>${btn}</div>`;
}

/* ------------------------------------------------------------------ 章節列表 */
async function viewChapters(view) {
  const chs = await api("GET", B("/chapters"));
  view.innerHTML = `
    <div class="page-head"><div><h1>章節</h1><div class="sub">共 ${chs.length} 章　·　點一列開啟</div></div>
      <div class="row"><button onclick="Panel.openForm('chapter_cards')">排章綱</button><button class="primary" onclick="Panel.openForm('write')">寫章節</button></div></div>
    <div class="card">
      ${chs.length ? `<div class="table-wrap"><table>
        <thead><tr><th>章</th><th>章名</th><th>功能</th><th>章綱</th><th style="text-align:right">正文字數</th><th>候選稿</th></tr></thead>
        <tbody>${chs.map((c) => `<tr class="click" onclick="go('#/b/${enc(S.book)}/ch/${c.no}')">
          <td>第${c.no}章</td><td>${esc(c.title)}</td><td class="muted">${esc(c.func)}</td>
          <td>${c.card_file ? statusBadge(c.card_status || "草稿") : '<span class="badge b-bad">無</span>'}</td>
          <td class="num">${c.text_file ? fmtNum(c.chars) : '<span class="muted">—</span>'}</td>
          <td>${c.candidate_file ? `<span class="badge b-accent">待審 ${fmtNum(c.candidate_chars)} 字</span>` : ""}</td></tr>`).join("")}
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
      ${!c.card_file ? `<button onclick="Panel.openForm('chapter_cards',{from:${no},to:${no}})">補章綱</button>` : ""}
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
    <div id="goal-box"></div>
    <div id="review-box"></div>
    <div id="doc"></div>`;
  if (tab === "revision") return renderRevision($("#doc"), no, rv);
  if (c.card_file && (tab === "text" || tab === "candidate")) renderGoals($("#goal-box"), no, tab === "candidate", cur && cur[2]);
  if (tab === "text" || tab === "candidate") renderReview($("#review-box"), no, tab === "candidate", cur && cur[2]);
  if (cur) await docView($("#doc"), cur[2], { prose: tab === "text" || tab === "candidate", checkable: tab === "text" || tab === "candidate" });
  else $("#doc").innerHTML = `<div class="card empty">這章還沒有任何檔案。</div>`;
  if (tab === "candidate") {
    $("#cand-accept").onclick = async () => {
      if (!confirm(`採用第${no}章？候選稿會移到正文，並請 ${Panel.provName()} 回寫追蹤資料。`)) return;
      try { const r = await api("POST", B(`/candidate/${no}/accept?provider=${enc(Panel.prov())}`)); Panel.attach(r.job); go(`${base}?tab=text`); } catch (e) { fail(e); }
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

/* ------------------------------------------------------------------ 文件檢視／編輯 */
async function docView(el, path, opts = {}) {
  let f;
  try { f = await api("GET", B("/file?path=" + enc(path))); }
  catch (e) { el.innerHTML = `<div class="card empty">${esc(e.message)}</div>`; return; }
  let editing = false, findings = null;
  let fm, body;
  [fm, body] = splitFM(f.text);
  const render = () => {
    const fmHtml = Object.keys(fm).length ? `<div class="fm">${Object.entries(fm).filter(([, v]) => v !== "" && v !== "[]")
      .map(([k, v]) => `<span class="badge">${esc(k)}：${esc(v)}</span>`).join("")}</div>` : "";
    el.innerHTML = `
      <div class="doc-wrap ${findings ? "with-side" : ""}">
        <div class="card">
          <div class="doc-bar">
            <span class="path">${esc(f.path)}</span>${opts.prose ? `<span class="badge">${fmtNum(f.chars)} 字</span>` : ""}
            <span class="grow"></span>
            ${opts.checkable ? `<button class="sm" data-a="check">檢查用語與 AI 味</button>` : ""}
            ${editing ? `<button class="sm" data-a="cancel">取消</button><button class="sm primary" data-a="save">儲存</button>`
              : `<button class="sm" data-a="edit">編輯</button>`}
          </div>
          ${editing ? `<textarea class="editor ${opts.prose ? "prose" : ""}" spellcheck="false">${esc(f.text)}</textarea>`
            : `${fmHtml}<div class="md ${opts.prose ? "prose" : ""}">${md(body)}</div>`}
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
        const r = await api("PUT", B("/file"), { path: f.path, text, mtime: f.mtime });
        toast("已儲存");
        f = await api("GET", B("/file?path=" + enc(path)));
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
  const draw = () => {
    let n = 0;
    el.innerHTML = `
      <div class="card" style="margin-bottom:14px">
        <div class="row"><b>修訂對照</b><span class="badge">${rv.changes} 處變更</span><span class="muted small">原稿：${esc(rv.base_path)}　·　${fmtTime(rv.created)}</span>
          <span class="grow"></span><button class="sm" id="rv-all-new">全部採用修訂</button><button class="sm" id="rv-all-old">全部保留原文</button></div>
        ${rv.stale ? '<div class="alert warn" style="margin-top:8px"><span class="k">對不上</span><span class="t">原稿在修訂之後被改過了，這份修訂不能套用，請捨棄後重新修訂。</span></div>' : ""}
        <details style="margin-top:8px"><summary class="small">處理的意見與 AI 的說明</summary><div class="md small" style="margin-top:6px">${md("**意見**\n\n" + (rv.notes || "") + "\n\n**說明**\n\n" + (rv.report || ""))}</div></details>
      </div>
      <div class="rv-blocks">${rv.blocks.map((b) => {
        if (b.type === "same") {
          return b.old.length > 2
            ? `<details class="rv-same"><summary class="muted small">${b.old.length} 段沒有變更（展開）</summary>${b.old.map((x) => `<p>${esc(x)}</p>`).join("")}</details>`
            : `<div class="rv-same">${b.old.map((x) => `<p>${esc(x)}</p>`).join("")}</div>`;
        }
        const k = String(b.index); const useNew = (choice[k] || "new") === "new"; n++;
        const oldHtml = b.old.length ? b.old.map((x, i) => `<p>${b.inline ? inlineHtml(b.inline[i], "old") : esc(x)}</p>`).join("") : '<p class="muted small">（原文沒有這段）</p>';
        const newHtml = b.new.length ? b.new.map((x, i) => `<p>${b.inline ? inlineHtml(b.inline[i], "new") : esc(x)}</p>`).join("") : '<p class="muted small">（修訂刪掉了這段）</p>';
        return `<div class="rv-change">
          <div class="rv-side old ${useNew ? "" : "chosen"}" data-k="${k}" data-v="old"><div class="rv-tag">原文</div>${oldHtml}</div>
          <div class="rv-side new ${useNew ? "chosen" : ""}" data-k="${k}" data-v="new"><div class="rv-tag">修訂</div>${newHtml}</div>
        </div>`;
      }).join("")}</div>
      <div class="card row" style="margin-top:14px;position:sticky;bottom:10px">
        <span class="muted small">點左右兩邊選擇要的版本。套用後會存成候選稿${rv.base_path.startsWith("正文") ? "（原本的正文不動，採用候選稿時才覆蓋並回寫追蹤）" : ""}。</span>
        <span class="grow"></span><button class="sm danger" id="rv-discard">捨棄這份修訂</button>
        <button class="primary" id="rv-apply" ${rv.stale ? "disabled" : ""}>套用到候選稿</button></div>`;
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
        go(`#/b/${enc(S.book)}/ch/${no}?tab=candidate`);
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
    modal(`<h2>恢復稿</h2><div class="muted small" style="margin-bottom:8px">${esc(r.label)}　·　${esc(r.reason)}　·　${fmtNum(r.chars)} 字</div>
      <textarea class="editor prose" style="min-height:50vh" readonly>${esc(r.text)}</textarea>
      <div class="row" style="margin-top:10px"><span class="grow"></span><button id="rc-copy">複製</button><button onclick="closeModal()">關閉</button></div>`, (el) => {
      $("#rc-copy", el).onclick = () => { navigator.clipboard.writeText(r.text).then(() => toast("已複製")); };
    });
  } catch (e) { fail(e); }
};
/* ------------------------------------------------------------------ 大綱 */
async function viewOutline(view, file) {
  const files = await api("GET", B("/outline"));
  if (!file && files.length) file = files[0].file;
  view.innerHTML = `
    <div class="page-head"><div><h1>大綱</h1><div class="sub">全書大綱與卷綱。章綱在「章節」頁。</div></div>
      <div class="row"><button onclick="Panel.openForm('concept')">故事核心診斷</button><button onclick="Panel.openForm('master_outline')">全書大綱</button>
      <button onclick="Panel.openForm('volume_outline')">卷綱</button><button class="primary" onclick="Panel.openForm('chapter_cards')">排章綱</button></div></div>
    <div class="split">
      <div class="list">${files.length ? files.map((x) => `<div class="item ${x.file === file ? "active" : ""}" onclick="go('#/b/${enc(S.book)}/outline?f=${enc(x.file)}')"><div class="nm">${esc(x.name)}</div></div>`).join("")
        : '<div class="muted">還沒有大綱。</div>'}
        <div class="item" onclick="go('#/b/${enc(S.book)}/bible?t=核心&f=${enc("設定/故事核心.md")}')"><div class="nm">故事核心</div><div class="ds">設定/故事核心.md</div></div>
      </div>
      <div id="doc">${file ? "" : '<div class="card empty"><div class="big">⌘</div>還沒有大綱。可以先做「故事核心診斷」，再規劃全書大綱。</div>'}</div>
    </div>`;
  if (file) await docView($("#doc"), file);
}

/* ------------------------------------------------------------------ 設定集 */
async function viewBible(view, t, file) {
  const b = await api("GET", B("/bible"));
  t = t || "角色";
  const tabs = ["角色", "勢力", "世界觀", "核心", "草稿"];
  const list = b[t] || [];
  if (!file && list.length) file = list[0].file;
  const btns = {
    "角色": `<button class="primary" onclick="Panel.openForm('character')">新增／補完角色</button>`,
    "勢力": `<button onclick="Panel.openForm('free',{text:'請使用 novel-bible skill 建立一個新勢力：'})">新增勢力</button>`,
    "世界觀": `<button onclick="Panel.openForm('free',{text:'請使用 novel-bible skill 設計世界觀：'})">設計世界觀</button>`,
    "核心": `<button onclick="Panel.openForm('style')">分析／調整文風</button><button onclick="Panel.openForm('preference')">記錄偏好</button>`,
    "草稿": `<button onclick="Panel.openForm('gen_drafts')">生成草稿</button><button class="primary" onclick="Panel.openForm('promote_drafts')">草稿轉正式</button>`,
  };
  view.innerHTML = `
    <div class="page-head"><div><h1>設定集</h1><div class="sub">靜態設定。角色目前的位置、傷勢、知道什麼，在「伏筆與時間線」頁。</div></div>
      <div class="row">${btns[t] || ""}<button onclick="Panel.openForm('intake')">整理內容入庫</button></div></div>
    <div class="tabs">${tabs.map((x) => `<button class="tab ${x === t ? "active" : ""}" onclick="go('#/b/${enc(S.book)}/bible?t=${enc(x)}')">${x}${b[x] && b[x].length ? ` <span class="badge">${b[x].length}</span>` : ""}</button>`).join("")}</div>
    <div class="split">
      <div class="list">${list.length ? list.map((e) => `
        <div class="item ${e.file === file ? "active" : ""}" onclick="go('#/b/${enc(S.book)}/bible?t=${enc(t)}&f=${enc(e.file)}')">
          <div class="row"><span class="nm">${esc(e.name)}</span><span class="grow"></span>${e.role ? `<span class="badge">${esc(e.role)}</span>` : ""}${e.status === "草稿" ? statusBadge("草稿") : ""}</div>
          ${e.summary ? `<div class="ds">${esc(e.summary)}</div>` : ""}</div>`).join("")
        : `<div class="muted">這裡還是空的。</div>`}</div>
      <div id="doc">${file ? "" : '<div class="card empty"><div class="big">✦</div>選左邊的項目查看。</div>'}</div>
    </div>`;
  if (file) await docView($("#doc"), file);
}

/* ------------------------------------------------------------------ 伏筆與時間線 */
async function viewTracking(view, t) {
  const d = await api("GET", B("/tracking"));
  t = t || "foreshadow";
  const tabs = [["foreshadow", "伏筆"], ["timeline", "時間線"], ["chars", "角色狀態"], ["state", "狀態卡"], ["glossary", "名詞表"]];
  const latest = d.latest || 0;
  const chn = (s) => { const m = String(s || "").match(/(\d+)/); return m ? parseInt(m[1]) : null; };
  let body = "";
  if (t === "foreshadow") {
    const rows = d.foreshadow.rows;
    body = rows.length ? `<div class="card"><div class="row" style="margin-bottom:8px"><label class="cb" style="margin:0"><input type="checkbox" id="hide-done" checked> 隱藏已回收／廢棄</label>
      <span class="grow"></span><span class="muted small">黃底：重要度中以上、超過 ${d.stale_foreshadow} 章沒出現，或已過預計回收章</span></div>
      <div class="table-wrap"><table id="fs-table"><thead><tr>${d.foreshadow.headers.map((h) => `<th>${esc(h)}</th>`).join("")}</tr></thead><tbody>
      ${rows.map((r) => {
        const done = ["已回收", "廢棄"].includes(r["狀態"]);
        const last = chn(r["最後出現"]) || chn(r["埋設章"]);
        const due = chn(r["預計回收"]);
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
    body = g.rows.length ? `<div class="card"><div class="row" style="margin-bottom:8px"><span class="grow"></span><button class="sm" onclick="go('#/b/${enc(S.book)}/bible?t=核心&f=${enc("設定/名詞表.md")}')">編輯名詞表</button></div>
      <div class="table-wrap"><table><thead><tr>${g.headers.map((h) => `<th>${esc(h)}</th>`).join("")}</tr></thead>
      <tbody>${g.rows.map((r) => `<tr>${g.headers.map((h) => `<td>${esc(r[h])}</td>`).join("")}</tr>`).join("")}</tbody></table></div></div>`
      : `<div class="card empty">名詞表是空的。</div>`;
  }
  view.innerHTML = `
    <div class="page-head"><div><h1>伏筆與時間線</h1><div class="sub">這裡是「已經發生的事實」，寫完章節後由 Claude 回寫。目前寫到第 ${latest} 章。</div></div>
      <div class="row"><button onclick="Panel.openForm('review_all')">伏筆與角色健康檢查</button></div></div>
    <div class="tabs">${tabs.map(([k, l]) => `<button class="tab ${k === t ? "active" : ""}" onclick="go('#/b/${enc(S.book)}/tracking?t=${k}')">${l}</button>`).join("")}</div>
    ${body}`;
  if (t === "foreshadow" && $("#hide-done")) {
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
      <label class="f"><span>預設執行者</span><select id="c-defprov">${(c.providers || []).map((p) => `<option value="${esc(p.id)}" ${p.id === c.default_provider ? "selected" : ""}>${esc(p.name)}</option>`).join("")}</select></label>
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
      <h2 style="margin-bottom:12px">警示</h2>
      <div class="grid g2">
        <label class="f"><span>伏筆幾章沒出現就提醒</span><input type="number" id="c-sf" value="${esc(c.stale_foreshadow)}"></label>
        <label class="f"><span>角色幾章沒登場就提醒</span><input type="number" id="c-sc" value="${esc(c.stale_character)}"></label>
      </div>
    </div>
    <div class="row" style="margin-top:14px"><span class="grow"></span><button class="primary" id="c-save">儲存設定</button></div>`;
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
          <label class="f"><span>API 金鑰 ${S.keyStatus && S.keyStatus[p.id] ? `<span class="badge b-ok">${esc(S.keyStatus[p.id])}</span>` : ""}</span>
            <input type="password" data-key="1" value="${esc(keys[p.id] || "")}" placeholder="${S.keyStatus && S.keyStatus[p.id] ? "留空＝不變更" : "本機服務可留空"}"></label>
          <label class="f"><span>或用環境變數名稱</span><input type="text" data-k="key_env" value="${esc(p.key_env || "")}" placeholder="例如 DEEPSEEK_API_KEY"></label>
          <label class="f"><span>上下文長度（tokens）</span><input type="number" data-k="context_tokens" value="${esc(p.context_tokens)}"></label>
          <label class="f"><span>最大輸出（tokens）</span><input type="number" data-k="max_output" value="${esc(p.max_output)}"></label>
          <label class="f"><span>溫度</span><input type="number" step="0.1" data-k="temperature" value="${esc(p.temperature)}"></label>
          <label class="f"><span>輸入價格（每百萬 tokens，美元，選填）</span><input type="number" step="0.01" data-k="price_in" value="${esc(p.price_in || 0)}"></label>
          <label class="f"><span>輸出價格（每百萬 tokens，美元，選填）</span><input type="number" step="0.01" data-k="price_out" value="${esc(p.price_out || 0)}"></label>
        </div>
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
      card.querySelectorAll("[data-r]").forEach((sel) => sel.onchange = () => {
        provs[i].reasoning = Object.assign({}, provs[i].reasoning || {}, { [sel.dataset.r]: sel.value });
      });
      card.querySelector('[data-a="del"]').onclick = () => { if (confirm("刪除這個服務設定？")) { provs.splice(i, 1); renderProvs(); } };
      card.querySelector('[data-a="test"]').onclick = async () => {
        const msg = card.querySelector("[data-msg]");
        msg.textContent = "連線中……";
        try {
          await saveProvs();
          const r = await api("POST", `/api/providers/${enc(provs[i].id)}/models`);
          $(`#ml-${i}`).innerHTML = r.models.map((m) => `<option value="${esc(m)}">`).join("");
          msg.innerHTML = `<span class="badge b-ok">連線成功</span> 可用模型：${r.models.map(esc).join("、") || "（伺服器沒有列出）"}`;
          if (!provs[i].model && r.models.length === 1) { provs[i].model = r.models[0]; card.querySelector('[data-k="model"]').value = r.models[0]; }
        } catch (e) { msg.innerHTML = `<span class="badge b-bad">失敗</span> ${esc(e.message)}`; }
      };
    });
  };
  const saveProvs = async () => {
    const r = await api("POST", "/api/providers", { providers: provs, keys });
    S.config = r.config; S.keyStatus = r.key_status;
    Object.keys(keys).forEach((k) => delete keys[k]);
    return r;
  };
  renderProvs();
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
          <span class="small muted">（正文共 ${chs.length} 章，${fmtNum(chs.reduce((a, c) => a + c.chars, 0))} 字；章綱也套用這個範圍）</span>
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
            <span class="muted small">${m.cover ? "（" + esc(m.cover) + "）" : "（把 封面.jpg 或 封面.png 放在書資料夾裡就會出現）"}</span></label>
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
      vertical: $("#x-vert").checked, use_cover: $("#x-cover").checked,
      from: from && from !== first ? from : null, to: to && to !== last ? to : null,
    };
    if (body.title === m.book_title) body.title = "";
    const btn = $("#x-go");
    btn.disabled = true; btn.textContent = "匯出中……";
    try {
      const r = await api("POST", B("/export"), body);
      const parts = [];
      if (r.chapters) parts.push(`${r.chapters} 章、${fmtNum(r.chars)} 字`);
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
  provObj() { return ((S.config && S.config.providers) || []).find((p) => p.id === this.prov()) || { id: "claude_code", type: "claude_code", name: "Claude Code" }; },
  provName() { return this.provObj().name; },
  isClaude() { return this.provObj().type === "claude_code"; },
  renderProv() {
    const ps = (S.config && S.config.providers) || [];
    $("#prov-sel").innerHTML = ps.map((p) => `<option value="${esc(p.id)}" ${p.id === this.prov() ? "selected" : ""}>${esc(p.name)}${p.type !== "claude_code" && !p.base_url ? "（未設定）" : ""}</option>`).join("");
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
        return `<label class="f"><span>${esc(f.label)}</span><input type="${f.type === "number" ? "number" : "text"}" data-k="${f.key}" value="${esc(v)}"></label>`;
      }).join("")}
      <div class="row"><span class="grow"></span><button class="primary" id="pf-go">執行</button></div>`;
    const first = el.querySelector("[data-k]"); if (first) first.focus();
    $("#pf-go").onclick = () => {
      const p = {};
      el.querySelectorAll("[data-k]").forEach((i) => p[i.dataset.k] = i.type === "checkbox" ? i.checked : (i.type === "number" ? (i.value ? parseInt(i.value) : null) : i.value));
      this.run(id, p);
    };
  },
  closeForm() { $("#panel-form").innerHTML = ""; },
  async run(action, params) {
    try {
      const job = await api("POST", B("/jobs"), { action, params, provider: this.prov() });
      this.closeForm();
      this.attach(job);
    } catch (e) { fail(e); }
  },
  async reply() {
    const text = $("#reply-text").value.trim();
    if (!text || !S.job) return;
    if (S.job.status === "running") { toast("還在執行，請等這一輪結束", true); return; }
    try {
      const job = await api("POST", B("/jobs"), { action: "reply", resume: S.job.session_id, resume_provider: S.job.provider, provider: S.job.provider || this.prov(), params: { text } });
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
      else { const raw = st.textContent; st.innerHTML = `<details class="ev-full"><summary>模型輸出全文（${raw.length} 字）</summary><div class="md">${md(raw)}</div></details>`; }
      return;
    }
    if (e.kind === "text") { S.lastText = e.text; this.add(`<div class="ev-text"><div class="md">${md(e.text)}</div></div>`); }
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
        this.add(`<div class="ev-report"><div class="rh">匯報</div><div class="md">${md(e.text)}</div></div>`);
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
      const j = await api("GET", B("/jobs/" + S.job.id));
      S.job.status = j.status; S.job.session_id = j.session_id;
    } catch (e) { /* ignore */ }
    S.books = (await api("GET", "/api/books").catch(() => ({ books: S.books }))).books;
    if (document.querySelector("textarea.editor")) toast("任務完成。你正在編輯，所以頁面沒有自動重新整理。");
    else if (S.book) refresh();
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
  if (S.provider && !((S.config && S.config.providers) || []).find((p) => p.id === S.provider)) S.provider = null;
  $("#prov-sel").onchange = (ev) => Panel.setProv(ev.target.value);
  Panel.renderProv();
  Panel.renderActions();
  route();
})();
