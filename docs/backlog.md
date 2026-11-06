# 待辦：P4／P5 期間發現、但不在該階段範圍

> 每條寫「症狀／為什麼當時不改／下一個階段怎麼處理」。P4 的五條在 P5 收掉三條半，狀態標在標題後面。

## ① `Panel.show(id)` 對不存在的任務會留 2 筆 console（P5 已修）

- 修法：`Panel.show` 的 catch 改走 `FE.fail`（會吞 AbortError、ApiError 不印 console），全域 `fail`／`toast` 也變成 `FE.fail`／`FE.toast` 的薄別名。

## ② `S.onSharedJob` 換頁即清，任務在離開共用庫後完成不再跳 toast（未修，留 P6）

- 症狀：共用庫分頁一離開就把 `S.onSharedJob` 清掉，之後任務完成沒有任何提示（要自己去「任務紀錄」看）。
- 為什麼 P5 沒修：要改成「由 `FE.jobs` 的事件統一跳 toast」就得動 `FE.jobs` 的公開介面（kit 端），P5 不動 kit。
- P6 怎麼處理：在 `panel.finish` 之外掛一個全域監聽（`FE.jobs` 若沒有事件匯流，就在 `Panel.mount` 的 `onend` 統一處理，並讓頁面只訂閱），或回饋 fekit 加 `onend` 的全域版本。

## ③ `bookOpts`／`provOpts`／`provSelectHtml` 仍是字串版（P5 已修）

- 修法：改成回節點的 `bookOptions()`／`provOptions()`／`provSelect()`，13 處呼叫端全部改寫，`nsShared.nodesFromHtml` 與 DOMParser 一起刪。

## ④ `static/locales` 兩個既有資料問題（屬翻譯資料，仍未修）

- 症狀一：章節表的表頭第一欄 en 是空字串。症狀二：總覽頁的「下一章」en／ja 沒有翻。
- 為什麼還沒修：翻譯資料要走 `docs/i18n-workflow.md` 的流程（補鍵→初翻→人工核可）。
- **P5 另外留下一批**：`tools/i18n_keys.json` 還記著 P5 刪掉的字串（`static/i18n.js`、舊 `#panel` 的標籤等）。要重跑 `tools/i18n_extract.py` 再清 `en.json`／`ja.json` 的失效鍵，否則 `check_parity` 會一直算它們的覆蓋率。

## ⑤ `FE.PAGES` 的 key 形狀限制（未修，建議回饋 fekit）

- 症狀：`matchPage` 是「最長的 key 勝出」，「一個路徑前綴 + 可能沒有殘餘段」無法只用 key 表達（P4 最後用 `b/:book` 的 handler 自己判斷 `ctx.args.length`）。
- P6 怎麼處理：建議 fekit 支援「結尾 `:` 代表 0 個殘餘段才算命中」，或在文件寫明這個限制。

---

## P5 期間新發現

### ⑥ fekit 的 `drawAsk` 會把 `null` 塞進 `replaceChildren`（kit 缺陷，未修）

- 症狀：面板回覆框多一個裸的 `null` 文字節點（`vendor/fekit/fe/jobs.js` 的 `drawAsk`）。
- 現況：`app.js` 的 `Panel.mount` 的 `onchange` 每次重畫後把 `.job-panel .job-ask` 裡的純文字節點刪掉（三行繞路，有註解）。
- P6：要修在 fekit 本體（`E:\dev\front-end\kit\fe\jobs.js`），修好後刪掉那三行。**不要**手改 `vendor/fekit`。

### ⑦ `static/relgraph.js` 沒有換成 `FE.graph`（關係圖）

- 為什麼：`vendor/fekit/fe` 沒有 `graph.js`，而 `FE.graph` 需要 Cytoscape 的 vendor 檔與 `THIRD_PARTY_NOTICES`；`sync_kit.py --add graph` 在唯讀的 `E:\dev\front-end` 那一側，本輪不能動。
- P6：`sync_kit.py E:\novel-studio --add graph` → `page_tracking.js` 的 `REL_VIEW === "graph"` 改 `FE.graph`（資料轉換照 `轉移計畫 §9.6`）。做不到等價就繼續留 `relgraph.js`。

### ⑧ `app.js` 還有字串版 HTML 建構（`innerHTML`）

- 範圍：`renderChapterStructure`、`renderCard`（視覺卡）、`renderIllSettings`（設定頁插畫）、`loraRowsHtml`／`bindLoraRows`。它們是 P4 留在 `app.js` 的共用字串 renderer，頁面本身已經是節點版。
- 風險：字串裡的 `esc()` 一旦漏一個就是注入點；也讓「不用 `innerHTML`」的規則在 `app.js` 破功。
- P6：逐支改節點版（`renderIllSettings` 最大，建議最後）。

### ⑨ `style.css` 還留著舊三欄的規則

- `#sidebar`、`#main`、`#panel`、`#panel-resizer`、`#panel-fab`、`#lang-select`、`.side-bottom`、`.brand` 這些選擇器已經沒有對應的 DOM；`:root` 的 `--panel-w` 也沒人用了。
- 現況：`ns-fekit.css` 用兩條補丁擋住撞名的 `#app{display:flex}` 與 `.split{grid-template-columns:260px 1fr}`。
- P6：刪舊規則＋把 `ns-fekit.css` 的兩條補丁收回 `style.css`（每刪一段就重拍該頁截圖）。

### ⑩ `static/vendor/marked.min.js` 已經沒有人用

- `FE.md` 用的是 `/fekit/vendor/marked/*`；`index.html` 還載著舊的 `marked.min.js`，而 `#/about` 的第三方清單也還寫著它。
- P6：改 about 頁的清單（會動到 `tools/i18n_keys.json` 的字串）→ 刪 `static/vendor/marked.min.js` 與 `marked.LICENSE.md` → 在根目錄補一份 `THIRD_PARTY_NOTICES.md`（目前只有 `vendor/fekit/THIRD_PARTY_NOTICES.md` 與 `plugin*/THIRD_PARTY_NOTICES.md`）。

### ⑪ 頂列麵包屑是空的

- `FE.start({ crumbs: shell.crumbs_el })` 已經接上，但 18 頁都沒有呼叫 `ctx.crumbs([...])`（P4 也沒有）。
- P6：在 `ns_page.js` 依 `routeName` 給「書名 › 頁名」，或決定拿掉頂列的 `crumbs`。

### ⑫ `search`／`reverse`／`drift` 三頁的導覽沒有 active 項目

- 這三頁不在 `navItems()` 的清單裡（P4 的舊側欄也只有 8＋6 個入口），所以側欄不會標示目前位置。
- P6：決定要不要掛到「總覽」的 `page` 陣列，或另立「工具」群組。

### ⑬ 舊 `localStorage` key 沒有刪

- `migrateStore()` 只把舊 key「複製」進 `FE.store`（`novel-studio.*`），舊的 `ns_lang`／`provider`／`actsCollapsed`／`search-scopes`／`panelOpen`／`panelW` 還在。
- 影響：沒有功能問題，只是留著死資料。P6 可在遷移成功後刪舊 key（要小心：刪了就不能回滾到 P4 版）。
