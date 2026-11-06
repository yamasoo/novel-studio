/* fekit core.js — 核心工具。介面與合約見 docs/02_API合約.md。
 * 只掛 window.FE；載入時不動 DOM、不掛路由，呼叫 FE.start() 才開始。 */
(function () {
  "use strict";

  if (window.FE) {
    console.warn("fekit：core.js 被載入了兩次，第二次已略過");
    return;
  }

  /* ──────────────── DOM ──────────────── */

  const $ = (sel, el = document) => el.querySelector(sel);
  const $$ = (sel, el = document) => Array.from(el.querySelectorAll(sel));

  const SVG_NS = "http://www.w3.org/2000/svg";
  const PROP_KEYS = new Set(["checked", "disabled", "selected", "hidden", "multiple", "indeterminate", "muted"]);
  const URL_KEYS = new Set(["href", "src", "action", "formaction", "xlink:href", "data", "ping"]);
  const FORBIDDEN_KEYS = new Set(["innerhtml", "outerhtml", "srcdoc"]);   // 比對用小寫

  function unsafeUrl(value) {
    // 瀏覽器解析網址時會忽略控制字元與空白，比對前要先去掉（例如 "java\tscript:"）。
    const text = String(value).replace(/[\x00-\x20]/g, "").toLowerCase();
    return /^(javascript|vbscript):/.test(text) || text.startsWith("data:text/html");
  }

  function toNodes(kids) {
    const nodes = [];
    for (const kid of kids.flat(Infinity)) {
      if (kid === null || kid === undefined || kid === true || kid === false) continue;
      nodes.push(kid.nodeType ? kid : document.createTextNode(String(kid)));
    }
    return nodes;
  }

  function setStyle(el, value) {
    if (typeof value === "string") {
      el.setAttribute("style", value);
      return;
    }
    for (const [name, val] of Object.entries(value)) {
      if (val === null || val === undefined || val === false) continue;
      if (name.startsWith("--") || name.includes("-")) el.style.setProperty(name, String(val));
      else el.style[name] = val;
    }
  }

  function applyProps(el, props, isSvg) {
    let lateValue;
    for (const [key, value] of Object.entries(props)) {
      // HTML 的屬性名稱不分大小寫（setAttribute 會轉小寫），防護要比對小寫名稱，
      // 否則 HREF、ONclick 這類寫法會繞過。SVG 的屬性名稱有意義（viewBox），
      // 寫入時仍用原本的 key。
      const name = key.toLowerCase();
      if (FORBIDDEN_KEYS.has(name)) throw new TypeError(`h() 不支援 ${key}：請用子節點或 md.js`);
      if (name.startsWith("on") && name.length > 2) {
        if (value === null || value === undefined || value === false) continue;
        if (typeof value !== "function") throw new TypeError(`h() 的 ${key} 必須是函式`);
        el.addEventListener(name.slice(2), value);
        continue;
      }
      if (value === null || value === undefined) continue;
      if (name.startsWith("aria-")) {
        el.setAttribute(key, String(value));
        continue;
      }
      if (value === false && (isSvg || !PROP_KEYS.has(name))) continue;
      if (name === "class") {
        const text = Array.isArray(value) ? value.filter(Boolean).join(" ") : String(value);
        el.setAttribute("class", text);
      } else if (name === "style") {
        setStyle(el, value);
      } else if (name === "value" && !isSvg) {
        lateValue = value;
      } else if (PROP_KEYS.has(name) && !isSvg) {
        el[name] = !!value;
      } else if (URL_KEYS.has(name) && unsafeUrl(value)) {
        console.warn(`fekit：已略過不安全的 ${name}`, value);
      } else {
        el.setAttribute(key, value === true ? "" : String(value));
      }
    }
    return lateValue;
  }

  function isProps(value) {
    return value !== null && typeof value === "object" && !value.nodeType && !Array.isArray(value);
  }

  function build(el, props, kids, isSvg) {
    // props 可省略：h("p", "文字")、h("div", node)、h("ul", [li, li])
    const hasProps = props === null || props === undefined || isProps(props);
    const all = hasProps ? kids : [props, ...kids];
    const lateValue = hasProps && props ? applyProps(el, props, isSvg) : undefined;
    el.append(...toNodes(all));
    // select 要等 option 都放進去，value 才選得到。
    if (lateValue !== undefined) el.value = lateValue;
    return el;
  }

  const h = (tag, props, ...kids) => build(document.createElement(tag), props, kids, false);
  const svg = (tag, props, ...kids) => build(document.createElementNS(SVG_NS, tag), props, kids, true);

  /* ──────────────── 請求 ──────────────── */

  class ApiError extends Error {
    constructor(message, { status = 0, code = null, data = null, path = "" } = {}) {
      super(message);
      this.name = "ApiError";
      this.status = status;
      this.code = code;
      this.data = data;
      this.path = path;
    }
  }

  const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

  function metaContent(name) {
    const el = document.querySelector(`meta[name="${name}"]`);
    return el ? el.getAttribute("content") || "" : "";
  }

  function isSameOrigin(url) {
    try {
      return new URL(url, location.href).origin === location.origin;
    } catch (_) {
      return false;
    }
  }

  function withQuery(path, query) {
    if (!query) return path;
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(query)) {
      if (value === null || value === undefined) continue;
      if (Array.isArray(value)) value.forEach((item) => params.append(key, item));
      else params.append(key, value);
    }
    const text = params.toString();
    if (!text) return path;
    return path + (path.includes("?") ? "&" : "?") + text;
  }

  // 只有同來源的變更請求才帶權杖，避免把權杖送給別的網站。
  function securityHeaders(method, url) {
    const token = metaContent("fe-token");
    if (!token || SAFE_METHODS.has(method) || !isSameOrigin(url)) return {};
    return { "X-FE-Token": token };
  }

  function isRawBody(body) {
    return body instanceof FormData || body instanceof Blob || body instanceof ArrayBuffer ||
      ArrayBuffer.isView(body) || body instanceof URLSearchParams;
  }

  // api() 與 upload() 共用：把回應轉成回傳值，失敗時丟 ApiError。
  function parseResponse(status, text, contentType, path) {
    const ok = status >= 200 && status < 300;
    const isJson = /\bjson\b/i.test(contentType || "");
    let data = null;
    let badJson = false;
    if (isJson && text) {
      try {
        data = JSON.parse(text);
      } catch (_) {
        badJson = true;
      }
    }
    if (ok) {
      if (badJson) throw new ApiError("伺服器回應的格式不正確", { status, code: "bad_json", path });
      if (!text) return null;
      return isJson ? data : text;
    }
    const body = data && typeof data === "object" ? data : null;
    let message = `請求失敗（HTTP ${status}）`;
    if (body && typeof body.error === "string" && body.error) message = body.error;
    else if (body && typeof body.detail === "string" && body.detail) message = body.detail;
    throw new ApiError(message, { status, code: body && body.code ? body.code : null, data: body, path });
  }

  const NETWORK_MESSAGE = "無法連線到伺服器，請確認程式還在執行";

  function abortError() {
    return new DOMException("請求已中止", "AbortError");
  }

  async function api(path, opts = {}) {
    const hasBody = opts.body !== undefined;
    const method = (opts.method || (hasBody ? "POST" : "GET")).toUpperCase();
    const url = withQuery(path, opts.query);
    const headers = new Headers(opts.headers || {});
    if (!headers.has("Accept")) headers.set("Accept", "application/json");
    for (const [key, value] of Object.entries(securityHeaders(method, url))) headers.set(key, value);

    const init = { method, headers };
    if (hasBody) {
      if (isRawBody(opts.body)) {
        init.body = opts.body;
      } else {
        init.body = JSON.stringify(opts.body);
        if (!headers.has("Content-Type")) headers.set("Content-Type", "application/json");
      }
    }

    // 逾時與外部 signal 共用一個 AbortController，才分得出是哪一種中止。
    const ctrl = new AbortController();
    let timedOut = false;
    const onAbort = () => ctrl.abort();
    if (opts.signal) {
      if (opts.signal.aborted) throw abortError();
      opts.signal.addEventListener("abort", onAbort, { once: true });
    }
    const timer = opts.timeout ? setTimeout(() => { timedOut = true; ctrl.abort(); }, opts.timeout) : null;
    init.signal = ctrl.signal;

    try {
      const response = await fetch(url, init);
      const text = await response.text();
      return parseResponse(response.status, text, response.headers.get("Content-Type"), path);
    } catch (error) {
      if (error instanceof ApiError) throw error;
      if (timedOut) throw new ApiError("請求逾時，請稍後再試", { status: 0, code: "timeout", path });
      if (error && error.name === "AbortError") throw error;
      throw new ApiError(NETWORK_MESSAGE, { status: 0, code: "network", path });
    } finally {
      if (timer) clearTimeout(timer);
      if (opts.signal) opts.signal.removeEventListener("abort", onAbort);
    }
  }

  // fetch 拿不到上傳進度，所以這裡用 XMLHttpRequest。
  function upload(path, file, opts = {}) {
    return new Promise((resolve, reject) => {
      if (opts.signal && opts.signal.aborted) {
        reject(abortError());
        return;
      }
      const method = (opts.method || "POST").toUpperCase();
      const url = withQuery(path, opts.query);
      const xhr = new XMLHttpRequest();
      xhr.open(method, url);
      const name = opts.name !== undefined ? opts.name : file.name || "";
      const headers = Object.assign(
        { Accept: "application/json", "Content-Type": file.type || "application/octet-stream", "X-Filename": encodeURIComponent(name) },
        opts.headers || {},
        securityHeaders(method, url)
      );
      for (const [key, value] of Object.entries(headers)) xhr.setRequestHeader(key, value);

      const onAbort = () => xhr.abort();
      const cleanup = () => { if (opts.signal) opts.signal.removeEventListener("abort", onAbort); };
      if (opts.signal) opts.signal.addEventListener("abort", onAbort, { once: true });

      if (opts.onprogress) {
        xhr.upload.addEventListener("progress", (e) => {
          const total = e.lengthComputable ? e.total : file.size;
          opts.onprogress(total ? e.loaded / total : 0, e.loaded, total);
        });
      }
      xhr.addEventListener("load", () => {
        cleanup();
        try {
          resolve(parseResponse(xhr.status, xhr.responseText, xhr.getResponseHeader("Content-Type"), path));
        } catch (error) {
          reject(error);
        }
      });
      xhr.addEventListener("error", () => {
        cleanup();
        reject(new ApiError(NETWORK_MESSAGE, { status: 0, code: "network", path }));
      });
      xhr.addEventListener("abort", () => {
        cleanup();
        reject(abortError());
      });
      xhr.send(file);
    });
  }

  /* ──────────────── toast、fail ──────────────── */

  const TOAST_MAX = 5;
  let toastHost = null;

  function toast(message, kind, opts = {}) {
    if (!toastHost || !toastHost.isConnected) {
      toastHost = h("div", { class: "toast-host", "aria-live": "polite" });
      document.body.append(toastHost);
    }
    const duration = opts.duration !== undefined ? opts.duration : (kind === "err" ? 7000 : 3000);
    const el = h("div", { class: ["toast", kind && `toast-${kind}`], role: kind === "err" ? "alert" : "status" }, message);
    let timer = null;
    const close = () => {
      if (timer) clearTimeout(timer);
      el.remove();
    };
    el.addEventListener("click", close);
    toastHost.append(el);
    while (toastHost.children.length > TOAST_MAX) toastHost.firstElementChild.remove();
    if (duration > 0) timer = setTimeout(close, duration);
    return close;
  }

  const isAbort = (error) => !!error && error.name === "AbortError";

  function fail(error) {
    if (isAbort(error)) return;
    if (error instanceof Error && !(error instanceof ApiError)) console.error(error);
    toast((error && error.message) || String(error), "err");
  }

  /* ──────────────── modal、confirm ──────────────── */

  const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
  const modalStack = [];
  let modalSeq = 0;

  const focusablesIn = (el) => $$(FOCUSABLE, el).filter((node) => node.getClientRects().length > 0);

  function onModalKeydown(event) {
    const top = modalStack[modalStack.length - 1];
    if (!top) return;
    if (event.key === "Escape") {
      // 輸入法組字中的 Esc 是取消組字，不是關閉對話框。
      if (event.isComposing || event.keyCode === 229) return;
      if (top.dismissible) {
        event.preventDefault();
        event.stopPropagation();
        top.close();
      }
    } else if (event.key === "Tab") {
      const list = focusablesIn(top.el);
      if (!list.length) {
        event.preventDefault();
        top.el.focus();
        return;
      }
      const first = list[0];
      const last = list[list.length - 1];
      const active = document.activeElement;
      if (!top.el.contains(active)) {
        event.preventDefault();
        first.focus();
      } else if (event.shiftKey && (active === first || active === top.el)) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      }
    }
  }

  function modal(input) {
    const opts = isProps(input) ? input : { body: input };
    const dismissible = opts.dismissible !== false;
    const previous = document.activeElement;
    let closed = false;
    let settle;
    const closedPromise = new Promise((resolve) => { settle = resolve; });

    const close = (value) => {
      if (closed) return;
      closed = true;
      const index = modalStack.indexOf(entry);
      if (index >= 0) modalStack.splice(index, 1);
      if (!modalStack.length) document.removeEventListener("keydown", onModalKeydown, true);
      backdrop.remove();
      if (previous && previous.isConnected && typeof previous.focus === "function") previous.focus();
      if (opts.onclose) opts.onclose(value);
      settle(value);
    };

    const resolveSlot = (slot) => (typeof slot === "function" ? slot(close) : slot);
    const titleId = `fe-modal-title-${++modalSeq}`;
    const head = opts.title !== undefined && opts.title !== null
      ? h("div", { class: "modal-head", id: titleId }, opts.title) : null;
    const foot = opts.foot !== undefined && opts.foot !== null
      ? h("div", { class: "modal-foot" }, resolveSlot(opts.foot)) : null;
    const body = h("div", { class: "modal-body" }, resolveSlot(opts.body));
    const box = h("div", {
      class: ["modal", opts.wide && "modal-wide"],
      role: "dialog",
      "aria-modal": "true",
      "aria-labelledby": head ? titleId : null,
      tabindex: "-1",
    }, head, body, foot);
    const backdrop = h("div", { class: "modal-backdrop" }, box);

    // 要在背景按下、也在背景放開才算點背景；從輸入框拖曳選字到外面放開不能關閉。
    let pressedOnBackdrop = false;
    backdrop.addEventListener("mousedown", (e) => { pressedOnBackdrop = e.target === backdrop; });
    backdrop.addEventListener("click", (e) => {
      if (dismissible && pressedOnBackdrop && e.target === backdrop) close();
      pressedOnBackdrop = false;
    });

    const entry = { el: box, close: () => close(), dismissible };
    if (!modalStack.length) document.addEventListener("keydown", onModalKeydown, true);
    modalStack.push(entry);
    document.body.append(backdrop);

    const target = $("[data-autofocus]", box) || focusablesIn(body)[0] || (foot && focusablesIn(foot)[0]) || box;
    target.focus();

    close.closed = closedPromise;
    close.el = box;
    return close;
  }

  modal.close_all = () => {
    for (const entry of modalStack.slice().reverse()) entry.close();
  };

  function confirmDialog(message, opts = {}) {
    const close = modal({
      title: opts.title !== undefined ? opts.title : "請確認",
      body: h("div", { style: "white-space:pre-wrap" }, message),
      foot: (done) => [
        h("button", { class: "btn", type: "button", "data-autofocus": opts.danger ? "" : null, onclick: () => done(false) }, opts.cancel || "取消"),
        h("button", {
          class: ["btn", opts.danger ? "btn-danger" : "btn-primary"],
          type: "button",
          "data-autofocus": opts.danger ? null : "",
          onclick: () => done(true),
        }, opts.ok || "確定"),
      ],
    });
    return close.closed.then((value) => value === true);
  }

  /* ──────────────── store ──────────────── */

  const memoryStore = new Map();

  function storeKey(key) {
    return `${metaContent("fe-app") || "fe"}.${key}`;
  }

  const store = {
    get(key, fallback) {
      const full = storeKey(key);
      let raw = null;
      try {
        raw = window.localStorage.getItem(full);
      } catch (_) {
        raw = null;
      }
      if (raw === null && memoryStore.has(full)) raw = memoryStore.get(full);
      if (raw === null) return fallback;
      try {
        return JSON.parse(raw);
      } catch (_) {
        return fallback;
      }
    },
    set(key, value) {
      if (value === undefined) {
        store.remove(key);
        return true;
      }
      const full = storeKey(key);
      const raw = JSON.stringify(value);
      try {
        window.localStorage.setItem(full, raw);
        memoryStore.delete(full);
        return true;
      } catch (_) {
        memoryStore.set(full, raw);
        return false;
      }
    },
    remove(key) {
      const full = storeKey(key);
      memoryStore.delete(full);
      try {
        window.localStorage.removeItem(full);
      } catch (_) {
        /* localStorage 不可用，記憶體的部分已經刪了 */
      }
    },
  };

  /* ──────────────── dirty 防呆 ──────────────── */

  let dirtyFlag = false;
  let dirtyAsking = null;

  function onBeforeUnload(event) {
    event.preventDefault();
    event.returnValue = "";
  }

  const dirty = {
    message: "有尚未存檔的修改，確定要離開嗎？",
    set(value = true) {
      const next = !!value;
      if (next === dirtyFlag) return;
      dirtyFlag = next;
      // 只有未存檔時才掛，平常掛著 beforeunload 會讓瀏覽器停用往返快取。
      if (next) window.addEventListener("beforeunload", onBeforeUnload);
      else window.removeEventListener("beforeunload", onBeforeUnload);
    },
    is: () => dirtyFlag,
    confirm() {
      if (!dirtyFlag) return Promise.resolve(true);
      if (dirtyAsking) return dirtyAsking;
      dirtyAsking = confirmDialog(dirty.message, {
        title: "尚未存檔",
        ok: "放棄修改並離開",
        cancel: "留在這一頁",
        danger: true,
      }).then((ok) => {
        dirtyAsking = null;
        if (ok) dirty.set(false);
        return ok;
      });
      return dirtyAsking;
    },
  };

  /* ──────────────── 路由 ──────────────── */

  // 不繼承 Object.prototype：#/constructor、#/__proto__ 不能比對到內建成員。
  const PAGES = Object.create(null);
  const LOADING_DELAY_MS = 120;

  const router = {
    started: false,
    root: null,
    crumbs: null,
    home: "home",
    hash: "#/",
    seq: 0,
    ctrl: null,
    ctx: null,
    pendingTarget: null,
  };

  const normHash = (hash) => (hash && hash !== "#" ? hash : "#/");

  function toHash(input) {
    const text = String(input);
    if (text.startsWith("#")) return normHash(text);
    return `#/${text.replace(/^\/+/, "")}`;
  }

  function resolveEl(target) {
    return typeof target === "string" ? $(target) : target || null;
  }

  function decodePart(text) {
    try {
      return decodeURIComponent(text);
    } catch (_) {
      return text;
    }
  }

  function parseHash(hash) {
    const body = hash.replace(/^#\/?/, "");
    const mark = body.indexOf("?");
    const path = mark >= 0 ? body.slice(0, mark) : body;
    const search = mark >= 0 ? body.slice(mark + 1) : "";
    return {
      parts: path.split("/").filter(Boolean).map(decodePart),
      query: Object.fromEntries(new URLSearchParams(search)),
    };
  }

  function matchPage(parts) {
    let best = null;
    const wanted = parts.length ? parts : [router.home];
    for (const key of Object.keys(PAGES)) {
      if (key === "not_found") continue;
      const segs = key.split("/").filter(Boolean);
      if (!segs.length || segs.length > wanted.length) continue;
      const params = {};
      let fixed = 0;
      let ok = true;
      for (let i = 0; i < segs.length; i += 1) {
        if (segs[i].startsWith(":")) {
          params[segs[i].slice(1)] = wanted[i];
        } else if (segs[i] === wanted[i]) {
          fixed += 1;
        } else {
          ok = false;
          break;
        }
      }
      if (!ok) continue;
      const better = !best || segs.length > best.size || (segs.length === best.size && fixed > best.fixed);
      if (better) best = { key, params, size: segs.length, fixed, args: wanted.slice(segs.length) };
    }
    return best;
  }

  function hashOf(...input) {
    const query = input.length && isProps(input[input.length - 1]) ? input.pop() : null;
    const path = input.map((part) => encodeURIComponent(String(part))).join("/");
    const search = query ? withQuery("", query).replace(/^\?/, "") : "";
    return `#/${path}${search ? `?${search}` : ""}`;
  }

  function view(...nodes) {
    if (!router.root) throw new Error("FE.view()：請先呼叫 FE.start()，或頁面裡的主區節點還不存在");
    router.root.replaceChildren(...toNodes(nodes));
  }

  function crumbs(items, target) {
    const el = target ? resolveEl(target) : router.crumbs;
    if (!el) return;
    el.classList.add("crumbs");
    const list = items || [];
    const nodes = [];
    list.forEach((item, index) => {
      if (index) nodes.push(h("span", { class: "sep" }));
      if (index === list.length - 1) nodes.push(h("span", { class: "cur" }, item.label));
      else if (item.href) nodes.push(h("a", { href: item.href }, item.label));
      else nodes.push(h("span", {}, item.label));
    });
    el.replaceChildren(...nodes);
  }

  // 捲回頂端：捲主區所在的捲動容器；主區不在捲動容器裡才捲整個視窗。
  function resetScroll(root) {
    for (let node = root; node && node !== document.body; node = node.parentElement) {
      const overflow = getComputedStyle(node).overflowY;
      if (overflow === "auto" || overflow === "scroll") {
        node.scrollTop = 0;
        return;
      }
    }
    window.scrollTo(0, 0);
  }

  function errorView(error, ctx) {
    const message = (error && error.message) || String(error);
    return h("div", { class: "stack" },
      h("div", { class: "alert alert-err" }, `這一頁載入失敗：${message}`),
      h("div", { class: "row" },
        h("button", { class: "btn", type: "button", onclick: () => { if (ctx.active()) route(); } }, "重試"),
        h("a", { class: "btn btn-ghost", href: "#/" }, "回首頁")));
  }

  function notFoundView() {
    return h("div", { class: "empty" }, "找不到這個頁面。", " ", h("a", { href: "#/" }, "回首頁"));
  }

  async function render(hash) {
    if (router.ctrl) router.ctrl.abort();
    const ctrl = new AbortController();
    const seq = ++router.seq;
    const hashChanged = hash !== router.hash;
    router.ctrl = ctrl;
    router.hash = hash;
    dirty.set(false);
    modal.close_all();
    crumbs([]);

    const { parts, query } = parseHash(hash);
    const found = matchPage(parts);
    const root = router.root;
    const before = root.firstChild;
    let rendered = false;
    const untouched = () => !rendered && root.firstChild === before;

    const ctx = {
      page: found ? found.key : "not_found",
      params: found ? found.params : {},
      args: found ? found.args : [],
      parts,
      query,
      hash,
      signal: ctrl.signal,
      active: () => seq === router.seq,
      view(...nodes) {
        if (!ctx.active()) return;
        rendered = true;
        view(...nodes);
        if (hashChanged) resetScroll(root);
      },
      crumbs(items) {
        if (ctx.active()) crumbs(items);
      },
    };
    router.ctx = ctx;

    window.dispatchEvent(new CustomEvent("fe-route", {
      detail: { hash, page: ctx.page, parts, params: ctx.params, args: ctx.args, query },
    }));

    // 資料很快回來時不要閃「載入中」；比對 firstChild 是因為舊頁面可能自己改主區。
    const loadingTimer = setTimeout(() => {
      if (ctx.active() && untouched()) root.replaceChildren(h("p", { class: "muted" }, "載入中…"));
    }, LOADING_DELAY_MS);

    try {
      const handler = found ? PAGES[found.key] : PAGES.not_found;
      if (handler) await handler(ctx);
      else ctx.view(notFoundView());
      if (ctx.active() && untouched()) view();
    } catch (error) {
      if (ctx.active() && !isAbort(error)) {
        console.error(error);
        ctx.view(errorView(error, ctx));
      }
    } finally {
      clearTimeout(loadingTimer);
    }
  }

  function route() {
    if (!router.started) throw new Error("FE.route()：請先呼叫 FE.start()");
    return render(router.hash);
  }

  function setUrlHash(hash) {
    // replaceState 不會觸發 hashchange，也不會多一筆歷史紀錄。
    history.replaceState(history.state, "", location.pathname + location.search + hash);
  }

  function onHashChange() {
    const target = normHash(location.hash);
    if (target === router.hash) return;
    if (!dirtyFlag && router.pendingTarget === null) {
      render(target);
      return;
    }
    // 導頁已經發生，先把網址改回來，等使用者決定。詢問中再導頁只記最後的目的地。
    setUrlHash(router.hash);
    const asking = router.pendingTarget !== null;
    router.pendingTarget = target;
    if (asking) return;
    dirty.confirm().then((ok) => {
      const finalTarget = router.pendingTarget;
      router.pendingTarget = null;
      if (ok) {
        setUrlHash(finalTarget);
        render(finalTarget);
      }
    });
  }

  async function go(input) {
    const target = toHash(input);
    if (target !== normHash(location.hash)) {
      location.hash = target;
      return;
    }
    if (router.started && await dirty.confirm()) await route();
  }

  function start(opts = {}) {
    const root = resolveEl(opts.root || "#view");
    if (!root) throw new Error(`FE.start()：找不到主區節點 ${String(opts.root || "#view")}`);
    router.root = root;
    if (opts.crumbs !== undefined) router.crumbs = resolveEl(opts.crumbs);
    if (opts.home) router.home = opts.home;
    if (!router.started) {
      router.started = true;
      window.addEventListener("hashchange", onHashChange);
    }
    return render(normHash(location.hash));
  }

  /* ──────────────── 匯出 ──────────────── */

  window.FE = {
    version: "0.0.1",
    $, $$, h, svg,
    api, upload, ApiError,
    toast, fail, modal, confirm: confirmDialog,
    store, dirty,
    PAGES, start, go, route, view, crumbs,
    hash: hashOf,
    current: () => router.ctx,
  };
})();
