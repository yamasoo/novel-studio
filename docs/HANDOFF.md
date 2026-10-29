# HANDOFF：Novel Studio 三語與續寫改善

> 這份檔案給「下一個對話」或「未來的自己」看。看完這一頁就能接手，不需要重讀整份報告。

## 專案

- 路徑：`<專案資料夾>`
- 來源：<https://github.com/yamasoo/novel-studio>（`main`，commit `4e20b45`，v1.16.2）
- 執行：`.\start.bat`（第一次會建 `.venv` 並安裝 5 個套件，需網路）→ <http://127.0.0.1:8765>
- 檢查：`python tools/check_i18n.py`、`python tools/check_parity.py`（不需要模型、不花錢）

## 報告

- `docs/檢視報告-2026-10-29.md`（Markdown，可直接 diff）
- `docs/檢視報告-2026-10-29.docx`（Word 版）
- 重點：§2.2 十項實測缺陷、§3 三語方案 T1–T8、§4 續寫方案 P1–P7、§5 複雜度總表、附錄 E 的 13 句待補翻譯。

## 已定決策

1. 繁中仍是**唯一來源**；英日譯文是產物，不是來源。
2. 先做「事後稽核＋覆蓋率閘門」（T1–T3），**暫緩**產生式外掛（T7）與穩定鍵重構（T8）。
3. 續寫先做「合約、檢索、文風閉環、回歸測試」（P1–P4），再做「A 書→B 書」（P6）。
4. 目前**沒有任何 CI**；第 1 週的目標就是把紀律變成機器。

## 目前狀態（2026-10-29）

- repo 在 `main`，工作區是乾淨的；以下是**未追蹤**的新增物，等第 1 週一起 commit：
  - `tools/check_parity.py`（結構對等＋翻譯新鮮度檢查器）
  - `tools/i18n.lock.json`（翻譯基準，30 組）
  - `docs/`（本報告與交接檔）
  - `docs/ci-checks.yml`（CI 草稿）
- 基準檢查結果：`check_i18n` 全過；`check_parity` **FAIL 4、WARN 45**。
  - FAIL 2 條是 locale 缺 13 句（英日各 13）＋2 條是 `tw-terms.md` 誤報（要加白名單）。

## 下一步（第 1 週清單）

1. 把 `docs/ci-checks.yml` 放成 `.github/workflows/checks.yml`（先只擋 FAIL）。
2. `tools/check_parity.py`：加 `tw-terms.md` 白名單；locale 檢查加「`==` 同形標記」；納入 17 個範本與 demo。
3. 補 13 句翻譯（報告附錄 E 已有英日譯文）；清 319／320 個失效鍵。
4. 建 `i18n/glossary.tsv`（術語表）並讓 `check_parity` 檢查禁用譯法。
5. 修 S1（`app.py:372` 路徑驗證）、S2（Origin／CSRF）、S5（請求執行緒 `set_lang`）。
6. 開分支 `chore/i18n-guardrails`，一個項目一個 commit；每完成一項回報 `git diff --stat` 與驗證指令。

## 驗證指令

```powershell
cd <專案資料夾>
python tools/check_i18n.py
python tools/check_parity.py
git status --short
```

## 注意

- 舊的 clone 在 `<舊的 clone>`（OneDrive 底下，`.git` 同步容易衝突）；以 `<專案資料夾>` 為準。
- 不要直接把 AI 初翻 merge 進語言檔：先出 patch、人工核可（見報告 T4）。
- 這份檔案可以隨時刪，不需要進版控；要進版控就放 `docs/`。
