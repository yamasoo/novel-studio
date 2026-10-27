/* 角色關係圖：純 SVG，不依賴外部套件。
   資料來自後端 relations.graph_data：節點（角色、勢力）、勢力成員、全部關係列。
   勢力是一個框，成員放在框裡；角色之間的關係是帶箭頭的線（A 對 B、B 對 A 分開畫）。
   滑桿可以看到第 N 章當時的關係。 */
(function () {
  const MAIN = ["主角", "主要配角"];
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const chNo = (s) => { const m = String(s || "").match(/\d+/); return m ? parseInt(m[0], 10) : 0; };
  const short = (n) => { n = String(n); if (n.length > 7 && n.includes("·")) return n.split("·")[0]; return n.length > 9 ? n.slice(0, 8) + "…" : n; };
  const cut = (s, n) => { s = String(s || ""); return s.length > n ? s.slice(0, n) + "…" : s; };
  const PH = 32, ROW = 46, PER_COL = 4, HEAD = 34, PAD = 14;
  const pillW = (n) => Math.max(76, short(n).length * 15 + 30);
  const hue = (i) => (i * 67 + 18) % 360;

  function activeAt(r, n) {
    const ended = String(r["結束章"] || "").trim();
    return chNo(r["起始章"]) <= n && (!ended || chNo(ended) > n);
  }

  function mount(el, data) {
    const nodes = data.nodes || [], latest = data.latest || 0;
    const st = { n: latest, all: false, sel: null, pos: {}, view: { x: 0, y: 0, k: 1 }, laid: false, fit: true };
    el.innerHTML = `<div class="rg">
      <div class="rg-side"><div class="rg-list"></div><div class="rg-detail"></div></div>
      <div class="rg-main">
        <div class="rg-head"><div><b>角色關係圖</b><div class="rg-stat"></div></div>
          <div class="rg-btns"><button class="sm" data-a="fit" title="縮放到看得到全部">回到中心</button><button class="sm" data-a="relayout" title="把拖動過的位置排回原樣">重新排列</button></div></div>
        <svg class="rg-svg" xmlns="http://www.w3.org/2000/svg"></svg>
        <div class="rg-foot">
          <label class="rg-slider">看到第 <b class="rg-n"></b> 章 <input type="range" min="0" max="${Math.max(latest, 1)}" value="${latest}"></label>
          <label class="cb" style="margin:0"><input type="checkbox" class="rg-all"> 顯示配角與反派</label>
          <span class="rg-legend"><i class="lg lg-n"></i>目前有效的關係　<i class="lg lg-new"></i>這一章剛改變的　<i class="lg lg-box"></i>勢力（成員在框裡）　<i class="lg lg-free"></i>無所屬</span>
        </div>
      </div></div>`;
    const svg = el.querySelector(".rg-svg"), listEl = el.querySelector(".rg-list"), detEl = el.querySelector(".rg-detail");
    const statEl = el.querySelector(".rg-stat"), nEl = el.querySelector(".rg-n");
    let model = null;

    // ------------------------------------------------------------ 資料整理
    function build() {
      const chars = nodes.filter((x) => x.kind === "角色"), facs = nodes.filter((x) => x.kind === "勢力");
      const byName = {}; nodes.forEach((x) => { byName[x.name] = x; });
      const visChars = chars.filter((c) => st.all || MAIN.includes(c.role));
      const visSet = new Set(visChars.map((c) => c.name));
      const rowsN = (data.rows || []).filter((r) => activeAt(r, st.n) && byName[r["誰"]] && byName[r["對誰"]] && r["誰"] !== r["對誰"]);
      const facVis = new Set(facs.filter((f) => visChars.some((c) => c.faction === f.name)).map((f) => f.name));
      rowsN.forEach((r) => {   // 沒有成員的勢力：只要和看得到的角色或勢力有關係就顯示
        const a = byName[r["誰"]], b = byName[r["對誰"]];
        if (a.kind === "勢力" && (visSet.has(b.name) || facVis.has(b.name))) facVis.add(a.name);
        if (b.kind === "勢力" && (visSet.has(a.name) || facVis.has(a.name))) facVis.add(b.name);
      });
      const shown = (name) => visSet.has(name) || facVis.has(name);
      const own = (r) => {   // 角色和自己所屬勢力之間的關係：用框表示，不畫線
        const a = byName[r["誰"]], b = byName[r["對誰"]];
        return (a.kind === "角色" && b.kind === "勢力" && (a.faction === b.name || (a.also || []).includes(b.name))) ||
               (b.kind === "角色" && a.kind === "勢力" && (b.faction === a.name || (b.also || []).includes(a.name)));
      };
      const edges = rowsN.filter((r) => shown(r["誰"]) && shown(r["對誰"]) && !own(r));
      const groups = [];
      facs.filter((f) => facVis.has(f.name)).forEach((f) => {
        const mem = visChars.filter((c) => c.faction === f.name);
        if (mem.length) groups.push({ key: f.name, label: f.name, members: mem.map((c) => c.name), box: true });
      });
      const free = visChars.filter((c) => !c.faction || !facVis.has(c.faction)).map((c) => c.name);
      if (free.length) groups.push({ key: "__free", label: "無所屬", members: free, box: true, free: true });
      const loose = facs.filter((f) => facVis.has(f.name) && !visChars.some((c) => c.faction === f.name)).map((f) => f.name);
      return { chars, facs, byName, visChars, visSet, facVis, rowsN, edges, groups, loose, hidden: rowsN.length - edges.length - rowsN.filter((r) => shown(r["誰"]) && shown(r["對誰"]) && own(r)).length };
    }

    // ------------------------------------------------------------ 版面
    function layout() {
      const m = model, gs = m.groups.map((g) => {
        const cols = Math.ceil(g.members.length / PER_COL), rows = Math.min(g.members.length, PER_COL);
        const colW = Math.max(...g.members.map(pillW)) + 22;
        return Object.assign({}, g, { cols, rows, colW, w: cols * colW + PAD * 2 - 22 + 22, h: HEAD + rows * ROW + PAD });
      }).sort((a, b) => b.members.length - a.members.length);
      const MAXW = 980; let x = 0, y = 0, rowH = 0;
      gs.forEach((g) => {
        if (x > 0 && x + g.w > MAXW) { x = 0; y += rowH + 56; rowH = 0; }
        g.members.forEach((nm, i) => {
          const c = Math.floor(i / PER_COL), r = i % PER_COL;
          if (!st.pos[nm] || !st.laid) st.pos[nm] = { x: x + PAD + c * g.colW + g.colW / 2 - 11, y: y + HEAD + r * ROW + PH / 2 + 6 };
        });
        x += g.w + 64; rowH = Math.max(rowH, g.h);
      });
      let lx = 0; const ly = y + rowH + 60;
      m.loose.forEach((nm) => { if (!st.pos[nm] || !st.laid) st.pos[nm] = { x: lx + pillW(nm) / 2, y: ly }; lx += pillW(nm) + 30; });
      st.laid = true;
    }
    const rectOf = (name) => {
      const g = model.groups.find((q) => q.key === name && q.box);
      if (g) {
        const ps = g.members.map((nm) => ({ p: st.pos[nm], w: pillW(nm) }));
        const x0 = Math.min(...ps.map((q) => q.p.x - q.w / 2)) - PAD, x1 = Math.max(...ps.map((q) => q.p.x + q.w / 2)) + PAD;
        const y0 = Math.min(...ps.map((q) => q.p.y - PH / 2)) - HEAD + 4, y1 = Math.max(...ps.map((q) => q.p.y + PH / 2)) + PAD;
        return { x: x0, y: y0, w: x1 - x0, h: y1 - y0, box: true };
      }
      const p = st.pos[name], w = pillW(name);
      return { x: p.x - w / 2, y: p.y - PH / 2, w, h: PH };
    };
    const centerOf = (r) => ({ x: r.x + r.w / 2, y: r.y + r.h / 2 });
    function clip(r, to) {   // 從矩形中心朝 to 的方向，找到邊界上的點
      const c = centerOf(r), dx = to.x - c.x, dy = to.y - c.y;
      if (!dx && !dy) return c;
      const sx = dx ? (r.w / 2) / Math.abs(dx) : Infinity, sy = dy ? (r.h / 2) / Math.abs(dy) : Infinity, s = Math.min(sx, sy);
      return { x: c.x + dx * s, y: c.y + dy * s };
    }

    // ------------------------------------------------------------ 繪圖
    const S = (tag, attrs, inner) => `<${tag} ${Object.entries(attrs || {}).map(([k, v]) => `${k}="${esc(v)}"`).join(" ")}>${inner || ""}</${tag}>`;
    function draw() {
      const m = model, sel = st.sel;
      const related = new Set(); if (sel) { related.add(sel); m.edges.forEach((r) => { if (r["誰"] === sel || r["對誰"] === sel) { related.add(r["誰"]); related.add(r["對誰"]); } }); }
      let boxes = "", lines = "", pills = "";
      m.groups.forEach((g, i) => {
        const r = rectOf(g.key), h = hue(i), name = g.label;
        boxes += `<g class="rg-box" data-box="${esc(g.key)}">` +
          S("rect", { x: r.x, y: r.y, width: r.w, height: r.h, rx: 14, style: g.free ? "fill:none;stroke:var(--line-2);stroke-dasharray:5 4" : `fill:hsla(${h},42%,52%,.10);stroke:hsla(${h},42%,45%,.65)` }) +
          S("text", { x: r.x + 12, y: r.y + 21, class: "rg-boxlabel" }, esc(g.label)) + "</g>";
      });
      // 勢力之間／勢力與角色之間的線也畫在同一層；成對的兩個方向分開彎
      const pairs = {};
      m.edges.forEach((r) => { const k = [r["誰"], r["對誰"]].sort().join("\u0001"); (pairs[k] = pairs[k] || []).push(r); });
      m.edges.forEach((r) => {
        const A = rectOf(r["誰"]), Bx = rectOf(r["對誰"]);
        const ca = centerOf(A), cb = centerOf(Bx);
        const k = [r["誰"], r["對誰"]].sort().join("\u0001"), two = pairs[k].length > 1;
        const forward = r["誰"] < r["對誰"] ? 1 : -1;
        const off = two ? 20 * forward : 0;
        const dx = cb.x - ca.x, dy = cb.y - ca.y, len = Math.hypot(dx, dy) || 1, nx = -dy / len, ny = dx / len;
        const ctl = { x: (ca.x + cb.x) / 2 + nx * off * 2, y: (ca.y + cb.y) / 2 + ny * off * 2 };
        const p1 = clip(A, ctl), p2 = clip(Bx, ctl);
        const mid = { x: 0.25 * p1.x + 0.5 * ctl.x + 0.25 * p2.x, y: 0.25 * p1.y + 0.5 * ctl.y + 0.25 * p2.y };
        const isNew = chNo(r["起始章"]) === st.n && st.n > 0, on = sel && (r["誰"] === sel || r["對誰"] === sel);
        const cls = "rg-edge" + (isNew ? " is-new" : "") + (on ? " is-on" : "") + (sel && !on ? " is-dim" : "");
        const tip = `${r["誰"]} → ${r["對誰"]}\n關係：${r["關係"] || "—"}${r["態度"] ? "\n態度：" + r["態度"] : ""}${r["起始章"] ? "\n" + r["起始章"] + "起" : ""}${r["變化原因"] ? "\n" + r["變化原因"] : ""}`;
        lines += `<g class="${cls}"><title>${esc(tip)}</title>` +
          S("path", { d: `M${p1.x},${p1.y} Q${ctl.x},${ctl.y} ${p2.x},${p2.y}`, "marker-end": `url(#rg-ar${isNew ? "-new" : on ? "-on" : ""})` }) +
          (m.edges.length <= 8 || on ? S("text", { x: mid.x, y: mid.y + 4, "text-anchor": "middle" }, esc(cut(r["關係"] || r["態度"], 8))) : "") + "</g>";   // 線多時只在選到角色時才標文字，避免疊在一起
      });
      const allPill = [...m.visChars.map((c) => c.name), ...m.loose];
      allPill.forEach((nm) => {
        const p = st.pos[nm]; if (!p) return;
        const nd = m.byName[nm], w = pillW(nm), fac = nd.kind === "勢力";
        const cls = "rg-pill" + (fac ? " is-fac" : nd.role === "主角" ? " is-lead" : "") + (nm === sel ? " is-sel" : "") + (sel && !related.has(nm) ? " is-dim" : "");
        pills += `<g class="${cls}" data-n="${esc(nm)}" transform="translate(${p.x - w / 2},${p.y - PH / 2})"><title>${esc(nm + (nd.role ? "（" + nd.role + "）" : ""))}</title>` +
          S("rect", { width: w, height: PH, rx: 16 }) + S("text", { x: w / 2, y: PH / 2 + 5, "text-anchor": "middle" }, esc(short(nm))) + "</g>";
      });
      const v = st.view;
      svg.innerHTML = `<defs>${["", "-new", "-on"].map((s2) => `<marker id="rg-ar${s2}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" class="rg-arrow${s2}"/></marker>`).join("")}</defs>` +
        `<g class="rg-world" transform="translate(${v.x},${v.y}) scale(${v.k})">${boxes}${lines}${pills}</g>`;
      nEl.textContent = st.n;
      const members = m.groups.filter((g) => g.box && !g.free).length;
      statEl.textContent = `${m.visChars.length} 個角色 · ${members} 個勢力 · ${m.edges.length} 條關係 · 第 ${st.n} 章` + (m.hidden > 0 ? ` · 另有 ${m.hidden} 條涉及未顯示的角色` : "");
      sideLists();
    }

    function sideLists() {
      const m = model;
      listEl.innerHTML = m.groups.map((g) => `<details open><summary>${esc(g.label)} <span class="muted">${g.members.length}</span></summary>${g.members.map((nm) => `<button class="rg-item${nm === st.sel ? " on" : ""}" data-n="${esc(nm)}">${esc(short(nm))}<span class="muted">${esc(m.byName[nm] ? m.byName[nm].role : "")}</span></button>`).join("")}</details>`).join("") +
        (m.loose.length ? `<details open><summary>勢力（沒有成員）</summary>${m.loose.map((nm) => `<button class="rg-item${nm === st.sel ? " on" : ""}" data-n="${esc(nm)}">${esc(short(nm))}</button>`).join("")}</details>` : "");
      const sel = st.sel;
      if (!sel || !m.byName[sel]) { detEl.innerHTML = `<div class="muted small" style="padding:8px 4px">點圖上的人或勢力，這裡會列出他在第 ${st.n} 章的所有關係。拖動圓點可以整理位置；滾輪縮放；拖背景移動。</div>`; return; }
      const nd = m.byName[sel], out = m.rowsN.filter((r) => r["誰"] === sel), inn = m.rowsN.filter((r) => r["對誰"] === sel);
      const line = (r, to) => { const o = to ? r["對誰"] : r["誰"], hid = !(m.visSet.has(o) || m.facVis.has(o)); return `<div class="rg-rel${hid ? " dim" : ""}"><b>${esc(o)}</b>${hid ? '<span class="muted">（未顯示）</span>' : ""}：${esc(r["關係"] || "—")}${r["態度"] ? `<span class="badge">${esc(r["態度"])}</span>` : ""}<div class="muted small">${esc([r["起始章"] ? r["起始章"] + "起" : "", r["變化原因"]].filter(Boolean).join("　"))}</div></div>`; };
      detEl.innerHTML = `<div class="rg-dh"><b>${esc(sel)}</b> <span class="muted">${esc(nd.kind === "勢力" ? "勢力" : nd.role)}</span></div>` +
        (nd.kind === "角色" ? `<div class="muted small">所屬：${esc(nd.faction || "無")}${(nd.also || []).length ? "（也在 " + esc(nd.also.join("、")) + "）" : ""}</div>` : `<div class="muted small">成員：${esc((nd.members || []).join("、") || "無")}</div>`) +
        `<div class="rg-sec">他對別人（${out.length}）</div>${out.map((r) => line(r, true)).join("") || '<div class="muted small">沒有紀錄</div>'}` +
        `<div class="rg-sec">別人對他（${inn.length}）</div>${inn.map((r) => line(r, false)).join("") || '<div class="muted small">沒有紀錄</div>'}`;
    }

    function fit() {
      const g = svg.querySelector(".rg-world"); if (!g) return;
      const b = g.getBBox(), W = svg.clientWidth || 800, H = svg.clientHeight || 560;
      if (!b.width) return;
      const k = Math.min((W - 60) / b.width, (H - 100) / b.height, 1.25);
      st.view = { k, x: (W - b.width * k) / 2 - b.x * k, y: 60 + (H - 80 - b.height * k) / 2 - b.y * k };
      g.setAttribute("transform", `translate(${st.view.x},${st.view.y}) scale(${st.view.k})`);
    }
    function refresh(refit) { model = build(); layout(); draw(); if (refit) fit(); }

    // ------------------------------------------------------------ 互動
    let drag = null;
    const pt = (e) => { const r = svg.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; };
    svg.addEventListener("pointerdown", (e) => {
      const pill = e.target.closest(".rg-pill"), box = e.target.closest(".rg-box");
      const p = pt(e);
      if (pill) drag = { type: "node", n: pill.dataset.n, sx: p.x, sy: p.y, moved: false };
      else if (box) drag = { type: "box", g: model.groups.find((q) => q.key === box.dataset.box), sx: p.x, sy: p.y, moved: false };
      else drag = { type: "pan", sx: p.x, sy: p.y, vx: st.view.x, vy: st.view.y, moved: false };
      svg.setPointerCapture(e.pointerId);
    });
    svg.addEventListener("pointermove", (e) => {
      if (!drag) return;
      const p = pt(e), dx = p.x - drag.sx, dy = p.y - drag.sy;
      if (!drag.moved && Math.hypot(dx, dy) < 4) return;
      drag.moved = true;
      if (drag.type === "pan") { st.view.x = drag.vx + dx; st.view.y = drag.vy + dy; svg.querySelector(".rg-world").setAttribute("transform", `translate(${st.view.x},${st.view.y}) scale(${st.view.k})`); return; }
      const mv = (nm) => { const q = st.pos[nm]; q.x += (p.x - drag.sx) / st.view.k * 1; q.y += (p.y - drag.sy) / st.view.k * 1; };
      (drag.type === "node" ? [drag.n] : (drag.g ? drag.g.members : [])).forEach(mv);
      drag.sx = p.x; drag.sy = p.y; draw();
    });
    svg.addEventListener("pointerup", (e) => {
      const d = drag; drag = null;
      if (!d || d.moved) return;
      if (d.type === "node") st.sel = st.sel === d.n ? null : d.n;
      else if (d.type === "pan") st.sel = null;
      else return;
      draw();
    });
    svg.addEventListener("wheel", (e) => {
      e.preventDefault();
      const p = pt(e), k0 = st.view.k, k1 = Math.min(3, Math.max(0.3, k0 * (e.deltaY < 0 ? 1.12 : 1 / 1.12)));
      st.view.x = p.x - (p.x - st.view.x) * (k1 / k0); st.view.y = p.y - (p.y - st.view.y) * (k1 / k0); st.view.k = k1;
      svg.querySelector(".rg-world").setAttribute("transform", `translate(${st.view.x},${st.view.y}) scale(${k1})`);
    }, { passive: false });
    el.addEventListener("click", (e) => {
      const it = e.target.closest(".rg-item"); if (it) { st.sel = st.sel === it.dataset.n ? null : it.dataset.n; draw(); return; }
      const b = e.target.closest("[data-a]"); if (!b) return;
      if (b.dataset.a === "fit") fit();
      if (b.dataset.a === "relayout") { st.pos = {}; st.laid = false; refresh(true); }
    });
    el.querySelector("input[type=range]").addEventListener("input", (e) => { st.n = parseInt(e.target.value, 10); st.laid = true; refresh(false); });
    el.querySelector(".rg-all").addEventListener("change", (e) => { st.all = e.target.checked; st.sel = null; st.pos = {}; st.laid = false; refresh(true); });
    refresh(true);
    return { state: st, refresh };
  }
  window.RelGraph = { mount };
})();
