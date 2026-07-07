# JARVIS user guide — how to actually use it

This is the manual for everyday use, written for someone who has never touched the code.
It assumes JARVIS is installed (if not: your OS guide in [`setup/`](../setup/) first).

## Starting JARVIS

- **Mac:** double-click `launchers/JARVIS.command` (first time only: open Terminal in the
  JARVIS folder and run `chmod +x launchers/JARVIS.command`).
- **Windows:** double-click `launchers/JARVIS.bat` (right-click → Send to → Desktop to make
  a desktop shortcut).
- **Any OS, from a terminal:** `python run_app.py` inside the JARVIS folder (with the
  virtual environment active).

A window opens with two pages — **Chat** and **Settings** — switchable at the top-left.
Close the window to stop JARVIS completely (mic and camera included).

## The interface at a glance

**Header indicators (always truthful — this is your privacy dashboard):**

| Indicator | Meaning |
|---|---|
| `MIC LISTENING — say 'jarvis'` (green) | Hands-free mode on. Audio is being checked for the wake word locally and discarded. **Click it to turn the mic off.** |
| `MIC OFF` | Microphone device is fully closed. **Click to turn listening back on.** |
| `CAMERA ACTIVE` (red) | A snapshot is being taken right now. Only lights during camera commands. |
| `LLM ONLINE` / `LLM OFFLINE` | Whether the AI brain (API key) is working. Offline = local features still work. |
| `■ Stop voice` | Cuts JARVIS off mid-sentence. |

**Sidebar:** your open tasks, recent notes, and recent desk snapshots, always current.

## Talking to JARVIS

Three ways, all equivalent — pick per moment:

1. **Hands-free:** say **"jarvis"** (or "hey jarvis"), wait for the beep, then speak
   naturally: *"jarvis… what's on my desk?"*, *"jarvis… explain recursion simply"*.
   It starts speaking as soon as the first sentence of its reply is ready (no waiting for
   the full answer). After it finishes, **just keep talking** — it listens for ~8 seconds
   after each reply so you can go back and forth without repeating the wake word (say
   nothing to end the conversation, or turn this off: Settings → Hands-free → Conversation
   mode). Your words and its replies appear in the chat with a 🎤.
2. **Typing:** just type in the chat box. Anything without a leading `/` is normal
   conversation.
3. **Push-to-talk (terminal only):** type `/voice`, speak, press Enter.

**Controlling the microphone:**

- Say **"shutdown"** (or "stop listening" / "go to sleep") → mic fully off.
- Type anything, click the MIC indicator, or use `/listen` → listening again.
- Type `/sleep` → mic off without saying anything.
- In **Settings → Hands-free wake word** you can disable the feature entirely, or adjust
  sensitivity if it false-triggers on TV/music (raise it) or misses you (lower it).

**Conversation tips:**

- It remembers the recent conversation — follow-ups like *"shorter"*, *"give me an example"*,
  *"now in Python"* work.
- It knows your open tasks, recent notes, and the latest desk snapshot without being told.
- Replies are spoken aloud; `■ Stop voice` or `/stop` (or saying "stop talking") interrupts.
- `/clear` wipes the conversation history for a fresh start (notes/tasks/memories stay).

## Every command, by job

Type `/help` anytime for this list inside the app.

### Seeing your desk
| Command | What it does |
|---|---|
| `/desk` | Photo + spoken description of what's on the desk (also: say *"what's on my desk"*) |
| `/look <question>` | Photo + answer a question: `/look where is my calculator?`, `/look is my desk messy?` |
| `/read` | Photo + read a page/label/whiteboard you hold up to the camera (AI vision — good with handwriting) |
| `/ocr` | Same but free/offline (needs tesseract installed; best for clean printed text) |
| `/snapshot` | Just take and save a photo, no analysis, no API cost |
| `/changes` | What appeared/disappeared since the previous `/desk` (free — no API call) |
| `/scenes` | History of recent desk snapshots |

### Notes, tasks, reminders
| Command | Example |
|---|---|
| `/note <text>` | `/note lab partner's email is sam@uni.edu` |
| `/notes` | List notes (delete by recreating — or ask JARVIS) |
| `/task <text> [due <when>]` | `/task finish stats assignment due friday` |
| `/tasks` · `/done <n>` · `/deltask <n>` | List / complete / delete by number |
| `/remind <delay> <text>` | `/remind 25m stretch` · `/remind 2h submit the form` |
| `/reminders` | List pending reminders (they're spoken when they fire) |

### Long-term memory — always your call
| Command | Example |
|---|---|
| `/remember <fact>` | `/remember citation style: APA 7` — JARVIS uses it from then on |
| `/memories` | Everything it has stored about you (this is the complete list — there is no hidden memory) |
| `/forget <key>` | `/forget citation style` — gone immediately |

### University work
| Command | Example |
|---|---|
| `/plan <brief + deadline>` | `/plan 2000-word ethics essay due 20 Oct` → milestone plan working back from the deadline |
| `/explain <concept>` | `/explain eigenvalues` → intuition, proper explanation, common exam trap |
| `/flashcards <topic or pasted notes>` | `/flashcards paste your lecture notes here…` |
| `/timetable <your week>` | `/timetable 4 subjects, work Thursdays, exam in 3 weeks` |
| `/cite <source, style>` | `/cite Smith 2021 Deep Learning MIT Press, APA 7` |
| `/doc <file path>` | `/doc ~/Downloads/lecture4.pdf` → summary + key points + deadlines found |
| `/docq <question>` | Follow-up questions about the last `/doc`: `/docq what's examinable?` |

> **The line it won't cross:** JARVIS helps you *understand and organise* — it will not write
> submittable work, answer quizzes/exams, or help pass AI writing off as yours. Ask anyway
> and it declines in one sentence and offers the legitimate version (outline, draft feedback,
> explanation).

### Coding and projects
| Command | Example |
|---|---|
| `/project <folder>` | `/project ~/uni/comp2000-assignment` → loads your code |
| `/projq <question>` | `/projq why does main.py crash on empty input?` |
| `/code <question + pasted code>` | Explains the bug and *why*, then the minimal fix |
| `/run <python>` | `/run print(sum(range(100)))` — sandboxed, 10s limit |

### Looking things up — just ask

JARVIS has web search built in (Settings → AI Brain → Web search): *"who won the game this
morning?"*, *"current price of a Pi 5?"*, *"what changed in Python 3.13?"* — it searches,
answers, and cites. About a cent per search on the API backend.

### Using your computer and apps — just ask

No special command needed. When a request requires real action, JARVIS does it itself,
step by step:

> *"tidy my Downloads into subfolders by file type"* · *"check my email for anything from
> my tutor this week"* · *"start a Word doc with an outline for my ethics essay"*

It reads folders and files, runs commands, and uses connected apps until the task is done.
Before anything risky (writing a file, running a command, sending an email) it shows you
exactly what it wants to do and waits for your y/N in the terminal; every reply that took
actions ends with an "Actions taken" list (shown on screen, not read aloud). Plain
questions never touch tools.

| Command | Purpose |
|---|---|
| `/agent <task>` | Optional: *force* task mode explicitly |
| `/apps` | List connected apps (Gmail, calendar, …) and their status |

### Heavy work on demand — the Opus tier

For most things JARVIS quietly uses the cheap model, stepping up to the smart one only
when the task earns it. When you need serious output — a proper report, a deep analysis —
just say so and it brings out the big model (Opus), with a much longer reply budget:

> *"write me an in-depth report on battery chemistries for my project"* · *"do a deep
> dive into this dataset"* · *"use opus: compare these two architectures"*

Trigger words: **"in-depth"**, **"deep dive"**, **"comprehensive"**, **"thorough
analysis"**, or the explicit **"use opus"**. It costs more per request (roughly
$0.25–$1 per report on the API — see [`COST_CONTROL.md`](COST_CONTROL.md)), and it
*never* runs unless you summon it. Which model answers the call is configurable in
**Settings → AI Brain → Deep-work model**.

Which folders it may touch — and the off switch — live in **Settings → Computer & Apps**.
Connecting Gmail/calendar takes one config file and a one-time login:
[`COMPUTER_AND_APPS.md`](COMPUTER_AND_APPS.md).

### Local-first mode — free, private everyday chat

JARVIS can run everyday chat on a **free model on your own computer** and only
reach for the paid cloud when it actually helps (hard questions, desk vision,
documents, and agent tasks). It's the cheapest *and* most private setup.

One-time setup:
1. Install [Ollama](https://ollama.com) (it starts on its own after install).
2. In a terminal: `ollama pull qwen3:8b` (use `qwen3:4b` on an older machine).
3. **Settings → AI Brain → Brain source → `local_first`**, then Save & Apply.

Keep your Claude API key in Settings — local-first uses it only when a request
is worth the cloud. Want *everything* offline? Pick `ollama` instead (chat only;
vision and agent tasks need the cloud). See [`COST_CONTROL.md`](COST_CONTROL.md).

### A more natural voice

The default voice (`pyttsx3`) is free and instant but robotic. Two free,
**entirely offline** upgrades — pick whichever is easier for you.

**Kokoro (recommended — one `pip install`, no files to download by hand):**

1. `pip install kokoro` (pulls in a neural TTS model; it's a large download,
   done once).
2. **Settings → Speaker & Voice output → Voice engine → `auto`** (use Kokoro
   whenever it's installed) or **`kokoro`** (always use it).
3. Pick a **Kokoro voice** from the dropdown (`af_heart` is a good default;
   `af_*` American female, `am_*` American male, `bf_*`/`bm_*` British).
   Save & Apply. The first spoken reply downloads the voice model, then it's
   fully offline. The speaking-speed slider maps onto Kokoro's pace.

**Piper (a single binary + a voice file you download):**

1. Install piper — see [github.com/rhasspy/piper](https://github.com/rhasspy/piper)
   (a single binary; put it on your PATH).
2. Download a voice, e.g. `en_US-lessac-medium` — you need **both** the `.onnx`
   and its `.onnx.json`, in the same folder.
3. **Settings → Speaker & Voice output → System voice (fallback) → `piper`**,
   then paste the full path to the `.onnx` file into **Piper voice model**.
   Save & Apply.

Either way, if the upgrade isn't installed or set up, JARVIS quietly falls back
to the OS voice — turning it on can never leave you with a mute assistant.
(Setting **System voice** to `none` disables *all* speech, Kokoro included.)
Curious how fast the voice pipeline is? Type `/voicestats` for speech-to-text
and synthesis timings.

### Ask your own notes (`/ask`) — private, cited search

JARVIS can answer from **your own material** — saved notes, long-term memories,
and any Markdown in your vault — and cite where each answer came from, instead of
guessing. It's fully local and free (search runs on Ollama).

1. One-time: install [Ollama](https://ollama.com), then `ollama pull nomic-embed-text`.
2. Build the index: `/index` (re-run it after adding notes or vault files).
3. Ask: `/ask what did I decide about the thesis topic?` — or just say
   *"search my notes about thermodynamics"*.

Answers end with a **Sources** list ([1], [2] …). If the answer isn't in your
saved material, JARVIS says so rather than making something up. Add material with
`/note …`, `/remember …`, `/export` (mirrors memory to your vault), or by writing
Markdown straight into the vault folder — then `/index` again.

### Proactive & housekeeping commands

| Command | Purpose |
|---|---|
| `good morning` / `/briefing` | Spoken daily briefing: date, open tasks, due items, reminders, latest note |
| `/ask …` | Answer from YOUR notes/memories/vault, with citations |
| `/index` | (Re)build the searchable index of your notes & vault |
| `/usage` | What JARVIS has cost you — calls, tokens, estimated $ (today / 7 days / 30 days) |
| `/voicestats` | Voice speed — speech-to-text and text-to-speech timing (recent) |
| `/brief` · `/detailed` | Switch between short spoken replies and full detailed ones |
| `/export` | Write your notes, memories and tasks to a Markdown/Obsidian vault |

`/export` writes to the folder in **Settings → Advanced → Markdown/Obsidian vault**
(default `data/vault`). Point it inside an Obsidian vault and everything JARVIS
remembers becomes browsable and searchable there — in plain Markdown you own.

### Control
`/listen` mic on · `/sleep` mic off · `/stop` stop speaking · `/status` component health ·
`/clear` reset conversation · `/help` all commands

## The Settings page

Everything configurable lives here — organised into cards, each option explained in plain
English. The important ones:

- **AI Brain** — where the intelligence comes from. *Brain source*: `anthropic` (API key,
  fastest), `claude_code` (your Claude Pro subscription — no API cost, slower), or
  `hybrid` (chat on the API, big tasks on your subscription — recommended if you have
  Pro; setup in [`COST_CONTROL.md`](COST_CONTROL.md#already-paying-for-claude-pro-use-it-as-the-brain)).
  Plus your API key (shown masked once saved) and which models to use — including the
  *Deep-work model* (Opus) that only runs when you ask for an in-depth job.
- **Microphone & Speech** — pick your mic *by name*. If JARVIS hears you badly, check you
  selected the desk speakerphone, not the laptop's built-in mic.
- **Hands-free wake word** — on/off toggle and the sensitivity slider.
- **Speaker & Voice output** — pick the output device and set speaking speed (160–190 feels
  most natural). **Voice engine** chooses the neural Kokoro voice (`auto`/`kokoro`) or the
  plain system voice; see *A more natural voice* above for the one-time `pip install kokoro`.
- **Camera & Vision** — *Scan for cameras* finds what's plugged in; *Test camera* shows you
  exactly what JARVIS sees (use this to aim the camera). Also: how many days snapshots are
  kept (0 = delete right after analysis).
- **Computer & Apps** — the agent-mode controls: on/off, which folders it may touch,
  whether it must ask before each risky action, and the per-task step limit.
- **Device tests** (bottom) — after any change, hit Save & Apply, then run 🔊 🎤 📷 🧠.
  Green = working; red tells you precisely what to fix.

**Save & Apply** makes changes live in about a second. Only exception: changing the
dashboard port needs an app restart.

## Daily patterns that work well

- **Study session:** `/doc` this week's lecture PDF → `/docq` what you didn't get →
  `/flashcards` from the summary → `/remind 50m break`.
- **Assignment kickoff:** `/plan <the brief + due date>` → turn each milestone into a
  `/task … due …` → ask it to critique your outline as you draft.
- **Debugging:** `/project` your folder once, then `/projq` freely — it keeps the code
  in mind for the session.
- **Desk sanity:** *"jarvis… where did I put my calculator?"* — it looks.

## Your data, in one place

Everything JARVIS knows lives in the `data/` folder inside JARVIS:
`data/jarvis.db` (notes, tasks, memories, chat history — one SQLite file),
`data/snapshots/` (recent photos, auto-pruned), `data/logs/` (technical logs).
Copy the folder to back it up; delete it for a factory reset. Nothing is synced anywhere.
