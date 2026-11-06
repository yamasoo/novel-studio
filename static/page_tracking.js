/* 追蹤頁（轉移計畫 §8.2.16）：從 app.js 搬 viewTracking（原 783-929）＋ dueCh（原 773-780）。
   nsPage("b/:book/tracking","tracking",{book:true},render)；參數取 ctx.query.t。
   七個分頁（伏筆／時間線／讀者認知／角色關係／角色狀態／狀態卡／名詞表）照舊；表格全部改成節點（tableNode）。
   關係圖仍用 static/relgraph.js 的全域 window.RelGraph.mount（P5 才換），這裡只呼叫不改寫。
   REL_VIEW／REL_NOTE 從 app.js 的全域改成這支的模組變數；角色卡與狀態卡用全域 docView（傳自己建的節點）；
   原生 confirm 全改 FE.confirm；重新載入一律 FE.route()（舊版是遞迴呼叫 viewTracking）。 */
(function () {
  "use strict";

  const { h } = FE;
  const { statusBadgeNode } = nsShared;
  const enc = encodeURIComponent;

  let REL_VIEW = "table";   // 角色關係：表格 / 關係圖
  let REL_NOTE = "";        // 「從角色檔建立」的說明，顯示在草稿上面

  // 伏筆「預計回收」→ 章號（規則同 project.due_chapter：「起推進」「呼應」「第二幕」「未排定」不算回收章）
  function dueCh(s) {
    const m = String(s || "").match(/^\s*第\s*(\d+)\s*(?:章)?(?:\s*[～~\-–至到]\s*第?\s*(\d+))?\s*章([\s\S]*)$/);
    if (!m) return null;
    const rest = m[3].trim();
    if (/^(起|開始|呼應|推進|再|埋|提及)/.test(rest)) return null;
    const n = parseInt(m[2] || m[1], 10);
    return /^(前後|左右)/.test(rest) ? n + 2 : n;
  }

  function tableNode(id, headers, rows, opts) {
    const o = opts || {};
    const rowClass = o.rowClass || (() => "");
    const cell = o.cell || ((r, x) => r[x]);
    return h("div", { class: "table-wrap" },
      h("table", id ? { id } : {},
        h("thead", {}, h("tr", {}, headers.map((x) => h("th", {}, x)))),
        h("tbody", {}, rows.map((r) => h("tr", { class: rowClass(r) },
          headers.map((x) => h("td", {}, cell(r, x))))))));
  }

  async function render(ctx) {
    const signal = ctx.signal;
    const t = ctx.query.t || "foreshadow";
    const d = await FE.api(B("/tracking"), { signal });
    const latest = d.latest || 0;
    const chn = (s) => { const m = String(s || "").match(/(\d+)/); return m ? parseInt(m[1], 10) : null; };

    const tabs = [["foreshadow", "伏筆"], ["timeline", "時間線"], ["reader", "讀者認知"], ["relations", "角色關係"], ["chars", "角色狀態"], ["state", "狀態卡"], ["glossary", "名詞表"]];
    const tabsNode = h("div", { class: "tabs" }, tabs.map(([k, l]) => h("button", {
      class: "tab" + (k === t ? " active" : ""),
      onclick: () => FE.go("#/b/" + enc(S.book) + "/tracking?t=" + k),
    }, l)));
    const head = h("div", { class: "page-head" },
      h("div", {},
        h("h1", {}, "伏筆與時間線"),
        h("div", { class: "sub" }, "這裡是「已經發生的事實」，寫完章節後由 Claude 回寫。目前寫到第 " + latest + " 章。")),
      h("div", { class: "row" }, h("button", { onclick: () => Panel.openForm("review_all") }, "伏筆與角色健康檢查")));

    let body = null;
    let docEl = null;
    const after = [];   // 畫完之後才綁的事件

    if (t === "foreshadow") {
      const rows = d.foreshadow.rows;
      if (!rows.length) {
        body = h("div", { class: "card empty" }, h("div", { class: "big" }, "⟲"), "還沒有伏筆紀錄。寫完章節後 Claude 會自動登記。");
      } else {
        const hideBox = h("input", { type: "checkbox", id: "hide-done", checked: true });
        const table = tableNode("fs-table", d.foreshadow.headers, rows, {
          rowClass: (r) => {
            const done = ["已回收", "廢棄"].includes(r["狀態"]);
            const last = chn(r["最後出現"]) || chn(r["埋設章"]);
            const due = dueCh(r["預計回收"]);
            const stale = !done && ((["高", "中"].includes(r["重要度"]) && last && latest - last > d.stale_foreshadow) || (due && latest > due));
            return (done ? "dim done " : "") + (stale ? "hl" : "");
          },
          cell: (r, x) => (x === "狀態" ? statusBadgeNode(r[x]) : r[x]),
        });
        body = h("div", { class: "card" },
          h("div", { class: "row", style: "margin-bottom:8px" },
            h("label", { class: "cb", style: "margin:0" }, hideBox, " 隱藏已回收／廢棄"),
            h("span", { class: "grow" }),
            h("span", { class: "muted small" },
              "黃底：重要度中以上、超過 " + d.stale_foreshadow + " 章沒出現，或已過預計回收章（「預計回收」要寫成「第N章」才算；「起推進」「呼應」不算）")),
          table);
        after.push(() => {
          const apply = () => table.querySelectorAll("tr.done").forEach((tr) => { tr.style.display = hideBox.checked ? "none" : ""; });
          hideBox.onchange = apply;
          apply();
        });
      }
    } else if (t === "timeline") {
      const rows = d.timeline.rows;
      body = rows.length
        ? h("div", { class: "card" },
          h("div", { class: "muted small", style: "margin-bottom:8px" }, "「讀者目前知道」是寫作時的資訊邊界；揭示章為「未揭示」的列以黃底標示。"),
          tableNode(null, d.timeline.headers, rows, { rowClass: (r) => (/未/.test(r["揭示章"] || "") ? "hl" : "") }))
        : h("div", { class: "card empty" }, "還沒有時間線。");
    } else if (t === "reader") {
      const rd = d.reader_draft, rl = d.reader;
      const isOpen = (r) => r["類型"] !== "已知" && !(chn(r["回收章"]) && chn(r["回收章"]) <= latest);
      const readerTable = (x, id) => tableNode(id, x.headers, x.rows, {
        rowClass: (r) => (isOpen(r) ? "" : "dim done"),
        cell: (r, xh) => (xh === "類型"
          ? h("span", { class: "badge " + (r[xh] === "誤認" ? "b-warn" : r[xh] === "懸念" ? "b-ok" : "") }, r[xh])
          : r[xh]),
      });
      const intro = h("div", { class: "muted small", style: "margin-bottom:8px" },
        "讀者讀到目前的認知：", h("b", {}, "懸念"), "是讀者在等答案的問題，", h("b", {}, "誤認"), "是讀者誤以為的事，",
        h("b", {}, "已知"), "是讀者知道、但劇中角色未必知道的事。寫稿時只帶和本章有關的；還沒回收的不會被提前說破。「作者真相」選填。");
      const parts = [];
      if (rd.rows.length) {
        const adoptBtn = h("button", { class: "sm primary", id: "rp-adopt" }, "採用草稿");
        const discardBtn = h("button", { class: "sm danger", id: "rp-discard" }, "捨棄");
        parts.push(h("div", { class: "card", style: "margin-bottom:14px;border-color:var(--warn,#c90)" },
          h("div", { class: "card-title" },
            h("h2", {}, "草稿（" + rd.rows.length + " 條，尚未生效）"),
            h("span", { class: "grow" }),
            adoptBtn,
            h("button", {
              class: "sm",
              onclick: () => Panel.run("reader_reconcile", {}),
              title: "拿後面的時間線與章節摘要比對，找出已經揭曉、部分揭曉、重複的條目",
            }, "比對回收"),
            h("button", { class: "sm", onclick: () => openCharState("追蹤/讀者認知_草稿.md") }, "編輯草稿"),
            discardBtn),
          h("div", { class: "muted small", style: "margin-bottom:8px" },
            "AI 產生的結果（從時間線轉換，或回收比對；比對的逐條理由在草稿最後，按「編輯草稿」可以看）。請檢查：有沒有把你的底牌寫成讀者已經在懷疑的懸念、有沒有漏掉你刻意埋的誤導、回收章對不對。"
            + (rl.rows.length ? "採用後會取代現在的帳本（舊的會先備份）。" : "")),
          readerTable(rd, "rp-draft")));
        after.push(() => {
          adoptBtn.onclick = async () => {
            if (!(await FE.confirm("採用這份草稿？之後寫稿、審查、回寫都會用它。"))) return;
            try {
              await FE.api(B("/tracking/reader/adopt"), { method: "POST", signal });
              FE.toast("已採用讀者認知帳本");
              FE.route();
            } catch (e) { FE.fail(e); }
          };
          discardBtn.onclick = async () => {
            if (!(await FE.confirm("捨棄這份草稿？（會移到 .studio/備份）"))) return;
            try {
              await FE.api(B("/tracking/reader/discard"), { method: "POST", signal });
              FE.route();
            } catch (e) { FE.fail(e); }
          };
        });
      }
      if (rl.rows.length) {
        const hideBox = h("input", { type: "checkbox", id: "hide-done", checked: true });
        const card = h("div", { class: "card" },
          h("div", { class: "row", style: "margin-bottom:8px" },
            h("label", { class: "cb", style: "margin:0" }, hideBox, " 隱藏已回收與已知"),
            h("span", { class: "grow" }),
            rd.rows.length ? null : h("button", {
              class: "sm",
              onclick: () => Panel.run("reader_reconcile", {}),
              title: "拿後面的時間線與章節摘要比對，找出已經揭曉、部分揭曉、重複的條目；結果存成草稿",
            }, "比對回收"),
            h("button", { class: "sm", onclick: () => openCharState("追蹤/讀者認知.md") }, "編輯")),
          intro,
          readerTable(rl, "fs-table"));
        parts.push(card);
        after.push(() => {
          const apply = () => card.querySelectorAll("tr.done").forEach((tr) => { tr.style.display = hideBox.checked ? "none" : ""; });
          hideBox.onchange = apply;
          apply();
        });
      } else if (!rd.rows.length) {
        parts.push(h("div", { class: "card empty" },
          h("div", { class: "big" }, "?"),
          "還沒有讀者認知帳本。",
          h("br"),
          "新書寫完章節後會自動登記；已經寫了很多章的書，可以先從時間線轉換一份草稿，確認後再採用。",
          d.timeline.rows.length
            ? h("div", { style: "margin-top:12px" }, h("button", {
              class: "primary",
              onclick: () => Panel.run("reader_init", {}),
            }, "從時間線建立（AI 轉換，" + d.timeline.rows.length + " 列）"))
            : null));
      }
      docEl = h("div", { id: "doc", style: "margin-top:14px" });
      body = h("div", {}, parts, docEl);
    } else if (t === "relations") {
      const rd = d.relations_draft, rl = d.relations;
      const cols = (x) => x.headers.filter((x2) => x2 !== "編號");
      const relTable = (x, id) => tableNode(id, cols(x), x.rows, {
        rowClass: (r) => (r["結束章"] ? "dim done" : ""),
      });
      const intro = h("div", { class: "muted small", style: "margin-bottom:8px" },
        "誰對誰的關係，一個方向一列（A 對 B、B 對 A 分開記）。關係改變時，舊的那列會填上「結束章」、另開一列，所以歷史都留著；淡色的列是已經結束的舊關係。寫稿時只帶在場角色之間、目前有效的關係。");
      const buildBtn = (label) => h("button", {
        class: "sm rl-build",
        title: "把各角色檔「## 關係」裡的「對象：描述」整理成表格草稿。不用模型、不花 token；確認後才會生效。",
        onclick: async (ev) => {
          const b = ev.target;
          b.disabled = true;
          try {
            const r = await FE.api(B("/tracking/relations/build"), { method: "POST", signal });
            REL_NOTE = r.message || "";
            FE.route();
          } catch (e) { FE.fail(e); b.disabled = false; }
        },
      }, label);
      const parts = [];
      if (rd.rows.length) {
        const adoptBtn = h("button", { class: "sm primary", id: "rl-adopt" }, "採用草稿");
        const discardBtn = h("button", { class: "sm danger", id: "rl-discard" }, "捨棄");
        const noteNode = REL_NOTE ? FE.md.render(REL_NOTE) : null;
        if (noteNode) { noteNode.classList.add("small"); noteNode.style.marginBottom = "8px"; }
        parts.push(h("div", { class: "card", style: "margin-bottom:14px;border-color:var(--warn,#c90)" },
          h("div", { class: "card-title" },
            h("h2", {}, "草稿（" + rd.rows.length + " 列，尚未生效）"),
            h("span", { class: "grow" }),
            adoptBtn,
            h("button", { class: "sm", onclick: () => openCharState("追蹤/關係_草稿.md") }, "編輯草稿"),
            discardBtn),
          noteNode,
          h("div", { class: "muted small", style: "margin-bottom:8px" },
            "從角色檔的「## 關係」整理出來的，「關係」欄是角色檔那句描述原文。請檢查：對象有沒有認錯人、方向對不對、要不要把描述拆成「關係」和「態度」。"
            + (rl.rows.length ? "採用後會取代現在的關係表（舊的會先備份）。" : "")),
          relTable(rd, "rl-draft")));
        after.push(() => {
          adoptBtn.onclick = async () => {
            if (!(await FE.confirm("採用這份草稿？之後寫稿、審查、回寫都會用它。"))) return;
            try {
              await FE.api(B("/tracking/relations/adopt"), { method: "POST", signal });
              REL_NOTE = "";
              FE.toast("已採用角色關係表");
              FE.route();
            } catch (e) { FE.fail(e); }
          };
          discardBtn.onclick = async () => {
            if (!(await FE.confirm("捨棄這份草稿？（會移到 .studio/備份）"))) return;
            try {
              await FE.api(B("/tracking/relations/discard"), { method: "POST", signal });
              REL_NOTE = "";
              FE.route();
            } catch (e) { FE.fail(e); }
          };
        });
      }
      if (rl.rows.length) {
        parts.push(h("div", { class: "row", style: "margin-bottom:10px" },
          h("div", { class: "seg compact" },
            [["table", " 表格"], ["graph", " 關係圖（依勢力分組）"]].map(([v, label]) => h("label", {},
              h("input", {
                type: "radio", name: "rel-view", value: v, checked: REL_VIEW === v,
                onchange: () => { REL_VIEW = v; FE.route(); },
              }),
              h("span", {}, label))))));
      }
      if (rl.rows.length && REL_VIEW === "graph") {
        const rgRoot = h("div", { id: "rg-root" });
        parts.push(h("div", { class: "card" }, rgRoot));
        after.push(() => {
          if (!d.relations_graph) {
            rgRoot.replaceChildren(h("div", { class: "muted", style: "padding:24px" },
              "後端還沒送出關係圖資料——工作台程式是更新前啟動的，請關掉工作台（命令列視窗）後重新啟動，再回到這一頁。"));
          } else if (!window.RelGraph) {
            rgRoot.replaceChildren(h("div", { class: "muted", style: "padding:24px" },
              "關係圖的程式檔沒載入，請按 Ctrl+F5 強制重新整理。"));
          } else {
            window.RelGraph.mount(rgRoot, d.relations_graph);
          }
        });
      } else if (rl.rows.length) {
        const hideBox = h("input", { type: "checkbox", id: "hide-done", checked: true });
        const filterInput = h("input", { type: "text", id: "rl-filter", placeholder: "篩選角色或關鍵字", style: "max-width:200px;margin-left:10px" });
        const card = h("div", { class: "card" },
          h("div", { class: "row", style: "margin-bottom:8px" },
            h("label", { class: "cb", style: "margin:0" }, hideBox, " 只看目前有效"),
            filterInput,
            h("span", { class: "grow" }),
            rd.rows.length ? null : buildBtn("從角色檔補關係草稿"),
            h("button", { class: "sm", onclick: () => openCharState("追蹤/關係.md") }, "編輯")),
          intro,
          relTable(rl, "fs-table"));
        parts.push(card);
        after.push(() => {
          const apply = () => {
            const q = filterInput.value.trim(), hide = hideBox.checked;
            card.querySelectorAll("#fs-table tbody tr").forEach((tr) => {
              tr.style.display = ((hide && tr.classList.contains("done")) || (q && !tr.textContent.includes(q))) ? "none" : "";
            });
          };
          hideBox.onchange = apply;
          filterInput.oninput = apply;
          apply();
        });
      } else if (!rd.rows.length) {
        parts.push(h("div", { class: "card empty" },
          h("div", { class: "big" }, "⇄"),
          "還沒有角色關係表。",
          h("br"),
          "新書寫到前幾章時會自動登記；已經寫了很多章的書，可以從角色檔的「## 關係」轉換一份草稿，確認後再採用。",
          h("div", { style: "margin-top:12px" }, buildBtn("從角色檔建立草稿"))));
      }
      docEl = h("div", { id: "doc", style: "margin-top:14px" });
      body = h("div", {}, parts, docEl);
    } else if (t === "chars") {
      body = d.characters.length
        ? h("div", {},
          h("div", { class: "grid g3" }, d.characters.map((c) => {
            const last = chn(c.last), gap = last ? latest - last : null;
            return h("div", {
              class: "card item", style: "cursor:pointer",
              onclick: () => openCharState(c.file),
            },
              h("div", { class: "row" },
                h("span", { class: "nm", style: "font-size:15px" }, c.name),
                h("span", { class: "grow" }),
                gap !== null && gap > 15 ? h("span", { class: "badge b-warn" }, gap + " 章未登場") : null),
              h("div", { class: "muted small" }, "最後登場：" + (c.last || "—") + "　·　更新至：" + (c.updated_to || "—")));
          })),
          h("div", { id: "doc", style: "margin-top:14px" }))
        : h("div", { class: "card empty" }, "還沒有角色狀態。");
    } else if (t === "state") {
      docEl = h("div", { id: "doc" });
      body = docEl;
    } else if (t === "glossary") {
      const g = d.glossary;
      body = g.rows.length
        ? h("div", { class: "card" },
          h("div", { class: "row", style: "margin-bottom:8px" },
            h("span", { class: "muted small" }, g.rows.length + " 條"),
            h("span", { class: "grow" }),
            h("button", {
              class: "sm",
              onclick: () => Panel.run("glossary_org", {}),
              title: "AI 重新分類（地點、組織、物品、技術、制度……），把地點、船艦、武器等寫成設定集的主題檔，合併重複的勢力；名詞表留作索引。結果先存成草稿",
            }, "整理進設定集"),
            h("button", {
              class: "sm",
              onclick: () => FE.go("#/b/" + enc(S.book) + "/bible?t=核心&f=" + enc("設定/名詞表.md")),
            }, "編輯名詞表")),
          tableNode(null, g.headers, g.rows))
        : h("div", { class: "card empty" }, "名詞表是空的。");
    }

    ctx.view(head, tabsNode, body);
    after.forEach((fn) => fn());
    if (t === "state" && docEl) await docView(docEl, "追蹤/狀態卡.md", { signal });
  }

  nsPage("b/:book/tracking", "tracking", { book: true }, render);
})();
