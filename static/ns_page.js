/* 頁面註冊（轉移計畫 §8.0 第 2 條、§8.3）。
   P4 的每個 page_*.js 都用 nsPage 註冊一個 FE.PAGES 條目：
   setBook／renderNav／S 是 app.js 的全域，本檔在 app.js 之後載入才抓得到，所以掛 window.nsPage
   （不用 const：其他 script 要能直接取用）。 */
(function () {
  "use strict";

  window.nsPage = function (key, routeName, options, render) {
    FE.PAGES[key] = async (ctx) => {
      if (options.book) await setBook(ctx.params.book || null);
      else if (options.clearBook) await setBook(null, true);
      S.routeName = routeName || "";
      renderNav();
      await render(ctx);
    };
  };
})();
