# 第三方授權聲明

本專案自己撰寫的程式碼以 [MIT 授權](LICENSE) 發布。下表是**隨專案一起散佈**的第三方檔案；
授權全文都放在同一資料夾或子資料夾，不連網載入。

| 名稱 | 版本 | 授權 | 檔案 | 來源 |
|---|---|---|---|---|
| fekit | 0.0.1 | MIT | `vendor/fekit/`（`fe/`、`css/`、`py/fekit/`） | 內部前端套件，複製品與同步資訊見 `vendor/fekit/VENDORED.md`、`vendor/fekit/THIRD_PARTY_NOTICES.md` |
| marked | 18.1.3 | MIT（LICENSE 另含 Markdown 原作者的 BSD-3-Clause 條文） | `vendor/fekit/vendor/marked/marked.umd.js`、`vendor/fekit/vendor/marked/LICENSE` | npm `marked@18.1.3`，經 fekit 同步進來 |
| Cytoscape | 3.34.4 | MIT | `vendor/fekit/vendor/cytoscape/cytoscape.min.js`、`vendor/fekit/vendor/cytoscape/LICENSE` | npm `cytoscape@3.34.4`，經 fekit 同步進來（角色關係圖） |
| oh-story-claudecode | — | MIT | 只參考設計概念，未使用其程式碼 | <https://github.com/worldwonderer/oh-story-claudecode>，授權全文見 `plugin/THIRD_PARTY_NOTICES.md` |

## 說明

- **前端不再自帶 marked**：`FE.md` 用的是 fekit 帶的 `vendor/fekit/vendor/marked`，舊的
  `static/vendor/marked.min.js` 與 `static/vendor/marked.LICENSE.md` 已刪除（本專案的 `static/vendor/` 目錄整個移除）。
- **Python 套件不隨專案附帶**：FastAPI（MIT）、Uvicorn（BSD-3-Clause）、PyYAML（MIT）、
  opencc-python-reimplemented（Apache-2.0）由 `requirements.txt` 安裝到 `.venv`，授權見各自的套件說明。
- **介面文字與流程的參考來源**（未使用程式碼）：moshu 墨書、Pagekin（AI-Novel-Writer）、Novelcrafter、
  Sudowrite、Scriveno、Leech & Short《Style in Fiction》、Chinese-WebNovel-Skill，清單見「關於」頁。
- **執行時不連 CDN**：所有前端檔案都由本機的 `/static/` 與 `/fekit/` 提供。
- 第三方以 MIT 優先；0BSD、BSD、ISC、Apache-2.0 在版本紀錄中說明理由；GPL 類不採用（Pagekin 只參考概念、未使用程式碼）。
