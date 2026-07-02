# Your build checklist (physical/manual tasks only)

Everything below is your side of the deal. No coding anywhere on this list.

## Phase 1 — Buy (one order, ~$50–70)
- [ ] 1080p USB webcam ("1080p webcam autofocus")
- [ ] USB speakerphone puck ("USB conference speakerphone")
- [ ] Gooseneck clamp mount ("gooseneck webcam clamp mount 1/4 inch")
- [ ] 2m USB extension cable ("USB 3.0 extension cable 2m")

## Phase 2 — Software prerequisites (15 min, while parts ship)
- [ ] Install Python 3.10+ (Windows: python.org installer, **tick "Add to PATH"**)
- [ ] Install Git (git-scm.com)
- [ ] Create an Anthropic API key at console.anthropic.com (add ~$5 credit)
- [ ] Set a monthly spend limit in the Anthropic console (Settings → Limits)

## Phase 3 — Install the assistant (10 min, follow your OS guide in `setup/`)
- [ ] Clone/copy this repository onto the computer
- [ ] Run the venv + `pip install -r requirements.txt` commands from the setup guide
- [ ] Copy `.env.example` to `.env` and paste in your API key
- [ ] Linux/Pi only: run the `apt install` line from the setup guide

## Phase 4 — Mount and plug in (10 min)
- [ ] Clamp the mount at the back of the desk / shelf; webcam 40–70 cm above desk, angled ~45° down
- [ ] Plug webcam in (use extension cable if needed)
- [ ] Place speakerphone flat on the desk within 1 m of your chair, plug in
- [ ] Turn on a desk lamp aimed at the work surface (vision quality doubles)
- [ ] macOS/Windows: approve the camera + microphone permission prompts when they appear

## Phase 5 — Test (5 min)
- [ ] `python run_assistant.py --check` → every line should say OK (fix hints print if not)
- [ ] Run the 9-step first demo from the README (type, speak, snapshot, /desk, note, task, reminder)
- [ ] `python run_dashboard.py` → open http://127.0.0.1:8321, send a message, watch the
      CAMERA indicator flip during `/desk`

Done. The assistant is live. Next upgrade when you feel like it: wake word + nicer voice
(README → "Upgrades after the MVP").
