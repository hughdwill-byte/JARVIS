# Architecture & AI model strategy

## Plain-English overview

One Python process is the assistant (`app/assistant.py`). Three thin front-ends drive it:
the desktop app (`run_app.py` — the Flask dashboard in a native pywebview window), the
browser dashboard (`run_dashboard.py`), and a terminal loop (`run_assistant.py`). Input —
typed, or spoken (wake-word or push-to-talk, transcribed locally) — goes to a **router**:
slash commands run local tools directly; everything else goes to the **LLM brain** with a
compact context block (latest desk summary, open tasks, recent notes, approved preferences,
last N conversation turns). Replies print to screen and are optionally spoken by a local
TTS engine. All state lives in one SQLite file you can copy, inspect, or delete.

**Settings** (`app/dashboard/settings.py`) is schema-driven: one list of field definitions
renders the whole Settings page, validates writes, and persists to `.env` (comments
preserved, unknown keys rejected, the API key masked and never echoed back). *Save & Apply*
hot-swaps the running Assistant with a freshly-loaded config, so changes apply in ~1 second
without restarting the process.

## Voice data flow

```mermaid
sequenceDiagram
    participant U as You
    participant M as Mic (sounddevice)
    participant WW as openWakeWord (LOCAL)
    participant W as faster-whisper (LOCAL)
    participant A as Assistant/Router
    participant C as Claude API (CLOUD)
    participant T as pyttsx3 TTS (LOCAL)
    U->>M: "jarvis" (or /voice push-to-talk)
    Note over M,WW: [MIC ACTIVE] — chunks scored locally,<br/>discarded until wake word fires
    M->>WW: 80ms chunks
    WW->>M: wake! record until you pause
    M->>W: audio buffer (never leaves machine)
    W->>A: transcript text
    A->>C: text + trimmed context (only free-chat; commands stay local)
    C->>A: reply text
    A->>T: reply
    T->>U: spoken audio (interruptible with /stop)
```

## Vision data flow

```mermaid
sequenceDiagram
    participant U as You
    participant Cam as Webcam (OpenCV)
    participant P as Pillow resize (LOCAL)
    participant V as Claude vision (CLOUD)
    participant S as Scene memory (SQLite)
    U->>Cam: /desk (explicit command only)
    Note over Cam: [CAMERA ACTIVE] banner
    Cam->>P: full-res frame, saved to data/snapshots/
    P->>V: JPEG downscaled to ≤1024px (cost + privacy)
    V->>U: spoken desk description
    V->>S: summary + "OBJECTS: ..." inventory (text only)
    Note over S: /changes diffs the last two inventories LOCALLY — no API call
```

## What runs where

| Layer | Where | Cost |
|---|---|---|
| Wake word detection (openWakeWord) | Local | Free |
| Speech-to-text (faster-whisper) | Local | Free |
| Text-to-speech (pyttsx3) | Local | Free |
| OCR (`/ocr`, tesseract) | Local | Free |
| Camera capture, resize, retention pruning | Local | Free |
| Router, tasks, notes, reminders, scene diffing, sandboxed `/run` | Local | Free |
| SQLite memory + dashboard | Local | Free |
| Chat brain, desk description, `/read`, doc summaries | Claude API | The only paid piece |

**Cheapest functional setup:** no API key at all — notes, tasks, reminders, snapshots, OCR
and the dashboard work; chat replies explain what's missing. **The real setup:** one
Anthropic API key (~$3–8/month typical student use). **Fully-local alternative:** point
`llm_client.py` at Ollama (llama3.1-8b) — free but much weaker and no vision-quality parity;
not the default because the brain is where quality matters most.

## Model strategy & cost control

Two models, routed automatically in `app/brain/llm_client.py`:

- **Fast/cheap (claude-haiku-4-5):** everyday chat, quick questions, task phrasing.
- **Smart (claude-sonnet-5):** anything with an image, `/doc`, `/projq`, `/code`, `/plan`,
  long pasted content (>600 chars), or "hard" keywords (debug, derive, refactor…).

Built-in cost reducers:

1. **Local preprocessing** — STT, OCR, scene diffing, and integrity pre-checks never hit the API.
2. **Images only on demand** — one downscaled (≤1024px, q85 JPEG) image per vision command;
   `/changes` reuses stored text instead of re-sending photos.
3. **Short prompts** — context block caps (5 tasks, 3 notes, 10 prefs), history trimmed to
   `MEMORY_CONTEXT_TURNS` (default 12), replies capped at `LLM_MAX_TOKENS` (default 1024).
4. **Cheap-by-default routing** with escalation only when heuristics say the task is hard.
5. **Free fallbacks** — `/ocr` (local tesseract) vs `/read` (cloud vision); use the free one
   for clean printed text.

## Privacy trade-offs

Sending data to a cloud API is the price of a strong brain. What this design does about it:

- **Audio: never uploaded.** Transcription is local; only the resulting *text* goes to the API.
- **Images: only on explicit vision commands**, downscaled first, deleted from disk after
  `SNAPSHOT_RETENTION_DAYS` (set `0` for delete-after-analysis). Long-term memory keeps text
  descriptions, never pixels. Keep the camera aimed at the desk surface, not at people or
  housemates' space.
- **Text: your messages and stored context go to the API** — don't paste secrets/passwords
  into chat. Anthropic's API terms do not train on API data by default, but treat any cloud
  service as "someone else's computer".
- **The camera is never always-on.** For the mic, hands-free wake-word mode does keep the
  device streaming — but every chunk is scored locally and discarded, nothing is stored or
  uploaded until the wake word fires, and saying "shutdown" closes the device entirely.
  Turn it off in Settings for strict push-to-talk-only operation (mic opens per-utterance).
- **Everything visible:** `[CAMERA ACTIVE]`/`[MIC ACTIVE]` banners in the terminal; the
  app header shows live MIC LISTENING / CAMERA ACTIVE / LLM pills (the mic pill is also the
  on/off toggle); `/status` shows every device's state.
- **Memory under your control:** `/memories` lists all long-term facts, `/forget` deletes,
  and nothing is stored long-term without your explicit `/remember`.
