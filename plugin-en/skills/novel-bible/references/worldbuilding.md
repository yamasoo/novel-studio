# Worldbuilding method

## 1. Build only what the story uses

Worldbuilding serves the plot. For every setting ask: **which part of the plot will use it?** If you cannot answer, do not build it yet, or leave one line in a draft.

What the opening needs is usually a few sentences: where the lead is, what the rules of the game are here, and where the lead stands within those rules. Other detail waits until the plot reaches it.

## 2. Write rules, not prose

A setting file must be usable to "check" the chapter text, so write it as listed rules:

- Bad: "The magic system of this world is profound and varied, with many grades, each with its own character."
- Good:
  - Magic has nine grades: Body, Channel, Core …
  - Each grade has early, middle and late stages
  - Fighting across one stage: possible, with a technique or artifact
  - Fighting across a whole grade: nearly impossible unless at great cost (burning lifespan, destroying the artifact)

## 3. Every ability needs a cost and limits

An ability without a cost makes conflict collapse: if the lead can solve everything, the reader is not tense. For each ability or cheat, state clearly:
- **Trigger**: under what conditions can it be used?
- **Cost**: what is lost by using it? (stamina, lifespan, memory, favors, the risk of exposing identity)
- **Limits**: how many times a day? What does it not work on?
- **Growth path**: how does it get stronger? What unlocks at each stage?

The rules of a cheat ability are at the "ask the author first" level: the AI may not add or change them itself.

## 4. Common topics and the questions to answer

| Topic | Must at least answer |
|---|---|
| Power system | How is it graded? How do you level up? Conditions for crossing grades? Where do the resources come from? |
| Geography | Where does the story mainly take place? How far apart are the places and how do you travel between them? |
| Social structure | Who holds power? How are classes divided? Where is the lead? |
| Economy | What is traded? What does an ordinary person earn in a month? Is the lead short of money? |
| History | Which past events affect the present plot? |
| Religion / belief | What do people believe? How does it shape characters' choices? |

Economic anchors (prices, incomes) are hard to change once written into the text, so set them carefully and note them in the worldbuilding file.

## 5. Mark when the reader learns it

Note on each important setting "when the reader learns it". This directly affects what the text may write: a setting not yet revealed may be known to the characters, but the narration cannot spell it out.

## 6. Common faults

- A long worldbuilding lecture in the opening while the plot stands still.
- A huge setting that has nothing to do with the lead's situation.
- Contradictory rules (chapter 3 says you cannot cross grades, chapter 30 has the lead cross two with no cost).
- Economic numbers written off the cuff that do not add up later.

## 7. Categories and tags

Every worldbuilding file's frontmatter must have a `分類` field, set to exactly one of these 11 fixed values. Write the Chinese value as shown; the English gloss is for reference only:

力量體系 (power system), 地理與氣候 (geography & climate), 歷史與年表 (history & timeline), 社會與政治 (society & politics), 經濟與物資 (economy & goods), 宗教信仰 (religion & belief), 文化與風俗 (culture & customs), 科技原理 (technology principles), 載具與兵器 (vehicles & weapons), 生態與資源 (ecology & resources), 其他 (other)

- Decide by "what question this file answers": a mechanism (how an ability works) → 力量體系; a specific object (a particular ship or weapon) → 載具與兵器; institutions and legal status → 社會與政治.
- Use 其他 only when nothing else fits; do not invent new categories for a handful of files.
- `標籤` is optional and can hold several subtypes, e.g. `[艦船]`, `[武器]`, `[外星]`.
