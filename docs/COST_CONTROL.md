# Cost control

## Upfront hardware

| Tier | New spend | What you get |
|---|---|---|
| A — Minimum | **$25–35** | Webcam (with its mic) + existing computer/speakers |
| B — Recommended | **$50–70** | 1080p webcam + USB speakerphone + mount + cable |
| C — Advanced | **$150–250** | Dedicated mini PC/Pi, better cam, pedal, LED, small screen |

## Monthly API cost (the only recurring cost)

One Anthropic API key. Rough per-action costs at current pricing:

| Action | Model | Approx. cost |
|---|---|---|
| Casual chat turn | Haiku | ~$0.001–0.003 |
| Hard question / code help | Sonnet | ~$0.01–0.03 |
| `/desk` or `/read` (one 1024px image) | Sonnet | ~$0.01–0.02 |
| `/doc` PDF summary (capped at ~6k tokens) | Sonnet | ~$0.03–0.06 |
| Web search (per search performed) | either | ~$0.01 + tokens |

Realistic monthly estimates:

- **Light** (few chats/day, occasional /desk): **$2–4/month**
- **Typical student use** (daily study help, several vision calls): **$5–10/month**
- **Heavy** (constant code help, many documents): **$15–25/month**

Set a hard spending limit in the Anthropic console (Settings → Limits) — do this on day one.

## How the code keeps costs down (already built in)

- **Prompt caching**: the persona/tool instructions (the biggest fixed chunk of every
  request) carry an Anthropic cache breakpoint — within a 5-minute window, repeat calls
  re-read that prefix at 10% of normal input price. Back-and-forth conversation is where
  this saves most (roughly 30–60% off input costs in an active session).
- Cheap model by default; smart model only for images, documents, and hard-task heuristics.
- Images downscaled to ≤1024px JPEG before upload; scene *diffs* computed locally from text.
- Conversation context trimmed (`MEMORY_CONTEXT_TURNS=12`), replies capped (`LLM_MAX_TOKENS=1024`).
- Document text capped at ~24k chars per call.
- Free local paths: `/ocr` instead of `/read` for clean print; `/changes` costs $0;
  tasks/notes/reminders never touch the API.

## Knobs you can turn (all in the app: Settings → Save & Apply)

- **AI Brain → Heavy-lifting model = claude-haiku-4-5** — run everything on Haiku
  (cheapest, weaker vision).
- **AI Brain → Max reply length = 512** — shorter replies.
- **Advanced → Conversation memory = 6** — less history sent per call.
- **Camera & Vision → Image detail = 768** — cheaper vision calls.

(The same settings exist as `LLM_MODEL_SMART`, `LLM_MAX_TOKENS`, `MEMORY_CONTEXT_TURNS`,
and `VISION_MAX_IMAGE_EDGE` in `.env` if you prefer editing files.)

## Already paying for Claude Pro? Use it as the brain

If you have a Claude Pro/Max subscription, JARVIS can bill usage to it instead of (or as
well as) the API — **Settings → AI Brain → Brain source**:

| Brain source | Speed | Cost | Best for |
|---|---|---|---|
| `anthropic` (API key) | ~1–2 s/reply | ~$5–10/month | Snappiest voice experience (default) |
| `claude_code` (your Pro plan) | ~4–8 s/reply | $0 extra | Cost-free, if you don't mind the pause |
| `hybrid` | fast chat, slower big tasks | a few $/month | **Recommended combo**: chat/voice on the API, documents & vision on your Pro plan |

One-time setup for `claude_code`/`hybrid`: install [Node.js](https://nodejs.org), then
`npm install -g @anthropic-ai/claude-code`, then run `claude` in a terminal and log in
with your claude.ai account. Notes: Pro has usage windows shared with your own claude.ai
chatting (heavy JARVIS use eats that allowance), and on the claude_code-only backend
in-chat computer actions run read-only unless you enable *Act without asking* (the CLI
can't show per-action y/N prompts).

## Which paid things are worth it

| Service | Verdict |
|---|---|
| Anthropic API key | **Worth it immediately** — it's the entire brain, and it's cheap at this scale. |
| Cloud TTS (ElevenLabs etc.) | **Wait.** pyttsx3 is robotic but free; try free `edge-tts` first if the voice bothers you. |
| Cloud STT (OpenAI Whisper API) | **Wait.** Local faster-whisper is free and fine; only consider if you move to a Pi. |
| Search APIs | **Wait.** Add a web-search tool later if you actually miss it. |
| New hardware beyond Tier B | **Wait** until the MVP has run for a couple of weeks. |
