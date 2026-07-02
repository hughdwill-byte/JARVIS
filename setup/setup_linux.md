# Setup — Linux (Ubuntu/Debian; other distros: translate the apt line)

## 1. Prerequisites
```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git \
    libportaudio2 portaudio19-dev espeak-ng libespeak-ng1
# Optional, for local OCR (/ocr):
sudo apt install -y tesseract-ocr
# Camera access:
sudo usermod -a -G video $USER   # then log out and back in
```
(`libportaudio2` = microphone, `espeak-ng` = offline TTS voice.)

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
nano .env    # paste ANTHROPIC_API_KEY=sk-ant-... — Ctrl+O to save, Ctrl+X to exit
```

## 4. Device tests
```bash
ls /dev/video*                            # webcam should appear (video0, video1…)
python run_assistant.py --check
python -m app.audio.push_to_talk --list   # set MIC_DEVICE_INDEX in .env if needed
python -m app.audio.push_to_talk          # record + transcribe test
```
Audio problems? Open `pavucontrol` (install if missing) and check the Recording tab while
the mic test runs. More fixes: `docs/TROUBLESHOOTING.md`.

## 5. Run
```bash
python run_app.py          # ← desktop app: chat + settings in a native window
python run_assistant.py    # terminal version
python run_dashboard.py    # browser version, http://127.0.0.1:8321
```
Note: the native window needs GTK/QT webview libs on Linux
(`sudo apt install gir1.2-webkit2-4.1 python3-gi` on Ubuntu); if missing, `run_app.py`
automatically opens in your browser instead — same app.

In the app, open **Settings** to pick your microphone, speaker and camera by name and run
the device tests. Day-to-day usage: [`docs/USER_GUIDE.md`](../docs/USER_GUIDE.md).
