# Rules for filing settings

## 1. Three sources, one entrance

| Source | Example | Goes to |
|---|---|---|
| Written by the author | the author pastes a character intro, or edits a file directly | if the author clearly says "that's it" → official; otherwise ask once "settle it directly?" |
| Extracted from conversation | half an hour on worldbuilding, then "organize what we just settled" | what the author **clearly agreed to** → official; what was only discussed without a decision → draft |
| AI-generated | "generate 5 supporting characters", "design this country's tax system" | always into `設定/草稿/` first, official only after the author confirms |

When you cannot tell whether something is "confirmed", put it in drafts. A draft misfiled costs little; an official setting misfiled contaminates the chapter text.

## 2. How to extract from conversation

1. Look back over the conversation (or the transcript the author pasted) and list every setting element mentioned.
2. Mark each one:
   - **Settled**: the author said "good", "that's it", "I like this", or proposed it themselves and it was not overturned.
   - **Under discussion**: several options were offered and none chosen, or the author said "let me think".
   - **Rejected**: what the author said no to.
3. For anything overturned, the **last** statement wins.
4. Write the settled into official files; write the under-discussion into drafts with the candidate options noted; do not write the rejected (unless the author wants a "do not do" recorded; then put it in the glossary's notes column or the character's remarks).
5. In the report list in a table: what went official, what went to drafts, what was not taken.

## 3. Draft to official

When the author says "X in the drafts is ready" or "these are all settled":

1. Read the draft file and tidy the format with the right template (`_範本/角色.md` and so on).
2. Change the frontmatter `狀態` to `正式` and move it to the matching official folder.
3. Check for conflicts with existing official settings (same name, contradictory rules, mismatched relationships). Ask the author first if there is a conflict.
4. Register any new terms in the glossary.
5. Delete the draft file.

## 4. Registering after a chapter (following novel-write's declaration)

After finishing a chapter, novel-write lists the "write it and report it" new things. You register them in the database:

| Type of new thing | Registered in |
|---|---|
| Named supporting character | `設定/角色/{name}.md` (role: 配角; fill only what has appeared in the text, leave other fields empty) |
| New faction | `設定/勢力/{name}.md` |
| New rule, demonstration of an ability, geographic or institutional detail | the matching `設定/世界觀/{topic}.md`, adding a rule |
| New term or form of address | `設定/名詞表.md` |
| New foreshadowing, relationship or promise | these are "facts"; novel-write writes them into `追蹤/`, not handled here |

When registering, **write only the information the chapter text has already shown**; do not invent a backstory for a supporting character. To add one, ask the author or put it in a draft.

## 5. Handling conflicts

When two settings contradict each other:

1. Do not pick a side and change it yourself.
2. List: the two places that contradict (file, original wording) and which written chapters cite each.
3. Give the author 2-3 options with a recommendation. Usually recommend "go with what the text already says", because readers have already seen it.
4. After the author decides, change the setting file; if the text must change, hand it to novel-write's revision flow.

## 6. Naming rules

- The file name is the setting's most common name, e.g. `Ines Marlow.md`, `The Quay Guild.md`, `Power System.md`.
- Aliases go in the frontmatter `別名`; do not open a separate file for an alias.
- Same name, different people: add a qualifier, e.g. `Old Pell (the Marlows' steward).md`.
- Keep spelling consistent across the book (for example choose one of "harbor" / "harbour" and note it in the glossary).
