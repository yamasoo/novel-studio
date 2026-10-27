# Novel Studio

> Language: [繁體中文](README.md) · English · [日本語](README.ja.md)

A local workbench for writing long-form serial novels with AI. All story data (settings, outlines, tracking, manuscripts) is plain Markdown with YAML, the web UI manages the project, and the writing itself can run on different AI backends:

- **Claude Code**: uses your Claude subscription. The built-in novel-* skills read and write the files directly (in `plugin/`, `plugin-en/` and `plugin-ja/`).
- **DeepSeek, llama.cpp and other OpenAI-compatible services**: the workbench assembles the context, the model returns text or JSON, and Python writes the files.
- The same data works with any of these backends. The workbench does not depend on `~/.claude`.
- It runs only on your own machine (127.0.0.1) and is not exposed to the network.

> The Traditional Chinese README is the complete reference for every workflow. This page covers setup, languages and the main features.

## Writing languages

Each book has its own writing language: Traditional Chinese (`zh-TW`), English (`en`) or Japanese (`ja`). Choose it when you create the book; it is stored as `語言:` in `設定/故事核心.md`.

- Folder names, file names, frontmatter keys, table headers and status words stay as fixed Chinese tokens in every language, so tracking, search and export work the same way. Free text uses the book's language.
- API mode switches its prompts by language. Claude Code mode loads `plugin/` (Traditional Chinese), `plugin-en/` or `plugin-ja/`.
- Style checks and style metrics have a version for each language. Word count is counted in words for English and in characters for Japanese.
- Traditional Chinese output is unchanged.

## Main features

| Page | What it does |
|---|---|
| Bookshelf | All novels, word counts, candidate counts; create a book (opens an interview); add the sample book |
| Overview | Chapters written, word count, outline progress, state card, and items needing attention (tracking behind, pending candidates, pending revisions, recovery drafts, foreshadowing overdue, dormant characters, settings drafts) |
| Chapters | Outline status, word count and candidates for every chapter; per-chapter editing, review, outline checks and style checks |
| Outline | Read and edit the book outline and volume outlines |
| Settings | Characters, factions, world-building, core settings (story core, style, author preferences, glossary) and drafts |
| Foreshadowing & timeline | Foreshadowing table, timeline, reader-knowledge ledger, character relations (who relates to whom, with history), character states, state card, glossary |
| Task log | Full record of each task, cost estimates and recovery drafts |
| Export | EPUB 3 or TXT from the manuscript, outlines, chapter cards, settings and tracking data; no network and no AI needed |
| Illustrations | Covers, chapter and setting images via Forge Neo or ComfyUI |
| Shared library | Style files, chapter structures and author preferences shared by all books |
| Import | Split old TXT, Markdown or Word manuscripts into chapters (done locally, no AI) |
| AI panel | Switch the AI backend, run actions, see live output (including reasoning), answer the AI's questions, stop a task |

### Highlights

- **Candidate drafts first.** A new chapter goes to `候選/` before it touches the manuscript. You review it, then adopt it (tracking is updated), ask for a rewrite with notes, or discard it. Tracking data is not changed until you adopt.
- **Consistency checks.** Before writing, the planned beats are compared with the settled facts. After writing, a local check confirms the tracking files were updated.
- **Review with revision.** Review lists issues with severity, category and quoted text, without touching the draft. You tick the issues to fix, and the revision is shown side by side with the original before you apply it.
- **Whole-chapter pipeline.** One button runs: outline → draft → outline check → de-AI pass → review → automatic selection → revision → apply → settle and update tracking. Each step can use a different backend, and a failed step can be resumed.
- **Reader-knowledge ledger.** Tracks what the reader knows, doubts or has been misled about, separately from the timeline, so the AI does not reveal answers early.
- **Relations with history.** Who-to-whom relations are recorded one direction per row, with a relation graph grouped by faction.
- **Search.** Search the earlier text locally with Ctrl+K. It is not affected by traditional or simplified characters.
- **Build settings from a manuscript.** For a book that is already written, the AI can read the chapters in batches and draft the settings, outlines and tracking files. You adopt or discard each draft.
- **Shared library.** Style files (with local statistics), chapter structures and cross-book author preferences, including banned words.

## Requirements

- Windows 10/11 (macOS and Linux also work)
- Python 3.9 or later
- For Claude Code mode: Claude Code, installed and signed in. The skills are included; no separate installation is needed.

## Installation

1. Download the project or `git clone` it, into any folder.
2. On Windows, double-click `start.bat`. On macOS or Linux, run `./start.sh`. The first run creates a virtual environment and installs the packages. Later runs start directly.
3. Your browser opens http://127.0.0.1:8765.
4. On first launch, choose a folder for your books (for example a `novel` folder under Documents). You can change it later in Settings. The workbench does not use any existing folder automatically.
5. To look around first, click "Add sample book".

## Setting up a backend

### DeepSeek

1. Create an API key on the DeepSeek platform.
2. In Settings → AI backends → DeepSeek, paste the key, or set the environment variable `DEEPSEEK_API_KEY` and enter its name.
3. Click "Test connection / list models" and choose a model.
4. Optionally enter the context length and prices for cost estimates.
5. To use several models from one provider, add them under "Available models". Each model can have its own context length, output limit, prices and token ratio. The key is shared.

### llama.cpp (local)

1. Start the model with llama-server, for example:
   ```
   llama-server -m your-model.gguf -c 32768 -ngl 99 --port 8080
   ```
   The `-c` value must match the context length set in the workbench.
2. Keep the URL `http://127.0.0.1:8080/v1` and test the connection. Then click "Calibrate" next to the tokens-per-character setting, which measures the ratio with the server's `/tokenize` endpoint.
3. Local model quality varies a lot. Try short chapters before deciding which tasks to use it for.

LM Studio and Ollama are OpenAI-compatible too. Add them with "Add OpenAI-compatible service". Default URLs: LM Studio `http://127.0.0.1:1234/v1`, Ollama `http://127.0.0.1:11434/v1`.

### Where API keys are stored

By default keys are kept in the operating system's credential store (Windows Credential Manager, macOS Keychain), encrypted by the system. If none is available, they go to `secrets.json` in the workbench folder, which is listed in `.gitignore`. You can also use environment variables. The lookup order is: credential store → `secrets.json` → environment variables.

## Settings

Settings are stored in `config.json`, which is not committed to git.

| Item | Description |
|---|---|
| Book library folder | Each book is a subfolder |
| AI backends | Claude Code, DeepSeek, llama.cpp, or your own OpenAI-compatible service |
| Claude executable path | Leave empty to detect it automatically; otherwise enter the full path |
| Model | For Claude Code, leave empty for the default, or enter `opus` or `sonnet` |
| Permission mode | Default `acceptEdits`, which lets Claude read and write files in the book folder |
| Pre-write consistency check, automatic outline check | Can be turned off separately |
| Warning thresholds | How many chapters before a foreshadowing or character is flagged as dormant |
| Service | Port, and a "Restart service" button |

## Project layout

```
novel-studio/
├── app.py              server (FastAPI)
├── studio/             workbench modules (project, runner, providers, context, tracking, revision, export, illustrations, ...)
├── plugin/             built-in novel-* skills, Traditional Chinese (Claude Code plugin format)
├── plugin-en/          English novel-* skills
├── plugin-ja/          Japanese novel-* skills
├── static/             web UI
├── examples/           sample style files, style examples, ComfyUI workflow templates
└── demo/               tutorial slides and the sample book
```

Created when you run the app and never committed: `config.json`, `secrets.json` (only when no credential store is available), `.venv/`.

## Troubleshooting

- **Buttons do nothing, or "claude command not found":** run `where claude` (Windows) or `which claude` (macOS/Linux) and enter the full path under Settings → Claude executable path.
- **Claude says it cannot write files:** check that the permission mode is `acceptEdits`.
- **I edited a file by hand. Will the workbench see it?** Yes. It reads files directly, so refresh the page.
- **Output was cut off with a non-Claude model:** raise the output limit in Settings. For llama.cpp, also check that `-c` is large enough. Cut-off text is saved as a recovery draft, and you can continue it.

## Credits and license

Released under the [MIT License](LICENSE). The in-app "About" page lists the libraries and projects used, including marked.js (MIT), FastAPI (MIT), Uvicorn (BSD-3-Clause), PyYAML (MIT), and opencc-python-reimplemented (Apache-2.0), which are installed from `requirements.txt` and not bundled. The skills draw on the ideas of several open projects; see `plugin/THIRD_PARTY_NOTICES.md`, `plugin-en/THIRD_PARTY_NOTICES.md` and `plugin-ja/THIRD_PARTY_NOTICES.md`.

Issues and suggestions: use "Report an issue" at the bottom of the left sidebar in the app.
