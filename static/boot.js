/* 小說工作台 啟動：i18n → 資料 → 舊面板 → 路由（轉移計畫 §5.4、§6.3）。
   P3 加 Panel 轉接，P5 換 shell。
   S／api／fail／Panel／provChoices 都是 app.js 的全域；本檔在 app.js 之後載入，抓得到。 */
"use strict";

// 舊的 #lang-select 是舊 i18n 在 DOMContentLoaded 時填的；現在改由 FE.i18n 產生（§6.3）。
function mountLangSelect() {
  const old = document.getElementById("lang-select");
  if (!old) return;
  // data-i18n-skip 不可少：語言選單的語言名稱不應該被翻譯
  old.replaceWith(FE.i18n.select({
    id: "lang-select", class: "lang-select",
    title: "Language / 言語 / 語言", "aria-label": "Language", "data-i18n-skip": "",
  }));
  // 舊程式（app.js 的開新書對話框）仍讀 localStorage.ns_lang；換語言時同步寫一份。
  // P4 換掉那個讀取點後，這幾行跟著 ns_lang 一起刪。
  const el = document.getElementById("lang-select");
  el.addEventListener("change", () => {
    try { localStorage.setItem("ns_lang", el.value); } catch (e) { /* ignore */ }
  });
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

(async function boot() {
  // 舊語言存在 ns_lang；新 store 是 novel-studio.lang（FE.store 以 meta fe-app 為前綴）。第一次啟動時遷移。
  try {
    const legacy = localStorage.getItem("ns_lang");
    if (legacy && localStorage.getItem("novel-studio.lang") === null) {
      localStorage.setItem("novel-studio.lang", JSON.stringify(legacy));
    }
  } catch (e) { /* ignore */ }

  // 語言檔是 fetch（非同步）；一定要在 FE.start() 之前 await，否則第一次路由會先以中文出現。
  await FE.i18n.init({
    base: "/static/locales",
    langs: [["zh-TW", "繁體中文"], ["en", "English"], ["ja", "日本語"]],
  });
  mountLangSelect();
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

  // P3 起這行要刪：那時 #panel-log 已經從 index.html 拿掉（見轉移計畫 7.3）。
  $("#panel-log").innerHTML = '<div class="ev-empty">從上方選一個動作，或在頁面上按按鈕。' +
    '<br>Claude 的過程與匯報會顯示在這裡。</div>';

  let open = false;
  try { open = localStorage.getItem("panelOpen") === "1"; } catch (e) { /* ignore */ }
  Panel.toggle(open);

  try { S.provider = localStorage.getItem("provider") || null; } catch (e) { /* ignore */ }
  if (S.provider && !provChoices().find((p) => p.id === S.provider)) S.provider = null;
  $("#prov-sel").onchange = (ev) => Panel.setProv(ev.target.value);
  Panel.renderProv();
  Panel.renderActions();

  // 舊路由交接（P1 全部視為舊）：PAGES 沒登記的路徑都交給舊的 route()。
  FE.PAGES.not_found = () => route();
  await FE.start({ root: "#view" });
})();
