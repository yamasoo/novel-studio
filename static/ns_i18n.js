/* 舊程式用 window.I18N 與 window.t；這裡把它們接到 fekit 的 FE.i18n（轉移計畫 §6.2、D3-11）。
   本檔只定義墊片，不呼叫 init()：init() 在 boot.js 的 FE.start() 之前 await。
   舊呼叫端（app.js 內 100 多處 I18N.t／I18N.tr／I18N.lang）不用改；
   P4 逐頁換掉 I18N.* 之後，本檔與 static/i18n.js 一起在 P5 刪除。 */
(function () {
  "use strict";

  const FE = window.FE;
  if (!FE || !FE.i18n) {
    console.error("ns_i18n.js：要在 fe/core.js 與 fe/i18n.js 之後載入");
    return;
  }

  window.t = FE.t;
  window.I18N = {
    get lang() { return FE.i18n.lang; },       // 舊版是字串；新版跟著 FE.i18n
    get LANGS() { return FE.i18n.langs; },     // 舊版是陣列常數；新版回傳複本（只給顯示用）
    t: FE.t,
    tr: FE.i18n.tr,
    missing: FE.i18n.missing,                  // 開發時查缺口：I18N.missing
    setLang: (code) => FE.i18n.set(code),      // 一樣直接 reload
  };
})();
