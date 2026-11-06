/* fekit shell.js — 三欄外殼。介面見 docs/02_API合約.md 第 7 節。
 * 依賴 core.js，只加上 FE.shell；載入時不動 DOM，呼叫 FE.shell.mount() 才開始。 */
(function () {
  "use strict";

  const FE = window.FE;
  if (!FE) throw new Error("fekit：shell.js 要在 core.js 之後載入");
  if (FE.shell) {
    console.warn("fekit：shell.js 被載入了兩次，第二次已略過");
    return;
  }

  const { h, store } = FE;

  const DEFAULT_SIZES = {
    nav: { min: 140, max: 360, width: 200 },
    panel: { min: 260, max: 900, width: 380 },
  };
  const KEY_STEP = 16;
  const KEY_STEP_LARGE = 64;
  const HANDLE_WIDTH = 6;
  const BADGES = new Set(["busy", "ok", "warn", "err"]);

  let current = null;

  const resolveEl = (target) => (typeof target === "string" ? document.querySelector(target) : target);

  // store 裡的值可能被改壞或來自舊版，不是正常數字就用預設。
  function storedWidth(pane, fallback) {
    const value = store.get(`shell.w.${pane}`, fallback);
    return Number.isFinite(value) && value > 0 ? value : fallback;
  }

  function safeDecode(text) {
    try {
      return decodeURIComponent(text);
    } catch (_) {
      return text;
    }
  }

  // "#/items/%E5%A4%9C?x=1" → "items/夜"；不是 hash 連結回傳 null。
  function hashPath(hash) {
    if (typeof hash !== "string" || !hash.startsWith("#")) return null;
    return safeDecode(hash.replace(/^#\/?/, "").split("?")[0].replace(/\/+$/, ""));
  }

  function routeSnapshot() {
    const ctx = FE.current();
    if (ctx) return { hash: ctx.hash, page: ctx.page, parts: ctx.parts, params: ctx.params, args: ctx.args, query: ctx.query };
    return { hash: location.hash || "#/", page: null, parts: [], params: {}, args: [], query: {} };
  }

  function isActive(item, route) {
    if (item.external) return false;
    if (typeof item.active === "function") return !!item.active(route);
    if (item.page !== undefined && item.page !== null) {
      return (Array.isArray(item.page) ? item.page : [item.page]).includes(route.page);
    }
    const target = hashPath(item.href);
    return target !== null && target === hashPath(route.hash);
  }

  function mount(opts = {}) {
    if (current) throw new Error("FE.shell.mount()：一個頁面只能掛一次");
    const root = resolveEl(opts.root || document.body);
    if (!root) throw new Error(`FE.shell.mount()：找不到節點 ${String(opts.root)}`);

    const hasNav = opts.nav !== undefined && opts.nav !== null;
    const hasPanel = opts.panel !== undefined && opts.panel !== null;
    const panelLabel = opts.panel_label || "面板";
    const mainMin = opts.main_min !== undefined ? opts.main_min : 320;
    const narrowAt = opts.narrow_at !== undefined ? opts.narrow_at : 900;
    const slots = opts.slots || {};
    const sizes = {
      nav: Object.assign({}, DEFAULT_SIZES.nav, opts.sizes && opts.sizes.nav),
      panel: Object.assign({}, DEFAULT_SIZES.panel, opts.sizes && opts.sizes.panel),
    };

    // wanted 是使用者要的寬度（會記住）；實際寬度還要看視窗放不放得下。
    const state = {
      nav: { exists: hasNav, wanted: storedWidth("nav", sizes.nav.width), off: store.get("shell.off.nav", false) === true, drawer: false },
      panel: { exists: hasPanel, wanted: storedWidth("panel", sizes.panel.width), off: store.get("shell.off.panel", false) === true, drawer: false },
    };
    const panes = {};
    const handles = {};
    const toggles = {};

    /* ── 節點 ── */

    const crumbsEl = h("nav", { class: "crumbs shell-crumbs", "aria-label": "目前位置" });
    const viewEl = h("div", { class: "shell-view", id: "view" });
    const mainEl = h("main", { class: "split-pane split-pane-main shell-main" }, viewEl);
    const navEl = hasNav ? h("nav", { class: "nav", "aria-label": "導覽" }) : null;
    const panelEl = hasPanel ? h("div", { class: "shell-panel-body" }) : null;
    const scrim = h("div", { class: "shell-scrim", onclick: () => closeDrawers(true) });

    const makeToggle = (pane, text, label) => {
      toggles[pane] = h("button", {
        class: "btn btn-ghost btn-sm shell-toggle",
        type: "button",
        title: `顯示／隱藏${label}`,
        "aria-label": `顯示／隱藏${label}`,
        "aria-controls": `fe-shell-${pane}`,
        onclick: () => toggle(pane),
      }, text, h("span", { class: "shell-dot hidden", "aria-hidden": "true" }));
      return toggles[pane];
    };

    const makeHandle = (pane, label) => {
      handles[pane] = h("div", {
        class: "split-handle",
        role: "separator",
        tabindex: "0",
        title: "拖曳調整寬度；雙擊恢復預設",
        "aria-label": `調整${label}寬度`,
        "aria-orientation": "vertical",
        "aria-controls": `fe-shell-${pane}`,
        "aria-valuemin": String(sizes[pane].min),
        "aria-valuemax": String(sizes[pane].max),
      });
      wireHandle(pane, handles[pane]);
      return handles[pane];
    };

    function brandNode() {
      if (!opts.brand) return null;
      const brand = typeof opts.brand === "string" ? { label: opts.brand } : opts.brand;
      return h("a", { class: "shell-brand", href: brand.href || "#/" },
        brand.mark ? h("span", { class: "shell-seal", "aria-hidden": "true" }, brand.mark) : null,
        h("span", { class: "shell-brand-text" }, brand.label));
    }

    const top = h("header", { class: "shell-top" },
      hasNav ? makeToggle("nav", "☰", "導覽") : null,
      brandNode(),
      crumbsEl,
      h("div", { class: "grow" }),
      slots.top || null,
      hasPanel ? makeToggle("panel", panelLabel, panelLabel) : null);

    if (hasNav) {
      panes.nav = h("aside", { class: "split-pane split-pane-side shell-nav", id: "fe-shell-nav" },
        slots.nav_head || null, navEl, slots.nav_foot ? h("div", { class: "shell-nav-foot" }, slots.nav_foot) : null);
    }
    if (hasPanel) {
      panes.panel = h("aside", { class: "split-pane split-pane-side shell-panel", id: "fe-shell-panel", "aria-label": panelLabel }, panelEl);
    }

    const body = h("div", { class: "split shell-body" },
      hasNav ? panes.nav : null,
      hasNav ? makeHandle("nav", "導覽") : null,
      mainEl,
      hasPanel ? makeHandle("panel", panelLabel) : null,
      hasPanel ? panes.panel : null,
      scrim);
    const el = h("div", { class: "shell" }, top, body);

    /* ── 寬度 ── */

    // 左欄優先：它只先替右欄留最小寬度，右欄再用剩下的空間。
    function widths() {
      const total = el.clientWidth;
      const fit = (pane, room) => {
        const { min, max } = sizes[pane];
        const limit = total > 0 ? Math.min(max, room) : max;
        return Math.round(Math.max(min, Math.min(state[pane].wanted, limit)));
      };
      const shown = (pane) => state[pane].exists && !state[pane].off;
      const free = total - mainMin;
      const nav = fit("nav", free - HANDLE_WIDTH - (shown("panel") ? sizes.panel.min + HANDLE_WIDTH : 0));
      const panel = fit("panel", free - HANDLE_WIDTH - (shown("nav") ? nav + HANDLE_WIDTH : 0));
      return { nav, panel };
    }

    function applyLayout() {
      const narrow = isNarrow();
      el.classList.toggle("shell-narrow", narrow);
      let anyDrawer = false;
      const layout = widths();
      for (const pane of ["nav", "panel"]) {
        const info = state[pane];
        if (!info.exists) continue;
        const width = layout[pane];
        panes[pane].style.setProperty("--shell-w", `${width}px`);
        panes[pane].classList.toggle("split-collapsed", narrow ? !info.drawer : info.off);
        panes[pane].classList.toggle("shell-drawer-open", narrow && info.drawer);
        handles[pane].classList.toggle("split-collapsed", narrow || info.off);
        handles[pane].setAttribute("aria-valuenow", String(width));
        const open = narrow ? info.drawer : !info.off;
        toggles[pane].setAttribute("aria-expanded", String(open));
        anyDrawer = anyDrawer || (narrow && info.drawer);
      }
      scrim.classList.toggle("shell-scrim-on", anyDrawer);
      mainEl.inert = anyDrawer;
    }

    function setWidth(pane, value, persist) {
      const { min, max } = sizes[pane];
      state[pane].wanted = Math.round(Math.max(min, Math.min(max, value)));
      // 拖曳時實際寬度可能被視窗限制，記住的要是畫面上看到的值。
      state[pane].wanted = widths()[pane];
      applyLayout();
      if (persist) store.set(`shell.w.${pane}`, state[pane].wanted);
    }

    function wireHandle(pane, handle) {
      const direction = pane === "nav" ? 1 : -1;

      handle.addEventListener("pointerdown", (event) => {
        if (event.button !== 0) return;
        event.preventDefault();
        handle.focus({ preventScroll: true });
        const startX = event.clientX;
        const startWidth = widths()[pane];
        let finished = false;
        try {
          handle.setPointerCapture(event.pointerId);
        } catch (_) {
          /* 測試環境或指標已消失時會丟錯，仍然可以靠事件冒泡拖曳 */
        }
        handle.classList.add("dragging");
        document.body.classList.add("fe-dragging");

        const move = (e) => setWidth(pane, startWidth + direction * (e.clientX - startX), false);
        const end = () => {
          if (finished) return;
          finished = true;
          handle.classList.remove("dragging");
          document.body.classList.remove("fe-dragging");
          handle.removeEventListener("pointermove", move);
          handle.removeEventListener("pointerup", end);
          handle.removeEventListener("pointercancel", end);
          handle.removeEventListener("lostpointercapture", end);
          store.set(`shell.w.${pane}`, state[pane].wanted);
        };
        handle.addEventListener("pointermove", move);
        handle.addEventListener("pointerup", end);
        handle.addEventListener("pointercancel", end);
        handle.addEventListener("lostpointercapture", end);
      });

      handle.addEventListener("dblclick", () => {
        state[pane].wanted = sizes[pane].width;
        store.remove(`shell.w.${pane}`);
        applyLayout();
      });

      handle.addEventListener("keydown", (event) => {
        const now = widths()[pane];
        const step = event.shiftKey ? KEY_STEP_LARGE : KEY_STEP;
        let next = null;
        if (event.key === "ArrowRight") next = now + direction * step;
        else if (event.key === "ArrowLeft") next = now - direction * step;
        else if (event.key === "Home") next = sizes[pane].min;
        else if (event.key === "End") next = sizes[pane].max;
        else if (event.key === "Enter") {
          event.preventDefault();
          toggle(pane, false);
          if (toggles[pane]) toggles[pane].focus();
          return;
        } else return;
        event.preventDefault();
        setWidth(pane, next, true);
      });
    }

    /* ── 收合與抽屜 ── */

    const media = window.matchMedia(`(max-width: ${narrowAt}px)`);
    function isNarrow() {
      return media.matches;
    }

    function closeDrawers(restoreFocus) {
      let closed = null;
      for (const pane of ["nav", "panel"]) {
        if (state[pane].drawer) {
          state[pane].drawer = false;
          closed = pane;
        }
      }
      applyLayout();
      if (closed && restoreFocus && toggles[closed]) toggles[closed].focus();
    }

    function focusInto(pane) {
      // 面板裡可能有隱藏的按鈕，隱藏的節點拿不到焦點。
      const candidates = pane.querySelectorAll('a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])');
      const target = Array.from(candidates).find((node) => node.getClientRects().length > 0);
      if (target) {
        target.focus();
      } else {
        pane.setAttribute("tabindex", "-1");
        pane.focus();
      }
    }

    function toggle(pane, force) {
      const info = state[pane];
      if (!info || !info.exists) return false;
      if (isNarrow()) {
        const next = force === undefined ? !info.drawer : !!force;
        if (next === info.drawer) return next;
        const other = pane === "nav" ? "panel" : "nav";
        state[other].drawer = false;
        info.drawer = next;
        applyLayout();
        if (next) focusInto(panes[pane]);
        else if (toggles[pane]) toggles[pane].focus();
        return next;
      }
      const open = force === undefined ? info.off : !!force;
      info.off = !open;
      store.set(`shell.off.${pane}`, info.off);
      applyLayout();
      return open;
    }

    function isOpen(pane) {
      const info = state[pane];
      if (!info || !info.exists) return false;
      return isNarrow() ? info.drawer : !info.off;
    }

    function onKeydown(event) {
      if (event.key !== "Escape" || !isNarrow()) return;
      if (event.isComposing || event.keyCode === 229) return;
      if (!state.nav.drawer && !state.panel.drawer) return;
      event.preventDefault();
      closeDrawers(true);
    }

    /* ── 導覽 ── */

    let navConfig = opts.nav;
    let navSeq = 0;
    let navSignature = null;
    let navLinks = [];
    let lastHash = null;

    function drawNav(items, route) {
      const list = (items || []).flat(Infinity).filter(Boolean);
      const signature = JSON.stringify(list.map((item) => [item.group, item.label, item.href, item.icon, item.external]));
      if (signature !== navSignature) {
        navSignature = signature;
        navLinks = [];
        const nodes = list.map((item) => {
          if (item.group !== undefined) return h("div", { class: "nav-group" }, item.group);
          const link = h("a", {
            class: "nav-item",
            href: item.href,
            target: item.external ? "_blank" : null,
            rel: item.external ? "noopener" : null,
          }, item.icon ? h("span", { class: "nav-icon", "aria-hidden": "true" }, item.icon) : null, item.label);
          navLinks.push([item, link]);
          return link;
        });
        navEl.replaceChildren(...nodes);
      } else {
        // 項目沒變：物件可能是新的（active 函式要用新的），節點留著，焦點才不會跑掉。
        const fresh = list.filter((item) => item.group === undefined);
        navLinks = navLinks.map(([, link], index) => [fresh[index], link]);
      }
      for (const [item, link] of navLinks) {
        const active = isActive(item, route);
        link.classList.toggle("active", active);
        if (active) link.setAttribute("aria-current", "page");
        else link.removeAttribute("aria-current");
      }
    }

    function updateNav(route) {
      if (!hasNav) return;
      const seq = ++navSeq;
      const report = (error) => console.error("fekit：導覽設定函式失敗", error);
      try {
        const result = typeof navConfig === "function" ? navConfig(route) : navConfig;
        if (result && typeof result.then === "function") {
          result.then((items) => { if (seq === navSeq) drawNav(items, route); }, report);
        } else {
          drawNav(result, route);
        }
      } catch (error) {
        report(error);
      }
    }

    function onRoute(event) {
      const route = event.detail;
      updateNav(route);
      // FE.route() 重新載入同一頁（例如任務結束後）不能把使用者正在看的抽屜關掉。
      if (lastHash !== null && route.hash !== lastHash) closeDrawers(false);
      lastHash = route.hash;
    }

    /* ── 組裝 ── */

    const instance = {
      el,
      view_el: viewEl,
      crumbs_el: crumbsEl,
      nav_el: navEl,
      panel_el: panelEl,
      ready: Promise.resolve(),
      toggle,
      is_open: isOpen,
      is_narrow: isNarrow,
      width(pane, px) {
        if (!state[pane] || !state[pane].exists) return null;
        if (px !== undefined) setWidth(pane, px, true);
        return widths()[pane];
      },
      set_nav(items) {
        navConfig = items;
        updateNav(routeSnapshot());
      },
      refresh_nav() {
        updateNav(routeSnapshot());
      },
      badge(pane, value) {
        const button = toggles[pane];
        if (!button) return;
        const dot = button.querySelector(".shell-dot");
        dot.className = "shell-dot";
        if (BADGES.has(value)) dot.classList.add(`shell-dot-${value}`);
        else dot.classList.add("hidden");
      },
    };
    current = instance;

    root.append(el);
    applyLayout();
    if (hasPanel) {
      const content = typeof opts.panel === "function" ? opts.panel(panelEl, instance) : opts.panel;
      if (content && (content.nodeType || typeof content === "string")) panelEl.append(content);
    }

    media.addEventListener("change", () => {
      // 只在變寬時清抽屜：變窄的事件會晚一點才到，不能把剛打開的抽屜關掉。
      if (!media.matches) {
        state.nav.drawer = false;
        state.panel.drawer = false;
      }
      applyLayout();
    });
    new ResizeObserver(() => applyLayout()).observe(el);
    document.addEventListener("keydown", onKeydown);
    window.addEventListener("fe-route", onRoute);

    // 要先掛好 fe-route，第一次路由才標示得到目前頁面。
    if (opts.start !== false) {
      instance.ready = FE.start({ root: viewEl, crumbs: crumbsEl, home: opts.home || "home" });
    } else {
      updateNav(routeSnapshot());
    }
    return instance;
  }

  FE.shell = { mount, current: () => current };
})();
