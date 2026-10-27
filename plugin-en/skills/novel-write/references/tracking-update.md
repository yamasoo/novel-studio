# Write-back after finishing a chapter

Once the chapter text is final, update the files below in order. Principle: **write only what really happened in the chapter text.** What the card planned but the text did not deliver is not written into tracking.

File names, folder names, frontmatter keys and table headers stay in Chinese exactly as in the templates; the content you write into them is in English.

## 1. Chapter summary (new file)

`追蹤/章節摘要/第NNN章.md`, from `_範本/章節摘要.md`. 100-250 words: what happened, how the situation changed, what and who newly appeared, where the chapter stops. Put the actual word count in the frontmatter.

## 2. State card (overwrite to the latest)

`追蹤/狀態卡.md` is a snapshot of "now":
- **1 Current position**: set to the volume/chapter, story time and scene at the end of this chapter.
- **2 Main-line progress**: change it if it advanced.
- **3 Characters on stage**: the characters at the centre of the story at the end of this chapter; remove those who have left.
- **4 Next-chapter promise**: replace with the hook this chapter's ending leaves and what must be caught. Delete the previous chapter's promise if this chapter paid it off.
- **5 Long-term constraints**: add new ones; delete those lifted.
- **6 Continuity risks**: add error-prone details created in this chapter (a new wound, a new misunderstanding, an object that changed hands); delete what is no longer a risk.
- **7 Active foreshadowing**: sync with the "in progress" items and those due for handling soon in the foreshadowing table.
- Set the frontmatter `更新至` to this chapter.

Deleting outdated content is necessary; do not only keep adding below. When the whole file passes about 1,500 words, remove the oldest content that least affects the next chapter.

## 3. Character state (only change on change)

`追蹤/角色狀態/{character name}.md`:
- Update only characters who **changed in this chapter**: location, goal, body, emotion, abilities and resources, relationships, secrets known, unfinished business.
- A named important character appearing for the first time gets a new file from `_範本/角色狀態.md`.
- For characters who appear in this chapter, set `最後登場` to this chapter; for any with an update, set `更新至` to this chapter.
- "Secrets known" must be strict: write only what this character already knows **inside the story**, not what only the reader knows.

## 4. Foreshadowing table

`追蹤/伏筆.md`:
- **Newly planted**: add a row with the next ID (F plus three digits), status 已埋.
- **Advanced or lightly touched**: set `最後出現` to this chapter; set the status to 推進中.
- **Paid off**: set the status to 已回收 and `最後出現` to this chapter.
- Do not register foreshadowing that the card meant to plant but the text did not write.

## 5. Timeline

`追蹤/時間線.md`:
- Add a row (E plus three digits) for each important event in this chapter, or past event first mentioned in this chapter.
- "What the reader knows now" records how much the reader knows after reading this chapter.
- When this chapter reveals the truth about an old event, update that row's "what the reader knows now" and "revealing chapter".

### Reader-knowledge ledger

`追蹤/讀者認知.md` (skip if none of the cases below apply. If the file does not exist: for a new book whose timeline has fewer than 15 rows, create it from `_範本/讀者認知.md`; for an older book with many chapters already written, do not create it yourself, skip this section, and remind the author in the report that the studio can "build it from the timeline"):
- What makes the reader start waiting for an answer (noticing something off, an open question): add a 懸念 row (R plus three digits) worded as the question the reader is asking.
- What the chapter deliberately lets the reader get wrong: add a 誤認 row stating the version the reader believes.
- Key information the reader knows but some characters do not: add a 已知 row saying who does not know. Ordinary events need not be registered as 已知.
- When this chapter reveals or clarifies an old suspense or misbelief, fill that row's resolving chapter with this chapter.
- "Author's truth" is optional: fill it only if the card or timeline states the answer; if unsure, leave it blank and do not invent.

### Character relationships

`追蹤/關係.md` (skip if no relationship changed in this chapter. If the file does not exist: for a new book before chapter 15, create it from `_範本/關係.md`; for an older book with many chapters written, do not create it yourself, skip this section, and remind the author in the report that the studio can "build it from the character files"):
- One direction per row: "A toward B" and "B toward A" are separate; if only one side's view changes, only touch that row. "Relationship" records role or standing (master and pupil, allies, creditor); "attitude" records this person's feeling and warmth toward the other (trust, wariness, affection).
- **A relationship first clearly established in this chapter**: add a row (ID L plus three digits), set the starting chapter to this chapter, and write in the reason-for-change column which event in this chapter did it.
- **A relationship this chapter changed**: put this chapter in the old row's end chapter (do not edit its content), open a new row with the new relationship and attitude, set its starting chapter to this chapter, and note the cause. Do not overwrite the old row; keep the history.
- Leave unchanged relationships alone; use the formal names from the character files.

## 6. Setting registration (new things at the "write it and report it" tier)

Per novel-bible's intake rules (if novel-bible is installed, read section four of its references/intake-rules.md):
- Named supporting character → `設定/角色/` (fill only what has appeared in the text)
- New faction → `設定/勢力/`
- New rule or demonstration of an ability → the matching `設定/世界觀/` file
- New term or form of address → `設定/名詞表.md`

## 7. Card status

Change the `狀態` in this chapter's card frontmatter to `已寫`. If the text departs from the card (for example a change the author agreed to), note the actual treatment in one line under the card's notes.

## 8. Version control

If the project uses git, commit once when the write-back is done: `第NNN章 <title>`. No need to ask the author first (they agreed to git at setup); if the author never agreed to git, do not commit.

---

## Write-back when revising

After changing a chapter already written:
1. Rewrite that chapter's summary.
2. Compare before and after to find the **facts that changed** (who knows what, who is hurt, where an object went, relationship changes, foreshadowing planted or paid off).
3. Correct the related rows in the foreshadowing table and timeline.
4. State card, character state and the relationship table: change them only if the fact is still valid **now**. Example: if you changed an injury in chapter 5 but the character had long healed by chapter 20, the current character state needs no change.
5. List the **later chapters that may be affected**: search later summaries and chapter text for places that mention these facts, give the list to the author, and ask whether to fix them together or hand them to novel-review.
