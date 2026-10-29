# CLAUDE.md template

When novel-setup builds a project, write what lies between `---範本開始---` and `---範本結束---` below as `CLAUDE.md` in the book folder, replacing each `{...}` with the interview results. Keep it lean: this file is loaded at the start of every conversation, and a long one wastes context.

---範本開始---

# "{Title}" writing project

{One-line hook}

## Basics
- Genre: {genre}　Platform: {platform}　Expected length: {length}
- Viewpoint: {viewpoint and tense}
- Chapter length: {range, e.g. 2,000-3,000 words}
- Language: English. Follow the style file for spelling convention (American unless stated), curly quotes for dialogue, em dashes and ellipses used consistently. Input in another language is translated into English before it is written into files.

## Where things are
- Settings (static): `設定/`　story core, style, author preferences, glossary, worldbuilding, characters, factions; unconfirmed items in `設定/草稿/`
- Plans (not yet happened): `大綱/`　whole-book outline, volume outlines, chapter cards
- Facts (already happened): `追蹤/`　state card, character state, foreshadowing, timeline, chapter summaries
- Chapter text: `正文/第NNN章_<title>.md`
- Blank templates: `_範本/`

(Folder and file names stay in Chinese; the studio program reads them.)

## Iron rules
1. Keep plans and facts apart: the outline is plan, tracking is fact. Do not change tracking before the chapter text is final.
2. Keep drafts and official apart: chapter text may cite only official settings, never `設定/草稿/`.
3. The chapter card is the only plot blueprint for the chapter. The text does not change results the card has settled.
4. When writing, obey "what the reader knows now" in `追蹤/時間線.md`; do not spoil early.
5. **The continuation contract wins**: before writing any chapter, read `設定/續寫合約.md` (the app keeps it current: chapter count, characters, revealed and unrevealed secrets, open threads, the promise made for the end of the volume, and the forbidden zone). Facts it marks as unchangeable outrank the outline and outrank style.

## Three tiers of new things
Handle people and things that turn up while writing or planning by tier:
- **Just write it**: passers-by, one-off props, scene detail, fine detail of place names. No registration needed.
- **Write it and report it**: a named supporting character, a new faction, a new rule or demonstration of an ability, new foreshadowing, a new relationship or promise, a place or object that will recur. You may write it, but list it in the report and register it in the database.
- **Ask the author first**: a new main-line event or big twist, rules of a cheat ability / power system, revealing the truth or paying off important foreshadowing, changing a result the card settled or a character's decision, anything that conflicts with existing settings. Do not decide alone; stop and ask.
- When unsure: treat it as "write it and report it" while writing, and "ask the author first" while planning.

## Style priority
On any writing question, take the first of these that has a clear position:
**the author's request this time > `設定/文風.md` > `設定/作者偏好.md` > general writing rules**
Even a general rule that says "must" or "never" cannot override the author's clear choice. But style cannot change plot facts, the information boundary or a card's result.

## How we work
- Skills used: starting a book and style → novel-setup; settings database → novel-bible; outline and cards → novel-outline; chapters and revision → novel-write; consistency review → novel-review; removing AI voice → novel-deslop.
- Writing chapter text needs the author to say which chapter, or "continue". The default is one chapter, at most 3 at a time.
- When the author only says "continue" or "go with that", do not widen the scope: in the planning stage only plan, and do not start chapter text on your own.
- Reports to the author in plain words: what was written, what needs a decision, what is next. No file names or field names unless asked.
- When the author states a long-term preference ("from now on …", "remember …"), record it in `設定/作者偏好.md`; one-off requests are carried out and not recorded.

## Special rules for this book
{Special requests from the interview; delete this section if none}

---範本結束---
