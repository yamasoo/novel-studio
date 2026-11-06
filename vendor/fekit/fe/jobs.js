/* fekit jobs.js — 任務追蹤與面板。格式見 docs/02_API合約.md 第 4 節，介面見第 8 節。
 * 依賴 core.js，只加上 FE.jobs；不依賴 shell.js。 */
(function () {
  "use strict";

  const FE = window.FE;
  if (!FE) throw new Error("fekit：jobs.js 要在 core.js 之後載入");
  if (FE.jobs) {
    console.warn("fekit：jobs.js 被載入了兩次，第二次已略過");
    return;
  }

  const { h, api, fail, toast } = FE;

  const TERMINAL = new Set(["done", "error", "stopped"]);
  const FINISHED_ITEMS = new Set(["done", "skipped", "error", "stopped"]);
  const ITEM_STATES = new Set(["pending", "running", "done", "skipped", "error", "stopped"]);
  const PHASES = {
    starting: "準備中",
    waiting: "已送出，等待模型回應",
    streaming: "模型輸出中",
    thinking: "模型思考中",
    checking: "檢查輸出",
    repair: "修正輸出",
    idle: "待命",
  };
  const STATUS = {
    queued: ["排隊中", ""],
    running: ["執行中", "chip-accent"],
    done: ["完成", "chip-ok"],
    error: ["失敗", "chip-err"],
    stopped: ["已停止", "chip-warn"],
  };
  const KEEP_EVENTS = 5000;
  const LOG_LINES = 2000;
  const REQUEST_TIMEOUT_MS = 15000;
  const CLOSE_GRACE_MS = 5000;
  const MAX_RETRY_MS = 5000;
  const FLUSH_MS = 50;
  const NEAR_BOTTOM_PX = 40;
  const GAP = Symbol("gap");

  const isTerminal = (status) => TERMINAL.has(status);

  function blank(id) {
    return {
      id, seq: 0, kind: "", title: "", status: null, phase: "", note: "", progress: null,
      stop_requested: false, started_at: null, ended_at: null, items: [], log: [], stream: [],
      truncated: false, ask: null, error: null, result: null,
    };
  }

  // 合約 4.5。回傳這次新增的內容；整個丟棄時回傳 null。
  function applyPatch(job, patch) {
    if (!patch || typeof patch !== "object") return null;
    const seq = Number.isFinite(patch.seq) ? patch.seq : job.seq;
    if (seq < job.seq) return null;
    const fresh = seq > job.seq;
    const delta = { log: [], stream: [], truncated: fresh && patch.truncated === true };
    for (const [key, value] of Object.entries(patch)) {
      if (key === "seq" || key === "__proto__") continue;
      if (key === "log" || key === "stream") {
        if (!fresh || !Array.isArray(value)) continue;
        // 不用 push(...value)：一次太多筆會超過函式參數上限。
        for (const item of value) {
          job[key].push(item);
          delta[key].push(item);
        }
      } else {
        job[key] = value;
      }
    }
    job.seq = seq;
    return delta;
  }

  // POST 的回應只用來更新狀態（合約 4.5 第 6 條）。
  function applyFields(job, patch) {
    if (!patch || typeof patch !== "object") return;
    const fields = Object.assign({}, patch, { seq: job.seq });
    delete fields.log;
    delete fields.stream;
    applyPatch(job, fields);
  }

  function trim(list) {
    if (list.length > KEEP_EVENTS * 1.2) list.splice(0, list.length - KEEP_EVENTS);
  }

  const jobUrl = (base, id, suffix = "") => `${base}/${encodeURIComponent(id)}${suffix}`;

  async function list(opts = {}) {
    const data = await api(opts.base || "/api/jobs", {
      query: { status: opts.status, limit: opts.limit },
      signal: opts.signal,
    });
    return (data && data.jobs) || [];
  }

  /* ──────────────── 追蹤器 ──────────────── */

  function watch(input, opts = {}) {
    const first = typeof input === "object" && input !== null ? input : { id: input };
    if (first.id === undefined || first.id === null || first.id === "") throw new TypeError("FE.jobs.watch()：缺少任務 id");

    const base = typeof opts.base === "function" ? opts.base() : opts.base || "/api/jobs";
    const pollMs = opts.poll_ms !== undefined ? opts.poll_ms : 700;

    let generation = 0;   // 每次重開連線就加一，舊連線遲到的回呼一律作廢。
    let source = null;
    let ctrl = null;
    let pollTimer = null;
    let graceTimer = null;
    let recovering = false;
    let failures = 0;
    let closedForGood = false;
    // 只有看到任務還沒結束（或呼叫端說這是剛啟動的），結束時才通知。
    let liveSeen = opts.live !== false;

    const tracker = {
      job: blank(first.id),
      transport: opts.transport === "poll" ? "poll" : "sse",
      conn: "connecting",
      stop, reply, sync, restart, close,
    };
    applyFields(tracker.job, first);

    function emit(name, ...args) {
      if (closedForGood || !opts[name]) return;
      try {
        opts[name](...args);
      } catch (error) {
        // 使用者的回呼出錯不能被當成連線失敗。
        console.error(error);
      }
    }

    function setConn(state, error) {
      if (tracker.conn === state) return;
      tracker.conn = state;
      emit("onconn", state, error || null);
    }

    function clearGrace() {
      if (graceTimer) clearTimeout(graceTimer);
      graceTimer = null;
    }

    function teardown() {
      generation += 1;
      if (source) source.close();
      source = null;
      if (ctrl) ctrl.abort();
      ctrl = null;
      if (pollTimer) clearTimeout(pollTimer);
      pollTimer = null;
      clearGrace();
    }

    function receive(patch) {
      const job = tracker.job;
      if (patch && patch.id !== undefined && patch.id !== job.id) return;
      const delta = applyPatch(job, patch);
      if (!delta) return;
      trim(job.log);
      trim(job.stream);
      if (job.status && !isTerminal(job.status)) liveSeen = true;
      emit("onupdate", job, delta);
    }

    function notifyOnly() {
      emit("onupdate", tracker.job, { log: [], stream: [], truncated: false });
    }

    function finish() {
      teardown();
      setConn("closed");
      if (liveSeen) {
        liveSeen = false;
        emit("onend", tracker.job);
      }
    }

    function gone(error) {
      teardown();
      tracker.job.gone = true;
      setConn("gone", error);
      notifyOnly();
    }

    const fetchPatch = (signal) => api(jobUrl(base, tracker.job.id), {
      query: { since: tracker.job.seq },
      signal,
      timeout: REQUEST_TIMEOUT_MS,
    });

    /* 輪詢 */

    async function tick(gen) {
      let delay = pollMs;
      ctrl = new AbortController();
      try {
        const patch = await fetchPatch(ctrl.signal);
        if (gen !== generation) return;
        failures = 0;
        setConn("live");
        receive(patch);
        if (isTerminal(tracker.job.status)) {
          finish();
          return;
        }
      } catch (error) {
        if (gen !== generation || (error && error.name === "AbortError")) return;
        if (error.status === 404) {
          gone(error);
          return;
        }
        failures += 1;
        setConn("retrying", error);
        delay = Math.min(MAX_RETRY_MS, pollMs * 2 ** failures);
      }
      pollTimer = setTimeout(() => tick(gen), delay);
    }

    function fallBackToPoll() {
      teardown();
      tracker.transport = "poll";
      tick(generation);
    }

    /* SSE */

    async function recover(gen, es) {
      if (recovering) return;
      recovering = true;
      const hard = es.readyState === EventSource.CLOSED;
      try {
        const patch = await fetchPatch();
        if (gen !== generation) return;
        receive(patch);
        if (isTerminal(tracker.job.status)) finish();
        else if (hard) fallBackToPoll();
        else setConn("retrying");   // 瀏覽器會自己重連，onopen 會改回 live。
      } catch (error) {
        if (gen !== generation) return;
        if (error.status === 404) {
          gone(error);
        } else {
          setConn("retrying", error);
          if (hard) fallBackToPoll();
        }
      } finally {
        recovering = false;
      }
    }

    async function settle(gen) {
      if (isTerminal(tracker.job.status)) {
        finish();
        return;
      }
      // 伺服器說結束了，手上的狀態卻還沒結束：問一次，不行就改輪詢，不要卡住。
      try {
        receive(await fetchPatch());
      } catch (error) {
        if (gen !== generation) return;
        if (error.status === 404) {
          gone(error);
          return;
        }
      }
      if (gen !== generation) return;
      if (isTerminal(tracker.job.status)) finish();
      else fallBackToPoll();
    }

    function openSse(gen) {
      const es = new EventSource(jobUrl(base, tracker.job.id, `/events?since=${tracker.job.seq}`));
      source = es;
      es.onopen = () => {
        if (gen === generation) setConn("live");
      };
      es.onmessage = (event) => {
        if (gen !== generation) return;
        let patch;
        try {
          patch = JSON.parse(event.data);
        } catch (_) {
          console.warn("fekit：SSE 訊息不是 JSON，已略過", event.data);
          return;
        }
        setConn("live");
        receive(patch);
        clearGrace();
        if (isTerminal(tracker.job.status)) {
          graceTimer = setTimeout(() => {
            if (gen === generation) finish();
          }, CLOSE_GRACE_MS);
        }
      };
      es.addEventListener("close", () => {
        if (gen !== generation) return;
        es.close();
        settle(gen);
      });
      es.onerror = () => {
        if (gen === generation) recover(gen, es);
      };
    }

    function connect() {
      teardown();
      failures = 0;
      setConn("connecting");
      if (tracker.transport === "sse" && typeof EventSource !== "undefined") {
        openSse(generation);
      } else {
        tracker.transport = "poll";
        tick(generation);
      }
    }

    /* 動作 */

    async function stop() {
      let patch;
      try {
        patch = await api(jobUrl(base, tracker.job.id, "/stop"), { method: "POST", body: {} });
      } catch (error) {
        if (error.status === 404 && !closedForGood) gone(error);
        throw error;
      }
      // 只取 stop_requested：這個回應可能比 SSE 的結束訊息晚到，status 不能倒退。
      tracker.job.stop_requested = patch && patch.stop_requested !== undefined ? patch.stop_requested : true;
      notifyOnly();
      return patch;
    }

    async function reply(askId, text) {
      const patch = await api(jobUrl(base, tracker.job.id, "/reply"), { body: { ask_id: askId, text } });
      if (closedForGood) return patch;
      liveSeen = true;
      const nextId = patch && patch.id;
      if (nextId !== undefined && nextId !== null && nextId !== tracker.job.id) {
        teardown();
        tracker.job = blank(nextId);
        applyFields(tracker.job, patch);
        emit("onswitch", tracker.job);
        connect();
        return patch;
      }
      tracker.job.ask = null;
      applyFields(tracker.job, patch);
      clearGrace();
      if (tracker.conn === "closed") connect();
      else notifyOnly();
      return patch;
    }

    async function sync() {
      const gen = generation;
      try {
        const patch = await fetchPatch();
        if (gen !== generation) return tracker.job;
        receive(patch);
        if (isTerminal(tracker.job.status) && tracker.conn !== "closed") finish();
      } catch (error) {
        if (error.status === 404 && gen === generation) gone(error);
        else throw error;
      }
      return tracker.job;
    }

    function restart() {
      if (!closedForGood) connect();
    }

    function close() {
      teardown();
      tracker.conn = "closed";
      closedForGood = true;
    }

    connect();
    return tracker;
  }

  /* ──────────────── 面板 ──────────────── */

  function formatSeconds(value) {
    const secs = Math.max(0, Math.round(value));
    if (secs < 60) return `${secs} 秒`;
    if (secs < 3600) return `${Math.floor(secs / 60)} 分 ${secs % 60} 秒`;
    return `${Math.floor(secs / 3600)} 小時 ${Math.floor((secs % 3600) / 60)} 分`;
  }

  function progressOf(job) {
    const p = job.progress;
    if (p && Number.isFinite(p.total) && p.total > 0) {
      return { done: Math.max(0, Math.min(p.total, Number(p.done) || 0)), total: p.total };
    }
    const items = Array.isArray(job.items) ? job.items : [];
    if (items.length) return { done: items.filter((item) => FINISHED_ITEMS.has(item.state)).length, total: items.length };
    return null;
  }

  function panel(opts = {}) {
    const root = typeof opts.root === "string" ? document.querySelector(opts.root) : opts.root;
    if (!root) throw new Error("FE.jobs.panel()：需要 root 節點");

    const phases = Object.assign(Object.create(null), PHASES, opts.phases);
    const kinds = Object.assign(Object.create(null), opts.kinds);
    const maxSegs = opts.max_segs !== undefined ? opts.max_segs : 100;
    const maxChars = opts.max_chars !== undefined ? opts.max_chars : 200000;
    const idleMs = opts.idle_ms !== undefined ? opts.idle_ms : 3000;
    const baseOf = () => (typeof opts.base === "function" ? opts.base() : opts.base || "/api/jobs");

    let tracker = null;
    let destroyed = false;
    let pending = { stream: [], log: [] };
    let flushTimer = null;
    let elapsedTimer = null;
    let idleTimer = null;
    let pinned = true;
    let sending = false;
    let segs = new Map();
    let cappedNote = null;
    let itemsSig = null;
    let outcomeSig = null;
    let askId = null;

    /* ── 節點 ── */

    const titleEl = h("div", { class: "job-title" });
    const chipEl = h("span", { class: "chip", "aria-live": "polite" });
    const stopBtn = h("button", { class: "btn btn-sm", type: "button", onclick: () => stop() }, "停止");
    const phaseEl = h("div", { class: "job-phase" });
    const noteEl = h("div", { class: "job-note" });
    const barFill = h("div", { class: "bar-fill" });
    const barEl = h("div", { class: "bar", role: "progressbar" }, barFill);
    const connEl = h("div", { class: "alert alert-warn job-conn hidden", role: "status" });
    const itemsEl = h("ul", { class: "job-items hidden" });
    const headEl = h("div", { class: "job-head" },
      h("div", { class: "job-title-row" }, titleEl, chipEl, stopBtn),
      phaseEl, noteEl, barEl, connEl, itemsEl);

    const segsEl = h("div", { class: "job-segs" });
    const outcomeEl = h("div", {});
    const streamEl = h("div", { class: "job-stream stream" }, segsEl, outcomeEl);
    const askEl = h("div", { class: "job-ask hidden" });
    const logEl = h("div", { class: "log hidden" });
    const followEl = h("input", {
      type: "checkbox",
      checked: true,
      onchange: () => {
        if (followEl.checked) {
          pinned = true;
          toBottom();
        }
      },
    });
    const logBtn = h("button", {
      class: "btn btn-ghost btn-sm",
      type: "button",
      onclick: () => {
        logEl.classList.toggle("hidden");
        drawLogButton();
      },
    }, "紀錄");
    const clearBtn = h("button", { class: "btn btn-ghost btn-sm", type: "button", onclick: () => clear() }, "清空畫面");
    const footEl = h("div", { class: "job-foot" },
      h("label", { class: "check" }, followEl, "自動捲到最新"),
      h("span", { class: "grow" }), logBtn, clearBtn);
    const emptyEl = h("div", { class: "job-empty" }, opts.empty || "目前沒有任務。任務開始後，進度與模型輸出會顯示在這裡。");
    const el = h("div", { class: "job-panel" }, emptyEl, headEl, streamEl, askEl, logEl, footEl);
    root.append(el);

    /* ── 捲動 ── */

    const nearBottom = () => streamEl.scrollHeight - streamEl.scrollTop - streamEl.clientHeight < NEAR_BOTTOM_PX;
    const toBottom = () => { streamEl.scrollTop = streamEl.scrollHeight; };

    // 面板收合時高度是 0，不能拿來判斷使用者有沒有往上捲。
    streamEl.addEventListener("scroll", () => {
      if (streamEl.clientHeight > 0) pinned = nearBottom();
    });
    const resizer = new ResizeObserver(() => {
      if (followEl.checked && pinned) toBottom();
    });
    resizer.observe(streamEl);

    /* ── 串流 ── */

    function capSegments() {
      while (segs.size > maxSegs) {
        const [key, seg] = segs.entries().next().value;
        seg.el.remove();
        segs.delete(key);
        if (!cappedNote) {
          cappedNote = h("div", { class: "job-gap" }, "（較早的段落已從畫面移除）");
          segsEl.prepend(cappedNote);
        }
      }
    }

    function segment(key) {
      const id = String(key === undefined || key === null ? "" : key);
      let seg = segs.get(id);
      if (!seg) {
        const label = h("span", { class: "stream-seg-label hidden" });
        const node = document.createTextNode("");
        const text = h("div", { class: "job-seg-text" }, node);
        const box = h("div", { class: "job-seg live" }, label, text);
        seg = { el: box, label, text, node, format: "text", think: null, thinkNode: null, note: null, md: null, json: null, capped: false };
        segs.set(id, seg);
        segsEl.append(box);
        capSegments();
      }
      return seg;
    }

    function appendText(seg, value) {
      if (seg.md) {
        seg.md.remove();
        seg.md = null;
        seg.text.classList.remove("hidden");
      }
      seg.el.classList.add("live");
      seg.node.appendData(String(value === undefined || value === null ? "" : value));
      if (seg.node.length > maxChars) {
        seg.node.deleteData(0, seg.node.length - maxChars);
        if (!seg.capped) {
          seg.capped = true;
          seg.el.insertBefore(h("div", { class: "job-gap" }, "（這一段太長，前面的內容已從畫面移除）"), seg.text);
        }
      }
    }

    function appendThinking(seg, value) {
      if (!seg.think) {
        seg.thinkNode = document.createTextNode("");
        seg.think = h("details", { class: "job-think" }, h("summary", {}, "思考過程"), h("pre", {}, seg.thinkNode));
        seg.el.insertBefore(seg.think, seg.json || seg.text);
      }
      seg.thinkNode.appendData(String(value === undefined || value === null ? "" : value));
    }

    function endSegment(seg, note) {
      seg.el.classList.remove("live");
      if (note) {
        if (!seg.note) {
          seg.note = h("div", { class: "job-seg-note" });
          seg.el.append(seg.note);
        }
        seg.note.textContent = note;
      }
      const raw = seg.node.data;
      if (seg.format === "md" && opts.render_md && !seg.md) {
        try {
          seg.md = h("div", { class: "job-seg-md" }, opts.render_md(raw));
          seg.text.classList.add("hidden");
          seg.el.insertBefore(seg.md, seg.text);
        } catch (error) {
          // 轉換失敗就留純文字，內容不能因此消失。
          console.error(error);
          seg.md = null;
        }
      } else if (seg.format === "json") {
        if (!seg.json) {
          seg.json = h("details", { class: "job-json" }, h("summary", {}));
          seg.el.insertBefore(seg.json, seg.text);
          seg.json.append(seg.text);
        }
        seg.json.firstElementChild.textContent = `結構化資料（JSON，${raw.length} 字）`;
      }
    }

    function applyEvent(ev) {
      if (ev === GAP) {
        segsEl.append(h("div", { class: "job-gap" }, "（較早的輸出已被丟棄，只保留最近一段）"));
        // 缺口後面的內容要接在提示之後，不能接回前面的段落。
        segs = new Map();
        return;
      }
      if (!ev || typeof ev !== "object") return;
      const type = ev.type === undefined ? "text" : ev.type;
      const seg = segment(ev.seg);
      if (type === "begin") {
        if (ev.label) {
          seg.label.textContent = ev.label;
          seg.label.classList.remove("hidden");
        }
        if (ev.format === "md" || ev.format === "json") {
          seg.format = ev.format;
          seg.text.classList.toggle("job-seg-text-json", ev.format === "json");
        }
      } else if (type === "text") {
        appendText(seg, ev.text);
      } else if (type === "thinking") {
        appendThinking(seg, ev.text);
      } else if (type === "end") {
        endSegment(seg, ev.note);
      }
    }

    /* ── 紀錄 ── */

    let logCount = 0;

    function drawLogButton() {
      const shown = !logEl.classList.contains("hidden");
      logBtn.textContent = `${shown ? "收起紀錄" : "紀錄"}${logCount ? `（${logCount}）` : ""}`;
    }

    function applyLog(entries) {
      if (!entries.length) return;
      const stick = logEl.scrollHeight - logEl.scrollTop - logEl.clientHeight < NEAR_BOTTOM_PX;
      for (const entry of entries) {
        const line = typeof entry === "string" ? { text: entry } : entry || {};
        const level = line.level === "error" ? "log-err" : line.level === "warn" ? "log-warn" : line.level === "dim" ? "log-dim" : null;
        logEl.append(h("span", { class: ["log-line", level] }, line.text === undefined ? "" : String(line.text)));
        logCount += 1;
      }
      while (logEl.childElementCount > LOG_LINES) logEl.firstElementChild.remove();
      if (stick) logEl.scrollTop = logEl.scrollHeight;
      drawLogButton();
    }

    /* ── 狀態 ── */

    function drawPhase(job) {
      const running = job.status === "running" || job.status === "queued";
      const parts = [];
      if (running && job.ask) parts.push("等待你回覆");
      else if (job.status === "running" && job.phase) parts.push(phases[job.phase] || job.phase);
      if (job.started_at) {
        const end = job.ended_at || (running ? Date.now() / 1000 : null);
        if (end) parts.push(`${running ? "已執行" : "用時"} ${formatSeconds(end - job.started_at)}`);
      }
      const progress = progressOf(job);
      if (progress) parts.push(`${progress.done} / ${progress.total}`);
      phaseEl.textContent = parts.join("・");
    }

    function drawBar(job) {
      const progress = progressOf(job);
      const running = job.status === "running" || job.status === "queued";
      barEl.classList.toggle("hidden", !progress && !running);
      barEl.classList.toggle("bar-busy", !progress && running);
      barEl.classList.toggle("bar-ok", job.status === "done");
      barEl.classList.toggle("bar-err", job.status === "error");
      if (progress) {
        barFill.style.width = `${Math.round((100 * progress.done) / progress.total)}%`;
        barEl.setAttribute("aria-valuenow", String(progress.done));
        barEl.setAttribute("aria-valuemax", String(progress.total));
      } else {
        barFill.style.width = "";
        barEl.removeAttribute("aria-valuenow");
        barEl.removeAttribute("aria-valuemax");
      }
    }

    function drawItems(job) {
      const items = Array.isArray(job.items) ? job.items : [];
      const sig = JSON.stringify(items);
      if (sig === itemsSig) return;
      itemsSig = sig;
      itemsEl.classList.toggle("hidden", !items.length);
      itemsEl.replaceChildren(...items.map((item) => {
        const state = ITEM_STATES.has(item.state) ? item.state : "pending";
        return h("li", { class: ["job-item", `state-${state}`], title: item.note || null },
          h("span", {}, item.label === undefined ? "" : String(item.label)),
          item.note ? h("span", { class: "job-item-note" }, item.note) : null);
      }));
      const active = itemsEl.querySelector(".state-running");
      if (active) itemsEl.scrollTop = active.offsetTop - itemsEl.offsetTop - itemsEl.clientHeight / 2;
    }

    function drawOutcome(job) {
      const text = job.result && typeof job.result.text === "string" ? job.result.text : "";
      const message = job.status === "error" ? job.error || "任務失敗" : "";
      const sig = JSON.stringify([message, job.status === "done" ? text : ""]);
      if (sig === outcomeSig) return;
      outcomeSig = sig;
      const nodes = [];
      if (message) nodes.push(h("div", { class: "alert alert-err job-outcome", role: "alert" }, message));
      if (job.status === "done" && text) nodes.push(h("div", { class: "card card-flat job-outcome" }, text));
      outcomeEl.replaceChildren(...nodes);
    }

    function drawAsk(job) {
      const ask = job.ask;
      if (!ask) {
        if (askId !== null) {
          askId = null;
          askEl.classList.add("hidden");
          askEl.replaceChildren();
        }
        return;
      }
      // 同一個提問不重畫，打到一半的字才不會不見。
      if (ask.id === askId) return;
      askId = ask.id;
      const options = Array.isArray(ask.options) ? ask.options : [];
      const withText = ask.allow_text !== false || !options.length;
      const input = withText ? h("textarea", {
        class: "job-ask-input",
        rows: "2",
        placeholder: "輸入回覆（Ctrl+Enter 送出）",
        onkeydown: (event) => {
          if (event.key !== "Enter" || !(event.ctrlKey || event.metaKey)) return;
          if (event.isComposing || event.keyCode === 229) return;
          event.preventDefault();
          reply(input.value);
        },
      }) : null;
      askEl.replaceChildren(
        h("div", { class: "job-ask-prompt" }, ask.prompt === undefined ? "" : String(ask.prompt)),
        options.length ? h("div", { class: "job-ask-options" }, options.map((option) => h("button", {
          class: "btn btn-sm",
          type: "button",
          onclick: () => reply(option.value, option.label),
        }, option.label))) : null,
        input,
        input ? h("div", { class: "job-ask-send" },
          h("button", { class: "btn btn-primary btn-sm", type: "button", onclick: () => reply(input.value) }, "送出")) : null,
      );
      askEl.classList.remove("hidden");
      // 任務停在這裡等人，要讓使用者看得到。
      if (job.status === "running") reveal();
    }

    function drawConn(job) {
      const conn = tracker ? tracker.conn : "closed";
      let message = "";
      if (job.gone) message = "找不到這個任務，後端可能重新啟動過。";
      else if (conn === "retrying") message = "連線中斷，重試中…";
      connEl.textContent = message;
      connEl.classList.toggle("hidden", !message);
      connEl.classList.toggle("alert-err", !!job.gone);
      connEl.classList.toggle("alert-warn", !job.gone);
    }

    function drawHead(job) {
      titleEl.textContent = job.title || kinds[job.kind] || job.kind || "任務";
      titleEl.title = titleEl.textContent;
      const running = job.status === "running" || job.status === "queued";
      let [label, cls] = STATUS[job.status] || ["連線中…", ""];
      if (running && job.stop_requested) [label, cls] = ["停止中…", "chip-warn"];
      else if (job.status === "running" && job.ask) [label, cls] = ["等待回覆", "chip-warn"];
      chipEl.textContent = label;
      chipEl.className = ["chip", cls].filter(Boolean).join(" ");
      const canStop = running && !job.gone;
      stopBtn.classList.toggle("hidden", !canStop);
      stopBtn.disabled = !!job.stop_requested;
      stopBtn.textContent = job.stop_requested ? "停止中…" : "停止";
      noteEl.textContent = running ? job.note || "" : "";
      noteEl.classList.toggle("hidden", !noteEl.textContent);
      drawPhase(job);
      drawBar(job);
      drawConn(job);
    }

    function syncElapsedTimer(job) {
      const running = !!job && (job.status === "running" || job.status === "queued") && !job.gone;
      if (running && !elapsedTimer) {
        elapsedTimer = setInterval(() => {
          if (tracker) drawPhase(tracker.job);
        }, 1000);
      } else if (!running && elapsedTimer) {
        clearInterval(elapsedTimer);
        elapsedTimer = null;
      }
    }

    function setVisible(hasJob) {
      emptyEl.classList.toggle("hidden", hasJob);
      for (const node of [headEl, streamEl, footEl]) node.classList.toggle("hidden", !hasJob);
      if (!hasJob) {
        askEl.classList.add("hidden");
        logEl.classList.add("hidden");
      }
    }

    function drain() {
      const events = pending.stream;
      const lines = pending.log;
      pending = { stream: [], log: [] };
      events.forEach(applyEvent);
      applyLog(lines);
    }

    function flush() {
      if (flushTimer) clearTimeout(flushTimer);
      flushTimer = null;
      if (destroyed) return;
      const job = tracker ? tracker.job : null;
      setVisible(!!job);
      if (!job) {
        syncElapsedTimer(null);
        if (opts.onchange) opts.onchange(null);
        return;
      }
      drain();
      drawHead(job);
      drawItems(job);
      drawOutcome(job);
      drawAsk(job);
      if (!(job.status === "running" || job.status === "queued")) {
        // 任務停了就不會再有 end 事件，游標不能一直閃。
        segsEl.querySelectorAll(".job-seg.live").forEach((node) => node.classList.remove("live"));
      }
      if (followEl.checked && pinned) toBottom();
      syncElapsedTimer(job);
      if (opts.onchange) opts.onchange(job);
    }

    function schedule() {
      if (!flushTimer) flushTimer = setTimeout(flush, FLUSH_MS);
    }

    function reveal() {
      if (opts.onreveal) opts.onreveal();
    }

    function resetView() {
      pending = { stream: [], log: [] };
      segsEl.replaceChildren();
      outcomeEl.replaceChildren();
      logEl.replaceChildren();
      logCount = 0;
      drawLogButton();
      segs = new Map();
      cappedNote = null;
      itemsSig = null;
      outcomeSig = null;
      askId = null;
      askEl.classList.add("hidden");
      askEl.replaceChildren();
      pinned = true;
    }

    // 接著做的時候舊結果留在畫面上，新任務的段落另外開。
    function archiveOutcome() {
      segsEl.append(...outcomeEl.childNodes);
      outcomeSig = null;
      itemsSig = null;
      segs = new Map();
    }

    function notifyEnd(job) {
      if (opts.notify !== false) {
        const name = job.title || kinds[job.kind] || job.kind || "任務";
        if (job.status === "done") toast(`${name}：完成`, "ok");
        else if (job.status === "stopped") toast(`${name}：已停止`, "warn");
        else if (job.status === "error") toast(`${name}：失敗`, "err");
      }
      if (opts.onend) opts.onend(job);
    }

    /* ── 方法 ── */

    function attach(input, o = {}) {
      if (destroyed) throw new Error("FE.jobs.panel：面板已經移除");
      const id = typeof input === "object" && input !== null ? input.id : input;
      if (id === undefined || id === null || id === "") throw new TypeError("attach()：缺少任務 id");
      if (tracker) tracker.close();
      if (o.keep) {
        flush();
        archiveOutcome();
      } else {
        resetView();
      }
      const next = watch(input, {
        transport: opts.transport,
        base: o.base || baseOf(),
        poll_ms: opts.poll_ms,
        live: o.live !== false,
        onupdate(job, delta) {
          if (delta.truncated) pending.stream.push(GAP);
          for (const ev of delta.stream) pending.stream.push(ev);
          for (const line of delta.log) pending.log.push(line);
          schedule();
        },
        onconn: () => schedule(),
        onswitch() {
          // 這時 tracker.job 已經是新任務，不能用 flush()，否則舊結果會先被新狀態蓋掉。
          drain();
          archiveOutcome();
          schedule();
        },
        onend(job) {
          flush();
          notifyEnd(job);
        },
      });
      tracker = next;
      flush();
      if (o.reveal !== false) reveal();
      return next;
    }

    const show = (id, o = {}) => attach(id, Object.assign({}, o, { live: false }));

    async function run(path, body, o = {}) {
      try {
        const created = await api(path, { method: "POST", body: body === undefined ? {} : body });
        return attach(created, o);
      } catch (error) {
        fail(error);
        return null;
      }
    }

    async function resume(o = {}) {
      const base = o.base || baseOf();
      const before = tracker;
      const found = await list({ base, status: "queued,running", limit: 1 });
      if (!found.length) return null;
      // 查詢的這段時間裡，頁面已經自己接上別的任務（例如使用者剛按了執行）：
      // 以那個為準，不能被晚到的回應換掉。
      if (destroyed || tracker !== before) return null;
      attach(found[0], { base, reveal: false });
      return found[0];
    }

    async function stop() {
      if (!tracker) return;
      stopBtn.disabled = true;
      try {
        await tracker.stop();
      } catch (error) {
        fail(error);
      } finally {
        flush();
      }
    }

    async function reply(text, label) {
      if (!tracker || !tracker.job.ask || sending) return false;
      const body = String(text === undefined || text === null ? "" : text).trim();
      if (!body) {
        toast("請先輸入回覆", "warn");
        return false;
      }
      sending = true;
      const controls = Array.from(askEl.querySelectorAll("button, textarea"));
      controls.forEach((node) => { node.disabled = true; });
      try {
        await tracker.reply(tracker.job.ask.id, body);
        flush();
        segsEl.append(h("div", { class: "job-reply" }, label || body));
        pinned = true;
        toBottom();
        return true;
      } catch (error) {
        fail(error);
        // 通常是提問已過期（409）：同步後畫面會換成目前的狀態。
        if (tracker) tracker.sync().catch(() => {});
        return false;
      } finally {
        sending = false;
        controls.forEach((node) => { node.disabled = false; });
      }
    }

    function clear() {
      flush();
      segsEl.replaceChildren();
      segs = new Map();
      cappedNote = null;
      pinned = true;
    }

    function detach() {
      if (tracker) tracker.close();
      tracker = null;
      resetView();
      flush();
    }

    function destroy() {
      if (destroyed) return;
      if (tracker) tracker.close();
      tracker = null;
      destroyed = true;
      if (flushTimer) clearTimeout(flushTimer);
      if (elapsedTimer) clearInterval(elapsedTimer);
      if (idleTimer) clearTimeout(idleTimer);
      resizer.disconnect();
      el.remove();
    }

    /* ── 自動接上別處啟動的任務 ── */

    const tracking = () => tracker && tracker.conn !== "closed" && tracker.conn !== "gone";

    async function idleCheck() {
      if (destroyed) return;
      if (!tracking()) {
        try {
          const found = await list({ base: baseOf(), status: "queued,running", limit: 1 });
          if (!destroyed && !tracking() && found.length) attach(found[0], { reveal: false });
        } catch (_) {
          /* 伺服器暫時沒回應：下一輪再試 */
        }
      }
      if (!destroyed) idleTimer = setTimeout(idleCheck, idleMs);
    }

    drawLogButton();
    flush();
    if (opts.discover) idleCheck();

    return {
      el, attach, show, run, resume, stop, reply, clear, detach, destroy,
      job: () => (tracker ? tracker.job : null),
      tracker: () => tracker,
    };
  }

  FE.jobs = { panel, watch, list, apply_patch: applyPatch, blank, is_terminal: isTerminal };
})();
