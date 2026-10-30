# Novel Studio

> Language: [繁體中文](README.md) · English · [日本語](README.ja.md)

A local workbench for writing long-form serial novels with AI. All story data (settings, outlines, tracking, manuscripts) is plain Markdown with YAML, the web UI manages the project, and the writing itself can run on different AI backends:

- **Claude Code**: uses your Claude subscription. The built-in novel-* skills read and write the files directly (in `plugin/`, `plugin-en/` and `plugin-ja/`).
- **DeepSeek, llama.cpp and other OpenAI-compatible services**: the workbench assembles the context, the model returns text or JSON, and Python writes the files.
- The same data works with any of these backends. The workbench does not depend on `~/.claude`.
- It runs only on your own machine (127.0.0.1) and is not exposed to the network.

**New here?** On an empty bookshelf, the "First time here?" card adds a sample book in one click. It starts with the language of your interface, and you can pick another one. There are three, all original and all the same size, so you can try every page:

| Language | Sample book (folder in `demo/`) |
|---|---|
| English | *The Lantern Road*, a road fantasy (`demo/en_TheLanternRoad/`) |
| Japanese | 『辺境の薬師と竜の約束』, an isekai fantasy (`demo/ja_辺境の薬師と竜の約束/`) |
| Traditional Chinese | 《退婚之後》, a historical intrigue (`demo/退婚之後/`) |

Each has two chapters of text, one candidate draft, five chapter cards, settings and tracking data. The tutorial slides (`demo/小說工作台_新手教學.pptx`) exist only in Traditional Chinese; there is no English or Japanese version.

## Installation and settings

Setup steps, backends (DeepSeek / llama.cpp), where API keys are stored, and the settings reference moved to **[install.md](docs/en/install.md)**.

Other docs: [i18n workflow](docs/i18n-workflow.md), [continuation contract](docs/續寫合約.md), [regression eval](docs/回歸測試.md), [style loop](docs/文風閉環.md), [retrieval memory](docs/檢索式記憶.md), [drift report](docs/漂移偵測.md), [autopilot](docs/自動駕駛.md).

## Writing languages

Each book has its own writing language: Traditional Chinese (`zh-TW`), English (`en`) or Japanese (`ja`). Choose it when you create a book or import a manuscript. It is stored as `語言:` in `設定/故事核心.md`, and you can change it later with the "Writing language" selector on the Overview page. The interface language is a separate setting (bottom right).

- **What stays Chinese.** Folder names, file names, frontmatter keys, table headers, status words and the other fixed tokens stay in Chinese in every language, so tracking, search and export work the same way. Free text, such as chapter text, summaries and notes, uses the book's language. When a folder name is shown in this README, such as `設定/` (settings), `正文/` (chapter text) or `候選/` (candidate drafts), the real folder has that Chinese name.
- **Prompts and skills.** API mode switches its prompts by language. Claude Code mode loads `plugin/` (Traditional Chinese), `plugin-en/` or `plugin-ja/`.
- **Word count follows the book.** English is counted in words; Chinese and Japanese are counted in characters. The Bookshelf, Overview, Chapters page, export and the import preview all use the same unit.
- **Keys and option values are mapped back.** When a model returns JSON in English or Japanese, the studio maps the keys and the option values back to the fixed Chinese tokens before writing, so tracking tables stay uniform.
- **Output in the wrong language is retried once.** If most of what a model writes is not in the book's language, the studio asks it to rewrite once. If the second try still does not match, the result is kept and marked 待核對 ("to be checked") in the notes so you can look at it.
- **Export follows the language.** English books get "Chapter 1" headings and a "Contents" page. Japanese books can use "第N話" headings. Vertical writing is offered only for Chinese and Japanese.
- **Shared styles and structures carry a language label**, so an English style file is not applied to a Japanese book by accident.
- **Style checks and style metrics** have a version for each language.
- **Token estimates.** The studio counts Chinese and Japanese characters with the provider's "Tokens per character" setting, and other characters at about 0.3. If the estimate is far off for Japanese, adjust that ratio in the provider settings.
- Traditional Chinese output is unchanged.

## Main features

| Page | What it does |
|---|---|
| Bookshelf | All novels, word counts, candidate counts; create a book (opens a setup interview); add the sample book |
| Overview | Chapters written, word count, outline progress, status card, and "Needs attention" items (tracking behind, pending candidates, pending revisions, recovered drafts, threads overdue or dormant, characters absent for a long time, settings drafts) |
| Chapters | Chapter-card status, word count and candidates for every chapter. A chapter page has tabs for the chapter card, text, candidate draft and revision diff, and lets you edit, review, check against the chapter card and check wording and AI-sounding prose |
| Outline | Read and edit the book outline and the volume outlines |
| Story bible | Characters, factions, world, core settings (story core, style, author preferences, glossary) and drafts |
| Threads & timeline | Threads (foreshadowing, with dormant and overdue ones flagged), timeline (unrevealed events flagged), reader knowledge, relationships (who toward whom, with history), character states, status card, glossary |
| Task log | The full record of every task, cost estimates, recovered drafts; you can continue a task's conversation |
| Export | The text, outlines, chapter cards, story bible and tracking data as EPUB 3 or plain TXT |
| Illustrations | Overview of covers, chapter and setting images, and the book's art style; chapter pages and the Story bible also have illustration blocks |
| Shared library | Styles, chapter structures and author preferences shared by all books (bottom left) |
| Import a manuscript | Split old TXT, Markdown or Word manuscripts into chapters (bottom left, or on the Bookshelf) |
| AI panel | Switch the runner, buttons for every action, live output (including reasoning), answer the AI's questions, stop a task |

### Candidate drafts

When you write a chapter, the draft goes to `候選/` first and never straight into the text:

1. Click "Write chapter". The AI writes a candidate draft and reports back.
2. Read the candidate on the chapter page.
   - **Adopt** moves it to `正文/` and then writes back to the tracking data (summary, status card, character states, threads, timeline, glossary, chapter-card status).
   - **Send back for rewrite** lets you write notes, and the AI rewrites the candidate along them.
   - **Discard** moves it to `.studio/備份/` (the backup folder).
3. Nothing in tracking changes until you adopt. When you revise an older chapter, the status card and character states do not roll back to that chapter's state.

### Reconciling and checking against the chapter card

- **Reconcile with settled facts.** Before writing, every plot point on the chapter card is compared with facts that are already fixed (status card, character states, timeline, the previous chapter's ending). If they conflict, the settled fact wins and the report lists the conflict. You can turn this off in Settings.
- **Check against the chapter card.** The plot points and the closing hook on the chapter card become a checklist. The model reports each one as written or not written, quoting the text. The studio then compares the quote word for word, and a quote that cannot be found in the text is flagged "Quote doesn't match".

### Review and revision, passage by passage

- **Review only lists comments; it never touches the draft.** Each comment has a severity (Must fix / Should fix / Note), a category, the quoted line from the text and a suggested fix. A quote that does not match the text gets a ✕, a hint that the AI may be wrong.
- **Tick the comments, then revise.** Tick the ones to act on (you can add your own), and the AI changes only those places. The original is not overwritten.
- **Passage-by-passage comparison.** The "Revision diff" tab shows the original and the revision side by side, with deletions and insertions marked at character level. Click a side to use that version, and press "Apply to the candidate" to write it. If the original was edited after the revision was made, applying is blocked so your edits are not lost.

### Full-chapter automation

Press "⚡ Full chapter, automated" on the Overview, the Chapters list or a chapter page, pick a chapter range, and the studio runs these steps in order:

chapter card → write the chapter (candidate) → check against the chapter card → de-AI polish → review comments → auto-select comments → revise from the selected comments → apply all revisions → finalize and write back to tracking

- **One AI call per step.** Each step is the same single action you can run by hand and carries only the data it needs, so the context never overflows. Ticking, applying revisions and moving files into the text are done by Python, not the AI.
- **A runner for each step.** Under Settings → Full-chapter automation you can pick a different runner for the chapter card, writing, the chapter-card check, the de-AI pass, review, revision and the final write-back (the default follows the flow's runner). The assignment is recorded when the flow starts, so resuming uses the same one, and the flow page shows who ran each step. The matching buttons on the AI panel start from the same assignment, and you can override it in the form. If an assigned runner is unreachable, the flow stops at that step.
- **Re-run from a step.** When a flow stops or fails, every step has "↺ Re-run". A snapshot of the candidate is saved before each step; re-running restores the candidate to how it was before that step, backs up the later steps' checks, reviews and revisions to `.studio/備份/` and clears them, and then runs from that step. For the chapter card, writing, de-AI, review and revision steps you can add a line of instructions. A finalized chapter (tracking already written back) cannot be rolled back; use "Write a chapter (candidate)" to rewrite it. A chapter card that already existed is never rewritten by the flow.
- **Auto-select.** By default "Must fix" and "Should fix" are ticked; change it in Settings or when you start. Plot points the chapter-card check found missing are handed to the revision as well.
- **Local checks join the review.** The review comments include problems the local (non-AI) check still finds after the de-AI pass: banned words from your author preferences, simplified characters, suspected typos, mainland usage, engineering terms and uplifting chapter endings, labelled as local checks. A spot the AI already flagged is not repeated, repeated words are merged into one comment, and punctuation is fixed by the program rather than listed.
- **De-AI polish, passage by passage.** The de-AI pass never overwrites the draft directly. The report is a table of "original line | why it changes | what it becomes", and the "Revision diff" tab shows each passage with the reason beside it. Choose per passage and press "Apply"; it writes back to the file you started from (text or candidate), after backing it up. The text does not need a tracking re-run. In the full-chapter flow everything is applied automatically.
- **Fidelity check after de-AI.** The studio compares before and after locally: names from the story bible and glossary that vanished or dropped a lot, numbers that vanished or changed, dialogue that was rewritten or cut, and a length change above 15%. The result follows the de-AI report; in a single-chapter review it appears as a "Note". It only lists; the automatic flow does not change anything back.
- **Rhythm items in the check script.** Stock reactions ("froze for a second", "the air thickened"), bursts of very short sentences (four or more in a row), sentence lengths that are too even, too many dashes in narration (more than one per 400 words) and one character called four or more different names in a chapter. Habits your style allows go under "Allowed exceptions" and are kept by the de-AI pass.
- **Modes.** "Write one chapter, then pause" (default) stops after each finalized chapter, and you press continue. "Write continuously up to the last chapter" runs to the end.
- **Existing work is not redone.** An existing chapter card is not rewritten; an existing candidate starts at the check. Finalized chapters cannot be in the range.
- **A failure stops at that step.** The progress card shows which step failed and why. Fix it and press "Continue from this step"; the earlier steps do not run again. You can stop at any time, and progress survives a restart of the studio.
- While a flow runs, the panel follows the current step, and other AI actions on the same book are blocked so they cannot interfere.

### Keeping what was written when a task fails

When writing, revising or continuing is cut off by a lost connection, by you pressing stop or by truncated output, the text already produced is saved as a recovered draft. The Chapters page and the Task log show a hint, and you can "Finish writing" (the AI continues from the break and removes repeated sentences), "Save as a candidate draft as-is", look at it, or discard it.

### Export

Pick a format and contents on the Export page. The file is saved in the book's `匯出/` folder (export folder) and can also be downloaded. No network and no AI are needed.

- **Format.** EPUB 3 (with a table of contents, verified with epubcheck) or plain TXT.
- **Contents.** The text (with an optional chapter range), the book and volume outlines, chapter cards, the story bible (without drafts) and tracking data, in any combination. Only chapters adopted into `正文/` are exported.
- **Layout.** Chapter heading format: by book language (English "Chapter 1", Chinese and Japanese "第1章"), "第1章", "第一章", Japanese "第1話" style, title only, or as in the manuscript. Paragraph format: first-line indent, a blank line between paragraphs, or both.
- **EPUB.** Vertical writing (pages turn right to left) is available for Chinese and Japanese books only. A `封面.jpg` or `封面.png` in the book folder can be used as the cover. The headings and the Contents page are in the book's language.
- **TXT.** UTF-8 or UTF-8 with BOM (for old Notepad and some readers).
- The title, author and your last choices are remembered.

### Illustrations (Forge Neo)

Every chapter, every character, faction or world entry and the cover can have an illustration, all optional: where there is no image, nothing is shown. Images are stored in the book's `插圖/` folder (illustration folder, with a `.gitignore` so they stay out of git by default), and each image has a same-named .json next to it with the prompt, seed, parameters and the passage it came from.

The flow (every step can be skipped, or you can just click "Upload an image"):

1. **Pick a passage** (chapters). The studio scores action words, visual words, short sentences and chapter-card plot points locally and lists the three strongest passages. You can also paste your own.
2. **Characters and places.** It finds the characters and places mentioned in the passage. You can add or remove them, set left or right positions and give each one an action for this picture.
3. **Scene description.**
   - "AI generates the scene description" needs only a small JSON from the model (action, scene, composition tags and two or three English sentences); character looks, quality and style are assembled by the program. By default you can use DeepSeek or a local model, not Claude.
   - "Look up tags locally" turns Chinese words in the passage into Danbooru tag suggestions with the Chinese table that ships with tagcomplete, without AI.
4. **Assemble the prompt.** It follows the Anima format: "quality / rating / people count / artist → characters (left and right paragraphs for several people) → scene tags → English description", as "Tags + natural language", "Tags only" or "Mostly natural language". You can apply a style sheet (.xlsx or .json, see `examples/styles.example.json`: `{prompt}` substitution, `{A|B}` random choice, prompt / naturl_prompt / both). You can edit the result or copy it into Forge yourself.
5. **Send to Forge.** Jobs are queued to the Forge Neo API in order with progress and a stop button; finished images are saved back to the book folder.

**Visual card.** The settings file of a character, faction or world entry can have a "## 繪圖提示" section (drawing prompt: English tags and a sentence or two). Every illustration of that entry includes it automatically, which is what keeps a character looking the same each time. Write it by hand, look tags up locally, or ask the AI to produce it from the settings once.

**Connecting Forge Neo**

1. Add `--api` to Forge's launch arguments (`COMMANDLINE_ARGS` in its bat file) and restart Forge.
2. In the studio, open Settings → Illustrations, enter the Forge URL (default `http://127.0.0.1:7860`) and the Forge folder, and press "Read the latest parameters from Forge". It loads the sampler, steps, CFG, Shift, model and Module 1/2 (VAE, text encoder) from Forge's last image. The studio sends them in Forge's infotext format and lets Forge switch the model and modules itself.
3. Optionally choose a style sheet (.xlsx or .json). Without one, the sample `examples/styles.example.json` is used (55 general-audience styles: art styles, scenes, hairstyles, traditional clothes and so on). If the Forge folder has the tagcomplete extension, tag checks and the Chinese table are found automatically.
4. LoRA (optional): after "Test connection", type to search the LoRA list in the Forge block and pick a file. When generating, `<lora:name:weight>` and trigger words are added at the end of the positive prompt; if the prompt already has the same `<lora:name:` or the same word, it is not added twice.

**LoRA trigger words** (same for Forge and ComfyUI): after you pick a LoRA, the studio reads the same-named `.json` next to it (the format Forge's "Edit metadata" saves). The trigger words are the first three entries of `activation text`, and the weight is `preferred weight` (0 means not set, so 1 is used). Without a JSON, or with an empty `activation text`, the LoRA's file name is the trigger word. You can edit them, and clear them for a LoRA that needs none. `negative text` is not read.

**Style sheet format** (`examples/` has a JSON and an xlsx example; it is compatible with the StyleSelectorXL extension):

| Field | Meaning |
|---|---|
| `name` | Style name (unique) |
| `prompt` | Tags; `{prompt}` is replaced with the prompt the studio assembled, `{A\|B}` picks one at random |
| `naturl_prompt` | Natural-language description (optional; `natural_prompt` is accepted too) |
| `negative_prompt` | Negative prompt (optional) |
| `category` | Category as "Major > Minor", several separated by commas (optional) |
| `namezh`, `namejp`, `nameen` | Display names in each language (optional) |

When you export EPUB, the main image under Illustrations → Cover is the cover, and each chapter's main image sits at the start of the chapter (you can turn that off).

### Illustrations (ComfyUI)

In Settings → Illustrations, switch the image backend to ComfyUI, enter the URL (default `http://127.0.0.1:8188`) and press "Test connection".

- **Built-in nodes only.** The studio sends a workflow through ComfyUI's API and needs no custom nodes.
- **Image presets.** "Anima" and "MOSS-Image" come ready, and you can add more. Each preset can:
  - choose a workflow: leave it empty to use the bundled template (`examples/comfy/anima.api.json`, `moss.api.json`); for your own workflow, use "Export (API)" in the ComfyUI menu (enable developer mode in ComfyUI's settings if you do not see it);
  - choose the model, text encoder and VAE from ComfyUI's lists after the connection test, with suggestions based on file names; empty means whatever the workflow says;
  - turn on the Prompt Upsampler, which rewrites the prompt with an LLM (MOSS's Qwen3.5 9B) before sending, and needs a recent ComfyUI;
  - add LoRA (up to 8): pick a file (type to search), a weight (-4 to 4) and whether it is used; trigger words come from the same-named JSON (see "LoRA trigger words" above). Reading the JSON needs to know the LoRA folder; leave it empty to ask ComfyUI, and fill in "LoRA folder" in Settings if that fails. The studio uses the built-in LoraLoaderModelOnly, finds the model-loading node by walking back from the KSampler's model input and chains the LoRA after it, so you do not edit the workflow. The image record notes which LoRAs were used.
- **The studio changes only these.** Positive and negative prompts, seed, size, count, and the model and LoRA from the preset. The nodes to change are found by walking back from the KSampler; custom nodes that assemble prompts and preview nodes are skipped; sampler, steps and CFG stay as in your workflow. The settings page lists which nodes were found, which were skipped and what ComfyUI is missing.
- **Prompt format.** Anima is tags + natural language, like Forge. MOSS-Image automatically becomes English natural language, without quality, rating or artist tags.
- **Text in the image** (MOSS-Image only). On the draft page, "Text in the image" can add titles, signs, speech bubbles and so on, with position, size, font and colour; for the cover, tick "Put the book title". Chinese and English both work, English most reliably.
- Your own workflow is recorded only as a path in `config.json` (not in git); the file itself is never copied into the project.

### Shared library

It lives in the library folder under `_共用/` (shared folder), together with your novels and not in the studio's program folder, so it is never pushed to GitHub.

- **Styles.** Reusable style files.
  - Create one from a book's text, pasted text or uploaded files, by copying a book's current style, or by writing from a blank template.
  - The text metrics are computed locally: sentence length, paragraph length, dialogue share, punctuation habits, "de/di" density for Chinese, density of stock AI phrases, and frequent phrases (when analysing a book, that book's character and place names are excluded). The AI looks at these numbers when it writes.
  - "Apply to a book…" copies a style into that book's `設定/文風.md` (backing up the old file); "Compare with a book's text" shows the target and the actual side by side.
  - When a book's style file has text metrics, "Check wording and AI-sounding prose" also points out where the chapter strays far from the style.
  - **"Ask the AI to design a style".** Enter a name, genre (click tags such as "Whodunit mystery" or "Xianxia / cultivation"; for a mix write "skeleton + seasoning"), the feeling you want, references, viewpoint and so on, and the AI writes a complete style file across the thirteen style dimensions, with original example passages labelled by scene type and one counter-example. If you attach a sample, the text metrics are computed locally first and the rules are drawn from the sample.
  - **"Ask the AI to adjust".** Write your comments (for example "too many similes", "fill in all thirteen dimensions"); only the relevant entries change and the AI lists "old → new". The previous version is backed up under `_共用/.備份/`. Replying in the panel also counts as asking for an adjustment.
  - **"Try a passage".** It writes 200 to 300 words in the style and rates itself, so you can see whether the rules are workable; it never changes the style file.
  - Full examples are in `examples/`: psychological thriller, hard-boiled crime, urban realism, rural regional, wuxia, black humor and a space opera told by a historian: seven files, named `文風範例_*.md`. Styles carry a language label (see "Writing languages").
- **Chapter structures.** Beat-sheet templates. Built in: the classic four-part form, pressure and release, mystery and reveal, everyday and romance, and three acts. Copy and edit them or add your own.
  - "Apply to a book…" copies a structure into that book's `設定/章節結構/` and can make it the book's default; a single chapter can choose another on its chapter-card tab.
  - When writing and planning chapter cards, the AI follows the chosen structure; the chapter card's plot points come first.
- **Shared author preferences.** Long-term preferences across books, recurring faults and banned words. No copying: they apply to every book.
  - The AI reads them when writing, revising, de-AI polishing and reviewing; where they conflict with a book's own `設定/作者偏好.md`, the book wins.
  - The "Banned words" section is matched word for word by the program (a `/regular expression/` is allowed) and flagged under "Check wording and AI-sounding prose". A book's own `設定/作者偏好.md` can have a "## 禁用詞" section too.

### Import a manuscript

Everything is done locally, with no AI.

- Sources: TXT, Markdown, Word (.docx); you can pick several files at once (one file per chapter is fine) or paste text.
- The encoding is detected automatically (UTF-8, Big5, GB18030). Chinese manuscripts can be converted from Simplified to Taiwan Traditional, including word choice (OpenCC).
- Chapters are split by "第X章／第X回", "Chapter N", prologue and extra markers, or Markdown # headings; volume titles are skipped. The preview shows each chapter's number, title and size before you import.
- A chapter title written twice (spelled differently, in different scripts, or with only a number on the second line) is merged into one chapter, and a table of contents at the start is skipped.
- The preview checks every chapter and colours problems: empty, too short, too long, duplicate number, skipped number, number going backwards, simplified characters (also left over after conversion). Under 50 units counts as empty (words for English, characters for Chinese and Japanese).
- You can create a new book or add to an existing one, into the text or into candidates; when a chapter already exists, choose skip or overwrite (the original is backed up).
- After importing the text, use "Build settings from the text" (next section) so the AI works backwards to settings and tracking data, with no setup interview.

### Build settings from the text

For a book that is already written (an imported manuscript or a finished novel), the AI can work backwards to a full set of data. Start from "Needs attention" on the Overview, or at `#/b/<book name>/reverse`.

1. **Estimate.** Shows the chapters to read, the number of batches and the estimated tokens and cost. You can fill in "run up to chapter N" to try a small part first.
2. **Run.** The text is read in chapter order in batches of one to three chapters (depending on the runner's context length). Each batch carries what the last one left behind: known characters and aliases, open threads and suspense, and the previous chapter's ending. Every batch result is saved, so after a stop or a failure "Continue" resumes where it broke; after adding chapters, press "Run new chapters and refresh".
3. **Organize.** Characters, aliases, glossary terms, threads and reader knowledge are merged locally first, and then the AI writes the character files, factions, world, story core, book and volume outlines and the status card. This step uses only the per-chapter extractions and does not reread the text.
4. **Review the drafts.** Four groups: settings (characters, factions, world, story core, glossary), outlines (book and volume), chapter cards (one per chapter, status "Written") and tracking (chapter summaries, threads, timeline, reader knowledge, character states, status card). Open any of them, then "Adopt" or "Discard" each group; an existing file of the same name is backed up first.

Fields that cannot be inferred are marked "(not stated in the text)" or "to be filled", never invented. A character who appears in fewer than three chapters gets no character file and goes into the glossary.

The glossary is then organized once more (a book that already has a glossary can also run this alone, with "Organize into the story bible" under Threads & timeline → Glossary): categories and subcategories are redone; places, ships, weapons, technology, institutions, creatures and so on become topic files under `設定/世界觀/` (a separate file for anything that appears in five or more chapters); duplicate factions are merged, names of the same regime in different periods become a history, and anything uncertain is marked "Needs author review"; the glossary keeps every entry as an index, and its notes column points to the file with the details. Claude Code can run this too: the studio does the batching itself, and each batch is an independent `claude -p`. The approach draws on story-import in oh-story-claudecode (MIT).

## What each runner can do

Every button works with Claude Code and also with DeepSeek, llama.cpp and other OpenAI-compatible models. The difference is how:

| Action | Claude Code | Other models |
|---|---|---|
| Write chapter, send back for rewrite, revise, de-AI polish, continue a recovered draft | Reads files and writes the candidate itself | The studio assembles the context; the model writes; Python saves the candidate |
| Adopt and write back, fill in tracking | Updates the tracking files itself | The model returns JSON; Python updates the tracking files |
| Setup interview, style, preferences, story core, outlines, plan chapter cards, create characters, generate drafts, file content into the bible, turn drafts official | Reads and writes files itself | The model outputs the files to write in "file blocks"; Python checks the paths and writes |
| Review a chapter, revise from comments, check against the chapter card | Returns JSON; the studio saves and compares | Same |
| Whole-book health check, free questions | ✓ | ✓ (reports go to `.studio/審查報告/`) |
| Check project structure | ✓ | Checked directly by Python, no model call |

Safety limits for other models: they may write only `.md` files under `CLAUDE.md`, `設定/`, `大綱/` and `範例/`; chapter text can enter only through the candidate flow; only files in `設定/草稿/` can be deleted. Every file that is overwritten or deleted is backed up to `.studio/備份/` first.

Actions that need confirmation (the book outline, volume outlines, chapter-card planning) give a proposal first, and nothing is written until you reply "Confirm" in the panel.

### Reasoning effort by task

For each provider the settings page offers a "How it is controlled" choice and a separate reasoning effort for four stages: writing, planning, review and structured output. A reasoning model's thinking counts as output tokens, so turning thinking off for format-bound tasks saves money and keeps JSON from being cut off.

- DeepSeek: sends `thinking: {"type": "enabled"/"disabled"}` and `reasoning_effort` (low / high / max). Defaults: low for writing, high for planning, high for review, off for structured output.
- OpenAI-style: sends `reasoning_effort`.
- llama.cpp / Qwen3-style: sends `chat_template_kwargs: {"enable_thinking": true/false}`.
- Values you put in "Extra parameters" override these settings.

## How it works

**Claude Code.** The workbench runs, inside the book folder:

```
claude -p --output-format stream-json --verbose --plugin-dir <workbench>/plugin --permission-mode acceptEdits --allowedTools ...
```

(`plugin-en` or `plugin-ja` for English and Japanese books.) The instruction goes in on standard input, for example "Use the novel-write skill to write chapter 4 …", and the output streams live into the panel. When Claude needs a decision, it lists the options at the end of its report; you reply under the panel and the workbench continues the same conversation with `--resume`.

**Other models.** The workbench picks the settings, tracking and earlier text that matter for the task, prioritizes them within the context length and sends them; the model streams back, Python checks the result and writes the files.

The context length is "context length − max output". Tokens are estimated with the provider's "Tokens per character" (blank means automatic: 0.6, DeepSeek's official estimate, for DeepSeek and a cautious 1.2 for others; llama.cpp can "Calibrate"). When things do not fit, the lowest-priority parts are excerpted or skipped first (in this order: writing craft, summaries of earlier chapters, timeline and glossary …; the chapter card, the book's rules and the style are always included). The Task log lists the "context breakdown" so you can see which part took the most.

The timeline and glossary keep growing with the chapter count; above about 3,000 tokens only the rows related to this chapter are sent (for writing, revising, reconciling and review alike; the write-back still sees the whole file):

- **Timeline.** Whole rows are sent for: events the reader does not know at all or whose reveal chapter has not come, events of the last 10 chapters, and rows mentioning people or IDs named in the chapter card or the previous chapter's ending (a protagonist who appears in most rows is not used for matching). For other rows whose "what the reader knows now" still says "doesn't know", "only knows" or "believes …", only a one-line "what the reader still doesn't know" is sent, without the author's truth, so the model knows which suspense is still open. What the chapter card says will be revealed follows the chapter card; to make sure a row is sent whole, write its ID (for example E061) in the chapter card.
- **Glossary.** Terms that appear in the chapter card, status card, the previous chapter's ending, the settings of characters on stage and related threads; for forms of address, also when the person they address is on stage.
- **Threads.** Whole entries for those named on the chapter card, those due in chapters N−3 to N+5, and those that appeared in the last three chapters; other open threads are sent as a one-line index (ID, summary, planned payoff, importance); paid-off or dropped threads are not sent.
- **Reader knowledge** (when a ledger exists). Open suspense and misbeliefs related to this chapter are sent whole (with the author's truth); other open ones are sent without the answer; resolved ones are not sent. With a ledger, the timeline no longer guesses open questions from "doesn't know / believes" wording.
- **Relationships** (when a relationship table exists). Only relationships between characters on stage that are currently valid; for review, the history too, to catch relationships that changed for no reason or slid back.

Only one task runs per book at a time; saving is blocked while a task is running so the AI and you do not overwrite each other. Task logs, backups, reviews, revisions and recovered drafts are all stored in each book's `.studio/`.

### Searching the text

The search box above the left menu (or Ctrl+K, "Search the text") finds words in the earlier text, for example "jade token" or "Wren Hob". It reads the files directly, with no model and no tokens.

- Scope: only the text by default; tick candidate drafts, outlines and chapter cards, the story bible and tracking to widen it.
- Several words separated by spaces must appear in the same chapter; words in quotation marks are a whole phrase; Traditional and Simplified Chinese are not distinguished (so leftover simplified characters from an import are found too).
- Results are grouped by chapter, with the count in each chapter and the surrounding text, and a line at the top says in how many chapters the term appears and where it first appears. Clicking a result jumps to that chapter, highlights it and scrolls to the first match.

### Checks after tracking is written back

After every write-back (adopting, filling in, the finalize step of a full-chapter flow) the studio checks locally, spending no tokens, whether the tracking was written: the chapter summary, the status card, character states for characters who appear three or more times in the text, the threads and reader-knowledge entries named on the chapter card, a relationship change written in a character state but not in the relationship table, the timeline, the chapter-card status and registered new items. The result follows the task result; when there is a problem it appears under "Needs attention" on the Overview, and "Re-run write-back" refreshes that chapter. It checks only whether things were written, not whether the content is right.

### Reader knowledge

`追蹤/讀者認知.md` records **what is in the reader's head**, apart from the timeline of events:

| Type | Meaning | Example |
|---|---|---|
| 懸念 (suspense) | A question the reader is waiting to have answered | Why does the father confess? |
| 誤認 (misbelief) | Something the reader wrongly believes (for reversals) | The reader thinks the messenger was the second son |
| 已知 (known) | The reader knows it, but some characters do not | The reader knows the jade is fake; the lead does not |

(The three type words stay in Chinese in the file, because the studio reads them.)

- A blank "payoff chapter" means not yet revealed; writing, reconciling and review all remind the model not to give it away early. "Author's truth" is optional, so leave it empty if unsure.
- New books: entries are registered and resolved automatically during write-back.
- Books with many chapters already written: on Threads & timeline → Reader knowledge, press "Build from the timeline"; the AI converts the timeline in batches into a **draft**; review and edit it, and it takes effect only after "Adopt draft" (it does not affect writing before that). Until a ledger exists, write-back does not register a few stray entries.
- Suspense converted this way mostly has no payoff chapter (the timeline only records "the reader did not know then"). Press "Match payoffs", and the AI compares each one with the later timeline and chapter summaries: revealed ones get their payoff chapter, partly revealed ones are rewritten as the remaining question, duplicates are merged. The result is again saved as a draft, with a reason for each at the end.
- The Task log shows lines like "timeline 109 rows: 49 whole, 35 as open questions only; glossary 37/306; threads 13 whole, 31 as index". When a term is not carried, write it on the chapter card and it will be.

### Relationships

`追蹤/關係.md` records **who stands where toward whom**, one direction per row: "Wren → Hob" and "Hob → Wren" are separate, and the two sides may feel differently.

| From | Toward | Relationship | Attitude | Start | End | Reason for change |
|---|---|---|---|---|---|---|
| Hob | Wren | partner | respect | Ch 020 | | she carried the lantern into the river |

(The real file's column headers are Chinese, and chapters are written like `第020章`.)

- "Relationship" is a role or standing (master and pupil, allies, creditor); "attitude" is how this person feels toward the other (trust, wariness, affection).
- A change does **not overwrite**: the old row gets an end chapter and a new row is opened, so the history stays. A blank end chapter means currently valid. During write-back the AI reports only relationships that changed, and the studio closes the old row and opens the new one; re-running the write-back of a chapter does not create duplicates.
- Writing sends only currently valid relationships between characters on stage; review sends the history too; during write-back a reminder appears if a character state records a relationship change but the table was not updated. Revising an older chapter does not touch the table (the current relationship follows the newest chapter).
- New books (before chapter 15 is written back): created automatically. Books with many chapters already written: on Threads & timeline → Relationships, press "Create a draft from character files". The studio turns each character file's "## 關係" lines ("person: description") into a table draft, **without a model and without tokens**; review and edit, then "Adopt draft". Start chapters stay empty and fill in as write-backs happen; "attitude" is empty for you to fill. The "## 關係" section in character files is kept as a readable summary.
- **Relationship map.** Switch to "Relationship map (grouped by faction)" at the top of the Relationships page. Each faction is a box with its members inside, and arrows show relationships between characters (A toward B and B toward A are drawn separately). By default only the lead and main supporting characters are shown; tick "Show supporting cast and villains" to add the rest. Drag the "up to chapter N" slider to see the relationships at that point; lines that changed in that chapter are orange. Click a person or faction to list all relationships they have toward others and others toward them. Faction members come from the "related characters", leader and main members fields of `設定/勢力/`. It is plain SVG and needs no external package.

## Project layout

```
novel-studio/
├── app.py              server (FastAPI)
├── LICENSE             MIT license
├── start.bat / start.sh
├── requirements.txt
├── studio/             workbench modules
│   ├── project.py      reads a novel project: chapters, settings, tables, alerts, candidates
│   ├── runner.py       task management; runs Claude Code or other models in the background
│   ├── actions.py      the Claude Code instruction behind each button
│   ├── providers.py    streaming client for OpenAI-compatible services, reasoning control
│   ├── context.py      assembles context for non-Claude models and controls its length
│   ├── native.py       writing flows for non-Claude models
│   ├── native_files.py settings and outline flows for non-Claude models (file blocks)
│   ├── tracking.py     writes tracking files from JSON
│   ├── relations.py    relationship table, draft from character files, map data
│   ├── goals.py        reconciliation and chapter-card check
│   ├── revision.py     review comments and passage-by-passage revision
│   ├── recovery.py     recovered drafts
│   ├── export.py       EPUB and TXT export
│   ├── shared.py       shared library: styles (with local statistics), structures, preferences
│   ├── style_design.py designing, adjusting and trying styles with the AI
│   ├── pipeline.py     full-chapter automation
│   ├── importer.py     manuscript import: encoding, conversion, chapter splitting
│   ├── illust.py       illustrations: storage, visual cards, passages, tag tables, style sheets, prompts
│   ├── forge.py        Forge Neo API and image queue (also queues ComfyUI)
│   ├── comfy.py        ComfyUI API and workflow handling
│   ├── lang.py         each book's language, word-count unit
│   ├── textguard.py    language guard around the check scripts
│   ├── prompts/        prompt packs per language (zh_TW, en, ja)
│   └── presets/結構/   built-in chapter structures
├── plugin/             built-in novel-* skills, Traditional Chinese (Claude Code plugin format)
│   ├── .claude-plugin/plugin.json
│   └── skills/novel-setup, novel-style, novel-bible, novel-outline, novel-write, novel-review, novel-deslop
├── plugin-en/          English novel-* skills (original content, with an English check script)
├── plugin-ja/          Japanese novel-* skills (original content, with a Japanese check script)
├── static/             web UI (index.html, app.js, style.css, marked.js) and static/locales/ (en.json, ja.json)
├── tools/              developer tools (see below)
├── examples/           sample style sheets (styles.example.json / .xlsx), seven full style examples, ComfyUI template workflows (comfy/)
└── demo/               tutorial slides (Traditional Chinese only), and the sample books:
    ├── en_TheLanternRoad/              English sample book
    ├── ja_辺境の薬師と竜の約束/          Japanese sample book
    └── 退婚之後/                         Traditional Chinese sample book
```

Created when you run the app and never committed: `config.json`, `secrets.json` (only when no credential store is available), `.venv/`, and each book's `.studio/`.

### Tools for contributors

Run these from the project folder; they are for people who want to help translate or develop the studio.

| Tool | What it does |
|---|---|
| `python tools/check_i18n.py` | Run before pushing. Checks that the three prompt packs have the same keys and variables, that English values contain no Chinese sentences or kana, that the interface translations in `static/locales/` keep their `{0}` variables and folder paths exactly, and that no value is empty |
| `python tools/check_parity.py` | Checks that the three plugin editions have the same files and heading skeleton, that templates and the sample books' `_範本/` hold the same file set, that the three READMEs share one heading structure, that every UI string is translated, that no banned wording from the glossary is used, and whether a Traditional Chinese edit still waits for its translation (`--strict` fails on warnings too, `--update-lock` re-records the baseline) |
| `python tools/prompt_lang_audit.py` | Runs a short chapter flow against a mock model and checks that the prompts sent for English and Japanese books contain no Chinese sentences (it should return 0) |
| `python tools/i18n_extract.py [--merge static/locales/en.json]` | Extracts every Chinese UI string from the front end and the back end (messages and errors); with `--merge` it lists the ones a language file has not translated yet |
| `python tools/fix_filenames.py <book folder> [--apply]` | Repairs file names in older books that lost their spaces (for example `JimHawkins.md`); it only lists the changes unless you add `--apply` |

The interface text in the source stays Chinese and acts as the translation key; `static/locales/en.json` and `ja.json` map it to English and Japanese. A missing key shows the Chinese text, so translations can be added a batch at a time.

## Troubleshooting

If you run into a problem or have a suggestion, use "Report an issue" at the bottom of the left sidebar to open a GitHub issue.

- **Buttons do nothing, or "The claude command was not found":** run `where claude` (Windows) or `which claude` (macOS/Linux) and enter the full path under Settings → Claude executable path.
- **Claude says it cannot write files:** check that the permission mode is `acceptEdits`.
- **I edited a file by hand. Will the workbench see it?** Yes. It reads files directly, so refresh the page.
- **I want to add a button of my own:** edit `studio/actions.py`: add an entry to `ACTIONS` and write the matching Claude Code instruction in `build()`; to make it work for other models too, add a flow to `HANDLERS` in `studio/native.py`.
- **I want to use these skills in Claude Code in a terminal:** run `claude --plugin-dir <workbench folder>/plugin-en` (or `plugin`, `plugin-ja`).
- **The Task log says "context exceeds the limit, skipped: writing craft":** this is not an error. The chapter is written as usual with only the least important reference left out. Read the next line, "context breakdown", to see which part is largest: fill in or "Calibrate" the ratio if it is not set; for llama.cpp make sure `-c` matches the context length; and do not set "Max output" much larger than needed, because it is subtracted from the context first.
- **Output was cut off with a non-Claude model:** raise the output limit in Settings. For llama.cpp, also check that `-c` is large enough. Cut-off text is saved as a recovered draft, and you can continue it.
- **A chapter is marked 待核對 ("to be checked"):** the model did not write in the book's language even after one retry. Read it, fix it or send it back for a rewrite.

## Credits and license

Released under the [MIT License](LICENSE). The in-app "About" page lists everything that was referenced or used.

- marked.js (MIT), see `static/vendor/marked.LICENSE.md`
- FastAPI (MIT), Uvicorn (BSD-3-Clause), PyYAML (MIT) and [opencc-python-reimplemented](https://github.com/yichen0831/opencc-python) (Apache-2.0) are installed from `requirements.txt` and not bundled
- Some design ideas in the skills are adapted from [oh-story-claudecode](https://github.com/worldwonderer/oh-story-claudecode) (MIT); the full license text is in `plugin/THIRD_PARTY_NOTICES.md` (and the same file in `plugin-en/` and `plugin-ja/`)
- The page layout and the idea of "AI drafts go to a candidate area first" were inspired by [moshu 墨書](https://github.com/huihuijiangqiang/moshu) (its code is not used)
- Staged control of reasoning effort, pre-write reconciliation, chapter-card checks, separating review from revision and recovered drafts follow ideas from [Pagekin (AI-Novel-Writer)](https://github.com/EthanYoQ/AI-Novel-Writer) (concepts only; its GPL code is not used)
- The dimensions and wording of style files draw on the style-entry advice from [Novelcrafter](https://www.novelcrafter.com/courses/codex-cookbook/effective-style-entries), the Style fields and per-scene examples of [Sudowrite](https://docs.sudowrite.com/using-sudowrite/1ow1qkGqof9rtcyGnrWUBS/style/4gqKgVVjdN6XTKo71HChqV), the Voice DNA / STYLE-GUIDE template of [Scriveno](https://cdn.jsdelivr.net/npm/scriveno@3.8.0/templates/STYLE-GUIDE.md) and the [stylistic checklist](https://www.lancaster.ac.uk/fass/projects/stylistics/topic10/12method.htm) of Leech & Short, *Style in Fiction* (concepts only; the content is original)
- The division of labour in the Chinese web-novel workflow follows [Chinese-WebNovel-Skill](https://github.com/Tomsawyerhu/Chinese-WebNovel-Skill) (concepts only)
- The illustration feature can connect to [Stable Diffusion WebUI Forge – Neo](https://github.com/Haoming02/sd-webui-forge-classic/tree/neo); the prompt format follows the recommendations for [Anima](https://huggingface.co/circlestone-labs/Anima); the tag tables use files shipped with [a1111-sd-webui-tagcomplete](https://github.com/DominikDoom/a1111-sd-webui-tagcomplete) (MIT; read from the Forge folder, not bundled); the style sheet format is compatible with [StyleSelectorXL](https://github.com/ahgsql/StyleSelectorXL) (MIT)
