# Setup — macOS (Ventura or later, Intel or Apple Silicon)

## 1. Prerequisites
```bash
# Install Homebrew if you don't have it:
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install python@3.12 git
# Optional, for local OCR (/ocr command):
brew install tesseract
```

## 2. Get the code and install
```bash
git clone https://github.com/hughdwill-byte/JARVIS JARVIS
cd JARVIS
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 3. API key
Easiest: skip to step 5, start the app, and paste the key in **Settings → AI Brain →
Save & Apply**. Or by file:
```bash
cp .env.example .env
open -e .env    # paste ANTHROPIC_API_KEY=sk-ant-... then save
```

## 4. Permissions (macOS-specific gotcha)
The **first** time the assistant opens the camera/mic, macOS prompts once. Click Allow.
If you clicked Deny (or no prompt appears): System Settings → Privacy & Security →
**Camera** and **Microphone** → enable Terminal (or iTerm/whatever you use). Then fully quit
and reopen the terminal app.

## 5. Device tests
```bash
python run_assistant.py --check
python -m app.audio.push_to_talk --list   # set MIC_DEVICE_INDEX in .env if needed
python -m app.audio.push_to_talk          # record + transcribe test
```
Built-in FaceTime camera is usually index 0; your desk USB webcam becomes `CAMERA_INDEX=1`.

## 6. Run
```bash
python run_app.py          # ← desktop app: chat + settings in a native window
python run_assistant.py    # terminal version
python run_dashboard.py    # browser version, http://127.0.0.1:8321
```

Make it double-clickable (one time):
```bash
chmod +x launchers/JARVIS.command
```
Then double-click `launchers/JARVIS.command` in Finder to start JARVIS like an app
(you can drag it to the Dock). In the app, open **Settings** to pick your microphone,
speaker and camera by name, paste the API key, and press **Save & Apply** — no file
editing needed. Note: the mic/camera permission prompts are granted to the app that
launched JARVIS (Terminal or Finder), so approve them the first time each way you start it.

## 7. Hands-free "jarvis" mode on macOS

Works on both Intel and Apple Silicon — the wake-word detector uses the ONNX runtime
(installed by `requirements.txt`; the default TFLite backend has no Apple Silicon wheels,
which is why this project pins ONNX).

1. Make sure `WAKE_WORD_ENABLED=true` in `.env` (it is, in the template).
2. Start the assistant: `python run_assistant.py`. First run downloads the small
   (~5MB) wake model — needs internet once.
3. You'll see `[MIC ACTIVE — waiting for 'jarvis'...]`. Say **"jarvis"** (or "hey jarvis"),
   wait for the beep, then speak.
4. Say **"shutdown"** to close the microphone completely (`[MIC OFF]`), or type `/sleep`.
5. Type anything in the terminal (or `/listen`) to turn hands-free mode back on.

Gotchas:
- macOS mic permission must be granted to your Terminal app (step 4 above) — hands-free
  mode reads silence forever without it.
- If it false-triggers on music/videos, raise the sensitivity slider in
  **Settings → Hands-free wake word** to ~0.6; if it misses you, lower it to ~0.4.
- External USB speakerphone: pick it by name in **Settings → Microphone & Speech** so
  JARVIS doesn't listen through the built-in laptop mic, then run the 🎤 test.

You're set up — day-to-day usage is covered in [`docs/USER_GUIDE.md`](../docs/USER_GUIDE.md).
