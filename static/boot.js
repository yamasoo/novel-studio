/* 小說工作台 啟動：資料 → 舊面板 → 路由（轉移計畫 §5.4）。
   P2 在這裡加 i18n，P3 加 Panel 轉接，P5 換 shell。
   S／api／fail／Panel／provChoices 都是 app.js 的全域；本檔在 app.js 之後載入，抓得到。 */
"use strict";

(async function boot() {
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
