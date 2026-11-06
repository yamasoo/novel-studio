/* 單章頁（轉移計畫 §8.2.14）：從 app.js 搬 viewChapter（原 457-534）＋ renderGoals（原 787-809）＋
   renderReview（原 812-842）＋ inlineHtml（原 845-847）＋ renderRevision（原 848-900）。
   註冊 nsPage("b/:book/ch/:no","chapter",{book:true},render)：no 取 parseInt(ctx.params.no)、tab 取 ctx.query.tab。
   S.hl 的接線自己補：舊版是 route() 的 finally 做 highlightTerms，FE.PAGES 之後 route() 不會再跑，
   所以本頁在畫完 docView 之後檢查 S.hl → 呼叫全域 highlightTerms(docEl, terms) → 清掉。
   renderPipe／pipeModal／docView／renderGoals 之外的 renderChapterStructure／renderIllust／highlightTerms 都還是 app.js 全域。 */
(function () {
  "use strict";

  const { h } = FE;
  const { fmtNum, fmtTime } = nsShared;
  const enc = encodeURIComponent;

  const GOAL_ICON = { completed: ["✓", "b-ok"], unmet: ["✗", "b-bad"], unverified: ["？", "b-warn"], unknown: ["－", ""] };
  const GOAL_LABEL = { completed: "已寫到", unmet: "沒寫到", unverified: "引文對不上", unknown: "無法判斷" };
  const SEV_CLASS = { "必須修": "b-bad", "建議修": "b-warn", "提醒": "" };

  function inlineNodes(segs, side) {
    return segs.map(([op, s]) => (op === "eq" ? s
      : (op === (side === "old" ? "del" : "ins") ? h("mark", { class: op }, s) : null)));
  }

  function para(text, inline) {
    return h("p", { lang: bookLang(), "data-i18n-skip": "" }, inline || text);
  }

  async function renderGoals(el, no, candidate, path, signal) {
    let d;
    try { d = await FE.api(B("/goals/" + no), { signal }); } catch (e) { return; }
    if (!d.goals.length) return;
    const r = d.result && d.result.path === path ? d.result : null;
    const sm = r ? r.summary : null;
    const badges = r
      ? [
        h("span", { class: "badge b-ok" }, "已寫到 " + sm.completed),
        sm.unmet ? h("span", { class: "badge b-bad" }, "沒寫到 " + sm.unmet) : null,
        sm.unverified ? h("span", { class: "badge b-warn" }, "引文對不上 " + sm.unverified) : null,
        sm.unknown ? h("span", { class: "badge" }, "無法判斷 " + sm.unknown) : null,
        h("span", { class: "muted small" }, fmtTime(r.checked_at) + (r.stale ? "　稿子之後改過，結果可能過時" : "")),
      ]
      : h("span", { class: "muted small" }, "這份稿子還沒核對（" + d.goals.length + " 項）");

    const checkBtn = h("button", {
      class: "sm",
      onclick: (ev) => { ev.preventDefault(); Panel.run("goal_check", { chapter: no, candidate }); },
    }, r ? "重新核對" : "核對章綱");

    const items = (r ? r.items : d.goals).map((g) => {
      const st = g.status ? GOAL_ICON[g.status] : ["·", ""];
      return h("div", { class: "goal-item" },
        h("span", { class: "badge " + st[1], title: g.status ? GOAL_LABEL[g.status] : "" }, st[0]),
        h("div", { class: "grow" },
          h("div", {}, g.id + "　" + g.text),
          (g.note && g.status !== "completed")
            ? h("div", { class: "small", style: "color:var(--ink-2)" }, "→ " + g.note)
            : null,
          (g.evidence || []).map((q) => h("div", {
            class: "quote" + (q.found ? "" : " bad"),
            title: q.found ? "已在正文中找到" : "正文裡找不到這句",
          }, (q.found ? "" : "✗ ") + "「" + q.quote + "」"))));
    });

    el.replaceChildren(h("details", {
      class: "card goal-card",
      open: !!(r && (sm.unmet || sm.unverified)),
      style: "margin-bottom:14px",
    },
      h("summary", { class: "row" },
        h("b", {}, "章綱核對"),
        badges,
        h("span", { class: "grow" }),
        checkBtn),
      h("div", { class: "goal-list" }, items)));
  }

  async function renderReview(el, no, candidate, path, signal) {
    let rec;
    try { rec = (await FE.api(B("/review/" + no), { signal })).review; } catch (e) { return; }
    if (rec && rec.path !== path) rec = null;
    if (!rec) {
      el.replaceChildren(h("div", { class: "card review-card", style: "margin-bottom:14px" },
        h("div", { class: "row" },
          h("b", {}, "審查意見"),
          h("span", { class: "muted small" }, "審查後可以勾選要處理的意見，修訂結果會逐段讓你選擇。"),
          h("span", { class: "grow" }),
          h("button", { class: "sm", onclick: () => Panel.run("review_notes", { chapter: no, candidate }) }, "審查這份稿子"))));
      return;
    }

    const recheckBtn = h("button", {
      class: "sm",
      onclick: (ev) => { ev.preventDefault(); Panel.run("review_notes", { chapter: no, candidate }); },
    }, "重新審查");

    const items = rec.items.length
      ? rec.items.map((x) => h("label", { class: "rv-item" },
        h("input", { type: "checkbox", "data-id": x.id, checked: x.severity !== "提醒" }),
        h("div", { class: "grow" },
          h("div", {},
            h("span", { class: "badge " + (SEV_CLASS[x.severity] || "") }, x.severity),
            " ",
            x.category ? [h("span", { class: "badge" }, x.category), " "] : null,
            x.issue),
          x.quote
            ? h("div", { class: "quote" + (x.located ? "" : " bad"), title: x.located ? "已在正文中找到" : "正文裡找不到這句" },
              (x.located ? "" : "✗ ") + "「" + x.quote + "」")
            : null,
          x.suggestion ? h("div", { class: "small", style: "color:var(--ink-2)" }, "修法：" + x.suggestion) : null)))
      : h("div", { class: "muted" }, "沒有發現問題。");

    const extra = h("textarea", { id: "rv-extra", rows: "2", placeholder: "例如：第二場對話太長，砍一半" });
    const goBtn = h("button", { class: "primary sm", id: "rv-go" }, "依勾選意見修訂");
    goBtn.onclick = () => {
      const ids = Array.from(el.querySelectorAll("input[data-id]:checked")).map((i) => i.dataset.id);
      if (!ids.length && !extra.value.trim()) {
        FE.toast("請至少勾選一條意見，或寫下自己的意見", "err");
        return;
      }
      Panel.run("revise_notes", { chapter: no, ids, extra: extra.value });
    };

    el.replaceChildren(h("details", { class: "card review-card", open: true, style: "margin-bottom:14px" },
      h("summary", { class: "row" },
        h("b", {}, "審查意見"),
        h("span", { class: "muted small" }, rec.summary || ""),
        h("span", { class: "muted small" }, fmtTime(rec.checked_at) + (rec.stale ? "　稿子之後改過，意見可能過時" : "")),
        h("span", { class: "grow" }),
        recheckBtn),
      h("div", { class: "rv-list" }, items),
      h("label", { class: "f", style: "margin-top:10px" },
        h("span", {}, "你自己的修改意見（選填）"), extra),
      h("div", { class: "row" }, h("span", { class: "grow" }), goBtn)));
  }

  function renderRevision(el, no, rv, signal) {
    if (!rv) {
      el.replaceChildren(h("div", { class: "card empty" }, "沒有待確認的修訂。"));
      return;
    }
    const choice = {};
    const ds = rv.kind === "deslop";
    const newline = String.fromCharCode(10);

    const reasonsNode = (b) => (b.reasons || []).length
      ? h("div", { class: "rv-why small" },
        b.reasons.map((r) => h("div", {},
          h("span", { class: "badge b-warn" }, r.why || ""),
          " " + r.old + " → " + r.new)))
      : null;

    const draw = () => {
      el.replaceChildren();
      const card = h("div", { class: "card", style: "margin-bottom:14px" });
      const head = h("div", { class: "row" },
        h("b", {}, ds ? "去 AI 味對照" : "修訂對照"),
        h("span", { class: "badge" }, rv.changes + " 處變更"),
        (ds && (rv.items || []).length) ? h("span", { class: "badge" }, "逐處清單 " + rv.items.length + " 條") : null,
        h("span", { class: "muted small" }, "原稿：" + rv.base_path + "　·　" + fmtTime(rv.created)),
        h("span", { class: "grow" }),
        h("button", { class: "sm", id: "rv-all-new" }, "全部採用修訂"),
        h("button", { class: "sm", id: "rv-all-old" }, "全部保留原文"));
      const reportText = ds ? (rv.report || "")
        : "**意見**" + newline + newline + (rv.notes || "") + newline + newline + "**說明**" + newline + newline + (rv.report || "");
      const reportMd = FE.md.render(reportText);
      reportMd.classList.add("small");
      reportMd.setAttribute("lang", bookLang());
      reportMd.style.marginTop = "6px";

      card.append(
        head,
        rv.stale ? h("div", { class: "alert warn", style: "margin-top:8px" },
          h("span", { class: "k" }, "對不上"),
          h("span", { class: "t" }, "原稿在修訂之後被改過了，這份修訂不能套用，請捨棄後重新修訂。")) : null,
        h("details", { style: "margin-top:8px", open: !!ds },
          h("summary", { class: "small" }, ds ? "AI 的逐處清單與說明" : "處理的意見與 AI 的說明"),
          reportMd),
        (ds && (rv.unmatched || []).length)
          ? h("div", { class: "muted small", style: "margin-top:6px" },
            "清單裡有 " + rv.unmatched.length + " 條對不到段落（AI 抄的原句和原稿不完全一樣），只列在上面的清單裡。")
          : null);

      const blocks = h("div", { class: "rv-blocks" }, rv.blocks.map((b) => {
        if (b.type === "same") {
          const ps = b.old.map((x) => para(x));
          return b.old.length > 2
            ? h("details", { class: "rv-same" },
              h("summary", { class: "muted small" }, b.old.length + " 段沒有變更（展開）"), ps)
            : h("div", { class: "rv-same" }, ps);
        }
        const k = String(b.index);
        const useNew = (choice[k] || "new") === "new";
        const oldPs = b.old.length
          ? b.old.map((x, i) => para(x, b.inline ? inlineNodes(b.inline[i], "old") : null))
          : h("p", { class: "muted small" }, "（原文沒有這段）");
        const newPs = b.new.length
          ? b.new.map((x, i) => para(x, b.inline ? inlineNodes(b.inline[i], "new") : null))
          : h("p", { class: "muted small" }, "（修訂刪掉了這段）");
        return h("div", { class: "rv-change" },
          h("div", { class: "rv-side old" + (useNew ? "" : " chosen"), "data-k": k, "data-v": "old" },
            h("div", { class: "rv-tag" }, "原文"), oldPs),
          h("div", { class: "rv-side new" + (useNew ? " chosen" : ""), "data-k": k, "data-v": "new" },
            h("div", { class: "rv-tag" }, "修訂"), newPs, reasonsNode(b)));
      }));

      const noteText = ds
        ? "套用後寫回 " + rv.base_path + "（原檔先備份" + (rv.base_path.startsWith("正文") ? "；去 AI 味不改劇情，不用重跑回寫追蹤" : "") + "），並跑一次保真檢查。"
        : "套用後會存成候選稿" + (rv.base_path.startsWith("正文") ? "（原本的正文不動，採用候選稿時才覆蓋並回寫追蹤）" : "") + "。";
      const discardBtn = h("button", { class: "sm danger", id: "rv-discard" }, "捨棄這份" + (ds ? "去 AI 味結果" : "修訂"));
      const applyBtn = h("button", { class: "primary", id: "rv-apply", disabled: !!rv.stale }, ds ? "套用" : "套用到候選稿");

      const foot = h("div", { class: "card row", style: "margin-top:14px;position:sticky;bottom:10px" },
        h("span", { class: "muted small" }, "點左右兩邊選擇要的版本。" + noteText),
        h("span", { class: "grow" }),
        discardBtn,
        applyBtn);

      el.append(card, blocks, foot);

      el.querySelectorAll(".rv-side").forEach((d) => {
        d.onclick = () => { choice[d.dataset.k] = d.dataset.v; draw(); };
      });
      el.querySelector("#rv-all-new").onclick = () => {
        rv.blocks.forEach((b) => { if (b.type === "change") choice[b.index] = "new"; });
        draw();
      };
      el.querySelector("#rv-all-old").onclick = () => {
        rv.blocks.forEach((b) => { if (b.type === "change") choice[b.index] = "old"; });
        draw();
      };
      discardBtn.onclick = async () => {
        if (!(await FE.confirm("捨棄這份修訂？（會移到 .studio/備份）"))) return;
        try {
          await FE.api(B("/revision/" + no + "/discard"), { method: "POST", signal });
          FE.go("#/b/" + enc(S.book) + "/ch/" + no);
        } catch (e) { FE.fail(e); }
      };
      applyBtn.onclick = async () => {
        try {
          const r = await FE.api(B("/revision/" + no + "/apply"), { method: "POST", body: { choices: choice }, signal });
          FE.toast("已套用：採用修訂 " + r.used_new + " 處、保留原文 " + r.kept_old + " 處");
          FE.go("#/b/" + enc(S.book) + "/ch/" + no + "?tab=" + (r.kind === "deslop" && r.from_text ? "text" : "candidate"));
          if (r.kind === "deslop" && r.fidelity) {
            setTimeout(() => {
              const mdNode = FE.md.render(r.fidelity);
              FE.modal({
                title: "保真檢查",
                body: mdNode,
                foot: (done) => [h("button", { class: "btn btn-primary", type: "button", onclick: () => done(true) }, "知道了")],
              });
            }, 800);
          }
        } catch (e) { FE.fail(e); }
      };
    };
    draw();
  }

  async function render(ctx) {
    const signal = ctx.signal;
    const no = parseInt(ctx.params.no, 10);
    let tab = ctx.query.tab;
    const [chs, rvRes, recs] = await Promise.all([
      FE.api(B("/chapters"), { signal }),
      FE.api(B("/revision/" + no), { signal }).catch(() => ({})),
      FE.api(B("/recoveries"), { signal }).catch(() => []),
    ]);
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
    if (!tab || !tabs.find((t) => t[0] === tab)) {
      tab = (tabs.find((t) => t[0] === "candidate") || tabs.find((t) => t[0] === "text") || tabs[0] || [])[0];
    }
    const cur = tabs.find((t) => t[0] === tab);
    const base = "#/b/" + enc(S.book) + "/ch/" + no;

    // ── 頁首 ──
    const headRow = h("div", { class: "row" },
      prev ? h("button", { class: "ghost", onclick: () => FE.go("#/b/" + enc(S.book) + "/ch/" + prev.no) }, "← 第" + prev.no + "章") : null,
      next ? h("button", { class: "ghost", onclick: () => FE.go("#/b/" + enc(S.book) + "/ch/" + next.no) }, "第" + next.no + "章 →") : null);

    // ── 動作列 ──
    const actions = h("div", { class: "row", style: "margin-bottom:12px" },
      (!c.text_file && !c.candidate_file && c.card_file)
        ? h("button", { class: "primary", onclick: () => Panel.openForm("write", { from: no, to: no }) }, "寫這章")
        : null,
      !c.card_file
        ? h("button", { onclick: () => Panel.openForm("chapter_cards", { from: no, to: no }) }, "補這一章的章綱")
        : null,
      (!c.text_file || c.candidate_file)
        ? h("button", { onclick: () => pipeModal(no) }, "⚡ 整章自動" + (c.candidate_file ? "（從核對開始）" : ""))
        : null,
      c.text_file
        ? [
          h("button", { onclick: () => Panel.openForm("revise", { chapter: no }) }, "改稿"),
          h("button", { onclick: () => Panel.run("review_notes", { chapter: no }) }, "審查"),
          h("button", { onclick: () => Panel.openForm("deslop", { chapter: no }) }, "去 AI 味"),
        ]
        : null);

    const tabsNode = tabs.length
      ? h("div", { class: "tabs" }, tabs.map(([k, l]) => h("button", {
        class: "tab" + (k === tab ? " active" : ""),
        onclick: () => FE.go(base + "?tab=" + k),
      }, l)))
      : null;

    let acceptBtn = null, rejectBtn = null, discardBtn = null;
    const candidateAlert = tab === "candidate"
      ? (() => {
        acceptBtn = h("button", { class: "ok sm", id: "cand-accept" }, "採用");
        rejectBtn = h("button", { class: "sm", id: "cand-reject" }, "退回重寫");
        discardBtn = h("button", { class: "sm danger", id: "cand-discard" }, "捨棄");
        return h("div", { class: "alert info", style: "margin-bottom:12px" },
          h("span", { class: "k" }, "候選稿"),
          h("span", { class: "t" }, "審閱後按「採用」移入正文並回寫追蹤；不滿意就「退回」並寫下意見，AI 會改寫。"),
          acceptBtn,
          rejectBtn,
          h("button", { class: "sm", onclick: () => Panel.openForm("deslop", { chapter: no, candidate: true }) }, "去 AI 味"),
          discardBtn);
      })()
      : null;

    const recAlerts = myRecs.map((r) => h("div", { class: "alert warn", style: "margin-bottom:10px" },
      h("span", { class: "k" }, "恢復稿"),
      h("span", { class: "t" }, r.label + "中斷（" + r.reason + "），保留了 " + fmtNum(r.chars) + " 字。"),
      h("button", { class: "sm primary", onclick: () => Panel.run("recover_continue", { id: r.id }) }, "接著寫完"),
      h("button", { class: "sm", onclick: () => recoverTo(r.id) }, "直接存成候選稿"),
      h("button", { class: "sm", onclick: () => recoverView(r.id) }, "查看"),
      h("button", { class: "sm danger", onclick: () => recoverDiscard(r.id) }, "捨棄")));

    const rvAlert = (rv && tab !== "revision")
      ? h("div", { class: "alert info", style: "margin-bottom:10px" },
        h("span", { class: "k" }, "待確認修訂"),
        h("span", { class: "t" }, "有一份修訂（" + rv.changes + " 處變更）等你逐段確認。"),
        h("button", { class: "sm", onclick: () => FE.go(base + "?tab=revision") }, "開啟"))
      : null;

    const pipeBox = h("div", { class: "pipe-box" });
    const structBox = h("div", { id: "struct-box" });
    const goalBox = h("div", { id: "goal-box" });
    const reviewBox = h("div", { id: "review-box" });
    const docEl = h("div", { id: "doc" });

    ctx.view(
      h("div", { class: "page-head" },
        h("div", {},
          h("div", { class: "muted small" },
            h("a", { href: "#/b/" + enc(S.book) + "/chapters" }, "章節"), " ／ 第" + no + "章"),
          h("h1", {}, "第" + no + "章　" + (c.title || ""))),
        headRow),
      actions,
      tabsNode,
      candidateAlert,
      recAlerts,
      rvAlert,
      pipeBox,
      structBox,
      goalBox,
      reviewBox,
      docEl);

    renderPipe();

    if (tab === "card") renderChapterStructure(structBox, no);
    if (tab === "revision") renderRevision(docEl, no, rv, signal);
    else if (tab === "illust") renderIllust(docEl, "chapter:" + no, { chapter: no });
    else {
      if (c.card_file && (tab === "text" || tab === "candidate")) {
        renderGoals(goalBox, no, tab === "candidate", cur && cur[2], signal);
      }
      if (tab === "text" || tab === "candidate") renderReview(reviewBox, no, tab === "candidate", cur && cur[2], signal);
      if (cur) {
        await docView(docEl, cur[2], {
          prose: tab === "text" || tab === "candidate",
          checkable: tab === "text" || tab === "candidate",
          signal,
        });
      } else {
        docEl.replaceChildren(h("div", { class: "card empty" }, "這章還沒有任何檔案。"));
      }
    }

    // 搜尋頁跳過來的高亮：舊版是 route() 的 finally 做的，FE.PAGES 之後要由本頁自己收
    if (S.hl) {
      const terms = S.hl;
      S.hl = null;
      highlightTerms(docEl, terms);
    }

    if (tab === "candidate" && acceptBtn) {
      acceptBtn.onclick = async () => {
        if (!(await FE.confirm("採用第" + no + "章？候選稿會移到正文，並請 " + Panel.provName() + " 回寫追蹤資料。"))) return;
        try {
          const r = await FE.api(B("/candidate/" + no + "/accept?provider=" + enc(stepProv("accept"))), { method: "POST", signal });
          Panel.attach(r.job);
          FE.go(base + "?tab=text");
        } catch (e) { FE.fail(e); }
      };
      rejectBtn.onclick = () => {
        const noteArea = h("textarea", { id: "rj-note", rows: "5", placeholder: "例如：林晚太早亮出底牌了，改成先讓掌櫃說漏嘴" });
        FE.modal({
          title: "退回第" + no + "章候選稿",
          body: [h("label", { class: "f" }, h("span", {}, "要怎麼改？寫得越具體越好"), noteArea)],
          foot: (done) => [
            h("button", { class: "btn", type: "button", onclick: () => done(false) }, "取消"),
            h("button", {
              class: "btn btn-primary", type: "button", id: "rj-go",
              onclick: async () => {
                try {
                  const r = await FE.api(B("/candidate/" + no + "/reject"), {
                    method: "POST", body: { note: noteArea.value, provider: Panel.prov() }, signal,
                  });
                  done(true);
                  Panel.attach(r.job);
                } catch (e) { FE.fail(e); }
              },
            }, "退回重寫"),
          ],
        });
      };
      discardBtn.onclick = async () => {
        if (!(await FE.confirm("捨棄這份候選稿？（會移到 .studio/備份，不會永久刪除）"))) return;
        try {
          await FE.api(B("/candidate/" + no + "/discard"), { method: "POST", signal });
          FE.toast("已捨棄");
          FE.go(base);
        } catch (e) { FE.fail(e); }
      };
    }
  }

  // routeName 要用 "ch"：renderNav() 的高亮規則是 S.routeName === r 或 (r === "chapters" && S.routeName === "ch")，
  // 舊 route() 也是把 sub（"ch"）寫進 S.routeName；改成 "chapter" 會讓側欄的「章節」不再亮。
  nsPage("b/:book/ch/:no", "ch", { book: true }, render);
})();
