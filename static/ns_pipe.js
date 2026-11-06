/* 整章自動流程（轉移計畫 §8.3 的 ns_pipe.js）：從 app.js 搬 PIPE／PIPE_ICON／PIPE_STATUS／pipeFetch／renderPipe／
   pipeHtml／pipeWatch／pipeTick／pipeShowJob／pipeStop／pipeResume／pipeClear／pipeRewind／pipeModal（原 536-689）。
   對外維持原本的全域名稱（window.renderPipe／pipeModal／pipeStop／pipeResume／pipeClear／pipeShowJob／pipeRewind）：
   page_chapters.js 與 page_overview.js 現在就是呼叫 renderPipe() 與 pipeModal()。
   全部改成 h() 節點；兩個 modal 改 FE.modal；計時器在換頁（fe-route）且頁面已沒有 .pipe-box 時自動 clearInterval。
   這支是全域輪詢工具，沒有 ctx，所以請求不帶 signal（與舊版相同）。 */
(function () {
  "use strict";

  const { h } = FE;
  const enc = encodeURIComponent;

  const PIPE = { data: null, timer: null, book: null, lastJob: null, lastStatus: null, meta: null, rw: null };
  const PIPE_ICON = { done: "✓", skipped: "–", running: "●", failed: "✗", pending: "○" };
  const PIPE_STATUS = {
    running: ["執行中", "b-accent"], paused: ["這章完成，等你繼續", "b-ok"], done: ["全部完成", "b-ok"],
    failed: ["停在失敗的步驟", "b-bad"], stopped: ["已停止", "b-warn"],
  };

  const boxes = () => Array.from(document.querySelectorAll(".pipe-box"));

  function stopTimer() {
    if (PIPE.timer) { clearInterval(PIPE.timer); PIPE.timer = null; }
  }

  async function pipeFetch() {
    if (!S.book) return null;
    const book = S.book;
    try {
      const r = await FE.api(B("/pipeline"));
      if (book !== S.book) return null;
      PIPE.meta = r;
      PIPE.data = r.pipeline;
      PIPE.book = book;
      PIPE.rw = null;
      if (r.pipeline && ["failed", "stopped"].includes(r.pipeline.status)) {
        try { PIPE.rw = await FE.api(B("/pipeline/rewind_check")); } catch (e) { PIPE.rw = null; }
      }
    } catch (e) { PIPE.data = null; }
    return PIPE.data;
  }

  function stepNode(p, s) {
    const who = s.provider || (p.step_providers || {})[s.key];
    const rewind = PIPE.rw && PIPE.rw.steps[s.key] && PIPE.rw.steps[s.key].ok
      ? h("button", {
        class: "sm ghost",
        style: "white-space:nowrap;align-self:flex-start;margin-top:4px",
        title: "還原到這一步開始前的候選稿，從這裡重跑",
        onclick: () => pipeRewind(s.key),
      }, "↺ 重跑")
      : null;
    return h("div", { class: "pstep " + s.status, title: s.note || "" },
      h("span", { class: "pi" }, PIPE_ICON[s.status] || "○"),
      h("span", { class: "pl" }, s.label, who ? h("span", { class: "muted small" }, "（" + provName(who) + "）") : null),
      s.note ? h("span", { class: "pn" }, s.note) : null,
      rewind);
  }

  function pipeNode(p) {
    const hit = PIPE_STATUS[p.status] || [p.status, ""];
    const label = hit[0], cls = hit[1];
    const rng = p.from === p.to ? "第" + p.from + "章" : "第" + p.from + "～" + p.to + "章";
    const btns = [];
    if (p.status === "running") {
      if (p.job) btns.push(h("button", { class: "sm", onclick: () => pipeShowJob(p.job) }, "看目前這一步"));
      btns.push(h("button", { class: "sm danger", onclick: () => pipeStop() }, "停止"));
    } else {
      if (p.status === "failed" || p.status === "stopped") btns.push(h("button", { class: "sm primary", onclick: () => pipeResume() }, "從這一步繼續"));
      if (p.status === "paused") btns.push(h("button", { class: "sm primary", onclick: () => pipeResume() }, "繼續下一章（第" + p.chapter + "章）"));
      btns.push(h("button", { class: "sm ghost", onclick: () => pipeClear() }, "關閉"));
    }
    const head = h("div", { class: "row" },
      h("b", {}, "⚡ 整章自動流程"),
      h("span", { class: "muted small" },
        rng
        + (p.status === "running" || p.status === "failed" || p.status === "stopped" ? "　·　目前第" + p.chapter + "章" : "")
        + "　·　" + (p.mode === "continue" ? "連續寫" : "寫一章停一章")
        + "　·　自動勾選：" + ((p.severities || []).join("、") || "無")),
      h("span", { class: "badge " + cls }, label),
      h("span", { class: "grow" }),
      btns);

    const doneLine = (p.status === "paused" || p.status === "done")
      ? h("div", { class: "muted small", style: "margin-top:6px" },
        p.message || "",
        (p.done_chapters && p.done_chapters.length)
          ? ["　已定稿：", p.done_chapters.map((n, i) => [
            i ? "、" : null,
            h("a", { href: "#/b/" + enc(S.book) + "/ch/" + n + "?tab=text" }, "第" + n + "章"),
          ])]
          : null)
      : null;

    return h("div", { class: "card pipe " + p.status },
      head,
      doneLine,
      p.status === "failed"
        ? h("div", { class: "alert bad", style: "margin:8px 0 0" },
          h("span", { class: "k" }, "失敗"),
          h("span", { class: "t" }, p.error))
        : null,
      (p.status === "stopped" && p.message)
        ? h("div", { class: "muted small", style: "margin-top:6px" }, p.message)
        : null,
      (p.status === "paused" || p.status === "done")
        ? null
        : h("div", { class: "psteps" }, p.steps.map((s) => stepNode(p, s))));
  }

  function fill(el, p) {
    el.replaceChildren(...(p ? [pipeNode(p)] : []));
  }

  let filled = [];   // 上一次填過的 .pipe-box 節點；節點被換頁移掉就收計時器

  async function renderPipe() {
    const list = boxes();
    if (!list.length || !S.book) { stopTimer(); filled = []; return; }
    filled = list;
    const p = PIPE.book === S.book && PIPE.data && PIPE.data.status === "running" ? PIPE.data : await pipeFetch();
    list.forEach((el) => fill(el, p));
    pipeWatch(p);
  }

  function pipeWatch(p) {
    const running = p && p.status === "running";
    if (running && !PIPE.timer) PIPE.timer = setInterval(pipeTick, 1500);
    if (!running) stopTimer();
    if (p && running && p.job && p.job !== PIPE.lastJob) {
      PIPE.lastJob = p.job;
      if (!S.job || S.job.id !== p.job || S.job.status !== "running") pipeShowJob(p.job, true);
    }
  }

  async function pipeTick() {
    const list = filled.filter((el) => el.isConnected);
    if (!list.length) { stopTimer(); filled = []; return; }
    const before = PIPE.data && PIPE.data.status;
    const p = await pipeFetch();
    list.forEach((el) => fill(el, p));
    pipeWatch(p);
    if (before === "running" && (!p || p.status !== "running")) {
      if (p && p.status === "failed") FE.toast("整章自動流程停住了：" + p.error, "err");
      else if (p && (p.status === "paused" || p.status === "done")) FE.toast(p.message || "完成");
      if (!document.querySelector("textarea.editor")) await FE.route();
    }
  }

  async function pipeShowJob(id, quiet) {
    try {
      const j = await FE.api(B("/jobs/" + id));
      if (j.status === "running") Panel.attach(j, quiet, !!quiet);
      else if (!quiet || !S.job || S.job.status !== "running") Panel.show(id);
    } catch (e) { /* ignore */ }
  }

  async function pipeStop() {
    if (!(await FE.confirm("停止整章自動流程？目前這一步會中斷，之後可以從這一步繼續。"))) return;
    try { await FE.api(B("/pipeline/stop"), { method: "POST" }); FE.toast("正在停止……"); } catch (e) { FE.fail(e); }
  }

  async function pipeResume() {
    try {
      const r = await FE.api(B("/pipeline/resume"), { method: "POST", body: { provider: Panel.prov() } });
      PIPE.data = r.pipeline;
      renderPipe();
    } catch (e) { FE.fail(e); }
  }

  async function pipeClear() {
    try {
      await FE.api(B("/pipeline/clear"), { method: "POST" });
      PIPE.data = null;
      renderPipe();
    } catch (e) { FE.fail(e); }
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
    const noteArea = canNote
      ? h("label", { class: "f" },
        h("span", {}, "這次的要求（選填，只用在「" + st.label + "」這一步）"),
        h("textarea", { id: "rw-note", rows: "2", placeholder: "例如：保留更多對白；這次節奏放慢" }))
      : null;
    const close = FE.modal({
      title: "↺ 從「" + st.label + "」重跑",
      body: [
        h("p", { class: "small" }, what + "。"),
        h("p", { class: "small muted" }, "之後這幾步的結果會先備份到 .studio/備份/ 再清掉，然後重新執行：" + later.join(" → ")),
        noteArea,
      ],
      foot: (done) => [
        h("button", { class: "btn", type: "button", onclick: () => done(false) }, "取消"),
        h("button", {
          class: "btn btn-primary", type: "button", id: "rw-go",
          onclick: async () => {
            try {
              const r = await FE.api(B("/pipeline/rewind"), {
                method: "POST",
                body: { step: key, note: canNote ? close.el.querySelector("#rw-note").value : "" },
              });
              close();
              PIPE.data = r.pipeline;
              PIPE.rw = null;
              PIPE.lastJob = null;
              FE.toast("從「" + st.label + "」重跑");
              renderPipe();
            } catch (e) { FE.fail(e); }
          },
        }, "重跑"),
      ],
    });
  }

  async function pipeModal(no) {
    const [r, chs] = await Promise.all([FE.api(B("/pipeline")), FE.api(B("/chapters"))]);
    if (r.pipeline && r.pipeline.status === "running") return FE.toast("已經有整章自動流程在執行", "err");
    const firstOpen = (chs.find((c) => !c.text_file || c.candidate_file) || { no: (chs.length ? chs[chs.length - 1].no + 1 : 1) }).no;
    no = no || firstOpen;
    const lastCard = Math.max(no, ...chs.filter((c) => c.card_file).map((c) => c.no));
    const d = r.defaults;
    const fromInput = h("input", { type: "number", id: "pp-from", class: "num-in", value: String(no), min: "1" });
    const toInput = h("input", { type: "number", id: "pp-to", class: "num-in", value: String(no), min: "1" });
    const noteArea = h("textarea", { id: "pp-note", rows: "2", placeholder: "例如：這幾章節奏要快；不要新增角色" });
    const sevBoxes = r.severities.map((x) => h("label", { class: "cb" },
      h("input", { type: "checkbox", value: x, checked: d.severities.includes(x) }),
      " " + x));
    const stepProvNote = Object.keys(d.step_providers || {}).length
      ? h("div", { class: "muted small" },
        "各步驟另外指定："
        + AI_STEP_LABELS.filter(([k]) => (d.step_providers || {})[k])
          .map(([k, l]) => l + " → " + provName(d.step_providers[k])).join("、")
        + "；其他步驟用上面選的執行者。（設定 → 整章自動流程）")
      : null;
    const provSel = provSelect("pp-prov", Panel.prov());

    const close = FE.modal({
      title: "⚡ 整章自動流程",
      body: [
        h("p", { class: "muted small" },
          "每章依序：" + r.steps.map((s) => s.label).join(" → ") + "。",
          h("br"),
          "已有章綱就不重寫；已有候選稿就從核對開始。會呼叫 AI 的步驟各自呼叫一次；任何一步失敗都會停在那一步，修正後可以從那一步繼續。"),
        h("div", { class: "row" },
          h("span", { class: "small muted" }, "從第"),
          fromInput,
          h("span", { class: "small muted" }, "章到第"),
          toInput,
          h("span", { class: "small muted" }, "章"),
          h("span", { class: "muted small" }, "（章綱寫到第" + lastCard + "章）")),
        h("div", { class: "f", style: "margin-top:12px" }, h("span", {}, "跑法")),
        h("div", { class: "seg compact", id: "pp-mode" },
          h("label", {}, h("input", { type: "radio", name: "pp-mode", value: "stop", checked: d.mode !== "continue" }), h("span", {}, "寫一章停一章")),
          h("label", {}, h("input", { type: "radio", name: "pp-mode", value: "continue", checked: d.mode === "continue" }), h("span", {}, "連續寫到最後一章"))),
        h("div", { class: "f", style: "margin-top:12px" }, h("span", {}, "自動勾選哪些等級的審查意見（交給修訂）")),
        h("div", { class: "row", id: "pp-sev" }, sevBoxes),
        h("label", { class: "f", style: "margin-top:8px" },
          h("span", {}, "對整個流程的要求（選填，每一步都會帶上）"), noteArea),
        h("label", { class: "f" }, h("span", {}, "執行者"), provSel),
        stepProvNote,
      ],
      foot: (done) => [
        h("button", { class: "btn", type: "button", onclick: () => done(false) }, "取消"),
        h("button", {
          class: "btn btn-primary", type: "button", id: "pp-go",
          onclick: async () => {
            try {
              const body = {
                from: parseInt(fromInput.value, 10),
                to: parseInt(toInput.value, 10) || parseInt(fromInput.value, 10),
                mode: close.el.querySelector('input[name="pp-mode"]:checked').value,
                severities: Array.from(close.el.querySelectorAll("#pp-sev input:checked")).map((x) => x.value),
                note: noteArea.value,
                provider: provSel.value,
              };
              if (!body.from) return FE.toast("請輸入章號", "err");
              const res = await FE.api(B("/pipeline"), { method: "POST", body });
              close();
              PIPE.data = res.pipeline;
              PIPE.book = S.book;
              PIPE.lastJob = null;
              FE.toast("開始整章自動流程");
              if (!document.querySelector(".pipe-box")) FE.go("#/b/" + enc(S.book) + "/ch/" + body.from);
              else renderPipe();
            } catch (e) { FE.fail(e); }
          },
        }, "開始"),
      ],
    });
  }

  // 換頁後頁面上已經沒有 .pipe-box：把輪詢計時器收掉，不要讓它在背景跑
  // fe-route 在新頁畫面出現前就送出，所以等一輪再看畫面上還有沒有 .pipe-box
  window.addEventListener("fe-route", () => {
    setTimeout(() => {
      if (!document.querySelector(".pipe-box")) { stopTimer(); filled = []; }
    }, 0);
  });

  window.renderPipe = renderPipe;
  window.pipeModal = pipeModal;
  window.pipeStop = pipeStop;
  window.pipeResume = pipeResume;
  window.pipeClear = pipeClear;
  window.pipeShowJob = pipeShowJob;
  window.pipeRewind = pipeRewind;
})();
