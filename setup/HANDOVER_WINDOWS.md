# JARVIS — Mac → Windows handover

Everything you need to get JARVIS running on the new Windows PC. The goal:
**one command installs all software, all code, and your key.**

Branch installed: **`claude/ponytail-full-command-wuy33g`** (also the repo's default branch).

---

## The one thing to run

On the new Windows PC, open **PowerShell** (Start → type `powershell` → Enter) and paste
this single line:

```powershell
powershell -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/hughdwill-byte/JARVIS/claude/windows-setup-handover-ahmutr/setup/windows_bootstrap.ps1 | iex"
```

That downloads and runs the installer, which:

1. Installs **Python 3.12, Git, Node.js** (and, if you say yes, **Ollama, Tesseract,
   FFmpeg**) via winget — no manual downloads.
2. Clones the repo on the `claude/ponytail-full-command-wuy33g` branch to `C:\Users\<you>\JARVIS`.
3. Builds the Python virtualenv and installs every dependency.
4. Asks for your **Anthropic API key once, hidden**, and writes `.env`.
5. Optionally pulls the local Ollama models, sets up connected-apps, imports your old data.
6. Makes a **Desktop shortcut** and runs the self-test.

It's safe to re-run — it skips whatever is already done.

> Prefer not to run a remote script? Do the same manually:
> ```powershell
> git clone https://github.com/hughdwill-byte/JARVIS JARVIS ; cd JARVIS
> powershell -ExecutionPolicy Bypass -File setup\windows_bootstrap.ps1
> ```

---

## About the keys (read once)

**Your API keys are not in this repo and I can't copy them for you.** They live only in the
gitignored `.env` file on your Mac and were never uploaded anywhere. So the installer prompts
you to paste your key instead of carrying a file around — exactly what you asked for.

- **Anthropic API key** — the only one JARVIS *needs*. Powers chat, vision and agent tasks.
  Get it or make a fresh one at **https://console.anthropic.com** → API Keys. (A Claude Pro
  subscription is a different product and does **not** give you an API key.)
  - If you still have your Mac: it's the value after `ANTHROPIC_API_KEY=` in `~/JARVIS/.env`.
- You never have to touch `.env` by hand — you can also paste the key in the app:
  **Settings → AI Brain → Save & Apply**.

### Optional keys — only if you use those features (connected apps / MCP)

These go in `mcp_servers.json` (created from `mcp_servers.example.json`). Copy just the apps
you use from the Mac's file, or re-issue each token:

| App | Secret needed | Where to get it |
|---|---|---|
| Gmail | Google OAuth (browser login) | one-time `npx @gongrzhe/server-gmail-autoauth-mcp auth` |
| Google Calendar | `GOOGLE_OAUTH_CREDENTIALS` (path to `gcp-oauth.keys.json`) | Google Cloud Console |
| Google Drive | Google OAuth (browser login) | server README |
| Notion | `NOTION_TOKEN` | notion.so → My integrations |
| Slack | `SLACK_BOT_TOKEN` + `SLACK_TEAM_ID` | Slack app admin |
| GitHub | `GITHUB_PERSONAL_ACCESS_TOKEN` | github.com → Settings → Developer settings |
| Brave Search | `BRAVE_API_KEY` | brave.com/search/api |
| Spotify | `SPOTIFY_CLIENT_ID` + `SPOTIFY_CLIENT_SECRET` | developer.spotify.com |
| Hugging Face (optional) | `HF_TOKEN` in `.env` | huggingface.co → Access Tokens (only silences a warning) |

---

## Software inventory (what the installer sets up)

**Required**

- **Python 3.10+** — the app runtime.
- **Git** — to clone/update the code.
- **Node.js LTS** — runs connected-app (MCP) servers via `npx`.

**Optional but recommended**

- **Ollama** (https://ollama.com) — free offline brain + local notes search. Models:
  `qwen3:8b` (chat) and `nomic-embed-text` (RAG embeddings).
- **Tesseract OCR** — free local `/ocr` text reading from the camera.
- **FFmpeg** — smoother audio on some machines.
- **WebView2** — already on Windows 10/11; gives the native app window (falls back to browser).
- **Claude Code CLI** (only if you want to run the brain on a Claude Pro/Max subscription
  instead of the API): `npm install -g @anthropic-ai/claude-code`, then run `claude` once to log in.

All Python packages come from `requirements.txt`: anthropic, flask, opencv, pillow, pyttsx3,
sounddevice, faster-whisper, openwakeword, onnxruntime, pytesseract, pywebview, pypdf, mcp, etc.

---

## What can't come over automatically (2 files, only if you want your history)

Both are gitignored, so they only exist on your Mac:

1. **`.env`** — your Anthropic API key and settings.
2. **`mcp_servers.json`** — your connected-apps + their tokens (see table above).
3. **`data/jarvis.db`** — your notes, tasks, reminders and long-term memories. Copy it from
   `~/JARVIS/data/jarvis.db` on the Mac into the new `JARVIS\data\` folder (the installer can
   import it for you when asked). Skip it for a clean start.

Everything else is regenerated automatically.

### Easy way to bundle these on the Mac

Double-click **`launchers/make-secrets-zip.command`** in your Mac's JARVIS folder. It builds a
**password-protected** `jarvis-secrets.zip` on your Desktop containing whatever exists (`.env`,
`mcp_servers.json`, any Google OAuth file, and — if you want — `data/jarvis.db`). Send that zip to
the new PC and unzip it **into the `JARVIS` folder** (`.env` + `mcp_servers.json` at the root,
`jarvis.db` in `data\`), replacing what the installer created. Delete the zip afterwards.

> Safer alternative: don't move `.env` at all — just recreate the Anthropic key at
> console.anthropic.com and paste it into the installer's hidden prompt. Then the zip only needs
> `mcp_servers.json` and `data/jarvis.db`.

---

## First run

- Double-click the **JARVIS** desktop shortcut, or:
  ```powershell
  cd $HOME\JARVIS ; .venv\Scripts\activate ; python run_app.py
  ```
- **Windows gotcha:** Settings → Privacy & security → **Microphone** *and* **Camera** →
  turn ON "Let desktop apps access…" or the mic silently records nothing.
- In the app: **Settings** → pick microphone, speaker, camera by name → **Save & Apply** →
  run the four Device tests at the bottom.

Day-to-day usage: [`docs/USER_GUIDE.md`](../docs/USER_GUIDE.md). Trouble:
[`docs/TROUBLESHOOTING.md`](../docs/TROUBLESHOOTING.md).
