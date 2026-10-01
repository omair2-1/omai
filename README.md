# OMAI — private personal AI agent (free to run)

A personal AI agent that runs **on your own machine**, remembers things long-term, researches the web
with sources, and asks your permission before any consequential action. Every tool call and permission
decision goes into an audit log. Costs nothing: it uses a free LLM tier (or a local model) and
key-less DuckDuckGo search.

## Quick start (free)

```bash
python3 -m venv .venv && source .venv/bin/activate      # Windows: py -m venv .venv ; .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env         # Windows: copy .env.example .env   -> then put your free key in .env
omai
pytest                       # 59 tests, no key needed
```

### Choose your free brain

| Provider | Cost | Setup | Good for |
|---|---|---|---|
| `gemini` (default) | Free tier, rate-limited | Key at aistudio.google.com/apikey → `GEMINI_API_KEY` | Easiest start, best quality of the free options |
| `groq` | Free tier, rate-limited | Key at console.groq.com → `OMAI_PROVIDER=groq`, `GROQ_API_KEY` | Very fast |
| `ollama` | Free, unlimited | Install ollama.com, `ollama pull llama3.1:8b`, `OMAI_PROVIDER=ollama` | **Privacy** — nothing leaves your machine; needs ~8 GB+ RAM |
| `openrouter` | Free models available | `OPENROUTER_API_KEY` + `OMAI_MODEL=<id ending in :free>` | Fallback |
| `openai` | any OpenAI-compatible server | `OMAI_BASE_URL`, `OMAI_API_KEY`, `OMAI_MODEL` | Custom |
| `anthropic` | **Paid** | `ANTHROPIC_API_KEY` (`pip install -e ".[anthropic]"`) | Highest quality, built-in web search |

Free-tier limits and model names change. If a model stops working, run `omai --models` and set `OMAI_MODEL`.

**Privacy note:** free hosted tiers (Gemini, Groq, OpenRouter) may log or use your prompts, and
Google's free-tier terms allow using content to improve its products. Don't put anything sensitive in
them. Once OMAI reads your email, use `ollama` (local) or a paid tier.

## In the chat

`/help`, `/memory [query]`, `/forget <id>`, `/audit [n]`, `/reset`, `/quit`.

Try: *"Remember that my accountant is Rahul."* → `/reset` → *"Who is my accountant?"*
and *"What's the latest news on <topic>? Give sources."*

## Gmail setup (optional, read-only)

Lets OMAI list and summarize your inbox. Costs nothing; only your own Google account is involved.

1. Go to console.cloud.google.com and sign in.
2. Top dropdown → **New Project** → name it anything → **Create**, then make sure it's selected.
3. Search bar → **"Gmail API"** → open it → **Enable**.
4. Left menu → **APIs & Services → OAuth consent screen** (aka "Google Auth Platform") → **Get started**.
   App name: anything. Support email: yours. Audience: **External**. Add yourself as a **test user**.
   Agree to the data policy, **Create**.
5. **APIs & Services → Credentials → + Create Credentials → OAuth client ID**.
   Application type: **Desktop app**. Name: anything. **Create**.
6. Copy the **Client ID** and **Client Secret** shown.
7. In `.env`, uncomment and fill in:
   ```
   GMAIL_CLIENT_ID=your-client-id.apps.googleusercontent.com
   GMAIL_CLIENT_SECRET=your-client-secret
   ```
8. Run `omai`. The first time you ask it about email, a browser tab opens asking you to sign in and
   approve **read-only** access. Approve it. A token is then cached in `~/.omai/gmail_token.json`
   (owner-only permissions) so you won't be asked again.

Try: *"Do I have any unread emails? List the last 10."* or *"Summarize the email from <sender>."*

**Scope:** `gmail.readonly` only — OMAI cannot send, delete, or modify anything in your mailbox yet.
Email content is treated as untrusted data (see Security model) so a malicious email can't hijack the agent.

## Phone access via Telegram (optional, free)

Chat with OMAI from your phone. OMAI keeps running and doing the work on your computer; Telegram is
just the window into it. Only your own Telegram account gets replies - everyone else is ignored.

1. In Telegram, message **@BotFather** → send `/newbot` → give it a name, then a username ending in `bot`.
   Copy the **token** it replies with (looks like `123456789:ABC...`).
2. Message **@userinfobot** → it replies with your numeric **id**.
3. In `.env`:
   ```
   OMAI_TELEGRAM_TOKEN=123456789:ABC...
   OMAI_TELEGRAM_USER_ID=987654321
   ```
4. Run:
   ```
   omai --telegram
   ```
   Your computer needs to stay on and connected for the bot to respond. `/reset` clears the
   conversation; anything else is sent straight to OMAI, same as the local CLI.
5. Open the bot in Telegram on your phone and start chatting.

Approvals (for `Risk.CONFIRM` tools like `forget`) come through as a Telegram message asking
"Reply yes or no" - reply from your phone to approve or deny, same as pressing y/N in the terminal.

## GitHub (optional, free)

1. Go to github.com/settings/tokens -> **Generate new token (classic)**.
2. Tick the **repo** scope (or just **public_repo** if you only need public repos).
3. Generate, then copy the token (starts `ghp_`).
4. In `.env`: `GITHUB_TOKEN=ghp_...`

Try: *"List my repos."* / *"List open issues in <owner>/<repo>."* / *"Open an issue in <owner>/<repo>
titled 'X' describing Y."* (that last one needs your approval, like `forget` does.)

## YouTube (optional, free, read-only)

1. In the same Google Cloud project you used for Gmail (or a new one): **APIs & services -> Library**
   -> search **YouTube Data API v3** -> **Enable**.
2. **Credentials -> Create credentials -> API key**. Copy it.
3. In `.env`: `YOUTUBE_API_KEY=...`

Try: *"Find YouTube videos about <topic>."* / *"Summarize this video: <link>."*

## Design

| Piece | File | Notes |
|---|---|---|
| Agent loop | `omai/agent.py` | Tool rounds, error rollback, history trimming that never splits a tool call from its result |
| LLM backends | `omai/llm.py` | OpenAI-compatible (Gemini/Groq/Ollama/...) and Anthropic behind one interface; tolerant of weak models (bad JSON args, `finish_reason` quirks, Gemini thought signatures) |
| Memory | `omai/memory.py` | SQLite + FTS5 (BM25). Relevant notes auto-injected each turn; `remember`/`recall`/`forget` tools |
| Web research | `omai/web_tools.py` | DuckDuckGo search + page fetch, no key. Fetch refuses private/loopback/link-local addresses, re-checks every redirect, caps size |
| Permission gate | `omai/permissions.py` | `Risk.CONFIRM` tools need a human "y"; enforced in code; fails closed |
| Audit log | `omai/audit.py` | Every tool call + decision, values truncated |
| Tool registry | `omai/tools.py` | Each future integration = one `Tool` |
| Gmail (read-only) | `omai/gmail_tools.py`, `omai/gmail_auth.py` | `gmail_list` / `gmail_read`; OAuth token cached at `~/.omai/gmail_token.json` (0600); auto-refreshed |
| Telegram bridge | `omai/telegram_bot.py` | Long-polling, no server needed; owner-only allowlist; permission confirms round-trip through chat |
| GitHub | `omai/github_tools.py` | Personal access token; list repos/issues/commits (read), create issue (`CONFIRM`) |
| YouTube | `omai/youtube_tools.py` | API key; search videos, get video info (read-only) |

Data lives in `~/.omai/` (dir `0700`, files `0600`): `memory.db`, `audit.db`.

## Security model

- Only you can reach it: it is a local CLI. If you later add Telegram/WhatsApp/web, allowlist your own
  numeric user ID and drop everyone else before the message reaches the agent.
- **Prompt injection is the main risk** once the agent reads web pages and emails. Web content is
  marked untrusted, the system prompt says never to obey it, and — the real defence — send/post/delete
  tools are `Risk.CONFIRM`, so a hijacked model still cannot act without your "y". Keep every future
  write-capable tool `CONFIRM`. Smaller/free models are easier to trick than large ones, so this
  code-level gate matters even more.
- `remember` is auto-allowed and audit-logged; review with `/memory`, delete with `/forget`.
- Secrets come from the environment / `.env` only; `.env` is git-ignored.

## Limitations (honest list)

- DuckDuckGo search is unofficial scraping via the `ddgs` package: it can rate-limit or break.
- Free/small models use tools less reliably than large paid ones; expect occasional retries.
- Memory is keyword search (not semantic) for now.

## Roadmap

- [x] Phase 1 — chat, memory, CLI, permission gate, audit log, web research (free)
- [x] Phase 2 — Gmail read-only (`gmail.readonly`), list/summarise inbox
- [x] Phone access — Telegram bridge (`omai --telegram`)
- [ ] Phase 3 — Gmail send/draft (`CONFIRM`)
- [x] Phase 8 — GitHub (read + create issue, free, personal access token)
- [x] Phase 7 (read half) — YouTube search/video info (free, API key)
- [ ] Phases 5–6, 9–12 — WhatsApp/Instagram (need a Meta Business setup), X (no free tier anymore), Reddit/Spotify (free, need OAuth like Gmail), voice, browser/files, remote deployment

## Adding a tool

```python
Tool(
    name="gmail_send",
    description="Send an email from the owner's account.",
    input_schema={...},
    handler=send_fn,
    risk=Risk.CONFIRM,
    describe=lambda a: f"SEND EMAIL to {a['to']}\nSubject: {a['subject']}\n\n{a['body']}",
)
```
Register it in `build_agent()` in `cli.py`.
