# User guide

> Novel Studio is a local writing workbench: a book is a folder, the manuscript is Markdown, and the AI only runs the pipelines for you.
> This is a static guide. Read the two workflows first, and check the glossary at the end when a term is unclear.

## What do you want to do?

| I want to… | Go to |
|---|---|
| Start a brand-new book | Workflow 1: a new book from scratch |
| Turn an existing manuscript into a project | Workflow 2 A: import an old manuscript |
| Start a new book from an old book's skeleton | Workflow 2 B: spin off a new book |
| Generate characters, factions, worldview | How the settings bible grows |
| Look up a term | Glossary |
| Know which button is the right one | Duplicate entry points (some actions currently have several entrances) |

## Interface map

- **Shelf** (top of the left rail, or `#/`): all books, new book, import old manuscript
- **Inside a book, left rail**: Overview, Chapters, Outline, Settings, Foreshadowing & timeline, Jobs, Illustrations, Export
- **Right panel**: AI runner, action forms, job stream, reply box
- **Bottom right**: interface language; the actual model and library location live in Settings

---

## Workflow 1: a new book from scratch

### Step 0: create the book

Shelf → "＋ 開新書" (New book):

| Field | Advice |
|---|---|
| Book name | Also the folder name; renaming later means renaming the folder yourself |
| Writing language | Chooses the language of prompts and model output, independent of the interface language |
| Initial idea | One sentence is enough; the setup interview will ask more |
| Reference book (optional) | Only reuses its **style metrics and chapter structure** (numbers), never names or plot |
| Generate story skeleton | Costs about 1–2 minutes and a few model calls; the draft goes to `候選/新書草稿/` |

Creating the book starts the **setup interview** automatically. The questions appear in the right panel; answer them in the reply box.
The interview writes into `CLAUDE.md`, `設定/故事核心.md`, `設定/文風.md`, and so on.

### Step 1: story core → whole-book outline

1. Settings → "核心" (Core): check whether `設定/故事核心.md` makes sense; you can ask the AI to "分析／調整文風" (analyze/adjust style) or "記錄偏好" (record preferences)
2. Outline page → "全書大綱" (Whole-book outline): first ask for a **volume overview** (theme, chapter count, and end state of each volume)
3. If it is not right, say so and iterate; when satisfied, it writes `大綱/全書大綱.md`

### Step 2: open volume 1 (volume status → volume-outline draft → adopt)

The Outline page has a "卷況" (Volume status) card:

1. Press "開新卷" (Open a new volume): give the volume number and chapter range (20 chapters is fine to start; you can change it later)
2. It creates a **draft**: `大綱/草稿/卷綱_第1卷.md`, which you can edit directly
3. When happy, press "**採用**" (Adopt): it moves to the official volume outline with status "已確認" (confirmed), and appends the volume to `大綱/全書大綱.md`
4. The volume outline contains a "volume contract" (what this volume promises and where it must end); continuation prompts inject it first

> To change a confirmed volume: volume-status card → "修訂" (Revise) on that volume → a draft is written to `大綱/草稿/卷綱修訂_第N卷.md` → "看差異" (View diff) → "套用修訂" (Apply revision).
> The official outline is only ever written by "採用" (Adopt) or "套用修訂" (Apply revision); both back up first.

### Step 3: chapter cards for the whole volume + health check

1. Volume-status card → "排這一卷的章綱" (Lay out this volume's chapter cards): first get a **one-line-per-chapter overview**, not full detail for 20 chapters at once
2. Review the overview; reply "確認" (confirm) to write the actual card files (`大綱/章綱/第NNN章_*.md`)
3. Press "章綱體檢" (Chapter-card health check). It catches two problems:
   - **Early appearance / spoiler**: a character or setting that should appear much later is written into a card too early
   - **Too long absent**: a character disappears for too many chapters
4. Fix the cards before writing

> Whichever entry you press (Overview, Chapters, Outline or the volume-status card), the form comes with the range prefilled; an empty range is rejected and never falls back to chapter 1.

### Step 4: writing

| Method | Good for |
|---|---|
| Overview → "寫第 N 章" (Write chapter N) | One chapter at a time, with you watching |
| "⚡ 整章自動" (Auto whole chapter) | Running the whole pipeline |

The auto pipeline: chapter card → draft text → outline check → de-AI pass → style pass → review → tick issues → revise → apply → finalize.
The pipeline has **gates** and refuses with an explanation when:

- the chapter number is outside any **confirmed** volume outline
- the chapter has no chapter card yet
- the chapter card contains an early-appearance spoiler

Being blocked is not a bug; it means you should fix the volume outline or chapter cards first.

### Step 5: after each chapter

- **Candidate draft**: new text lands in `候選/`; review it from the Chapters page or the single-chapter page and finalize when happy
- **Review / revision**: the single-chapter page can run a review, show a revision diff, and apply items one by one
- **Tracking**: after finalizing, it writes summaries, foreshadowing, timeline, and character state back to the "Foreshadowing & timeline" page
- **Jobs**: every run, its token usage and cost are listed under "Jobs"

### Step 6: end of a volume → next volume

1. Overview → "卷末體檢" (End-of-volume check): compares the settings against the text and lists chapters that missed their cards, characters absent too long, unpaid foreshadowing, and style drift
2. If the volume outline needs updating, the check page can "產生卷綱更新草稿" (generate a volume-outline update draft); review it before appending
3. Next volume: volume-status "開新卷" → volume-outline draft (it reads the previous volume's end-of-volume draft) → adopt → lay out cards → write

### Where the files are

| Content | Location |
|---|---|
| Whole-book outline | `大綱/全書大綱.md` |
| Volume outline | `大綱/卷綱_第N卷.md` (drafts in `大綱/草稿/`) |
| Chapter cards | `大綱/章綱/第NNN章_*.md` |
| Manuscript | `正文/第NNN章_*.md` |
| Candidate drafts | `候選/` |
| Settings | `設定/角色/`, `設定/勢力/`, `設定/世界觀/`; drafts in `設定/草稿/` |
| Tracking | `追蹤/狀態卡.md`, `追蹤/伏筆.md`, `追蹤/章節摘要/` |
| Jobs and backups | `.studio/` (job records, backups, recoveries) |

---

## Workflow 2: starting from an old book

### A. Turn an old manuscript into a project (import + reverse-engineer)

Good for: you already have a docx/txt manuscript and want to continue or organize it here.

1. Left rail → "匯入舊稿" (Import old manuscript) → pick a file → preview the chapter split → import (creates a new book or adds to an existing one)
2. Open that book → Settings → "**從正文建立設定**" (Build settings from the text):
   - It reads the manuscript in batches and extracts characters, factions, worldview, and terms
   - Everything first goes into `設定/草稿/` and a candidate area
   - Review group by group; press "採用" (Adopt) to promote into the official settings and glossary
3. Run "卷末體檢" (End-of-volume check) when useful to see which chapters are not covered by settings
4. Chapter cards can also be reverse-engineered from the text as part of the same flow, then you continue writing forward

### B. Spin off a new book from an old one (P6: book A → book B)

Good for: keeping a book's voice and structure while writing a completely new story.

**When creating a new book:**

1. Shelf → "＋ 開新書" → choose a "參考書" (Reference book) → optionally tick "順便產生故事骨架" (Also generate a story skeleton)
2. Reference book only: the new book receives `設定/文風.md`, `設定/章節結構/結構.md`, `設定/風格指紋.json`, `設定/結構DNA.json` (computed locally, no model calls)
3. With the skeleton: about 1–2 more minutes to generate a **new** skeleton draft (title ideas, premise, hooks, protagonist, worldview, volume outline), written to `候選/新書草稿/`
4. The skeleton is a draft and is never applied automatically; copy what you like into settings and outline

**For a book that already exists:**

Outline page → "**參考書骨架**" (Skeleton from a reference book) → pick a reference book and optional notes → same skeleton draft.

> Only abstract traits are reused (style, structure, point of view, chapter rhythm). **No manuscript text, character names, place names, or events are carried over.**
> Use only your own works or public-domain ones. The runner must be an API runner (Claude Code cannot do this).

### C. Borrow only style / structure

- Shared library → Style, Chapter structure: measure a book into a shared template
- Settings → "核心" (Core) → "分析／調整文風" (Analyze/adjust style): tune targets for this book
- P6's "reference book" is the same idea, applied when creating a new book

---

## How the settings bible grows

The settings bible holds static settings (characters, factions, worldview, glossary). Where a character is *right now*, their injuries, and what they know live under "Foreshadowing & timeline".

Press **"生成設定" (Generate settings)** at the top right of the settings bible: it first asks what you already have — an outline/volume outlines, just a sentence or keywords, a block of text from a discussion, or only one missing character/faction/worldview.

| Method | When to use | Output |
|---|---|---|
| **從大綱長設定** (Grow settings from the outline) | You have an outline but the settings are empty | Character, faction, worldview drafts (choose scope; add reference direction and URLs) |
| **生成設定草稿** (Generate setting drafts) | You know exactly what you want, described in one sentence | Drafts |
| **整理內容入庫** (File content into the project) | You finished a discussion with the AI and have a long transcript | Settled items go official; open items stay drafts |
| **生成設定 → only one item missing** (character / faction / worldview) | Only one item is missing | A single item |
| **從正文建立設定** (Build settings from the text) | You have a manuscript and want to reverse-engineer | Drafts, adopted group by group |

All drafts live in `設定/草稿/`. Review them, then use "**草稿轉正式**" (Promote drafts) to file them; the glossary is updated at that step.

### Grow settings from the outline (new)

Settings → "生成設定" (Generate settings) → "我已經有大綱或卷綱":

- Tick the categories to grow (characters / factions / worldview)
- Optional "參考方向" (reference direction), e.g. "airship warfare modeled on WWII submarine tactics"
- Optional "參考網址" (reference URLs): the app fetches page text into the prompt (up to 3 pages, 6,000 characters each)
- It reads: the whole-book outline, every volume outline, the chapter-card list (first 60 chapters), the existing settings index, story core, style, author preferences, and the state card
- Output: character drafts (including first-appearance chapter), factions, worldview drafts

> This is not a search engine; the AI does not browse the web by itself. You supply the URLs; without them it uses its own knowledge plus the reference direction you write.

---

## Glossary

| Term | Meaning |
|---|---|
| **大綱 (outline)** | The overall plan, including the whole-book outline and each volume outline |
| **全書大綱 (whole-book outline)** | Volume overview: theme, chapter count, and end state per volume; `大綱/全書大綱.md` |
| **卷綱 (volume outline)** | The plan for one volume: main line, volume contract, required end state |
| **卷契約 (volume contract)** | What this volume promises the reader (what will and will not happen); injected first during continuation |
| **章綱 (chapter card)** | The plan for one chapter: scenes, events, who appears, closing hook |
| **章綱體檢 (chapter-card health check)** | Checks cards for early appearance / spoilers and for characters absent too long |
| **續寫合約 (continuation contract)** | `設定/續寫合約.md`: immutable facts and volume-end promises; outranks outline and style |
| **狀態卡 (state card)** | Where characters are now, injuries, what they know; written back after each finalized chapter |
| **伏筆 (foreshadowing)** | Threads planted but not yet paid off; the app warns when they go quiet or miss their due chapter |
| **讀者認知 (reader knowledge)** | What the reader knows and does not know yet (prevents characters from revealing things the reader already knows) |
| **漂移 (drift)** | Settings and text slowly diverging; caught by the end-of-volume check |
| **文風指標 (style metrics)** | Numbers such as dialogue ratio, sentence length, paragraph length |
| **風格指紋 (style fingerprint)** | Style numbers plus representative sentences measured from a book (names masked) |
| **結構 DNA (structure DNA)** | Abstract structure: point of view, chapter-length distribution, dialogue rhythm, chapter-length curve |
| **回歸測試 (regression eval)** | `book_eval`: fixed samples to check whether prompt/model changes made quality worse |
| **自動駕駛 (autopilot)** | Stops every K chapters to verify must-fix issues and style, then continues |
| **檢索式記憶 (retrieval memory)** | Retrieves relevant earlier passages into the context when writing a new chapter |
| **候選稿 (candidate draft)** | Not-yet-final text in `候選/`; it moves to `正文/` only after review |

---

## FAQ

**Why was "整章自動" (auto whole chapter) refused?**
Most often: the chapter number is outside the confirmed volume outline, the chapter has no card, or the card has an early appearance. Fix the outline/card, or change the chapter number.

**The volume-status card is missing.**
It only appears on the Outline page. If the book does not even have a whole-book outline yet, do "全書大綱" first.

**Reference URLs fail to load.**
Only `http/https` is fetched, up to 3 pages, 6,000 characters each. A 403 or timeout is noted as "抓取失敗" (fetch failed) in the prompt; everything else still generates.

**Claude Code cannot generate a skeleton?**
Skeletons need an API runner (for example DeepSeek). Switch it at the top of the right panel; Claude Code is only used by the workbench's own flows.

**Where do I see a job?**
The right panel is the live stream; finished runs are under "任務紀錄" (Jobs) with tokens and cost.

**I broke something.**
Every write is backed up first (`.studio/備份/`), and there are recovery drafts. The Jobs page shows which step failed.

---

## Duplicate entry points

Some actions still have several entrances (for example five "排章綱" buttons and four ways to generate settings).
Volume outlines are already unified: new volumes go "開新卷 → 採用", existing volumes go "修訂 → 看差異 → 套用修訂".
The full list and cleanup suggestions are in the project's `docs/入口檢查.md`; **for now the other flows are only documented, not changed**.
