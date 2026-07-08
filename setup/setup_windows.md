# Setup — Windows 10/11

## 1. Prerequisites
1. Install Python 3.10+ from https://python.org/downloads — **tick "Add python.exe to PATH"**.
2. Install Git from https://git-scm.com/download/win (defaults are fine).
3. Verify in a new PowerShell window:
   ```powershell
   python --version
   git --version
   ```

## 2. Get the code and install
```powershell
git clone https://github.com/hughdwill-byte/JARVIS JARVIS
cd JARVIS
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 3. API key
Easiest: skip to step 6, start the app, and paste the key in **Settings → AI Brain →
Save & Apply**. Or by file:
```powershell
copy .env.example .env
notepad .env
```
Paste your key: `ANTHROPIC_API_KEY=sk-ant-...` (no quotes). Save and close.

## 4. Permissions (Windows-specific gotcha)
Settings → Privacy & security → **Microphone** → turn ON "Let desktop apps access your
microphone". Do the same under **Camera**. Skipping this makes the mic silently record nothing.

## 5. Device tests
```powershell
python run_assistant.py --check          # all-in-one self test
python -m app.audio.push_to_talk --list  # list mics; put the right number in .env as MIC_DEVICE_INDEX
python -m app.audio.push_to_talk         # record + transcribe test
```
Camera opens the wrong device (e.g. laptop lid cam)? Set `CAMERA_INDEX=1` in `.env`.
Speaker test: step 1 of the first demo — the assistant speaks its reply.

## 6. Run
```powershell
python run_app.py           # ← desktop app: chat + settings in its own window
python run_assistant.py     # terminal assistant
python run_dashboard.py     # browser version, http://127.0.0.1:8321
```
(Every new PowerShell window: `cd JARVIS` then `.venv\Scripts\activate` first.)

Prefer double-click? Open the `launchers` folder and double-click **JARVIS.bat**
(right-click → Send to → Desktop (create shortcut) to put it on your desktop).
In the app, open **Settings** to pick your microphone, speaker and camera by name,
paste the API key, and press **Save & Apply** — no file editing needed.
The native window uses Windows' built-in WebView2 (already present on Windows 10/11);
if it's somehow missing, JARVIS opens in your browser instead — same app.

## Optional: the "JARVIS is working" light

Want a visible cue when JARVIS is listening / thinking / speaking, without a window
in your way? Turn on **Settings → Speaker & Voice output → Menu-bar status light**
(one-time `pip install pystray`). On Windows it appears as a small coloured dot in the
**system tray** (bottom-right, by the clock): green = listening, amber = thinking,
blue = speaking; it hides when idle and never covers your screen or blocks clicks.

Windows 11 hides *new* tray icons in the "⌃" overflow flyout by default. To keep the
dot always visible, drag it from that flyout onto the taskbar (or **Settings →
Personalization → Taskbar → Other system tray icons** and turn it on).

You're set up — day-to-day usage is covered in [`docs/USER_GUIDE.md`](../docs/USER_GUIDE.md).
