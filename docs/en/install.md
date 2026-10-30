# Installation and settings

> Moved out of the README. First-time setup, switching backends, key storage, and the settings reference live here.

## Requirements

- Windows 10/11 (macOS and Linux also work)
- Python 3.9 or later
- For Claude Code mode: Claude Code, installed and signed in. The skills are included; no separate installation is needed.

## Installation

1. Download the project or `git clone` it, into any folder.
2. On Windows, double-click `start.bat`. On macOS or Linux, run `./start.sh`. The first run creates a virtual environment and installs the packages (fastapi, uvicorn, pyyaml, opencc). Later runs start directly, and missing packages are installed automatically if `requirements.txt` changed after an update.
3. Your browser opens http://127.0.0.1:8765.
4. On first launch, the Bookshelf asks you to choose a folder for your books (for example a `novel` folder under Documents; use "Choose…" to pick it). You can change it later in Settings. The workbench does not use any existing folder automatically.
5. To look around first, click "Add the sample book".

## Setting up a backend

### DeepSeek

1. Create an API key on the DeepSeek platform.
2. In Settings → AI runners → DeepSeek, paste the key, or set the environment variable `DEEPSEEK_API_KEY` and enter its name.
3. Click "Test connection / fetch model list" and choose a model.
4. Enter the context length and prices from the official documentation (optional, for cost estimates).
5. To use several models from one provider (for example a fast, cheap one and a slow, strong one), press "Test connection" under "Available models" and click to add them, or press "Add a model" and fill one in by hand. Each model can have its own context length, max output, prices and tokens per character; blanks follow the settings above, and the key is shared. Afterwards every place that picks a runner (the side panel, forms, each step of the full-chapter automation) can choose "DeepSeek · a model".

Claude Code comes with four choices: Default, Sonnet, Opus and Haiku. Default sends no `--model` and follows Claude Code's own setting; the other three send `--model`. llama.cpp (local) keeps one model per runner.

### llama.cpp (local)

1. Start the model with llama-server, for example:
   ```
   llama-server -m your-model.gguf -c 32768 -ngl 99 --port 8080
   ```
   The `-c` value must match the context length set in the workbench. With about 16 GB of video memory, start with a quantized model of 14B or less and a 16K to 32K context.
2. Keep the URL `http://127.0.0.1:8080/v1` and press "Test connection". Then press "Calibrate" next to the tokens-per-character setting, which measures the real ratio of this model with the server's `/tokenize` endpoint (it only tokenizes, it does not generate), so the context estimate gets more accurate.
3. Local model quality varies a lot. Try short chapters before deciding which tasks to use it for.

LM Studio and Ollama are OpenAI-compatible too. Add them with "Add an OpenAI-compatible service". Default URLs: LM Studio `http://127.0.0.1:1234/v1`, Ollama `http://127.0.0.1:11434/v1`.

### Where API keys are stored

By default keys are kept in the operating system's credential store (Windows Credential Manager, macOS Keychain), encrypted by the system and tied to your sign-in, so no key file is left in the project folder. If none is available, they go to `secrets.json` in the workbench folder, which is listed in `.gitignore`. If an older version left a secrets.json, the settings page offers a one-click move into the credential store and deletes the file afterwards. You can also use environment variables. The lookup order is: credential store → `secrets.json` → environment variables.

## Settings

Settings are stored in `config.json`, which is not committed to git.

| Item | Description |
|---|---|
| Library folder | Each book is a subfolder |
| AI runners | Claude Code, DeepSeek, llama.cpp, or your own OpenAI-compatible service |
| Claude executable path | Leave empty to detect it automatically; if it is not found, enter the full path, for example `C:\Users\you\.local\bin\claude.exe` |
| Model | For Claude Code, leave empty for the default, or enter `opus` or `sonnet` |
| Permission mode | Default `acceptEdits`, which lets Claude read and write files in the book folder |
| Pre-write reconciliation, automatic chapter-card check | Can be turned off separately |
| Alert thresholds | How many chapters before a thread or a character is flagged as dormant (characters whose names contain "unnamed" or "one-off" are not flagged; dormant characters are merged into one expandable line) |
| Service | Port, and a "Restart the service" button |

After you change the port, update the program files or when the service misbehaves, press "Restart the service" on the settings page; the page reconnects by itself (and jumps to the new address after a port change). It cannot restart while a task is running.

## When the project sits inside a sandboxed workspace

If the app runs from the **`.venv` inside this project folder** while the library lives outside it, some
environments (a sandbox-managed workspace, or a cloud-synced folder) stop that python from writing to the library,
and saving a chapter fails with `PermissionError`. Point the app at a virtualenv outside the project:

```powershell
set NS_VENV=C:\Users\you\venvs\novel-studio
start.bat
```

Or run `start-external.bat`, which defaults to `%USERPROFILE%\venvs\novel-studio`.
The app checks at startup whether it can write to the library and prints this fix on the console if it cannot,
instead of failing when you save.
