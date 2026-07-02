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
git clone <your-repo-url> JARVIS
cd JARVIS
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 3. API key
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
python run_assistant.py     # terminal assistant
python run_dashboard.py     # then open http://127.0.0.1:8321
```
(Every new PowerShell window: `cd JARVIS` then `.venv\Scripts\activate` first.)
