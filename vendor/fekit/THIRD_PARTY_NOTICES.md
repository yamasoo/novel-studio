# THIRD_PARTY_NOTICES

`vendor/fekit/vendor/` 內每個第三方檔案都要附上自己的 LICENSE，並登記在這裡。
授權以 MIT 優先；0BSD、BSD、ISC、Apache-2.0 需在階段報告說明理由；GPL 類不採用。

| 名稱 | 版本 | 授權 | 檔案 | 來源 |
|---|---|---|---|---|
| marked | 18.1.3 | MIT（LICENSE 另含 Markdown 原作者的 BSD-3-Clause 條文，見下） | `vendor/marked/marked.umd.js`、`vendor/marked/LICENSE` | npm `marked@18.1.3`，`lib/marked.umd.js` |
| Cytoscape.js | 3.34.4 | MIT | `vendor/cytoscape/cytoscape.min.js`、`vendor/cytoscape/LICENSE` | npm `cytoscape@3.34.4`，`dist/cytoscape.min.js` |

## 說明

- **只改過一處**：刪掉檔尾的 `//# sourceMappingURL=...` 註解（沒有附 `.map` 檔，留著開發者工具會一直 404）。其餘與 npm 套件內容逐位元組相同。
- **marked 的 BSD-3-Clause 條文**：marked 的 `LICENSE` 在 MIT 本文之後，另附其 Markdown 解析規則所沿用的 John Gruber《Markdown》的 BSD-3-Clause 條文。整份 `LICENSE` 原樣隨檔案放在 `vendor/marked/`，散佈時要一起帶著。
- **Cytoscape.js 打包進單一檔案的程式**：Thenable（Ralf S. Engelschall，MIT）、Framer.js 彈簧函式（Koen Bok，MIT）、Bezier 函式（Gaetan Renaudeau，MIT）；依其原始碼的 `import` 與 `package.json`，還有 lodash（debounce、get、set、toPath）、heap、gl-matrix，三者皆為 MIT。沒有任何一項是 MIT 以外的授權。
- 以上都不連網載入，執行時只讀 `vendor/fekit/vendor/` 內的檔案。
