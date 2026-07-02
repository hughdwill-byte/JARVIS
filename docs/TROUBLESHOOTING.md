# Troubleshooting

**Start with the built-in diagnostics — they solve most problems for you:**

1. In the app: **Settings → Device tests** — run 🔊 🎤 📷 🧠. Each failure message says
   exactly what to fix.
2. Wrong device? **Settings → pick the microphone/speaker/camera by name → Save & Apply**
   (use *Scan for cameras* and *Rescan devices* after plugging things in).
3. From a terminal: `python run_assistant.py --check` tests every subsystem with fix hints.

Then find your symptom below.

## Camera not detected
- **Settings → Camera & Vision → Scan for cameras**, pick the right one, Save & Apply,
  then **Test camera** — the preview shows exactly what JARVIS sees.
- Close Zoom/Teams/browser tabs holding the camera, then scan again.
- Different USB port (prefer direct, not hub).
- Linux: `ls /dev/video*` should list a device; add yourself to the video group:
  `sudo usermod -a -G video $USER` then log out/in.
- macOS: System Settings → Privacy & Security → Camera → enable your terminal app.

## Microphone not detected / hears silence
- **Settings → Microphone & Speech** — pick your mic by name (the ★ marks the system
  default), Save & Apply, then **Test microphone**: it records 4 seconds and shows you what
  it heard.
- Check OS input volume isn't 0/muted; speak within ~1 m.
- Terminal alternative: `python -m app.audio.push_to_talk --list` then set
  `MIC_DEVICE_INDEX` in `.env`.
- **Windows:** Settings → Privacy & security → Microphone → enable "Let desktop apps access
  your microphone" (this is the classic silent-failure cause).
- **macOS:** System Settings → Privacy & Security → Microphone → enable Terminal/iTerm.
  The permission prompt only appears the first time — if you clicked Deny, fix it here.
- **Linux:** `sudo apt install libportaudio2`; check levels in `pavucontrol` (input tab).

## No sound output
- **Settings → Speaker & Voice output** — pick your speaker by name, Save & Apply, then
  **Test speaker**. "System default" follows your OS sound settings; picking a specific
  device locks JARVIS to it regardless.
- pyttsx3 backends: Windows/macOS work out of the box; **Linux needs** `sudo apt install espeak-ng`.
- Check the OS default output device is your speaker; test with any music.
- Raspberry Pi: force output with `sudo raspi-config` → System → Audio, and use
  `TTS_RATE=160` for clearer speech.
- Still nothing? Set `TTS_PROVIDER=none` to run text-only while you sort the speaker.

## API key errors ("rejected", 401)
- Paste the key in **Settings → AI Brain**, Save & Apply, then **Test API key**. Make sure
  you copied the whole key (they're long) with no extra spaces.
- Key must be active with credit: check console.anthropic.com → Billing.
- Editing `.env` by hand instead? The line must be exactly `ANTHROPIC_API_KEY=sk-ant-...` —
  no quotes, no spaces — then restart the app.

## `TypeError: unsupported operand type(s) for |` on startup (often with missing flask/whisper too)
Your virtual environment was built with an old Python (3.9 or earlier) — this one error
explains everything: the code needs 3.10+, and the dependency install aborts partway on
old Pythons, leaving modules like flask missing. Rebuild the venv with a modern Python,
**from the JARVIS folder**:
```bash
# macOS (get 3.12 first if needed: brew install python@3.12)
deactivate 2>/dev/null; rm -rf .venv
python3.12 -m venv .venv && source .venv/bin/activate
python --version          # must say 3.10+
pip install -r requirements.txt
python run_assistant.py --check
```
Windows: install Python 3.12 from python.org, then `py -3.12 -m venv .venv` and the same
steps. (Newer JARVIS versions detect this and print these instructions automatically.)

## Package install errors
- Always inside the venv (`source .venv/bin/activate` / `.venv\Scripts\activate`).
- Upgrade pip first: `python -m pip install --upgrade pip`.
- `sounddevice` fails on Linux/Pi → `sudo apt install libportaudio2 portaudio19-dev`.
- `opencv-python` slow/failing on Pi → use the apt package instead:
  `sudo apt install python3-opencv` and create the venv with `--system-site-packages`.
- `pyttsx3` on Linux → `sudo apt install espeak-ng libespeak-ng1`.
- Python must be 3.10+ (`python3 --version`).

## Slow responses
- First `/voice` is slow because Whisper downloads its model once — subsequent calls are fast.
- Whisper slow on weak hardware → `WHISPER_MODEL_SIZE=tiny` in `.env`.
- Vision calls take 3–8 s (upload + analysis) — normal.
- Chat slow? You may be routing everything to the smart model; check your messages aren't
  all >600 chars of pasted content.

## Expensive API usage
- See [`COST_CONTROL.md`](COST_CONTROL.md). Quick wins, all in **Settings**: set the
  heavy-lifting model to Haiku (AI Brain), lower image detail to 768 (Camera & Vision),
  reduce conversation memory to 6 turns (Advanced) — plus a spend limit in the Anthropic console.

## Bad image recognition
- Light the desk — a desk lamp fixes most "it can't see anything" complaints.
- Camera 40–70 cm above the desk, angled down; avoid backlight from a window behind the desk.
- For reading pages: hold the page flat, fill the frame, use `/read` (cloud) rather than
  `/ocr` for handwriting or curved pages.
- Raise `VISION_MAX_IMAGE_EDGE=1568` temporarily for small text (costs a bit more).

## TTS sounds robotic
- It is — pyttsx3 is the free offline engine. Adjust the speaking-speed slider in
  **Settings → Speaker & Voice output** (160–190 is most natural).
- Free upgrade: `pip install edge-tts` (Microsoft neural voices, needs internet) — swap the
  provider in `app/audio/text_to_speech.py`'s `speak()`; the class structure already isolates it.
- Paid (ElevenLabs) only if voice quality really matters to you.

## Raspberry Pi performance
- Use `WHISPER_MODEL_SIZE=tiny`, `VISION_MAX_IMAGE_EDGE=768`.
- Install OpenCV via apt (see install errors above), not pip.
- Pi 4/5 with 4GB+ required for local Whisper; below that, set `STT_PROVIDER=none` and type.
- Use a proper 5V/5A PSU — undervoltage throttles the CPU silently (`vcgencmd get_throttled`).

## Linux audio issues (general)
- PipeWire/PulseAudio device confusion: `pavucontrol` → Recording tab while `/voice` runs —
  make sure the stream is attached to the right mic.
- ALSA-only systems: set the default card in `~/.asoundrc`.
- "device busy": another app holds the mic exclusively; close it.

## App window / dashboard won't load
- The window is blank on Windows → WebView2 runtime missing (rare on Win 10/11); JARVIS
  falls back to your browser automatically — same app.
- Browser version: is `run_dashboard.py` still running in its terminal? It must stay open.
- Port taken → change the dashboard port in **Settings → Advanced** (or `DASHBOARD_PORT`
  in `.env`), then restart the app.
- It binds 127.0.0.1 (same machine only) by design; to reach it from your phone on your own
  LAN set `DASHBOARD_HOST=0.0.0.0` in `.env` — only on a network you trust.

## Claude Code backend problems (Brain source = claude_code or hybrid)
- "CLI not found" → install Node.js (nodejs.org), then
  `npm install -g @anthropic-ai/claude-code`, restart your terminal and JARVIS.
- "isn't logged in" → run `claude` in a terminal and sign in with your claude.ai
  (Pro) account; then try again.
- Replies stopped mid-day → you may have hit your Pro plan's usage window; it resets
  within a few hours, or switch Brain source to `anthropic` temporarily.
- Everything feels slow → that's the trade-off of this backend (~4–8s per reply);
  use `hybrid` so chat stays on the fast API.

## Wake word problems
- Doesn't hear "jarvis" → lower the sensitivity slider (Settings → Hands-free wake word)
  to ~0.4; check the right mic is selected; speak from within ~2 m.
- Triggers on TV/music/speech → raise sensitivity to ~0.6.
- First start needs internet once to download the small wake model (~5MB).
- Mac: `pip install onnxruntime` must have succeeded — rerun
  `pip install -r requirements.txt` if hands-free reports it missing.
