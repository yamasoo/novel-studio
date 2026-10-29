# HANDOFF：Novel Studio 三語與續寫改善

> 這份檔案給「下一個對話」或「未來的自己」看。看完這一頁就能接手，不需要重讀整份報告。

## 專案

- 路徑：`<專案資料夾>`
- 來源：<https://github.com/yamasoo/novel-studio>（`main`，commit `4e20b45`，v1.16.2）
- 執行：`.\start.bat`（第一次會建 `.venv` 並安裝 5 個套件，需網路）→ <http://127.0.0.1:8765>
- 檢查：`python tools/check_i18n.py`、`python tools/check_parity.py`、`python tools/prompt_lang_audit.py`（都不需要模型、不花錢）

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

## 目前狀態（2026-10-29，第 1 週完成）

- 分支 `chore/i18n-guardrails`，**18 個 commit**，尚未 merge 回 `main`。
- `check_i18n` 全過；`check_parity` **FAIL 0、WARN 0**（`--strict` 也過），CI 從第 2 週起就是 `--strict`。
- 介面字串：en／ja 都收斂到 1535 鍵，missing 0、stale 0、empty 0；16 條路徑／檔名類填 `==`（同形標記）。
- `i18n/glossary.tsv`：23 條術語，`check_parity` 會抓「禁用譯法」與「表跟介面不一致」。
- 翻譯基準 `tools/i18n.lock.json`：30 → 83 組（+17 範本、+36 個示範書檔案）。
- 三份 README 標題樹一致（1／11／20）；三本示範書 `_範本/` 都是 18 個檔。
- `tools/i18n_fill.py`：翻譯缺口 → 初翻 patch → 人工核可 → `--apply`。
- `studio/contract.py`：`設定/續寫合約.md`，priority 0 注入每章上下文（見 `docs/續寫合約.md`）。

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

## 下一步

1. **驗「文風目標」有沒有用已完成**（2026-10-29 A/B，見 `docs/文風閉環.md`）：同一支模型、同一批書，
   比「提示詞裡有沒有那串數字」。中文長篇的對白比例明顯改善（a-200 平均 48% → 24%，目標 19%）、
   b-40 只是從偏高變成略低、日文那本反而更偏（37% → 48%），a-200 的最大偏離同時變大。
   要再調的話，先把 after 樣本補到 4 個以上。
2. **重建基線（`--repeat 3`）已完成**（`f70ada0`）：9 次生成、1,241 秒，結果在 `eval/baseline.json`。
   單次抖動很大（同一章 `style_max_rel` 0.95／1.32／2.05），判讀請用中位數；
   這次 a-200 的 `style_max_rel` 由 0.96 升到 1.68，其他兩本反而降。
3. **P5 的收尾**：工作台按鈕與卷末提示（目前只有 CLI）、`--plan-out` 貼回卷綱的流程。
4. **T6 已完成**（T6 完整版）：需求／安裝／設定後端／設定四個區段搬到 `docs/安裝與設定.md`、
   `docs/en/install.md`、`docs/ja/install.md`；README 只留導覽與文件索引（三語標題分佈仍是 1／8／17）。
5. **續寫合約收尾已完成**：
   - Claude Code 模式的三份 `claude-md-template.md` 都加了「鐵律 5：寫正文前先讀 `設定/續寫合約.md`」，
     合約優先於大綱與文風。
   - 量測方式：`tools/contract_audit.py`（本機、零成本）拿設定回頭對正文，查「提前登場（≥15 章）」與
     「久別重逢（≥30 章，只看主角／配角）」；實測 B 書 0 處、A 書 2 處、C 書 23 處。
   - 「連續 10 章零衝突」已實跑（2026-10-29）：複製一本 50 章的書→連寫 51～60 章→
     `contract_audit` 回報 0 處；自動駕駛檢查點 55／60 都通過。細節與用量見 `docs/續寫合約.md`。
6. **卷先行（可用）**：續寫前先「卷綱草稿 → 討論確認 → 定案 → 整卷章綱」。
   - 2026-10-29 完成第一段：`studio/volume.py` 統一解析卷綱；合約與漂移不再退回錯的卷；
     整章自動流程遇到不在任何卷綱範圍內的章節會直接拒絕（409，訊息指出缺哪幾章）。
   - 2026-10-29 完成第二段：大綱頁多了「卷況」卡——「開新卷」產生 `大綱/草稿/卷綱_第N卷.md`、
     「採用」搬到正式卷綱（狀態改已確認）、「排這一卷的章綱」沿用既有章綱表單（先給總覽）；
     草稿也列進左側清單，可直接開檔編輯。
   - 2026-10-29 完成第三段：整章自動流程要求範圍內每一章都先有章綱，缺章綱就拒絕並叫你先排這一卷的章綱。
   - 2026-10-29 完成第四段：卷綱更新草稿也收進 `大綱/草稿/`（`卷綱更新_第a-b章.md`），跟新卷草稿同一個資料夾、
     用檔名與用途分開；大綱頁看得到、可編輯。
   - 2026-10-30 完成第五段：續寫合約接進「卷綱草稿」與「章綱」的上下文；採用卷綱時把這一卷追加進
     `大綱/全書大綱.md` 的分卷（只追加，範圍不同只警告）。
   - 剩下：卷末體檢的更新草稿與新卷草稿是否共用同一套資料夾／狀態欄位。見 `docs/卷先行.md`。

> Claude Code 模式的提示詞已經全部改走語言包（`b9ee6f8`）：review、revise、deslop、goal、
> illust、card 六個任務都不再寫死中文；`docs/i18n-workflow.md` 有新增字串時該做的三件事。

## 注意（本次新增）

- **絕對不要在書庫裡刪東西（2026-10-29 教訓）**。書的 `.studio/` 不是暫存：裡面有 `jobs/`（任務紀錄）、
  `備份/`（改檔前的舊版）、`反推/`（拆書進度與批次結果，一本 273 章的書是 91 個批次＋1.2 MB 累積）。
  那天為了清 `索引/recall.json` 一個快取，誤刪了整個 `.studio`，靠 `C:\Users\<你>\Documents\小說`
  的舊備份才補回來。要清快取就只刪 `索引/recall.json` 這一個檔，動手前先把完整路徑印出來確認。
- **S2 之後變更 API 要帶權杖**：`POST`／`PUT`／`DELETE` 需要 `X-NS-Token`（每次啟動產生、注入首頁），
  用 curl 或腳本直接打 API 會 403；`GET`／SSE 不受影響，頁面上的操作照常。
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
- 舊的 clone 在 `<舊的 clone>`（OneDrive 底下，`.git` 同步容易衝突）；以 `<專案資料夾>` 為準。
- 不要直接把 AI 初翻 merge 進語言檔：先出 patch、人工核可（見報告 T4）。

## 驗證指令

```powershell
cd <專案資料夾>
python tools/check_i18n.py          # 應印「全部通過」
python tools/check_parity.py        # 應印 FAIL 0、WARN 47（WARN 還沒燒完）
python tools/prompt_lang_audit.py   # en／ja 送出的訊息沒有中文句子
git diff --stat main...HEAD
```
