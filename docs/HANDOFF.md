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

- 分支 `chore/i18n-guardrails`，8 個 commit，**尚未 merge 回 `main`**。
- `check_i18n` 全過；`check_parity` **FAIL 0、WARN 47**（起點是 FAIL 4、WARN 45）。
- 介面字串：en／ja 都收斂到 1535 鍵，missing 0、stale 0、empty 0；16 條路徑／檔名類填 `==`（同形標記）。
- `i18n/glossary.tsv`：23 條術語，`check_parity` 會抓「禁用譯法」與「表跟介面不一致」。
- 翻譯基準 `tools/i18n.lock.json`：30 → 80 組（+17 範本、+33 個示範書檔案）。

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

## 下一步（第 2 週）

1. **WARN 燒減**：47 條最大宗是提示詞長度比例（en 是繁中的 2.9 倍，A8）與 README 標題分佈（A4）。
   清到 0 之後，CI 的 `check_parity` 才能改 `--strict`。
2. **T3 剩下的**：範本佔位符比對（A5：`{主題}`／`{topic}`／`{項目名}`）。
3. **A7**：繁中示範書缺 `_範本/讀者認知.md`、`關係.md`，多了 `專案規範.md`——補檔或列白名單，選一個。
4. **A9**：`prompt_lang_audit.py` 固定讀 `plugin/`；另外這次發現 `claude_review_job`／`claude_revise_job`
   的提示詞本身是**硬寫繁中**，en／ja 書會收到中文指令（S5 只補了 contextvar，沒動文案）。
5. T4 翻譯工作流（`i18n_fill.py`）與 P1 續寫合約。

## 注意（本次新增）

- **S2 之後變更 API 要帶權杖**：`POST`／`PUT`／`DELETE` 需要 `X-NS-Token`（每次啟動產生、注入首頁），
  用 curl 或腳本直接打 API 會 403；`GET`／SSE 不受影響，頁面上的操作照常。
- 驗 S2 時用 TestClient 打過 `/api/config`，`config.json` 被寫回預設值（該檔在 `.gitignore`，內容是空書庫）。
- **工作區權限**：只有根目錄可寫，`docs/`、`tools/`、`.git/` 這些既有子資料夾在受限沙箱下寫不進去
  （自動修復工具跑過兩次仍如此）。第 1 週的 git 指令都是在「完全權限」下執行的；
  換 clone 或換機器前先確認這一點，否則 `git checkout -b` 會直接失敗。
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
