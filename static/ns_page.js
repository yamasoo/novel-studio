/* 頁面註冊（轉移計畫 §8.0 第 2 條、§8.3）。
   P4 的每個 page_*.js 都用 nsPage 註冊一個 FE.PAGES 條目：
   setBook／renderNav／S 是 app.js 的全域，本檔在 app.js 之後載入才抓得到，所以掛 window.nsPage
   （不用 const：其他 script 要能直接取用）。
   麵包屑也在這裡統一給（「書名 › 頁名」）：書名取書庫清單，頁名取剛畫好的 h1，
   所以 18 個 page 檔不必各寫一次標題，也不會和 h1 文案分叉。 */
(function () {
  "use strict";

  // 頂列麵包屑：書內頁「書名 › 頁名」，非書內頁只有頁名；畫不出來就留空，不擋路由。
  function setCrumbs() {
    const list = [];
    if (S.book) {
      const book = (S.books || []).find((x) => x.id === S.book);
      list.push({ label: book ? book.name || book.id : S.book, href: "#/b/" + enc(S.book) });
    }
    const h1 = document.querySelector("#view h1");
    const title = h1 ? h1.textContent.trim() : "";
    // 總覽頁的 h1 就是書名，兩個一樣時只留書名那一段（不要「X › X」）。
    if (title && !(list.length === 1 && list[0].label === title)) list.push({ label: title });
    FE.crumbs(list);
  }

  window.nsPage = function (key, routeName, options, render) {
    FE.PAGES[key] = async (ctx) => {
      if (options.book) await setBook(ctx.params.book || null);
      else if (options.clearBook) await setBook(null, true);
      S.routeName = routeName || "";
      renderNav();
      await render(ctx);
      setCrumbs();
    };
  };
})();
