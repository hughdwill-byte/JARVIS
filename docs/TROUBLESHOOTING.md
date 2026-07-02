# Troubleshooting

Run `python run_assistant.py --check` first — it tests every subsystem and prints the exact
fix for anything missing. Then find your symptom below.

## Camera not detected
- Try `CAMERA_INDEX=1` (then 2) in `.env` — laptops' built-in cam is usually 0, USB cam 1.
- Close Zoom/Teams/browser tabs holding the camera.
- Different USB port (prefer direct, not hub). Re-plug and rerun `--check`.
- Linux: `ls /dev/video*` should list a device; add yourself to the video group:
  `sudo usermod -a -G video $USER` then log out/in.
- macOS: System Settings → Privacy & Security → Camera → enable your terminal app.

## Microphone not detected / hears silence
- `python -m app.audio.push_to_talk --list` — find your mic's number, set `MIC_DEVICE_INDEX` in `.env`.
- Check OS input volume isn't 0/muted; speak within ~1 m.
- **Windows:** Settings → Privacy & security → Microphone → enable "Let desktop apps access
  your microphone" (this is the classic silent-failure cause).
- **macOS:** System Settings → Privacy & Security → Microphone → enable Terminal/iTerm.
  The permission prompt only appears the first time — if you clicked Deny, fix it here.
- **Linux:** `sudo apt install libportaudio2`; check levels in `pavucontrol` (input tab).

## No sound output
- pyttsx3 backends: Windows/macOS work out of the box; **Linux needs** `sudo apt install espeak-ng`.
- Check the OS default output device is your speaker; test with any music.
- Raspberry Pi: force output with `sudo raspi-config` → System → Audio, and use
  `TTS_RATE=160` for clearer speech.
- Still nothing? Set `TTS_PROVIDER=none` to run text-only while you sort the speaker.

## API key errors ("rejected", 401)
- `.env` must contain exactly `ANTHROPIC_API_KEY=sk-ant-...` — no quotes, no spaces, no
  trailing newline mid-key. Restart the assistant after editing.
- Key must be active with credit: check console.anthropic.com → Billing.
- Make sure you copied the whole key (they're long).

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
- See [`COST_CONTROL.md`](COST_CONTROL.md). Quick wins: `LLM_MODEL_SMART=claude-haiku-4-5`,
  `VISION_MAX_IMAGE_EDGE=768`, `MEMORY_CONTEXT_TURNS=6`, and a spend limit in the console.

## Bad image recognition
- Light the desk — a desk lamp fixes most "it can't see anything" complaints.
- Camera 40–70 cm above the desk, angled down; avoid backlight from a window behind the desk.
- For reading pages: hold the page flat, fill the frame, use `/read` (cloud) rather than
  `/ocr` for handwriting or curved pages.
- Raise `VISION_MAX_IMAGE_EDGE=1568` temporarily for small text (costs a bit more).

## TTS sounds robotic
- It is — pyttsx3 is the free offline engine. Adjust `TTS_RATE` (160–190 is most natural).
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

## Dashboard won't load
- Is `run_dashboard.py` still running in its terminal? It must stay open.
- Port taken → change `DASHBOARD_PORT` in `.env`.
- It binds 127.0.0.1 (same machine only) by design; to reach it from your phone on your own
  LAN set `DASHBOARD_HOST=0.0.0.0` — only on a network you trust.
