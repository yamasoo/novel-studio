/* 小說工作台 啟動：store 遷移 → i18n → 資料 → 面板 → 路由（轉移計畫 §5.4、§6.3）。
   P5 換上 FE.shell 三欄外殼，index.html 的 #sidebar／#main／#panel 已刪除。
   S／api／fail／Panel／sideSearch 都是 app.js 的全域；本檔在 app.js 之後載入，抓得到。 */
"use strict";

/* 舊 localStorage 遷移進 FE.store（實際 key 以 meta fe-app 為前綴，即 novel-studio.*）。
   只在 store 還沒有值時寫，才不會蓋掉使用者後來調的狀態；壞值跳過，不影響啟動。
   i18n 與 shell 都會讀 store（語言、面板開關、寬度），所以要在 init／mount 之前跑完。 */
function migrateStore() {
  try {
    // ns_lang → lang 要趕在 FE.i18n.init 之前生效，否則英文／日文介面會退回中文
    const lang = localStorage.getItem("ns_lang");
    if (lang && FE.store.get("lang", undefined) === undefined) FE.store.set("lang", lang);

    const provider = localStorage.getItem("provider");
    if (provider !== null && FE.store.get("provider", undefined) === undefined) FE.store.set("provider", provider);

    const acts = localStorage.getItem("actsCollapsed");
    if (acts !== null && FE.store.get("actsCollapsed", undefined) === undefined) FE.store.set("actsCollapsed", acts === "1");

    const scopes = localStorage.getItem("search-scopes");
    if (scopes !== null && FE.store.get("search-scopes", undefined) === undefined) FE.store.set("search-scopes", JSON.parse(scopes));

    // 舊版面板預設收起：panelOpen 是 "1" 才算開著的，換成 shell 的 shell.off.panel。
    if (FE.store.get("shell.off.panel", undefined) === undefined) {
      FE.store.set("shell.off.panel", localStorage.getItem("panelOpen") !== "1");
    }

    if (FE.store.get("shell.w.panel", undefined) === undefined) {
      const w = parseInt(localStorage.getItem("panelW"), 10);
      if (Number.isFinite(w) && w > 0) FE.store.set("shell.w.panel", w);
    }
  } catch (e) { /* 舊值壞掉就維持預設 */ }
}

// 舊 i18n 會包住原生對話框；墊片照做，直到 P4 把頁面換成 FE.confirm／FE.modal（§6.3）。
function wrapNativeDialogs() {
  const nativeConfirm = window.confirm.bind(window);
  const nativeAlert = window.alert.bind(window);
  const nativePrompt = window.prompt.bind(window);
  window.confirm = (message) => nativeConfirm(FE.t(String(message)));
  window.alert = (message) => nativeAlert(FE.t(String(message)));
  window.prompt = (message, value) => nativePrompt(FE.t(String(message)), value);
}

/* 導覽項目：有書時先一段「本書」，再一段「工作台」。
   舊版把書架…關於放在側欄底部，改成 nav 項目之後 shell 會自己標 active，不用再手動比對 S.routeName。 */
function navItems() {
  const items = [];
  if (S.book) {
    const base = "#/b/" + enc(S.book);
    items.push(
      { group: "本書" },
      { label: "總覽", icon: "◉", href: base, page: ["b/:book", "b/:book/overview"] },
      { label: "章節", icon: "☰", href: base + "/chapters", page: ["b/:book/chapters", "b/:book/ch/:no"] },
      { label: "大綱", icon: "⌘", href: base + "/outline", page: "b/:book/outline" },
      { label: "設定集", icon: "✦", href: base + "/bible", page: "b/:book/bible" },
      { label: "伏筆與時間線", icon: "⟲", href: base + "/tracking", page: "b/:book/tracking" },
      { label: "任務紀錄", icon: "◷", href: base + "/jobs", page: "b/:book/jobs" },
      { label: "插圖", icon: "✎", href: base + "/illust", page: "b/:book/illust" },
      { label: "匯出", icon: "⇩", href: base + "/export", page: "b/:book/export" },
      { group: "工作台" });
  }
  items.push(
    { label: "書架", icon: "▤", href: "#/", page: "home" },
    { label: "共用庫", icon: "❖", href: "#/shared", page: "shared" },
    { label: "匯入舊稿", icon: "⇪", href: "#/import", page: "import" },
    { label: "設定", icon: "⚙", href: "#/settings", page: "settings" },
    { label: "說明", icon: "?", href: "#/guide", page: "guide" },
    { label: "關於", icon: "ⓘ", href: "#/about", page: "about" },
    { label: "GitHub 專案", href: "https://github.com/yamasoo/novel-studio", external: true },
    { label: "回報問題", href: "https://github.com/yamasoo/novel-studio/issues/new", external: true });
  return items;
}

(async function boot() {
  migrateStore();

  // 語言檔是 fetch（非同步）；一定要在 FE.start() 之前 await，否則第一次路由會先以中文出現。
  await FE.i18n.init({
    base: "/static/locales",
    langs: [["zh-TW", "繁體中文"], ["en", "English"], ["ja", "日本語"]],
  });
  wrapNativeDialogs();

  try {
    const [cfg, acts, books] = await Promise.all([
      api("GET", "/api/config"),
      api("GET", "/api/actions"),
      api("GET", "/api/books"),
    ]);
    S.config = cfg.config;
    S.claudeFound = cfg.claude_found;
    S.actions = acts;
    S.books = books.books;
  } catch (e) {
    fail(e);
  }

  // P3：面板本體是 FE.jobs.panel（轉移計畫 §7.4）；P5 把它放進 shell 的右欄。
  await FE.md.load();

  // 前文搜尋放左欄上方：沒有書時整塊隱藏，由 renderNav() 開關。
  const searchForm = FE.h("form", {
    class: "side-search",
    onsubmit: (ev) => { ev.preventDefault(); sideSearch(ev.target.q.value); },
  }, FE.h("input", { id: "side-q", name: "q", type: "search", placeholder: "搜尋前文（Ctrl+K）" }));

  // 語言選單與執行者選單放頂列；語言選單由 FE.i18n 維護，不再寫 localStorage.ns_lang。
  const shell = FE.shell.mount({
    root: "#app",
    brand: { label: "小說工作台", mark: "書", href: "#/" },
    nav: navItems,
    panel: (el) => {
      el.append(FE.h("div", { id: "panel-actions" }), FE.h("div", { id: "panel-form" }));
      Panel.mount(el);
      return null;
    },
    panel_label: "AI",
    sizes: { panel: { min: 340, max: 900, width: 420 } },
    slots: {
      top: FE.h("div", { class: "row" },
        FE.i18n.select({
          id: "lang-select", class: "lang-select",
          title: "Language / 言語 / 語言", "aria-label": "Language", "data-i18n-skip": "",
        }),
        FE.h("select", { id: "prov-sel", title: "執行者" })),
      nav_head: FE.h("div", { class: "shell-nav-head" },
        FE.h("select", { id: "book-switch", title: "切換書" }),
        searchForm),
    },
    start: false,
  });

  S.provider = FE.store.get("provider", null);
  if (S.provider && !provChoices().find((p) => p.id === S.provider)) S.provider = null;
  Panel.renderProv();
  Panel.renderActions();

  const provSel = document.querySelector("#prov-sel");
  if (provSel) provSel.onchange = (ev) => Panel.setProv(ev.target.value);

  // P4：PAGES 沒登記的路徑不再交給舊 route()（已刪）。fekit 在 PAGES.not_found 不存在時會自己畫 notFoundView()。
  await FE.start({ root: shell.view_el, crumbs: shell.crumbs_el });
  // FE.start 之後再 resume，避免和第一次路由的 setBook 搶
  Panel.resume().catch(() => {});
})();
