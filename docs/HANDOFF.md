# HANDOFF：Novel Studio 三語與續寫改善

> 這份檔案給「下一個對話」或「未來的自己」看。看完這一頁就能接手，不需要重讀整份報告。

## P6 收尾：backlog ⑥–⑬ 與 2.0.0（完成）

> 這一輪沒有新增功能，只把 P5 留下的收尾清乾淨並發版 **2.0.0**（2026-11-07）。分支 `feat/fekit-closeout`，**不 push、不合 main**。

**八個 commit（一個項目一個 commit）**

| commit | 項目 | 內容 |
|---|---|---|
| `ba9d302` | ⑩ | 「關於」頁第三方清單改指 fekit 帶的 marked；刪 `static/vendor/`；根目錄新增 `THIRD_PARTY_NOTICES.md` |
| `a89b66c` | ⑨ | `style.css` 刪舊三欄死規則 -38 行；`ns-fekit.css` 的外殼補丁收回 `style.css`（要排在 `.split` 之後才蓋得過） |
| `8f9a772` | ⑧ | `app.js` 16 個區塊字串 HTML → 節點（`FE.h`），`innerHTML` 歸零 |
| `47ec7ef` | ⑦ | `sync_kit.py --add graph` → `page_tracking.js` 關係圖改 `FE.graph`（Cytoscape 3.34.4）；刪 `relgraph.js` 與 35 條 `.rg-*` |
| `f0f73d1` | ⑪ | `ns_page.js` 統一給麵包屑「書名 › 頁名」（頁名取已渲染的 h1） |
| `8cde06f` | ⑫ | `boot.js` 導覽加「工具」群組（搜尋前文／從正文建立設定／卷末體檢），三頁有 active |
| `f465349` | ⑬ | 舊 localStorage key 遷移成功後刪除＋`legacy.pruned` 標記 |
| （發版 commit） | — | `VERSION = 2.0.0`、CHANGELOG／README／docs／`docs/screenshots/p6`、tag `v2.0.0` |

**已定決策**

1. 版號 **2.0.0**：`X-NS-Token` 不再接受、422 改 `{error,code,fields}`、非本機 Host 403，對外用 API 的人是破壞性變更。
2. ⑬ 真的刪舊 key（使用者同意）：回退到 P4 版時語言／執行者／面板寬度會回預設值，偏好本身都在 `FE.store`。
3. ⑪ 用「書名＋h1」推麵包屑，不新增 18 份標題對照表；總覽頁 h1 就是書名時只留一段。
4. ⑫ 三頁都是 book-scoped，掛在本書區的「工具」群組（不是掛到「總覽」的 page 陣列，那會讓側欄同時亮兩項）。

**驗收（實測）**

- 18 頁 × 6 種組態（zh-TW 深／淺 1440、en、ja、800×900 深／淺）＝ 108 次載入：console 0 錯誤、`h1` 都在、`.nav .nav-item.active` 正確、麵包屑非空。
- 關係圖：用自造 payload（2 勢力／4 角色／5 關係）驗到節點 6、邊 4（角色對自己所屬勢力不畫線）、第 5 章 1 條關係、勾「顯示配角與反派」變 2 條、滑到第 4 章 3 條、點節點跑出詳細資料、fit／relayout／深色主題 0 錯誤且非 GET 請求 0 次。真資料（7 節點／0 關係）不炸。
- `python -m compileall app.py studio ns_jobs.py`、`tools/check_i18n.py`、`tools/check_parity.py --strict`（FAIL 0／WARN 0）全過。
- 截圖：新基線 `docs/screenshots/p6`（41 張）；與 `p5` 的逐像素差異逐頁列在 2.0.0 的階段報告裡（來源是書庫資料成長、⑪⑫ 的介面改動、關係圖換套件）。

**P7 接手前要記得**

1. **⑥ 已修（2026-11-07）**：`FE.jobs.panel` 的 `drawAsk` 改成先濾掉 null 再 `replaceChildren`（fekit 本體 `56a37e4`，同一批還有新的 `FE.jobs.onend`）；`vendor/fekit` 已同步，`app.js` 的 `Panel.mount` 三行繞路已刪。要再同步一律回 fekit 本體跑 `tools/sync_kit.py`。
2. 截圖基線改用 `docs/screenshots/p6`（p5 保留當歷史）。
3. 新增的 backlog：⑭ i18n 失效鍵（含新的關係圖字串）、⑮ `app.js` 的 `esc()` 已無呼叫端、⑯ 書庫資料與 p5 基線不同步。
4. `vendor/fekit` 現在有 graph 模組與 Cytoscape；要再同步一律回 fekit 本體跑 `tools/sync_kit.py`。
5. 2026-11-07 收尾：⑮ 刪掉 `app.js` 裡 8 項 0 呼叫端的舊 helper（`esc`／`pad3`／`JB`／`S.es`／`S.lastText`／`Panel.open`／`Panel.reply`／`Panel.setWidth`，18 頁 console 0 錯誤、DOM 快照不變）；⑯ 基線確定用 `docs/screenshots/p6`，p6 拍完之後書庫又動過（⑰），要比像素前先重拍。

## P5：外殼、`fekit.install()`、舊檔清理（完成）

- **後端**：`app.py` 的守門換成 fekit 的 `install()`（`vendor/fekit/py`）。`MUTATE_TOKEN`／`TOKEN_JS`／`same_origin`／`guard_mutations` 全刪，
  首頁改 `fe.inject(html)`。**權杖只認 `X-FE-Token`（`X-NS-Token` 不再接受）**；`LocalGuard` 對所有請求驗 Host
  （預設 127.0.0.1／localhost／[::1]），綁 `0.0.0.0` 要在 `config.json` 填 `allowed_hosts`；`DEFAULT_CONFIG` 已加 `"allowed_hosts": []`。
- **行為變更**：`install()` 會裝自己的錯誤處理器 → 500 改通用句、`422` 由 `{"detail":[…]}` 變 `{"error","code","fields"}`、
  traceback 走 `log.exception`（後端視窗不再有 `↑ 上面是 GET … 的完整堆疊` 那一行）。
- **外殼**：`static/index.html` 只剩 `<div id="app"></div>`；`boot.js` 掛 `FE.shell.mount()`：頂列＝語言＋執行者＋AI 開關，
  左欄＝`#book-switch`＋前文搜尋＋`navItems()`（本書 8 項／工作台 8 項，含「回報問題」），右欄＝`#panel-actions`／`#panel-form`＋`Panel.mount()`；
  之後 `FE.start({ root: shell.view_el, crumbs: shell.crumbs_el })`。
- **app.js（816 行）**：`Panel` 只剩門面（`toggle`→`shell.toggle`、`setWidth`→`shell.width`、`onchange`→`shell.badge`）；
  `renderNav()` 只更新 `#book-switch` 的 option 與 `shell.refresh_nav()`；`setBook()` 會補一次 `renderNav()`（`#/b/<書>` 直開時側欄才不會空、書切換才選得到書）。
- **store**：`boot.js` 的 `migrateStore()` 在 `FE.shell.mount()` **之前**跑，把舊 `ns_lang`／`provider`／`actsCollapsed`／`search-scopes`／
  `panelOpen`／`panelW` 換算成 `FE.store`（前綴 `novel-studio.`）；只在 store 沒值時寫，重複整理頁不會蓋回使用者後來的調整。舊 key 沒刪。
- **刪掉的檔／碼**：`static/i18n.js`、`static/ns_i18n.js`（`window.t`／`window.I18N` 一起消失，改用 `FE.t`／`FE.i18n.*`）、`#modal`／`#toast` DOM、
  `modal()`／`closeModal()`、`bookOpts`／`provOpts`／`provSelectHtml`（改成回節點的 `bookOptions`／`provOptions`／`provSelect`）、`nsShared.nodesFromHtml`。
- **CSS**：`ns-fekit.css` 收下兩條 shell 補丁（`#app > .shell { flex: 1 1 auto; min-width: 0 }`、`.shell-body { display: flex }`）——
  舊 `style.css` 的 `#app{display:flex}` 會讓 `.shell` 縮成內容寬，`.split{grid-template-columns:260px 1fr}` 更會把主區壓成 260px。`style.css` 本身沒清。
- **保留**：`static/relgraph.js`（關係圖沒換，見 `docs/backlog.md`）、`static/vendor/marked.min.js`（已經沒人用，但 about 頁的第三方清單提到它）。

**驗收（實測，不是推論）**

- 108 次頁面載入（18 頁 × zh-TW 深／淺 × en × ja × 窄螢幕 800×900 深／淺）：console 0 錯誤、`h1` 都在、`.nav .nav-item.active` 正確、
  `#book-switch` 是 `SELECT` 且選到書、`#prov-sel` 7 個 option、`.job-panel` 都在；`search`／`reverse`／`drift` 三頁本來就不在導覽裡（P4 也是 0 個 active）。
- 36 張截圖（`docs/screenshots/p5`）與 `docs/screenshots/p4` 逐像素比對：**整頁級差異**（bbox 全幅、ge32 約 4.6 萬–29 萬像素），原因見 P5 報告的「預期內差異」清單；
  另補面板／窄螢幕抽屜／en／ja 共 5 張。
- 重啟後 curl：無權杖 `403 bad_token`、錯權杖 403、舊 `X-NS-Token` 403、跨來源 `403 bad_origin`、非本機 Host `403 bad_host`、
  `/fekit/py/*` 與 `/fekit/fekit.json` 404（`/fekit/fe/*`、`/fekit/css/*` 正常 200）。
- 面板任務：切 `claude_code` → `Panel.openForm('setup_new')` 開出表單（1 個 textarea＋`#pf-go`），全程 `window.__writes = 0`（fetch stub 攔掉所有非 GET）。
- 舊偏好遷移：寫入舊 key 後重載 → `provider=claude_code`、`actsCollapsed=true`、`search-scopes=["text","outline"]`、`shell.off.panel=false`、
  `shell.w.panel=640`、`lang=en`（`html lang=en`）；使用者改過 provider／寬度再重載，舊 key 不會蓋回去。
- `python -m compileall app.py studio ns_jobs.py`、`tools/check_i18n.py`、`tools/check_parity.py --strict`（FAIL 0、WARN 0）全過。

**P6 接手前要記得**：`boot.js` 的 `migrateStore()` 不要刪（刪了使用者舊偏好會靜默歸零）；`window.t`／`window.I18N` 已經不存在；
截圖新基線是 `docs/screenshots/p5`（**P6 起已改用 `docs/screenshots/p6`**）；`tools/i18n_keys.json` 還留著 P5 刪掉的字串（要重跑 `tools/i18n_extract.py` 再清語言檔，屬 i18n 流程）。
## P4：逐頁拆成 page_*.js（完成）

舊的單檔前端（`static/app.js`，3,672 行）已經**整份拆完**：18 個頁面各一個 `static/page_*.js`，
`app.js` 降到 **845 行**，只剩共用工具（`S`／`api`／`B`／`esc`／`toast`／`fail`／`setBook`／`renderNav`／
`highlightTerms`／`splitFM`／`parseHash`…）、`Panel` 面板轉接、以及還沒換掉的舊對話框（`modal`／`closeModal`）。

**共用檔（四支）**

| 檔案 | 內容 |
|---|---|
| `static/ns_page.js` | `nsPage(key, routeName, options, render)` 註冊殼：設 `S.routeName`、`setBook`／`clearBook`、`renderNav`、叫 handler |
| `static/ns_shared.js` | 狀態／任務 badge 的節點版、`fmtTime`／`fmtNum`／`unitCh` 轉接、`nodesFromHtml` |
| `static/ns_doc.js` | 文件檢視／編輯，對外仍是全域 `docView`（Markdown 用 `FE.md.render`、未存檔走 `FE.dirty`、Ctrl+S） |
| `static/ns_pipe.js` | 整章自動流程，對外仍是全域 `renderPipe`／`pipeModal`／…；換頁會停輪詢 |

**每頁的寫法（一致）**：IIFE ＋ `"use strict"`、只用 `ctx.view(...)` 寫主區、GET 一律 `FE.api(path, { signal: ctx.signal })`
（AbortError 不吞）、對話框用 `FE.modal`／`FE.confirm`／`FE.toast`／`FE.fail`、不用字串 `innerHTML`／行內 `onclick`。

**路由**：全部由 `FE.PAGES` 接管，舊的 `route()`／`guardedView()` 已刪；`PAGES.not_found` 交給 fekit 預設的
`notFoundView()`（「找不到這個頁面。回首頁」）。書內頁的 key 一律是 `b/:book/xxx`；`b/:book` 只吃 0 個殘餘段
（有殘餘段或書不存在時顯示 404）。

**驗收方式**：每個頁面 × 三語（zh-TW／en／ja）× 深淺（dark／light）各開一次，檢查 console 0 錯誤、h1、
側欄 active、`#view` 內行內 `onclick` 為 0；截圖基線在 `docs/screenshots/p4`（18 頁 × 深淺＝36 個 PNG），
比對用**逐通道最大差**（bbox／max／≥1／≥32／≥64 四項），不要用灰階（會低估真實差異）。

**P5 開工前先讀**：這一段 → `docs/backlog.md` → `static/ns_page.js` 與 `vendor/fekit/fe/core.js` 的
`matchPage`／`PAGES` 規則。P5 的重點是把殼（側欄、麵包屑、檔案選擇器）換成 fekit 的版本，並把還是字串版的
`bookOpts`／`provOpts`／`provSelectHtml` 改成節點版。

## 專案

- 路徑：`<專案資料夾>`
- 來源：<https://github.com/yamasoo/novel-studio>（`main`，`e26cfff`，v1.18.0；`dev` 與 `main` 同點）
- 執行：`.\start.bat`（第一次會建 `.venv` 並安裝 5 個套件，需網路）→ <http://127.0.0.1:8765>
- 檢查：`python tools/check_i18n.py`、`python tools/check_parity.py --strict`、`python tools/prompt_lang_audit.py`（都不需要模型、不花錢）

## 報告

- `docs/檢視報告-2026-10-29.md`（Markdown，可直接 diff）
- `docs/檢視報告-2026-10-29.docx`（Word 版）
- 重點：§2.2 十項實測缺陷、§3 三語方案 T1–T8、§4 續寫方案 P1–P7、§5 複雜度總表、附錄 E 的待補翻譯。
- 工作流規則（怎麼跑、擋什麼、術語表怎麼用）：`docs/i18n-workflow.md`

## 已定決策

1. 繁中仍是**唯一來源**；英日譯文是產物，不是來源。
2. 先做「事後稽核＋覆蓋率閘門」（T1–T3），**暫緩**產生式外掛（T7）與穩定鍵重構（T8）。
3. 續寫先做「合約、檢索、文風閉環、回歸測試」（P1–P4），再做「A 書→B 書」（P6）。
4. 沒有 CI 這件事已經改掉：push／PR 都會被 `.github/workflows/checks.yml` 擋。

## 目前狀態（2026-10-30，v1.18.0 已發版）

- `dev` 已於 2026-10-30 以 **squash merge** 合併回 `main`（PR `#2`，14 個 commit），發版 `v1.18.0`（`e26cfff`）。
  之前的 `v1.17.0`（PR `#1`，84 個 commit，`7274675`）是上一個基線。
  發版後 `dev` 已 `reset --hard main` 並 force push，現在與 `main` 同點。
- 之後 `dev` 是整合分支：功能 commit 進 `dev`，發版再 squash 回 `main`；**合併後要把 `dev` 對齊 `main`**
  （`git reset --hard main` ＋ `push --force-with-lease`），規則寫在 `docs/新對話交接.md`「分支與發版」。
- `check_i18n` 全過；`check_parity --strict` **FAIL 0、WARN 0**；`prompt_lang_audit` 也過；
  GitHub Actions 在 PR 與 `main` push 都綠（`checks.yml`）。
- 介面字串：`tools/i18n_keys.json` 1,628 鍵；en／ja 各 1,622 條（其餘是 `==` 同形標記）。
- `i18n/glossary.tsv`：36 條術語，`check_parity` 會抓「禁用譯法」與「表跟介面不一致」。
- 三份 README 標題分佈 **1／9／8**（2026-11-07 改成使用者導向：安裝→寫完一本書，含三張 `docs/images/*.svg` 示意圖）；
  技術內容（功能細節、各執行者、運作方式、檔案結構、貢獻者工具）搬到 `docs/開發者.md`。三本示範書 `_範本/` 都是 18 個檔。
- `tools/i18n_fill.py`：翻譯缺口 → 初翻 patch → 人工核可 → `--apply`。
- `studio/contract.py`：`設定/續寫合約.md`，priority 0 注入每章上下文（見 `docs/續寫合約.md`）。
- 書架統計有快取：`<專案>/.cache/books.json`（用「檔案數／大小／最新 mtime」的 stat 指紋失效，不讀內容）；
  冷啟動約 1 秒、熱讀約 0.1 秒。刪掉會自動重建，`.cache/` 在 `.gitignore`。
- 使用說明頁：左側「說明」→ `#/guide`，內容是 `static/guide/zh-TW.md`（靜態 Markdown，含兩個流程與名詞表；
  另有 `en.md`、`ja.md`，依介面語言自動選，找不到會 fallback 回中文）。
- 卷先行（`studio/volume.py`、`docs/卷先行.md`）：卷綱草稿→採用→整卷章綱→章綱體檢，工作台可操作。
  既有卷修訂：卷況「修訂」→ `大綱/草稿/卷綱修訂_第N卷.md` → 看 diff → 套用（備份、狀態已確認、同步大綱）；
  舊的「卷綱」直寫入口已移除。

### 第 1 週清單對照（一個項目一個 commit）

| # | 清單項目 | commit | 驗證 |
|---|---|---|---|
| 1 | CI 閘門（只擋 FAIL） | `9dfed59` | YAML 可解析；三個檢查本機全跑過 |
| 2 | check_parity：tw-terms 白名單、`==`、範本＋demo | `40ded2a` | FAIL 4 → 2（只剩沒翻的字串） |
| 3 | 補翻譯＋清失效鍵 | `1052896` | FAIL 0；1535 鍵；stale 0 |
| 4 | 術語表＋禁用譯法檢查 | `c199e68` | 術語檢查 0 條；順手統一 2 條 state card |
| 5 | S1 任意檔讀取 | `446f89f` | `book_path()` 六種越界路徑全拒 |
| 5 | S2 Origin／一次性權杖 | `a965aa4` | 跨來源／無權杖 → 403，首頁有注入 |
| 5 | S5 set_lang 缺口 | `72e2d28` | 假 en 書呼叫 review job 後 `cur_lang()==en` |

> 附錄 E 原本列 13 句，實測是 **14 句**（多了「`{0} → {1}`／關係」那條），已一併補上。

### 第 2 週清單對照

| # | 項目 | commit | 驗證 |
|---|---|---|---|
| 1 | WARN 47 → 8：換掉提示詞的兩條誤報檢查 | `9f7ac1c` | 字元比例與「英包有中文」都是假警報（見下） |
| 2 | A7：三本示範書 `_範本/` 補成 18 個檔 | `33ff67a` | demo WARN 6 → 0 |
| 3 | A4／T6 最小方案：繁中 README 補 4 節 | `d135264` | 三份都是 1／11／20 個標題 |
| 4 | CI 改 `--strict` | `dc78cfd` | WARN 8 → 0 後才開 |
| 5 | A5：範本 `{佔位符}` 對等檢查 | `ad65ea8` | 故意改壞會被抓（測過兩種） |
| 6 | A9：驗證載入的是自己那一版的 skill | `c1dbedd` | 負向測試強制讀 plugin/ → 兩條都抓到 |
| 7 | T4：`tools/i18n_fill.py` | `5533673` | list／apply 實測；fill 用假 provider 端到端 |
| 8 | P1：`設定/續寫合約.md` ＋ priority 0 注入 | `dd09434` | 預算 4000 時合約還在，其餘被丟 |

**兩個「報告說錯」的地方（重要，不要再重做一次）**

- **A8「英文是繁中 2.9 倍 → 內容不對稱」是指標問題。** 中文算字元、英文算單詞，整包 2.95 倍屬正常；
  15 條離群全是誤報（短標籤、格式列）。現在改比**句數**（ja 全部 1.00、en 最低 0.67，低於 0.6 才警告）。
- **A9「prompt_lang_audit 固定讀 plugin/」是誤報。** `plugin/` 只是基底，切換在
  `context.lang_plugin／skill_ref`（依 `prompts.cur_lang()`）；探針實測 en 書讀 plugin-en、ja 讀 plugin-ja。
  現在每次跑都會驗「該版在、別版不在」。

### 第 3 週清單對照

| # | 項目 | commit | 驗證 |
|---|---|---|---|
| 1 | P4：`tools/book_eval.py` 回歸測試 | `86dbe7e` | 三書×三任務跑完；指標對照已知答案；基線退步 → exit 1 |
| 2 | P3：文風保真閉環（`studio/style_loop.py`） | `ad80768` | 校準 0 明顯／走鐘 7 明顯；假模型先回走鐘稿 → 2 次呼叫、採用重寫版、匯報有 13 指標表 |

### 第 4 週

| # | 項目 | commit | 驗證 |
|---|---|---|---|
| 1 | P2：檢索式長期記憶（`studio/recall.py`） | 本 commit | 25 章合成書：查玉珮 → 4 段全是玉珮場景、全在第 21 章之前；上下文 +2.2%（<15%） |

### 第 5 週（選配）

| # | 項目 | commit | 驗證 |
|---|---|---|---|
| 1 | P5：大綱漂移偵測（`studio/drift.py`、`tools/drift.py`） | `86d9034` | 273 章書第 258–273 章：18 條偏離（2 位配角失蹤、300 條未回收伏筆最久 272 章、3 章文風偏離 ≥1.2 倍） |
| 2 | P7：自動駕駛檢查點（`studio/autopilot.py`） | `daee61d` | 每 2 章檢查：全過 → 5 章跑完、檢查點記在 2／4；第 2 章沒過 → 停在 paused、下一章 3 |

### P6（A 書→B 書）進度

| 步 | 項目 | commit | 驗證 |
|---|---|---|---|
| 0 | 相似度基準與門檻（`studio/similarity.py`、`tools/similarity.py`） | `4088127` | 語言差很大：zh containment 0.034／LCS 0 字、ja 0.081／0、en 0.347／33 字；照抄 1200 字 → 1.000／982 字、換名字 → 0.877／111 字 |
| 1 | 風格指紋（`studio/fingerprint.py`、`tools/fingerprint.py`） | `dcbd67b` | 三本真書都產得出；同一本書跑兩次逐位元組相同；代表句不撞來源名字（0 個）；副本上寫檔 2,187 bytes 可讀回 |
| 2 | 結構 DNA（`studio/sdna.py`、`tools/sdna.py`） | `2dfe203` | 四本真書：視角判得出來（3 人稱／1 人稱／混合）、DNA 兩次相同、JSON 撞名 0；副本寫檔 692 bytes |
| 4 | 護欄（`similarity.check()`、`tools/similarity.py`） | `ab475f0` | 照抄 1000 字 → containment 1.000／814 字、指到第 3/4/5 段 100%；換名字 → 0.834／111 字；自己寫的 0.02～0.024 → 可以 |
| 5 | 建專案（`studio/spawn.py`、`tools/spawn.py`） | `8218444` | 用B 書建新書：is_book True、19 項、parse_metrics 讀得到 6 項、合約 741 字、for_chapter 4,438 tokens 含章綱與文風目標、37 檔 |
| 3 | 新書骨架（`studio/spinoff.py`、`tools/spinoff.py`） | `4b1f2e0` | 假模型：禁用名單 48 個、第一次故意撞名 → 護欄擋下並重寫 → 共 3 次呼叫、最終撞名 0、草稿寫進 候選/新書草稿/ |
| 6 | 接進工作台（開新書對話框＋`/api/books/{id}/spinoff`） | 本 commit | 端點存在、前端含 nb-ref／nb-gen／spinoffGenerate、node --check 通過；spawn.seed 在 app 建的新書寫出 4 檔、指標 6 項 |

> 2026-10-31：新書多了「用參考書骨架直接開書」（跳過訪談，寫 `CLAUDE.md`／故事核心／世界觀／全書大綱／卷綱，
> 章綱之後再用卷先行排）；既有書仍只產生草稿，沒有「套用卷綱」。細節見 `docs/P6-新書骨架.md`。

## 下一步（2026-10-30 健康檢查後）

**舊清單已完成**：文風目標 A/B、`--repeat 3` 基線、T6 README 減量、續寫合約收尾、卷先行六段
（細節見各週表格與 `docs/卷先行.md`；不要再重做）。

**還沒做，依優先序**：

1. ~~**S4 任務與事件回收**~~ **已完成（2026-11-07）**：`Runner.jobs` 與 `ns_jobs.VIEWS` 各留最近 30 個
   **已結束**的任務（執行中的永遠保留；任務結束已寫進 `.studio/jobs/`，三個讀取端本來就會 fallback 讀檔，
   所以回收不掉資料）；`pipeline._wait` 加**總時長 30 分鐘＋閒置 10 分鐘**逾時，卡住時取消任務並讓那一步失敗、
   可以從那一步繼續。**刻意沒做**（2026-11-07 決策）：`Job.events` 執行中不截斷（要改 `View` 的游標契約，
   風險大於收益；單一任務的事件數有界）；`.studio/jobs/*.json` 不刪（書的 `.studio/` 是使用者資料，
   實測約 50 KB／任務，要清請自行決定）。
2. ~~**S3 原子寫檔收尾**~~ **已完成（2026-11-07）**：抽出 `project.write_atomic`（暫存檔＋`os.replace`），
   26 處會覆寫稿子／設定集／章綱／卷綱／合約的寫入點全部換掉；`.studio/備份` 每組（標籤_原檔名）留最新 30 份
   （`tracking.prune_backups`，共用庫與匯入備份也走同一套）。**還沒換的**：`.studio/` 內部紀錄（保真、
   回寫檢查、索引快取、步驟快照…）、書庫共用資產（`app.py` 共用庫存檔、`shared.py` 的文風／結構、
   `style_design.py`）、以及 `tools/` 的離線腳本；前兩批壞了影響較小但可再收。
3. **卷綱狀態語意**：舊書 32 份「正式路徑＋狀態草稿」已用 `tools/volume_status.py --apply` 轉正
   （備份在該書 `.studio/備份/`）；閘門與續寫合約**仍不看狀態**，依 2026-10-30 決策暫不收緊。
4. **自動化測試**：`tests/` 已有 4 支 unittest（`write_atomic` 的中斷保護、備份上限、繁簡守門、`ns_jobs`），
   **CI 會跑**（`checks.yml` 第一步，推 `main` 與 `dev` 都觸發）；仍缺卷綱／章綱閘門、`safe_path`、權杖的覆蓋，目前只有手動驗證。
5. **小缺口**：A6 語言檔重複鍵偵測、`tools/i18n_status.py`（T4 配套）、`contract_audit` 的「未登記角色」、
   P7 待辦檔與檢查點趨勢圖、漂移的卷末自動提示、P6 的「僅公有領域／自有作品」提示。
6. **刻意暫緩**：T7 產生式外掛、T8 穩定鍵重構（理由見「已定決策」）。

> Claude Code 模式的提示詞已經全部改走語言包（`b9ee6f8`）：review、revise、deslop、goal、
> illust、card 六個任務都不再寫死中文；`docs/i18n-workflow.md` 有新增字串時該做的三件事。

## 注意（本次新增）

- **絕對不要在書庫裡刪東西（2026-10-29 教訓）**。書的 `.studio/` 不是暫存：裡面有 `jobs/`（任務紀錄）、
  `備份/`（改檔前的舊版）、`反推/`（拆書進度與批次結果，一本 273 章的書是 91 個批次＋1.2 MB 累積）。
  那天為了清 `索引/recall.json` 一個快取，誤刪了整個 `.studio`，靠 `C:\Users\<你>\Documents\小說`
  的舊備份才補回來。要清快取就只刪 `索引/recall.json` 這一個檔，動手前先把完整路徑印出來確認。
- **S2 之後變更 API 要帶權杖**：`POST`／`PUT`／`DELETE` 需要 `X-FE-Token`（每次啟動產生、由 `fe.inject()` 寫進首頁的 `<meta name="fe-token">`），
  用 curl 或腳本直接打 API 會 403；`GET`／SSE 不受影響，頁面上的操作照常。P5 起舊的 `X-NS-Token` 不再接受。
- 驗 S2 時用 TestClient 打過 `/api/config`，`config.json` 被寫回預設值（該檔在 `.gitignore`，內容是空書庫）。
- **工作區權限（2026-10-29 實測）**：`workspace-write` 模式下只有書庫根目錄可寫，
  `docs/`、`tools/`、`.git/` 這些既有子資料夾寫不進去（自動修復工具跑過兩次仍如此），
  `git checkout -b` 會直接失敗。解法是**會話層級切到完全權限**：
  輸入框的權限控制項選「完全权限」，或直接打 `/permission danger-full-access`
  （設定 → 一般那一列只改「之後新開的會話」的預設）。切完後實測 `docs/`、`tools/`、`static/`、`.git/`
  都可寫，`git checkout -b` 正常。沙箱模式本身還是壞的，只是被繞過；要根治得處理那幾個資料夾缺的寫入授權。
- **在 DSH 工作階段裡跑 app：把 venv 放在專案外**（2026-10-29 實測）。從專案內的 `.venv` 啟動的 Python
  會被限制成「只能寫工作區」，於是書庫（`<書庫>`）、示範書複製、`config.json` 都會 `WinError 5 存取被拒`；
  換成專案外的 venv（`C:\Users\<你>\venvs\novel-studio`）同樣動作就全部成功，系統 Python 也成功。
  所以不是資料夾權限、也不是程式問題。啟動方式：

  ```powershell
  cd <專案資料夾>
  $env:NS_VENV = 'C:\Users\<你>\venvs\novel-studio'   # 或 setx 一次，之後新視窗都有
  .\start.bat
  ```

  `start.bat`／`start.sh` 都支援 `NS_VENV`，沒設就用專案內的 `.venv`。
  一般 Windows 環境（直接雙擊 `start.bat`，不經過這個工作階段）用專案內 `.venv` 是正常的。
- **`start.bat` 必須是 UTF-8（無 BOM）＋ CRLF**（2026-10-29 實測）。改成 LF 行尾時，cmd 會把
  多行 `if ( … )` 區塊接錯行，跑起來是一堆「不是內部或外部命令」的亂碼錯誤；存成 CP950 或 UTF-16 也會壞。
  改這個檔案請用會保留 CRLF 的編輯器（VS Code 右下角確認「CRLF」）。
- **任務紀錄會累積（2026-11-07 決策）**：`.studio/jobs/` 每個任務一個 json（實測約 50 KB，事件佔多數），
  記憶體只留最近 30 個已結束的任務，磁碟**不自動清理**。長期大量跑自動流程的書，這個資料夾會慢慢長大；
  要清就自己決定（先確認任務紀錄不再是需要的歷史）。
- **產出的繁體保護（2026-11-07）**：繁體書的模型產出在落檔前會過 `textguard.guard_text`／`guard_data`
  （設定集、追蹤、續寫合約、卷綱、骨架、視覺卡）：少量簡體字逐字轉繁、台灣用語對照、全形標點；
  整段偏簡體（>20 字）**不轉**，只回報「建議重跑」。說明走原本的回報通道（任務結果／warnings／後端視窗）。
  結構化 JSON 另外在 `lang_mismatch` 判簡體，會先請模型重寫一次。轉換需要 OpenCC（`requirements.txt` 有）。
- 舊的 clone 在 `<舊的 clone>`（OneDrive 底下，`.git` 同步容易衝突）；以 `<專案資料夾>` 為準。
- 不要直接把 AI 初翻 merge 進語言檔：先出 patch、人工核可（見報告 T4）。
- **repo 目前是 public**（2026-10-30 確認）。`main` 已用 squash 保持乾淨，但 PR `#1` 頁面與 `dev` 歷史仍看得到
  早期兩個帶作品名的 commit 訊息與舊版文件的本機路徑；要徹底清除得重建 repo 或請 GitHub Support 處理。

## 驗證指令

```powershell
cd <專案資料夾>
python -m unittest discover -s tests -p "test_*.py"   # 單元測試（CI 也會跑）
python tools/check_i18n.py               # 應印「全部通過」
python tools/check_parity.py --strict    # 應印 FAIL 0、WARN 0（--strict：WARN 也擋）
python tools/prompt_lang_audit.py        # en／ja 送出的訊息沒有中文句子
python tools/book_eval.py                # 假 provider 冒煙，不花錢
node --check static/app.js               # 前端語法
```
