/* 和田三造《配色總鑑》與 fekit 配色模板事典（純 DOM，零外部相依） */
(function () {
  "use strict";

  const BUILTIN_THEMES = [
    {
      id: "fekit-paper",
      name: "書卷朱紅",
      subtitle: "fekit 預設 · 鳥之子紙 × 朱紅 × 靛藍 × 松綠",
      scheme: "light",
      source: "fekit",
      swatches: ["#f6f2ea", "#8a3b2e", "#2f5a7a", "#3f6b3a"],
      tokens: {
        bg: "#f6f2ea", "bg-elev": "#fffdf8", "bg-sunken": "#ede7da",
        fg: "#2b2620", "fg-muted": "#6e655a", "fg-faint": "#9a9084",
        line: "#ddd4c4", "line-strong": "#c4b8a3",
        accent: "#8a3b2e", "accent-hover": "#722f24", "accent-soft": "#f1dfd9", "on-accent": "#fffdf8",
        info: "#2f5a7a", "info-soft": "#d9e6ef",
        ok: "#3f6b3a", "ok-soft": "#dfeadb",
        warn: "#8a6410", "warn-soft": "#f3e8c8",
        err: "#a02a2a", "err-soft": "#f4d9d6",
      },
    },
    {
      id: "fekit-ink",
      name: "暖墨深紙",
      subtitle: "fekit 深色 · 墨底 × 珊瑚朱 × 淺靛 × 若竹",
      scheme: "dark",
      source: "fekit",
      swatches: ["#1c1915", "#d9826f", "#86b6d8", "#8fc287"],
      tokens: {
        bg: "#1c1915", "bg-elev": "#26221c", "bg-sunken": "#15130f",
        fg: "#ece5d8", "fg-muted": "#b0a696", "fg-faint": "#857b6d",
        line: "#3a342b", "line-strong": "#52493c",
        accent: "#d9826f", "accent-hover": "#e89886", "accent-soft": "#3d2620", "on-accent": "#1c1915",
        info: "#86b6d8", "info-soft": "#1c2c38",
        ok: "#8fc287", "ok-soft": "#223020",
        warn: "#e0b95c", "warn-soft": "#382d12",
        err: "#ee8d86", "err-soft": "#3d1f1d",
      },
    },
    {
      id: "wada-suo",
      name: "白練與蘇芳",
      subtitle: "和田三造 · 白練 × 蘇芳 × 淺蔥 × 常磐綠",
      scheme: "light",
      source: "Sanzo Wada",
      swatches: ["#f5f1e8", "#8e354a", "#336e7b", "#3b6e52"],
      tokens: {
        bg: "#f5f1e8", "bg-elev": "#fdfbf7", "bg-sunken": "#eae3d5",
        fg: "#2c2426", "fg-muted": "#6d6064", "fg-faint": "#978a8e",
        line: "#dfd6c8", "line-strong": "#c7baa8",
        accent: "#8e354a", "accent-hover": "#74283a", "accent-soft": "#f2dce1", "on-accent": "#fffdf9",
        info: "#336e7b", "info-soft": "#d7e8ec",
        ok: "#3b6e52", "ok-soft": "#daeae0",
        warn: "#9c6d1b", "warn-soft": "#f4e8ca",
        err: "#a63038", "err-soft": "#f5dad9",
      },
    },
    {
      id: "wada-gunjo",
      name: "鳥之子與群青",
      subtitle: "和田三造 · 鳥之子 × 群青 × 綠青 × 鶸茶",
      scheme: "light",
      source: "Sanzo Wada",
      swatches: ["#f7f0e2", "#2c4f8c", "#3d7c68", "#7b6b28"],
      tokens: {
        bg: "#f7f0e2", "bg-elev": "#fffcf5", "bg-sunken": "#ece2ce",
        fg: "#24262e", "fg-muted": "#5f6370", "fg-faint": "#8c8f99",
        line: "#ded3bd", "line-strong": "#c4b69a",
        accent: "#2c4f8c", "accent-hover": "#213d6e", "accent-soft": "#dbe4f3", "on-accent": "#fffdf8",
        info: "#3d7c68", "info-soft": "#d8ebe5",
        ok: "#7b6b28", "ok-soft": "#eee8cc",
        warn: "#a36324", "warn-soft": "#f5e3cf",
        err: "#a3332f", "err-soft": "#f4dada",
      },
    },
    {
      id: "wada-rikyu",
      name: "利休鼠與煉瓦",
      subtitle: "和田三造 · 利休紙 × 煉瓦 × 藍鐵 × 松葉",
      scheme: "light",
      source: "Sanzo Wada",
      swatches: ["#eff0ea", "#a84a32", "#385566", "#4c6b45"],
      tokens: {
        bg: "#eff0ea", "bg-elev": "#fafbf7", "bg-sunken": "#e2e4db",
        fg: "#272a25", "fg-muted": "#61665d", "fg-faint": "#8a9085",
        line: "#d3d6ca", "line-strong": "#b8bdb0",
        accent: "#a84a32", "accent-hover": "#8b3b26", "accent-soft": "#f3dfd9", "on-accent": "#fffdf9",
        info: "#385566", "info-soft": "#dae4ea",
        ok: "#4c6b45", "ok-soft": "#dfeadd",
        warn: "#946d1e", "warn-soft": "#f2e8cc",
        err: "#a8332b", "err-soft": "#f4dad8",
      },
    },
    {
      id: "wada-sakura",
      name: "櫻鼠與葡萄茶",
      subtitle: "和田三造 · 櫻鼠 × 葡萄茶 × 花淺蔥 × 柳茶",
      scheme: "light",
      source: "Sanzo Wada",
      swatches: ["#f6f0f0", "#7a3e54", "#3e6d82", "#667346"],
      tokens: {
        bg: "#f6f0f0", "bg-elev": "#fffbfb", "bg-sunken": "#ebe1e2",
        fg: "#2c2427", "fg-muted": "#6d6065", "fg-faint": "#998c91",
        line: "#dfd1d3", "line-strong": "#c6b4b7",
        accent: "#7a3e54", "accent-hover": "#612f41", "accent-soft": "#eedde3", "on-accent": "#fffdfd",
        info: "#3e6d82", "info-soft": "#dae8ee",
        ok: "#667346", "ok-soft": "#e6eadb",
        warn: "#9c6d24", "warn-soft": "#f4e8d0",
        err: "#a8323e", "err-soft": "#f5d9dc",
      },
    },
    {
      id: "wada-chitose",
      name: "薄卵與千歲綠",
      subtitle: "和田三造 · 薄卵 × 千歲綠 × 紺藍 × 柿紅",
      scheme: "light",
      source: "Sanzo Wada",
      swatches: ["#f7f3e3", "#2f5d46", "#2f4b78", "#b35432"],
      tokens: {
        bg: "#f7f3e3", "bg-elev": "#fffdf5", "bg-sunken": "#ebe5ce",
        fg: "#252924", "fg-muted": "#5e655c", "fg-faint": "#8a9187",
        line: "#ded6bc", "line-strong": "#c4ba9b",
        accent: "#2f5d46", "accent-hover": "#234735", "accent-soft": "#d7e8df", "on-accent": "#fffdf8",
        info: "#2f4b78", "info-soft": "#dbe3f0",
        ok: "#b35432", "ok-soft": "#f4dfd7",
        warn: "#946b17", "warn-soft": "#f3e7c6",
        err: "#a62e2e", "err-soft": "#f4d8d8",
      },
    },
    {
      id: "wada-koiai",
      name: "濃藍與金茶",
      subtitle: "和田三造 · 濃藍 × 金茶 × 白綠 × 薄紅梅",
      scheme: "dark",
      source: "Sanzo Wada",
      swatches: ["#171f2b", "#d99b43", "#84bfa4", "#d9848f"],
      tokens: {
        bg: "#171f2b", "bg-elev": "#202b3b", "bg-sunken": "#111720",
        fg: "#e9edf2", "fg-muted": "#a3b0c2", "fg-faint": "#75849a",
        line: "#2f3d52", "line-strong": "#445670",
        accent: "#d99b43", "accent-hover": "#e6ae5c", "accent-soft": "#3a2e1b", "on-accent": "#171f2b",
        info: "#84bfa4", "info-soft": "#1b3329",
        ok: "#d9848f", "ok-soft": "#3a2227",
        warn: "#e5c063", "warn-soft": "#383018",
        err: "#f07c7c", "err-soft": "#3e2022",
      },
    },
    {
      id: "wada-tetsuonando",
      name: "鐵御納戶與珊瑚",
      subtitle: "和田三造 · 鐵御納戶 × 珊瑚 × 若草 × 淡藤",
      scheme: "dark",
      source: "Sanzo Wada",
      swatches: ["#182426", "#e07b67", "#93c47d", "#a49cd6"],
      tokens: {
        bg: "#182426", "bg-elev": "#213033", "bg-sunken": "#121b1d",
        fg: "#e7efef", "fg-muted": "#9fb4b6", "fg-faint": "#72898c",
        line: "#2f4347", "line-strong": "#435d62",
        accent: "#e07b67", "accent-hover": "#eb917f", "accent-soft": "#3d2520", "on-accent": "#182426",
        info: "#a49cd6", "info-soft": "#28253d",
        ok: "#93c47d", "ok-soft": "#22331e",
        warn: "#e0bd60", "warn-soft": "#383017",
        err: "#ef8383", "err-soft": "#3d2020",
      },
    },
    {
      id: "wada-kuriume",
      name: "栗梅與白群",
      subtitle: "和田三造 · 栗梅 × 鴇色 × 白群 × 刈安",
      scheme: "dark",
      source: "Sanzo Wada",
      swatches: ["#21191a", "#de8c98", "#7cb8cf", "#d8be66"],
      tokens: {
        bg: "#21191a", "bg-elev": "#2c2224", "bg-sunken": "#181213",
        fg: "#f0e7e8", "fg-muted": "#b8a5a8", "fg-faint": "#8a767a",
        line: "#423336", "line-strong": "#5b484c",
        accent: "#de8c98", "accent-hover": "#e8a2ac", "accent-soft": "#3e2529", "on-accent": "#21191a",
        info: "#7cb8cf", "info-soft": "#1b2f38",
        ok: "#d8be66", "ok-soft": "#363018",
        warn: "#e6b35a", "warn-soft": "#3a2c15",
        err: "#f08181", "err-soft": "#402020",
      },
    },
  ];

  const STORE_ID = "t2x.theme_id";
  const STORE_CUSTOM = "t2x.custom_themes";
  let currentId = "";
  let triggerBtn = null;

  function injectStyle() {
    if (document.getElementById("t2x-theme-css")) return;
    const st = document.createElement("style");
    st.id = "t2x-theme-css";
    st.textContent = [
      ".t2x-dots{display:inline-flex;align-items:center;gap:3px;margin-right:4px;vertical-align:middle}",
      ".t2x-dots i{width:8px;height:8px;border-radius:50%;display:inline-block;border:1px solid rgba(128,128,128,.35)}",
      ".t2x-tgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:10px;margin-top:10px;max-height:46vh;overflow-y:auto;padding:2px}",
      ".t2x-tcard{border:1px solid var(--line);border-radius:10px;overflow:hidden;background:var(--bg);cursor:pointer;display:flex;flex-direction:column;transition:border-color .12s,transform .12s}",
      ".t2x-tcard:hover{border-color:var(--accent);transform:translateY(-1px)}",
      ".t2x-tcard.on{border:2px solid var(--accent);box-shadow:0 0 0 2px var(--accent-soft)}",
      ".t2x-tstrip{display:grid;grid-template-columns:1.4fr 1fr 1fr 1fr;height:28px;width:100%}",
      ".t2x-tmeta{padding:8px 10px;display:flex;flex-direction:column;gap:3px}",
      ".t2x-tmeta-top{display:flex;align-items:center;justify-content:space-between;gap:6px}",
      ".t2x-tsub{font-size:11.5px;color:var(--fg-muted);line-height:1.35}",
      ".t2x-cform{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:8px;margin-top:10px;align-items:end}",
      ".t2x-cform label{display:flex;flex-direction:column;gap:3px;font-size:12px;color:var(--fg-muted)}",
      ".t2x-cform input[type=color]{width:100%;height:30px;padding:2px;border-radius:6px;border:1px solid var(--line-strong);background:var(--bg);cursor:pointer}",
    ].join("\n");
    document.head.appendChild(st);
  }

  function hexToRgb(hex) {
    const m = /^#?([0-9a-f]{6})$/i.exec(String(hex || "").trim());
    if (!m) return [128, 128, 128];
    const v = parseInt(m[1], 16);
    return [(v >> 16) & 255, (v >> 8) & 255, v & 255];
  }
  function mixHex(a, b, ratio) {
    const [r1, g1, b1] = hexToRgb(a);
    const [r2, g2, b2] = hexToRgb(b);
    const p = Math.max(0, Math.min(1, ratio));
    const h2 = (x) => Math.round(x).toString(16).padStart(2, "0");
    return "#" + h2(r1 + (r2 - r1) * p) + h2(g1 + (g2 - g1) * p) + h2(b1 + (b2 - b1) * p);
  }

  function buildCustomTheme(name, scheme, bg, accent, info, ok) {
    const isDark = scheme === "dark";
    const target = isDark ? "#ffffff" : "#1c1814";
    const softRatio = isDark ? 0.80 : 0.84;
    const warn = isDark ? "#e0b95c" : "#8a6410";
    const err = isDark ? "#ee8d86" : "#a02a2a";
    return {
      id: "custom-" + Date.now().toString(36),
      name: name.trim(),
      subtitle: (isDark ? "深色" : "淺色") + " · 自訂模板",
      scheme,
      source: "custom",
      swatches: [bg, accent, info, ok],
      tokens: {
        bg,
        "bg-elev": mixHex(bg, "#ffffff", isDark ? 0.06 : 0.72),
        "bg-sunken": mixHex(bg, "#000000", isDark ? 0.24 : 0.05),
        fg: isDark ? "#ece7df" : "#28231e",
        "fg-muted": mixHex(bg, target, 0.62),
        "fg-faint": mixHex(bg, target, 0.44),
        line: mixHex(bg, target, 0.14),
        "line-strong": mixHex(bg, target, 0.25),
        accent,
        "accent-hover": mixHex(accent, isDark ? "#ffffff" : "#000000", 0.16),
        "accent-soft": mixHex(accent, bg, softRatio),
        "on-accent": isDark ? bg : "#fffdf8",
        info,
        "info-soft": mixHex(info, bg, softRatio),
        ok,
        "ok-soft": mixHex(ok, bg, softRatio),
        warn,
        "warn-soft": mixHex(warn, bg, softRatio),
        err,
        "err-soft": mixHex(err, bg, softRatio),
      },
    };
  }

  function loadCustoms() {
    try {
      const raw = JSON.parse(localStorage.getItem(STORE_CUSTOM) || "[]");
      return Array.isArray(raw) ? raw.filter((t) => t && t.id && t.tokens) : [];
    } catch (_) { return []; }
  }
  function saveCustoms(list) {
    try { localStorage.setItem(STORE_CUSTOM, JSON.stringify(list)); } catch (_) {}
  }
  function allThemes() {
    return BUILTIN_THEMES.concat(loadCustoms());
  }

  function updateButton(theme) {
    if (!triggerBtn || !theme) return;
    const h = FE.h;
    const dots = h("span", { class: "t2x-dots" },
      (theme.swatches || []).slice(1, 4).map((c) => h("i", { style: "background:" + c })));
    triggerBtn.replaceChildren(dots, h("span", { "data-i18n-skip": "" }, theme.name));
  }

  function applyTheme(theme) {
    if (!theme || !theme.tokens) return;
    const root = document.documentElement;
    root.setAttribute("data-theme", theme.scheme === "dark" ? "dark" : "light");
    Object.entries(theme.tokens).forEach(([k, v]) => root.style.setProperty("--" + k, v));
    currentId = theme.id;
    try { localStorage.setItem(STORE_ID, theme.id); } catch (_) {}
    updateButton(theme);
  }

  function openModal() {
    injectStyle();
    const h = FE.h;
    let filter = "all";
    const grid = h("div", { class: "t2x-tgrid" });
    const filterBtns = [
      ["all", "All"],
      ["light", "Light"],
      ["dark", "Dark"],
      ["custom", "Custom"],
    ];
    const filterRow = h("div", { class: "row", style: "gap:6px" });

    function drawFilters() {
      filterRow.replaceChildren(...filterBtns.map(([k, label]) =>
        h("button", {
          type: "button",
          class: "btn sm" + (filter === k ? " primary" : ""),
          "data-i18n-skip": "",
          onclick: () => { filter = k; drawFilters(); drawGrid(); },
        }, label)
      ));
    }

    function drawGrid() {
      const items = allThemes().filter((t) => {
        if (filter === "light") return t.scheme !== "dark";
        if (filter === "dark") return t.scheme === "dark";
        if (filter === "custom") return t.source === "custom";
        return true;
      });
      if (!items.length) {
        grid.replaceChildren(h("div", { class: "muted small", "data-i18n-skip": "" }, "—"));
        return;
      }
      grid.replaceChildren(...items.map((t) => {
        const strip = h("div", { class: "t2x-tstrip" },
          (t.swatches || [t.tokens.bg, t.tokens.accent, t.tokens.info, t.tokens.ok]).map((c) =>
            h("span", { style: "background:" + c })));
        const delBtn = t.source === "custom"
          ? h("button", {
              type: "button", class: "btn sm danger", "data-i18n-skip": "",
              onclick: (ev) => {
                ev.stopPropagation();
                const next = loadCustoms().filter((x) => x.id !== t.id);
                saveCustoms(next);
                if (currentId === t.id) applyTheme(BUILTIN_THEMES[0]);
                drawGrid();
              },
            }, "×")
          : null;
        return h("div", {
          class: "t2x-tcard" + (t.id === currentId ? " on" : ""),
          role: "button",
          tabindex: "0",
          onclick: () => { applyTheme(t); drawGrid(); },
          onkeydown: (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); applyTheme(t); drawGrid(); } },
        },
          strip,
          h("div", { class: "t2x-tmeta" },
            h("div", { class: "t2x-tmeta-top" },
              h("strong", { "data-i18n-skip": "" }, t.name),
              delBtn || h("span", { class: "muted small", "data-i18n-skip": "" }, t.scheme === "dark" ? "Dark" : "Light")
            ),
            h("div", { class: "t2x-tsub", "data-i18n-skip": "" }, t.subtitle || "")));
      }));
    }

    const nameIn = h("input", { type: "text", placeholder: "Name", required: true });
    const schemeSel = h("select", {},
      h("option", { value: "light", "data-i18n-skip": "" }, "Light"),
      h("option", { value: "dark", "data-i18n-skip": "" }, "Dark"));
    const bgIn = h("input", { type: "color", value: "#f5f1e6" });
    const accIn = h("input", { type: "color", value: "#8e354a" });
    const infoIn = h("input", { type: "color", value: "#336e7b" });
    const okIn = h("input", { type: "color", value: "#3b6e52" });
    schemeSel.onchange = () => { bgIn.value = schemeSel.value === "dark" ? "#1b222c" : "#f5f1e6"; };

    const customForm = h("form", {
      class: "t2x-cform",
      onsubmit: (ev) => {
        ev.preventDefault();
        if (!nameIn.value.trim()) return;
        const list = loadCustoms();
        const created = buildCustomTheme(nameIn.value, schemeSel.value, bgIn.value, accIn.value, infoIn.value, okIn.value);
        list.push(created);
        saveCustoms(list);
        applyTheme(created);
        nameIn.value = "";
        drawGrid();
      },
    },
      h("label", { "data-i18n-skip": "" }, "Name", nameIn),
      h("label", { "data-i18n-skip": "" }, "Mode", schemeSel),
      h("label", { "data-i18n-skip": "" }, "BG", bgIn),
      h("label", { "data-i18n-skip": "" }, "Accent", accIn),
      h("label", { "data-i18n-skip": "" }, "Info", infoIn),
      h("label", { "data-i18n-skip": "" }, "OK", okIn),
      h("button", { type: "submit", class: "btn sm primary", "data-i18n-skip": "" }, "+ Save"));

    const importIn = h("input", {
      type: "file", accept: ".json,application/json", hidden: true,
      onchange: async (ev) => {
        const file = ev.target.files && ev.target.files[0];
        if (!file) return;
        try {
          const parsed = JSON.parse(await file.text());
          const incoming = Array.isArray(parsed) ? parsed : [parsed];
          const valid = incoming.filter((t) => t && t.name && t.tokens && t.tokens.bg && t.tokens.accent);
          if (!valid.length) return;
          const list = loadCustoms();
          valid.forEach((t) => {
            const item = Object.assign({}, t, { id: "custom-" + Date.now().toString(36) + Math.random().toString(36).slice(2, 5), source: "custom" });
            list.push(item);
          });
          saveCustoms(list);
          applyTheme(list[list.length - 1]);
          drawGrid();
        } catch (_) {}
        importIn.value = "";
      },
    });

    const exportBtn = h("button", {
      type: "button", class: "btn sm", "data-i18n-skip": "",
      onclick: () => {
        const blob = new Blob([JSON.stringify(loadCustoms(), null, 2)], { type: "application/json" });
        const a = h("a", { href: URL.createObjectURL(blob), download: "t2x-custom-themes.json" });
        a.click();
        setTimeout(() => URL.revokeObjectURL(a.href), 1000);
      },
    }, "Export JSON");
    const importBtn = h("button", {
      type: "button", class: "btn sm", "data-i18n-skip": "",
      onclick: () => importIn.click(),
    }, "Import JSON");

    drawFilters();
    drawGrid();

    FE.modal({
      title: "Sanzo Wada · Themes",
      body: h("div", {},
        h("div", { class: "row", style: "justify-content:space-between;gap:8px;flex-wrap:wrap" },
          filterRow,
          h("div", { class: "row", style: "gap:6px" }, importIn, importBtn, exportBtn)),
        grid,
        h("details", { style: "margin-top:12px;padding-top:10px;border-top:1px dashed var(--line)" },
          h("summary", { style: "cursor:pointer;font-weight:600;font-size:13px", "data-i18n-skip": "" }, "+ Custom Theme"),
          customForm)),
      foot: (close) => [h("button", { type: "button", class: "btn", onclick: () => close(), "data-i18n-skip": "" }, "Close")],
    });
  }

  function init() {
    injectStyle();
    const saved = (() => { try { return localStorage.getItem(STORE_ID); } catch (_) { return ""; } })();
    const preferDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
    const picked = allThemes().find((t) => t.id === saved)
      || BUILTIN_THEMES.find((t) => t.id === (preferDark ? "fekit-ink" : "fekit-paper"))
      || BUILTIN_THEMES[0];
    if (picked) applyTheme(picked);
  }

  function button(cls) {
    triggerBtn = FE.h("button", {
      id: "theme-picker-btn",
      type: "button",
      class: cls || "btn sm",
      title: "Themes (Sanzo Wada)",
      "data-i18n-skip": "",
      onclick: openModal,
    }, "Themes");
    const cur = allThemes().find((t) => t.id === currentId);
    if (cur) updateButton(cur);
    return triggerBtn;
  }

  window.NSThemes = { init, button, open: openModal, apply: applyTheme, all: allThemes };
})();
