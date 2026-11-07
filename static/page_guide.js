/* 說明頁（轉移計畫 §8.2.2）：從 app.js 的 viewGuide 搬過來（原本 3262-3278）。
   讀 /static/guide/<lang>.md，lang 取 FE.i18n.lang；找不到就退回 zh-TW。
   Markdown 用 FE.md.render（marked ＋ 白名單重建節點），不是 app.js 舊的 md()（marked 產字串直接塞進主區）。 */
(function () {
  "use strict";

  const { h } = FE;

  const FALLBACK = "zh-TW";

  function lang() {
    const want = FE.i18n && FE.i18n.lang;
    return ["zh-TW", "en", "ja"].includes(want) ? want : FALLBACK;
  }

  // 舊版是 fetch(u,{cache:"no-cache"})；FE.api 沒有 cache 選項，靜態檔走瀏覽器快取。
  async function loadText(signal) {
    for (const url of [`/static/guide/${lang()}.md`, `/static/guide/${FALLBACK}.md`]) {
      try {
        const text = await FE.api(url, { signal, headers: { Accept: "text/plain, text/markdown, */*" } });
        if (typeof text === "string" && text) return text;
      } catch (e) {
        // 換頁了：不要再試下一個，也不要畫舊頁。
        if (e && e.name === "AbortError") throw e;
      }
    }
    return null;
  }

  async function render(ctx) {
    const text = await loadText(ctx.signal);
    if (!text) {
      ctx.view(h("div", { class: "card empty" }, h("div", { class: "big" }, "?"), FE.t("找不到說明文件。")));
      return;
    }
    ctx.view(
      h("div", { class: "page-head" },
        h("div", {},
          h("h1", {}, FE.t("使用說明")),
          h("div", { class: "sub" }, FE.t("第一次用先看「兩個流程」；名詞看不懂再查名詞表。")))),
      h("div", { class: "card" }, FE.md.render(text)));
  }

  nsPage("guide", "guide", { clearBook: true }, render);
})();
