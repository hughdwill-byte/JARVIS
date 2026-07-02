# Your build checklist (physical/manual tasks only)

Everything below is your side of the deal. No coding anywhere on this list.
When you finish, read [`USER_GUIDE.md`](USER_GUIDE.md) to learn the day-to-day use.

## Phase 1 — Buy (one order, ~$50–70)
- [ ] 1080p USB webcam ("1080p webcam autofocus")
- [ ] USB speakerphone puck ("USB conference speakerphone")
- [ ] Gooseneck clamp mount ("gooseneck webcam clamp mount 1/4 inch")
- [ ] 2m USB extension cable ("USB 3.0 extension cable 2m")

Full options and what to avoid: [`HARDWARE.md`](HARDWARE.md).

## Phase 2 — Software prerequisites (15 min, while parts ship)
- [ ] Install Python 3.10+ (Windows: python.org installer, **tick "Add to PATH"**)
- [ ] Install Git (git-scm.com)
- [ ] Create an Anthropic API key at console.anthropic.com (add ~$5 credit)
- [ ] Set a monthly spend limit in the Anthropic console (Settings → Limits)

## Phase 3 — Install JARVIS (10 min, follow your OS guide in `setup/`)
- [ ] Clone/copy this repository onto the computer
- [ ] Run the venv + `pip install -r requirements.txt` commands from the setup guide
- [ ] Linux/Pi only: run the `apt install` line from the setup guide
- [ ] Mac only: `chmod +x launchers/JARVIS.command` so it's double-clickable

## Phase 4 — Mount and plug in (10 min)
- [ ] Clamp the mount at the back of the desk / shelf; webcam 40–70 cm above desk, angled ~45° down
- [ ] Plug webcam in (use extension cable if needed)
- [ ] Place speakerphone flat on the desk within 1 m of your chair, plug in
- [ ] Turn on a desk lamp aimed at the work surface (vision quality doubles)

## Phase 5 — Configure in the app (5 min, no file editing)
- [ ] Start JARVIS: double-click `launchers/JARVIS.command` (Mac) / `launchers/JARVIS.bat`
      (Windows), or `python run_app.py`
- [ ] macOS/Windows: approve the camera + microphone permission prompts when they appear
- [ ] Open **Settings** in the app: paste your API key, pick your **microphone**,
      **speaker**, and **camera** from the dropdowns, press **Save & Apply**
- [ ] Run all four **Device test** buttons: 🔊 speaker → 🎤 microphone → 📷 camera → 🧠 API key.
      Each failure message says exactly what to fix; aim the camera using the 📷 test preview

## Phase 6 — First conversation (2 min)
- [ ] Say **"jarvis"**, wait for the beep, ask *"what's on my desk?"* — it answers out loud
- [ ] Say **"jarvis"**, then **"shutdown"** — header shows MIC OFF
- [ ] Type `hello` — mic re-arms, JARVIS replies
- [ ] Type `/task test the assistant due today` — it appears in the sidebar

Done. JARVIS is live. Day-to-day usage manual: [`USER_GUIDE.md`](USER_GUIDE.md).
