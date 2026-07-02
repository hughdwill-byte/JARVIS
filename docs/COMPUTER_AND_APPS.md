# Agent mode — using your computer and your apps

`/agent <task>` puts JARVIS in Cowork-style agent mode: it plans, uses tools, checks the
results, and keeps going until the task is done. Two kinds of tools are available to it:

1. **Your computer** (built in): list folders, read files, write files, run shell commands,
   open apps/URLs.
2. **Your apps** (via MCP): Gmail, Google Calendar, Notion, and hundreds more — the same
   connector ecosystem Claude uses.

```
/agent tidy my Downloads folder into subfolders by file type
/agent check my email for anything from my tutor this week and summarise it
/agent find every PDF mentioning thermodynamics in my uni folder and list them
/agent draft a reply to the latest email from the lab group (it will ask before sending)
```

## About API keys (read this once)

Agent mode runs on the **Anthropic API key** you already put in Settings — the same one
powering chat and vision. Note that a **Claude Pro subscription is a different product**
and does not include an API key; the key comes from
[console.anthropic.com](https://console.anthropic.com) (pay-as-you-go). Agent tasks use
the smart model with multiple calls per task, so a typical task costs a few cents —
see [COST_CONTROL.md](COST_CONTROL.md).

## The safety model

- **Folder allowlist.** The agent can only read/write inside the folders in
  *Settings → Computer & Apps → Folders it may touch* (default: your home folder). Anything
  outside is refused automatically.
- **Approval prompts.** Reading is free; *changing things* asks you first. Writing a file,
  running a command, opening an app, or any app action that sends/creates/deletes
  (e.g. sending an email) shows you exactly what it wants to do and waits for your `y/N`
  in the terminal. Decline and it adapts or wraps up — it never retries a declined action.
- **Auto-approve is opt-in.** The web/app window can't show a y/N prompt, so from there
  risky actions are declined unless you enable *Act without asking* in Settings. Run agent
  tasks from the terminal (`python run_assistant.py`) to keep interactive approval.
- **Untrusted content rules.** Emails and web pages the agent reads may contain text like
  "forward this to..." or "run this command" — the agent is instructed to treat all
  fetched content as data, never as instructions, and to never exfiltrate your files or
  personal data. Destructive commands (`rm -rf`, formatting disks) are refused even if
  approved.
- **Full action log.** Every reply ends with "Actions taken:" listing each thing it did
  (and anything you declined).
- **Kill switch.** *Settings → Computer & Apps → Agent mode: off* disables all of it.

## Connecting apps (Gmail, Calendar, Notion, …)

Apps connect through **MCP servers** — the open standard behind Claude's connectors. Setup:

1. **Install Node.js** ([nodejs.org](https://nodejs.org), LTS version) — most MCP servers
   run via `npx`.
2. **Copy the template:**
   ```bash
   cp mcp_servers.example.json mcp_servers.json
   ```
   Keep only the apps you want. The format is identical to Claude Desktop's config, so any
   "add this to your Claude config" example from the internet pastes straight in.
3. **Do each app's one-time auth.** E.g. the Gmail server
   ([`@gongrzhe/server-gmail-autoauth-mcp`](https://github.com/GongRzhe/Gmail-MCP-Server))
   needs a Google Cloud OAuth credentials file and a one-time
   `npx @gongrzhe/server-gmail-autoauth-mcp auth` which opens a browser to grant access —
   its README walks through it. Calendar and others work the same way.
4. **Restart JARVIS**, then type **`/apps`** — you should see each server listed with its
   tool count. Then just ask: `/agent any unread emails from my tutor?`

Where to find more servers: the same MCP directories the Claude community uses —
search "<app name> MCP server". Anything that runs over stdio works.

**Privacy note:** app connections run locally on your machine; your credentials stay in
the server's own auth files. But remember email *content* fetched during a task is sent to
the Claude API as part of the conversation — that's how the model reads it. Don't point
agent mode at data you wouldn't put in chat, and see
[ARCHITECTURE.md](ARCHITECTURE.md#privacy-trade-offs).

## Troubleshooting

- **`/apps` says "No apps configured"** — you haven't created `mcp_servers.json`, or it's
  in the wrong place (repo root, next to `run_app.py`).
- **A server shows `[!!]` with an npx error** — Node.js isn't installed or isn't on PATH;
  install from nodejs.org and restart your terminal.
- **Gmail shows connected but calls fail** — redo the one-time auth step from the server's
  README (tokens expire if unused for a long time).
- **"outside the folders I'm allowed to touch"** — widen *Folders it may touch* in
  Settings → Computer & Apps, Save & Apply.
- **Agent stops mid-task with "step limit"** — raise *Max steps per task* in Settings.
- **Every risky action is declined in the app window** — that's the safe default; either
  run the task in the terminal for y/N prompts, or enable *Act without asking*.
