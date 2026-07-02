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
git clone <your-repo-url> JARVIS
cd JARVIS
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 3. API key
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
python run_assistant.py
python run_dashboard.py    # http://127.0.0.1:8321
```
