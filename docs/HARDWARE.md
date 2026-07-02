# Hardware guide — bill of materials

You handle everything on this page (buying, mounting, plugging in). No soldering, no
electronics skills needed at any tier. Once things are plugged in, you select which
microphone/speaker/camera JARVIS uses from dropdowns in the app's **Settings** page —
no configuration files.

## Which build to do first

**Build Tier B (Recommended) using a computer you already own.** Reasons:

- Compute is the expensive part, and you already have it. A laptop that runs a browser runs
  this entire stack.
- A Raspberry Pi is *slower and not cheaper* once you add PSU, SD card, and case (~$100+),
  and local Whisper STT is painfully slow on a Pi 4. The Pi is a nice *later* project to make
  the assistant a standalone appliance — wrong place to start.
- The only genuinely new hardware you need is a webcam pointed at the desk and a decent
  mic/speaker. ~$50–60 total.

**Don't overbuild at the start:** no wake-word button, no LED ring, no dedicated screen, no
sensors, no Pi. The MVP proves the software loop first; gadgets come after.

## Compute options compared

| Option | Cost | Verdict |
|---|---|---|
| **Your existing laptop/desktop** | $0 | **Winner.** Runs everything including local Whisper. |
| Main gaming/work PC | $0 | Also fine; slightly faster Whisper if it has a GPU. Downside: assistant only exists while your PC is on. |
| Old laptop (i5 4th-gen+, 8GB) | $0–80 used | Great as a dedicated always-on unit later. |
| Used mini PC (Dell/Lenovo/HP 1L "tiny") | $60–120 used | Best *dedicated* option per dollar. Search: "Dell OptiPlex micro i5 8GB". |
| Raspberry Pi 5 (8GB) + accessories | $110–140 new | Works, but use cloud STT or `tiny` Whisper; slowest option. For the appliance phase, not the MVP. |

## Bill of materials by tier

### Tier A — Minimum viable (~$25–35 new spend)

| Item | Choice | Est. price | Search terms | Avoid |
|---|---|---|---|---|
| Compute | Your existing computer | $0 | — | — |
| Camera | Any 1080p USB webcam | $15–25 | "1080p USB webcam microphone" | 480p/720p no-brand units — text won't be readable |
| Microphone | The webcam's built-in mic | $0 | — | — |
| Speaker | Laptop speakers / any 3.5mm or USB speaker you own | $0–10 | "USB mini speaker" | — |
| Mounting | Stack of books or the webcam's monitor clip | $0 | — | — |

### Tier B — Recommended (~$50–70 new spend) ← build this

| Item | Purpose | Recommended | Cheapest OK | Advanced | Est. price | Search terms | Avoid |
|---|---|---|---|---|---|---|---|
| Compute | Runs everything | Existing laptop/desktop | Same | Used mini PC as dedicated unit | $0 | "dell optiplex micro i5" (advanced only) | Buying new compute for the MVP |
| Camera | Sees the desk | 1080p USB webcam w/ 1.5m+ cable | Tier A webcam | Logitech C920/C922 (used ~$30–40) | $20–30 | "1080p webcam autofocus", "logitech c920 used" | Fisheye/wide-angle "conference" cams (distort text); ring-light gimmick cams |
| Mic + speaker | Hear you, talk back | **USB speakerphone puck** (mic+speaker in one, echo cancellation) | Webcam mic + existing speakers | Anker PowerConf (used) | $25–35 | "USB conference speakerphone", "anker powerconf used" | Gaming headsets (defeats the room-assistant point); XLR mics (overkill) |
| Mounting | Overhead-ish desk view | Cheap gooseneck phone/webcam clamp arm | Books/shelf | Small desk boom arm | $8–15 | "gooseneck webcam clamp mount 1/4 inch" | Suction mounts (fall), tape |
| Cables | Reach + tidiness | 2m USB-A extension | — | Powered USB hub | $5–8 | "USB 3.0 extension cable 2m" | Unpowered hubs with 3+ devices |

### Tier C — Advanced (~$150–250, later)

| Item | Option | Est. price | Notes |
|---|---|---|---|
| Dedicated compute | Used 1L mini PC (i5-8500T, 16GB) or Pi 5 8GB kit | $80–140 | Assistant becomes an always-on appliance |
| Camera | Logitech C920/C922 or 4K webcam | $30–70 | Better OCR of documents |
| Speakerphone | Anker PowerConf / Jabra Speak 410 (used) | $40–60 | Noticeably better far-field pickup |
| Push-to-talk button | USB foot pedal or macro key | $10–15 | "USB foot pedal switch HID" |
| LED indicator | Pi GPIO LED or smart-plug lamp | $5–10 | Physical "mic live" light |
| Screen | 7" HDMI touchscreen for the dashboard | $35–50 | "7 inch HDMI touchscreen" |
| Sensors (optional) | Motion/light sensor via Pi GPIO | $5 | Auto-dim, presence-aware reminders |

## Physical placement (your part)

- **Camera:** 40–70 cm above the desk surface, angled ~45° down, clamped to a shelf, monitor
  top, or gooseneck arm at the back of the desk. It should see the main working area, not
  your face. Check for glare from your desk lamp. USB into the computer directly (use the
  extension cable if needed).
- **Microphone/speakerphone:** flat on the desk, within ~1 m of where you sit, away from the
  keyboard (typing noise) and not directly under the speaker output path. USB in.
- **Speaker:** if separate from the mic, point it away from the mic to avoid the assistant
  hearing itself. 3.5mm or USB.
- **Optional screen (Tier C):** propped at the back of the desk showing the dashboard
  (`python run_dashboard.py`, browser in kiosk/fullscreen mode).
- Route cables along the desk edge; label the webcam's USB plug so you can find it.
- **Aiming the camera:** use Settings → Device tests → *Test camera* in the app — it shows
  exactly what JARVIS sees, so adjust the mount until the whole work surface is in frame.

## Shopping summary — what to actually order today (Tier B)

1. 1080p USB webcam — ~$25 — "1080p webcam autofocus"
2. USB speakerphone puck — ~$30 — "USB conference speakerphone"
3. Gooseneck clamp mount — ~$10 — "gooseneck webcam clamp mount"
4. 2m USB extension — ~$6 — "USB 3.0 extension cable 2m"

**Total: ~$70 max**, often under $55. Everything else waits until the MVP is running.
