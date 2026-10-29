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

## 下一步（第 3 週還沒做的）

1. **P3 文風保真閉環**：把 `shared.compare` 的 13 指標接進寫稿／去 AI 味之後，偏離就帶數字重寫一次。
   有了 P4 的指標，P3 的門檻可以先在示範書上校準，再進流程。
2. **P4 的第二階段**（等有 API 金鑰時）：
   - 用真 provider 跑一次，把 `eval/results/*-real.json` 複製成 `eval/baseline.json` 提交，之後每次改提示詞都比它
   - 之後才考慮加「LLM 評分（固定 rubric）」，而且要跟確定性指標分開看
   - 長篇 fixture（20 章以上）才能驗「第 30 章之後」的行為
3. **T6 完整版**（選配）：把安裝／後端設定搬到 `docs/<lang>/`，README 只留導覽；現在只做了結構對齊。
4. **續寫合約的兩件收尾**：
   - Claude Code 模式還沒吃到合約（`plugin*/skills/novel-setup/references/claude-md-template.md` 要加一行，三份）
   - 「連續 10 章零衝突」還沒量：要真的跑十章＋長篇 fixture，P4 才量得出來

> Claude Code 模式的提示詞已經全部改走語言包（`b9ee6f8`）：review、revise、deslop、goal、
> illust、card 六個任務都不再寫死中文；`docs/i18n-workflow.md` 有新增字串時該做的三件事。

## 注意（本次新增）

- **S2 之後變更 API 要帶權杖**：`POST`／`PUT`／`DELETE` 需要 `X-NS-Token`（每次啟動產生、注入首頁），
  用 curl 或腳本直接打 API 會 403；`GET`／SSE 不受影響，頁面上的操作照常。
- 驗 S2 時用 TestClient 打過 `/api/config`，`config.json` 被寫回預設值（該檔在 `.gitignore`，內容是空書庫）。
- **工作區權限（2026-10-29 實測）**：`workspace-write` 模式下只有書庫根目錄可寫，
  `docs/`、`tools/`、`.git/` 這些既有子資料夾寫不進去（自動修復工具跑過兩次仍如此），
  `git checkout -b` 會直接失敗。解法是**會話層級切到完全權限**：
  輸入框的權限控制項選「完全权限」，或直接打 `/permission danger-full-access`
  （設定 → 一般那一列只改「之後新開的會話」的預設）。切完後實測 `docs/`、`tools/`、`static/`、`.git/`
  都可寫，`git checkout -b` 正常。沙箱模式本身還是壞的，只是被繞過；要根治得處理那幾個資料夾缺的寫入授權。
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
