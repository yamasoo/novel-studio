/* 頁面檔的共用小工具（轉移計畫 §8.3）：單一來源，不跟 app.js 各寫一份。
   本檔在 app.js 之前載入，所以 fmtTime／fmtNum／unitCh／unitOfBook 直接轉呼叫 app.js 的同名全域
   （function 宣告是 window 的屬性，const 是全域語彙綁定，兩者在後續 script 都取得到）；
   statusBadge／jobBadge 的對照表只留在這裡，app.js 那兩個改成薄序列化。 */
(function () {
  "use strict";

  const { h } = window.FE;

  // app.js:71-74 的狀態 → badge class 對照表
  const STATUS_CLASS = {
    "已寫": "b-ok", "已確認": "b-info", "草稿": "b-warn", "正式": "b-ok",
    "已回收": "b-ok", "推進中": "b-info", "已埋": "b-warn", "廢棄": "",
  };

  function statusBadgeNode(s) {
    if (!s) return null;
    return h("span", { class: "badge " + (STATUS_CLASS[s] || "") }, s);
  }

  // app.js:1808-1812 的任務狀態；不認識的狀態是純文字（舊版就是 esc(s)），不是 badge
  const JOB_BADGE = {
    running: ["b-ok", "執行中"],
    done: ["", "完成"],
    error: ["b-bad", "失敗"],
    cancelled: ["b-warn", "已停止"],
  };

  function jobBadgeNode(s) {
    const hit = JOB_BADGE[s];
    if (!hit) return document.createTextNode(s == null ? "" : String(s));
    // 舊版的字串是 class="badge"（done）與 class="badge b-*"，沒有尾隨空白，這裡照留。
    return h("span", { class: hit[0] ? "badge " + hit[0] : "badge" }, hit[1]);
  }

  // 舊的 HTML 字串型 helper（bookOpts／provOpts／provSelectHtml）轉成節點用：
  // 惰性 DOMParser 產生的文件不執行 script、不載入圖片，比 innerHTML 安全。
  function nodesFromHtml(html) {
    const doc = new DOMParser().parseFromString(String(html == null ? "" : html), "text/html");
    return Array.from(doc.body.childNodes).map((node) => document.importNode(node, true));
  }

  // 薄序列化：app.js 的 statusBadge／jobBadge 呼叫端要的是字串，節點版在轉回 HTML。
  // 這是本檔唯一出現 outerHTML 的地方。
  function html(node) {
    if (!node) return "";
    if (node.nodeType === 1) return node.outerHTML;
    return esc(node.nodeValue == null ? "" : node.nodeValue);
  }

  window.nsShared = {
    statusBadgeNode,
    jobBadgeNode,
    html,
    nodesFromHtml,
    // 轉呼叫 app.js 的實作；本檔比 app.js 先載入，所以包一層到呼叫時才解析。
    fmtTime(t) { return fmtTime(t); },
    fmtNum(n) { return fmtNum(n); },
    unitCh(unit) { return unitCh(unit); },
    unitOfBook(id) { return unitOfBook(id); },
  };
})();
