# 待辦：P4 期間發現、但不在 P4 範圍

> 這些都是 P4（逐頁遷移）時看到、但刻意沒動的東西。每條都寫了「症狀／為什麼當時不改／下一個階段怎麼處理」。

## ① `Panel.show(id)` 對不存在的任務會留 2 筆 console

- 症狀：`Panel.show` 拿到壞 id 時會先 `fail()`（舊門面會 `console.error`）再顯示「讀不到任務」，瀏覽器留下 2 筆記錄。
- 當時不改：那是 P3 門面的既有行為，P4 只搬頁面、不動面板。
- P5 怎麼處理：`Panel.show` 改成 `FE.toast(msg)`＋不 `console.error`（或走 `FE.fail` 並確認它不印 console）。

## ② `S.onSharedJob` 換頁即清，任務在離開共用庫後完成不再跳 toast

- 症狀：共用庫的分頁一離開就把 `S.onSharedJob` 清掉，之後任務完成不會有任何提示（要自己去「任務紀錄」看）。
- 當時不改：清掉是為了避免舊頁回呼寫到新頁（P4 的競態防護），改成保留就要處理「回呼指向哪一頁」。
- P5 怎麼處理：把任務完成通知改成全域（`FE.jobs` 的事件／store），由面板統一跳 toast，頁面只訂閱。

## ③ `bookOpts`／`provOpts`／`provSelectHtml` 仍是字串版

- 症狀：這三支回傳 HTML 字串，頁面用 `nsShared.nodesFromHtml` 轉成節點才能用；多一層 DOMParser，也讓「字串拼 HTML」的寫法留在專案裡。
- 當時不改：還有 5 個呼叫端（共用庫 4 處、匯入頁 1 處），改成節點版要一次改完，屬於跨檔重構。
- P5 怎麼處理：改成 `bookOptions()`／`provOptions()`／`provSelect()` 回傳節點，同時刪掉 `nodesFromHtml`。

## ④ `static/locales` 兩個既有資料問題（屬翻譯資料，P4 禁改）

- 症狀一：章節表的表頭第一欄 en 是空字串。
- 症狀二：總覽頁的「下一章」en／ja 沒有翻。
- 當時不改：P4 的硬限制是 0 行改動 `static/locales` 與 `tools/i18n_keys.json`（翻譯資料由 i18n 流程處理）。
- 下一階段怎麼處理：走 `docs/i18n-workflow.md` 的流程補鍵與譯文，補完跑 `tools/check_i18n.py` 與 `tools/check_parity.py --strict`。

## ⑤ `FE.PAGES` 的 key 形狀限制（建議回饋 fekit）

- 症狀：`matchPage` 是「最長的 key 勝出」，所以「一個路徑前綴 + 可能沒有殘餘段」這種需求無法只用 key 表達
  （P4 最後是用「`b/:book` 的 handler 自己判斷 `ctx.args.length` → 畫 404」收掉）。
- 當時不改：改 fekit 的核心比對規則超出 P4 範圍。
- P5 怎麼處理：建議 fekit 支援「結尾 `:` 代表 0 個殘餘段才算命中」或在文件寫明這個限制；在那之前，共用 `ns_page.js`
  的頁面請照 P4 的寫法（handler 內判斷 `ctx.args`）。
