# Setup — Raspberry Pi (Pi 4/5, 4GB+ RAM, Raspberry Pi OS 64-bit)

The Pi is the "appliance" build — do this AFTER the MVP works on a normal computer.
Performance expectations: chat is fine (cloud), local STT needs the `tiny` model, vision
calls take a few seconds longer.

## 1. Prerequisites
```bash
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y python3-venv python3-pip git \
    libportaudio2 portaudio19-dev espeak-ng libespeak-ng1 \
    python3-opencv tesseract-ocr
```
Note: OpenCV comes from apt (pip builds take hours on a Pi).

## 2. Get the code and install
```bash
git clone https://github.com/hughdwill-byte/JARVIS JARVIS
cd JARVIS
python3 -m venv .venv --system-site-packages   # so the venv sees apt's python3-opencv
source .venv/bin/activate
python -m pip install --upgrade pip
# Skip opencv-python from requirements (apt provides it):
grep -v "^opencv-python" requirements.txt > /tmp/reqs.txt && pip install -r /tmp/reqs.txt
```

## 3. Pi-tuned .env
```bash
cp .env.example .env
nano .env
```
Set, in addition to your API key:
```
WHISPER_MODEL_SIZE=tiny
VISION_MAX_IMAGE_EDGE=768
TTS_RATE=160
```

## 4. Audio/camera checks
```bash
# Route audio (3.5mm vs HDMI vs USB): 
sudo raspi-config    # System Options -> Audio
ls /dev/video*       # USB webcam present?
python run_assistant.py --check
python -m app.audio.push_to_talk --list
```
Use the official 5V/5A PSU; check `vcgencmd get_throttled` returns `0x0` (undervoltage
silently halves performance).

## 5. Run (and optional auto-start)
```bash
python run_assistant.py    # terminal (recommended on a headless Pi)
python run_dashboard.py    # browser app: http://<pi-ip>:8321 from another device needs DASHBOARD_HOST=0.0.0.0
```
Configure devices from the browser app's **Settings** page (microphone/speaker/camera
dropdowns + test buttons) — easier than editing `.env` over SSH. Day-to-day usage:
[`docs/USER_GUIDE.md`](../docs/USER_GUIDE.md).
Auto-start the dashboard on boot:
```bash
sudo tee /etc/systemd/system/jarvis-dashboard.service > /dev/null <<'EOF'
[Unit]
Description=JARVIS dashboard
After=network.target

[Service]
User=pi
WorkingDirectory=/home/pi/JARVIS
ExecStart=/home/pi/JARVIS/.venv/bin/python run_dashboard.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl enable --now jarvis-dashboard
```
(Adjust paths if your username isn't `pi`.)
