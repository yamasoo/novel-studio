# 三語工作流（繁中 → 英／日）

> 原則：繁中是**唯一來源**，英日譯文是產物。檢查器保證「三份沒有走鐘」，不保證「譯得好」。

## 一個指令看狀態

```powershell
python tools/check_i18n.py       # 提示詞包的鍵／變數、語言檔變數與空值、路徑不被翻譯
python tools/check_parity.py     # 結構對等＋介面翻譯覆蓋率＋翻譯新鮮度（FAIL 回傳 1）
python tools/prompt_lang_audit.py  # 假 provider 跑 3 章，列出 en／ja 書送出的中文（不花錢）
```

三者都不呼叫真模型。CI（`.github/workflows/checks.yml`）在 push 與 PR 上跑同一組指令。

## 現在擋什麼、不擋什麼

| 檢查 | FAIL（擋 push） | WARN（只印出來） |
|---|---|---|
| `check_i18n` | 鍵或 `{變數}` 不一致、空值、路徑被翻譯 | — |
| `check_parity` | 外掛檔案不對等、SKILL frontmatter／標題層級／引用不同、範本缺檔、README 連到不存在的路徑、介面字串沒翻 | README 標題分佈、表格列數、提示詞長度比例、失效舊鍵、翻譯新鮮度 |
| `prompt_lang_audit` | 送出的訊息含中文句子 | — |

WARN 燒完（`check_parity --strict` 無 WARN）之後，才把 CI 改成 `--strict` 並讓 WARN 也擋。

## 翻譯新鮮度（`tools/i18n.lock.json`）

lock 記下每一組「繁中檔／en 檔／ja 檔」的 sha256。改了繁中但 en／ja 沒動，`check_parity` 會 WARN
「待更新翻譯」，直接指出要補哪一個檔——不需要人工 diff。發版前跑：

```powershell
python tools/check_parity.py --update-lock   # 三語都補完、確認過，才更新基準
```

## 不要直接改中文文案

`static/i18n.js` 用**中文原文當 key**，改一個字等於換一把鎖，英日翻譯會靜默失效（目前累積的失效鍵就是這樣來的）。
所以：

- 需要改說法時，**新增一句**並把舊句留著，等譯文跟上、`check_parity` 的失效鍵 WARN 歸零，再刪舊句。
- 只是換標點或全形半形，也走同一條路。

## 介面字串

- 新增使用者看得到的文字時，同時補 `static/locales/en.json` 與 `ja.json`，否則 `check_parity` 會 FAIL「沒翻」。
- 路徑、檔名、語言名稱這類三語本來就相同的字串，等值填 `"=="`（同形標記），不要用假翻譯充數。
- 譯文品質由人工核可；AI 只產出 patch，不直接改正式檔（見檢視報告 T4）。
