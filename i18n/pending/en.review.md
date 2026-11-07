# en 初翻待核可（2026-11-07 07:46）

核可後：python tools/i18n_fill.py --apply --lang en，再跑
python tools/check_i18n.py、python tools/check_parity.py --update-lock。

| # | 中文原文 | 建議譯文 |
|---|---|---|
| 1 | 1. 要畫哪一段 | 1. Which passage to illustrate |
| 2 | AI 產生的結果（從時間線轉換，或回收比對；比對的逐條理由在草稿最後，按「編輯草稿」可以看）。請檢查：有沒有把你的底牌寫成讀者已經在懷疑的懸念、有沒有漏掉你刻意埋的誤導、回收章對不對。 | AI result (converted from the timeline, or a thread-recovery comparison; the reason for each item is at the end of the draft, see “Edit draft”). Please check: did a card you kept hidden become a reader suspicion, did a misdirection you planted on purpose go missing, and is the recovery chapter right. |
| 3 | API 金鑰 | API key |
| 4 | ComfyUI 出圖設定 | ComfyUI image settings |
| 5 | Forge 出圖中 {0}% | Forge generating {0}% |
| 6 | GitHub 專案 | GitHub project |
| 7 | LoRA（出圖時加進提示詞： | LoRA (added to the prompt when generating:  |
| 8 | MOSS-Image 會照引號裡的字畫出來，中文、英文都可以（英文最穩）。要換行就在文字裡打 {0}n。最多 6 條；沒有加就不放文字。 | MOSS-Image draws the text inside the quotes, and Chinese or English both work (English is the safest). To break the line, type {0}n inside the text. Up to 6 items; add none and no text is drawn. |
| 9 | MOSS-Image 會自動改用自然語言，不加品質、分級與畫師標籤。 | MOSS-Image switches to natural language and adds no quality, rating, or artist tags. |
| 10 | MOSS-Image 用英文自然語言，不加品質、分級與畫師標籤 | MOSS-Image uses English natural language, with no quality, rating, or artist tags |
| 11 | {0}，共 {1} 章 | {0}, {1} chapters in total |
| 12 | ·　{0} 份 | ·　{0} files |
| 13 | ·　更新至： | ·　Updated:  |
| 14 | ·　自動勾選： | ·　Auto-selected:  |
| 15 | 。這只是草稿，不會改動設定或大綱；滿意再手動貼進「設定」與「大綱」。 | . This is only a draft and changes no settings or outlines. Copy it into Settings and Outline yourself when you are happy with it. |
| 16 | 」。可以勾選更多範圍再試。 | . Select more scopes and try again. |
| 17 | 」試寫一段 | ” write a sample passage |
| 18 | 下一步建議： | Next step:  |
| 19 | 下一章 | Next chapter |
| 20 | 中斷（{0}），保留了 {1} 字。 |  interrupted ({0}) and kept {1} characters. |
| 21 | 之後可以在「設定」改。 | You can change it later in Settings. |
| 22 | 份候選稿 |  candidate drafts |
| 23 | 份草稿 |  drafts |
| 24 | 份資料 |  files |
| 25 | 併入 | Merge |
| 26 | 例如 C:\\Users\\你\\.local\\bin\\claude.exe | e.g. C:\Users\you\.local\bin\claude.exe |
| 27 | 例如 D:\\ComfyUI\\models\\loras | e.g. D:\ComfyUI\models\loras |
| 28 | 例如 D:\\sd-webui-forge-neo | e.g. D:\sd-webui-forge-neo |
| 29 | 例如 {"top_p": 0.95} | e.g. {"top_p": 0.95} |
| 30 | 保留 | Keep |
| 31 | 修法： | Fix:  |
| 32 | 個角色 · {0} 個勢力 · {1} 條關係 · 第 {2} 章 |  characters · {0} factions · {1} relations · chapter {2} |
| 33 | 候選稿會還原成「{0}」開始前的版本（目前的候選稿先備份） | The candidate reverts to the version from before “{0}” started (the current candidate is backed up first) |
| 34 | 共 {0} 份檔案、{1} 處 | {0} files in total, {1} places |
| 35 | 出圖失敗： | Generation failed:  |
| 36 | 出場角色與地點 | Characters and places |
| 37 | 出現在 {0} 章正文 | appears in the text of {0} chapters |
| 38 | 分數 {0} | Score {0} |
| 39 | 切換書 | Switch book |
| 40 | 刪除 {0}？ | Delete {0}? |
| 41 | 刪除失敗：{0} | Delete failed: {0} |
| 42 | 匯入 {0} 章（{1} {2}）到《{3}》的{4}。 | Imported {0} chapters ({1} {2}) into {4} of 《{3}》. |
| 43 | 原稿：{0}　· | Original: {0}　· |
| 44 | 取樣器 {0} 種 | {0} samplers |
| 45 | 可用模型： | Available models:  |
| 46 | 各步驟另外指定： | Set per step:  |
| 47 | 名詞表另有： | Also in the glossary:  |
| 48 | 回報問題 | Report an issue |
| 49 | 回首頁 | Back to home |
| 50 | 在這裡開書 | Start a book here |
| 51 | 套用後寫回 {0}（原檔先備份 | Applying writes back to {0} (the original is backed up first |
| 52 | 套用後會存成候選稿 | Applying saves it as a candidate draft |
| 53 | 字 | characters |
| 54 | 小說工作台 v | Novel Studio v |
| 55 | 尺寸： | Size:  |
| 56 | 展開其餘 {0} 處 | Show the other {0} places |
| 57 | 工作台 | Workbench |
| 58 | 工具 | Tools |
| 59 | 已上傳 {0} 張 | Uploaded {0} images |
| 60 | 已在正文中找到 | Found in the text |
| 61 | 已套用到《{0}》 | Applied to 《{0}》. |
| 62 | 已定稿： | Finalized:  |
| 63 | 已寫入 {0} 個檔案： | Wrote {0} files:  |
| 64 | 已建立文風「{0}」 | Created the style “{0}” |
| 65 | 已採用 {0} 份 | Adopted {0} files |
| 66 | 待審 {0} | {0} to review |
| 67 | 從「{0}」重跑 | Re-run from “{0}” |
| 68 | 從角色檔的「## 關係」整理出來的，「關係」欄是角色檔那句描述原文。請檢查：對象有沒有認錯人、方向對不對、要不要把描述拆成「關係」和「態度」。 | Built from the ## Relations section of each character file; the relation column is that sentence as written there. Please check: whether a target was mistaken, whether the direction is right, and whether the description should split into relation and attitude. |
| 69 | 成員： | Members:  |
| 70 | 所屬： | Member of:  |
| 71 | 批 |  batches |
| 72 | 找不到「 | Cannot find “ |
| 73 | 找不到「{0}」 | Cannot find “{0}” |
| 74 | 找不到這個頁面。 | Page not found. |
| 75 | 拆章結果：{0} 章，{1} | Split result: {0} chapters, {1} |
| 76 | 挑動作最強的段落 | Pick the most active passage |
| 77 | 挑精華段落 | Pick the highlight passage |
| 78 | 捨棄這份 | Discard this one |
| 79 | 搬進 | Move into  |
| 80 | 改了連接埠、更新了工作台的程式檔，或服務怪怪的時候用。有任務在執行時無法重新啟動。 | Use it after changing the port or updating the workbench program files, or when the service acts up. It cannot restart while a task is running. |
| 81 | 文風「{0}」已更新 | Style “{0}” updated |
| 82 | 新書寫完章節後會自動登記；已經寫了很多章的書，可以先從時間線轉換一份草稿，確認後再採用。 | New books register these automatically once the chapters are written. For a book that already has many chapters, convert a draft from the timeline first, then adopt it after checking. |
| 83 | 更新於 | Updated  |
| 84 | 最後登場： | Last seen:  |
| 85 | 會開始產生骨架。 | and it will start building the skeleton. |
| 86 | 會開始開書訪談。 | and it will start the book interview. |
| 87 | 有正文無章綱 | Text, no chapter card |
| 88 | 本書 |  books |
| 89 | 本書　·　書庫： |  books　·　Library:  |
| 90 | 條 |  items |
| 91 | 標籤檢查： | Tag check:  |
| 92 | 模型 {0}、文字編碼器 {1}、VAE {2}、LoRA {3} 個 | {0} models, {1} text encoders, {2} VAEs, {3} LoRAs |
| 93 | 模型： | Model:  |
| 94 | 模組： | Modules:  |
| 95 | 樣式表共 {0} 個畫風 | The style sheet has {0} styles |
| 96 | 正向提示詞 | Positive prompt |
| 97 | 正向： | Positive:  |
| 98 | 正在量參考書的文風指標與結構 DNA（大書約 20–30 秒），完成後 | Measuring the style metrics and structural DNA of the reference books (about 20–30 seconds for a large book); when that finishes, |
| 99 | 正文裡找不到這句 | This sentence is not in the text |
| 100 | 正文高頻詞組： | Top phrases in the text:  |
| 101 | 段沒有變更（展開） |  paragraphs unchanged (expand) |
| 102 | 每個中文字幾 token | Tokens per Chinese character |
| 103 | 每章依序： | Per chapter, in order:  |
| 104 | 照「 | Follow “ |
| 105 | 產生失敗： | Generation failed:  |
| 106 | 用參考書骨架直接開書，要先選一本參考書 | To start a book directly from a reference skeleton, pick a reference book first |
| 107 | 用骨架直接開書要走 API 的執行者（Claude Code 不行），請先切換執行者。 | Starting a book directly from a skeleton needs an API runner (Claude Code will not work), so switch the runner first. |
| 108 | 畫面描述 | Scene description |
| 109 | 畫風與出圖 | Style and generation |
| 110 | 目前 {0}× | Now {0}× |
| 111 | 目前有效 | Currently valid |
| 112 | 程式在本機依動作詞、畫面詞、章綱情節點打分，不用 AI；也可以直接貼上或修改下面的文字。 | The program scores passages on this machine by action words, image words, and chapter-card plot points, with no AI. You can also paste or edit the text below. |
| 113 | 章、{0} |  chapters, {0} |
| 114 | 章。 |  chapters. |
| 115 | 章未登場 | Not yet appeared |
| 116 | 章綱已確認 | Chapter card confirmed |
| 117 | 章綱草稿 | Chapter card draft |
| 118 | 章要檢查 |  chapters to check |
| 119 | 章（原檔已備份）。 |  chapters (the originals are backed up). |
| 120 | 第{0}章的候選稿會先備份再移開，請 AI 重新寫一份 | The candidate draft for chapter {0} is backed up and moved aside, then the AI writes a new one |
| 121 | 第{0}章的章綱和候選稿會先備份再移開，請 AI 重寫章綱 | The chapter card and candidate draft for chapter {0} are backed up and moved aside, then the AI rewrites the chapter card |
| 122 | 第一章 ……{0}正文……{1}第二章 …… | Chapter one ……{0}body text……{1}Chapter two …… |
| 123 | 等待服務重新開啟 | Waiting for the service to come back |
| 124 | 簡體轉成台灣繁體（含用語，例如「軟件」→「軟體」） | Convert Simplified Chinese to Taiwan Traditional Chinese, wording included |
| 125 | 約 US$ | about US$ |
| 126 | 與觸發詞；提示詞裡已經有的不重複加） |  and trigger words; anything already in the prompt is not added twice) |
| 127 | 處 |  places |
| 128 | 處變更 |  changes |
| 129 | 複製正向提示詞 | Copy the positive prompt |
| 130 | 覆蓋了第 | Overwrote chapter  |
| 131 | 請 AI 調整「 | Ask the AI to adjust “ |
| 132 | 請 Claude 處理 | Ask Claude to handle it |
| 133 | 護欄：有名字和參考書重複（ | Guardrail: some names repeat in the reference book ( |
| 134 | 讀取 {0} 失敗 | Failed to read {0} |
| 135 | 負向： | Negative:  |
| 136 | 負面提示詞（留空＝ | Negative prompt (empty means  |
| 137 | 負面： | Negative:  |
| 138 | 跳過已存在的第 | Skipped the existing chapter  |
| 139 | 輸出約 {0}； | Output about {0};  |
| 140 | 近似，請確認是不是同一個地方 | Similar, so check whether they are the same place |
| 141 | 送 {0} 出圖 | Send to {0} for generation |
| 142 | 這個任務不屬於這本書 | This task does not belong to this book |
| 143 | 這本書已經是專案，不能用『直接開書』覆蓋。 | This book is already a project, so Direct start cannot overwrite it. |
| 144 | 這本書已經是專案，不能用『直接開書』覆蓋；請改用開書訪談或手動套用。 | This book is already a project, so Direct start cannot overwrite it. Use the book interview or apply it by hand instead. |
| 145 | 適用： | Applies to:  |
| 146 | 還沒有{0}。按右上角新增。 | No {0} yet. Add one with the button at the top right. |
| 147 | 還沒有插圖。 | No illustrations yet. |
| 148 | 重跑第{0}章的回寫追蹤？會依正文重新整理這章的摘要、伏筆、時間線、角色狀態等。 | Re-run the write-back tracking for chapter {0}? It rebuilds that chapter's summary, threads, timeline, and character states from the text. |
| 149 | 開書方式不對 | Wrong way to start the book |
| 150 | 開頭文字（{0}，{1} {2}）：{3}…… | Opening text ({0}, {1} {2}): {3}…… |
| 151 | 關係圖出錯：{0}　請按 Ctrl+F5 重新整理。 | Relation graph error: {0}　Press Ctrl+F5 to reload. |
| 152 | 關係圖畫不出來：{0}　請按 Ctrl+F5 重新整理。 | Could not draw the relation graph: {0}　Press Ctrl+F5 to reload. |
| 153 | 關係圖載不起來：{0}　請按 Ctrl+F5 重新整理。 | Could not load the relation graph: {0}　Press Ctrl+F5 to reload. |
| 154 | 骨架沒有內容，不能套用。 | The skeleton is empty, so it cannot be applied. |
| 155 | 骨架沒有卷綱，不能直接開書；請重試產生骨架。 | The skeleton has no volume outline, so a direct start is not possible. Generate the skeleton again. |
| 156 | 骨架沒有產生： | The skeleton was not generated:  |
| 157 | 骨架的卷綱格式不對，不能直接開書。 | The volume outline in the skeleton has the wrong format, so a direct start is not possible. |
| 158 | 點一下加進「場景標籤」。對照表是 tagcomplete 附的中文翻譯，有些詞不準，請挑著用。 | Click a tag to add it to the scene tags. The list is the Chinese translation that ships with tagcomplete, so some words are off; pick the ones that fit. |
| 159 | 點圖上的人或勢力，這裡會列出他在第 {0} 章的所有關係。滾輪縮放、拖背景移動。 | Click a character or faction in the graph and this lists all of their relations at chapter {0}. Scroll to zoom, drag the background to pan. |
| 160 | 點左右兩邊選擇要的版本。 | Click either side to choose the version you want. |
| 161 | （ComfyUI 找不到） | (ComfyUI not found) |
| 162 | （{0} 章有主圖 | ({0} chapters have a main image |
| 163 | （{0}，{1} 秒） | ({0}, {1} s) |
| 164 | （只在名詞表出現，合併不會改動它） | (appears only in the glossary; merging will not change it) |
| 165 | （數字），不會帶入任何名字或情節。 | (numbers), and brings in no names or plot. |
| 166 | （正文共 {0} 章，{1} {2}；章綱也套用這個範圍） | (the text has {0} chapters, {1} {2}; the chapter cards use this range too) |
| 167 | （第 {0} 卷） | (volume {0}) |
| 168 | （第 {0}–{1} 章） | (chapters {0}–{1}) |
| 169 | ），並跑一次保真檢查。 | ), then run a fidelity check. |
| 170 | ），請手動改掉。 | ), so change them by hand. |
| 171 | ）； 要用自己的 workflow，請在 ComfyUI 選單用「Export (API)」匯出（沒有這個選項的話，到 ComfyUI 設定開啟開發者模式）。工作台只改正向、負向、seed、尺寸、張數，組提示詞用的自訂節點會自動略過。 | ). To use your own workflow, export it with Export (API) in the ComfyUI menu; if that item is missing, turn on developer mode in the ComfyUI settings. The workbench only changes the positive prompt, the negative prompt, the seed, the size, and the batch count, and it skips your custom prompt-building nodes. |
| 172 | ，其中 {0} 份會覆蓋現有檔案（先備份） | , and {0} of them overwrite existing files (backed up first) |
| 173 | ，第一次在第 {0} 章 | , first in chapter {0} |
| 174 | ，簡體字約 | , with Simplified Chinese in about  |
| 175 | ；其他步驟用上面選的執行者。（設定 → 整章自動流程） | ; the other steps use the runner chosen above. (Settings → Full-chapter automation) |
| 176 | 之後這幾步的結果會先備份到 .studio/備份/ 再清掉，然後重新執行： | The results of these steps are backed up to .studio/備份/ before they are cleared, then they run again:  |
| 177 | 刪除「{0}」？{1}會移到 .studio/刪除，不會永久刪除；引用到它的地方（關係、伏筆、索引）可能失效。 | Delete “{0}”? {1} moves to .studio/刪除 and is not deleted for good, so places that reference it (relations, threads, the index) may break. |
| 178 | 寫作、改稿、去 AI 味、審查時，Claude Code 和其他模型都會讀這份檔案（和各書的 設定/作者偏好.md 衝突時以書為準）。「禁用詞」一節由程式在「檢查用語與 AI 味」時逐字比對，目前有 | Claude Code and the other models read this file when writing, revising, doing De-AI polish, or reviewing (a book's own 設定/作者偏好.md wins on any conflict). The program compares the Banned words section word by word during Check wording and AI feel, and it currently has  |
| 179 | 顯示 {0} / | Showing {0} / |

同形（填 "=="，10 條）：
- #/b/{0}/bible?t=核心&f=
- /bible?t=草稿
- 候選/新書草稿/骨架.md
- 文風/{0}.md
- 結構/{0}.md
- 設定/{0}/
- 追蹤/讀者認知.md
- 追蹤/讀者認知_草稿.md
- 追蹤/關係.md
- 追蹤/關係_草稿.md
