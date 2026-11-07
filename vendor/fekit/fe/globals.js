/* fekit globals.js — 選用：把常用函式掛到全域。要在 core.js 之後載入。
 * 刻意不提供 confirm：FE.confirm 是非同步的，蓋掉原生 confirm 會讓 if (confirm(...)) 永遠成立。
 * 也不提供 dirty：請用 FE.dirty.set()。 */
(function () {
  "use strict";

  if (!window.FE) {
    console.error("fekit：globals.js 要在 core.js 之後載入");
    return;
  }

  const NAMES = ["$", "$$", "h", "svg", "api", "upload", "toast", "fail", "modal", "store", "PAGES", "crumbs", "go", "route"];

  for (const name of NAMES) {
    if (name in window && window[name] !== window.FE[name]) {
      console.warn(`fekit：全域的 ${name} 已存在，已被覆蓋`);
    }
    window[name] = window.FE[name];
  }

  // t 是 i18n.js 提供的 FE.t。i18n.js 可能比這支晚載入，所以包一層，呼叫時才去找。
  if ("t" in window) console.warn("fekit：全域的 t 已存在，已被覆蓋");
  window.t = (...args) => {
    if (!window.FE.t) throw new Error("t()：還沒載入 i18n.js");
    return window.FE.t(...args);
  };
})();
