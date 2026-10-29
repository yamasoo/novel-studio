# 三語工作流（繁中 → 英／日）

> 原則：繁中是**唯一來源**，英日譯文是產物。檢查器保證「三份沒有走鐘」，不保證「譯得好」。

## 一個指令看狀態

```powershell
python tools/check_i18n.py       # 提示詞包的鍵／變數、語言檔變數與空值、路徑不被翻譯
python tools/check_parity.py     # 結構對等＋介面翻譯覆蓋率＋翻譯新鮮度（FAIL 回傳 1）
python tools/prompt_lang_audit.py  # 假 provider 跑 3 章，列出 en／ja 書送出的中文（不花錢）
```

三者都不呼叫真模型。CI（`.github/workflows/checks.yml`）在 push 與 PR 上跑同一組指令，
而且 `check_parity` 是以 `--strict` 跑的：**WARN 也會擋**（2026-10-29 起 WARN 歸零）。

## 現在擋什麼

| 檢查 | FAIL（擋 push） | WARN（`--strict` 下也擋） |
|---|---|---|
| `check_i18n` | 鍵或 `{變數}` 不一致、空值、路徑被翻譯 | — |
| `check_parity` | 外掛檔案不對等、SKILL frontmatter／標題層級／引用不同（繁中專屬檔已白名單）、範本缺檔、README 連到不存在的路徑、介面字串沒翻 | README 標題分佈、失效舊鍵、翻譯新鮮度、示範書 `_範本/` 檔案集不一致、術語表禁用譯法、提示詞句數少一半 |
| `prompt_lang_audit` | 送出的訊息含中文句子；載入到別版的 skill 內文（en 書卻讀到 `plugin/`） | — |

本機要看得寬鬆一點就跑不帶參數的 `python tools/check_parity.py`（只擋 FAIL）。

## 改繁中之前先想一下

`check_parity --strict` 在 CI 上會擋「繁中改了、en／ja 沒動」——這是刻意設計：它讓「翻譯還沒跟上」
變成紅燈，而不是靠人記得。所以改繁中內容的那個 PR 要把三語一起補，或先在本機確認、跑
`--update-lock` 並說明為什麼譯文不用改（例如只是把繁中補成英日已經有的內容）。

### 為什麼不比字元長度比例

早期版本用「英文長度 ÷ 繁中長度，超出 0.35～4.5 就 WARN」。實測 15 條離群**全是誤報**：
中文用字元、英文用單詞，短標籤（`整章` → `whole chapter`）與格式列（`字數：{0}` → `Words: {0}`）
的比例本來就從 1.0 到 5.1 都有可能。整包 en／ja 是繁中的 2.95 倍／1.43 倍，這也屬正常範圍。

真正要抓的是「漏翻一句」或「截斷一段」，所以改成**比句數**：同一段話的句子數跨語言幾乎不變
（實測 ja 全部 1.00、en 最低 0.67——那是英文用分號把兩句併成一句），低於 0.6 才算異常。
英文包裡殘留的中文則交給 `check_i18n` 判斷：它會先剝掉路徑、`第NNN章`、JSON 鍵名、「」欄位名、
表格列與 `<<<>>>` 標記，所以 `設定/故事核心.md`、`狀態：草稿` 這種資料格式不會被誤判成漏翻。

## 範本佔位符

`plugin*/skills/novel-setup/templates/` 的 17 個範本裡有 `{…}` 佔位符，是給模型看的「填這裡」指示。
模型會照抄，所以三版必須對得上。`check_parity` 驗三件事：

1. **數量對等**：同一個範本在三版的 `{…}` 數量要一樣（少了就是漏抄一個欄位）。
2. **一對一**：同一個繁中佔位符，在 en 只能有一種寫法、在 ja 也只能有一種（不能這份寫 `{topic}`、那份寫 `{subject}`）。
3. **語言別混**：en 的佔位符不能是中文；繁中／日文的佔位符不能混拉丁字母（`{N}` 除外）。

現行的對照（改範本時照這張表）：

| 繁中 | English | 日本語 |
|---|---|---|
| `{主題}` | `{topic}` | `{項目名}` |
| `{卷名}` | `{volume title}` | `{巻のタイトル}` |
| `{章名}` | `{title}` | `{題名}` |
| `{角色名}` | `{character name}` | `{人物名}` |
| `{勢力名}` | `{faction name}` | `{勢力名}` |
| `{名稱}` | `{name}` | `{名前}` |
| `{N}` | `{N}` | `{N}` |

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
- 譯文品質由人工核可；AI 只產出 patch，不直接改正式檔（見下面 T4）。

## 翻譯缺口 → 初翻 patch（`tools/i18n_fill.py`）

```powershell
python tools/i18n_fill.py --list              # 缺哪幾條、哪些建議填 "=="、有待核可的初翻
python tools/i18n_fill.py --fill              # 呼叫模型初翻 → i18n/pending/<lang>.json ＋ .review.md
python tools/i18n_fill.py --apply --lang en   # 人工核可後才併進 static/locales/
```

- `--fill` 需要 OpenAI 相容的執行者（`--provider deepseek` 之類）；Claude Code 不行。CI 不會跑這支。
- 送給模型的是**只有缺口的那幾條**＋術語表，不是整包語言檔；路徑類字串不送模型，直接建議 `==`。
- 模型只寫 `i18n/pending/`：`<lang>.json` 是機器可讀的提案，`<lang>.review.md` 是給人核可的兩欄表。
  `--apply` 之前請看過 review 檔——這是「人工只花在判斷」的那一步。
- `--apply` 之後跑 `python tools/check_i18n.py` 與 `python tools/check_parity.py --update-lock`，
  前者驗變數與路徑沒被翻壞，後者把新譯文登記成新的翻譯基準。

## 術語表（`i18n/glossary.tsv`）

「同一個概念，三語各叫什麼」只有一個答案：`zh`、`en`、`ja`、`禁用譯法`、`備註` 五欄，Tab 分隔。
`check_parity` 會做兩件事：

1. 語言檔與 `README.en.md`／`README.ja.md` 出現「禁用譯法」→ WARN（有人用了別的說法）。
2. 術語在介面語言檔裡有對應 key 時，值必須與表一致 → WARN（表與實作走鐘）。

新增概念（例如 P1 的「續寫合約」）時，先加一列到表裡，再改介面與提示詞——這樣「伏筆」「章綱」「讀者認知」
這類詞不會在 UI、提示詞、README 三處各長一個樣子。
