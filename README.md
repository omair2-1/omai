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

## Automatic fallback between free providers (optional)

If your primary provider (e.g. Gemini) hits its daily rate limit, OMAI can automatically try
another configured free provider instead of just erroring out.

In `.env`:
```
OMAI_FALLBACK_PROVIDERS=groq,ollama
GROQ_API_KEY=...
```
Only `gemini`, `groq`, `openrouter`, and `ollama` can be chained this way (they speak the same
API format, so switching mid-conversation is safe). It remembers whichever provider last worked
and tries that one first, so a dead provider isn't re-checked on every single message. The
startup line shows the chain, e.g. `fallback: ['gemini', 'groq']`.

Grok and OpenAI are deliberately not offered as presets: as of writing, neither has an ongoing
free API tier anymore (both now give only a one-time trial credit that runs out), which would
break "free to run" once it's spent.

## WhatsApp (optional, free)

Meta gives every WhatsApp Business app a free test number you can message from, plus up to
5 phone numbers you can allowlist to receive messages (e.g. your own contacts) - no business
verification needed for this.

1. Go to developers.facebook.com -> **My Apps -> Create App -> Business** type.
2. In the app, **Add Product -> WhatsApp**.
3. On the **API Setup** page, note the **Phone number ID** and the **temporary access token** shown.
4. Under the "To" field, click **Manage phone number list -> Add phone number**. Enter the number
   you want to message (e.g. your mom's, with country code) - she'll get a verification code to confirm.
5. In `.env`:
   ```
   WHATSAPP_TOKEN=the-temporary-token
   WHATSAPP_PHONE_NUMBER_ID=the-phone-number-id
   ```

Try: *"Send a WhatsApp message to +91... saying I'll be home by 8."* - this needs your approval,
like every other sending action.

**The catch:** that temporary token expires after 24 hours, so you'll need to copy a fresh one
from the same API Setup page periodically. A permanent token is possible via a Meta "System User"
but involves more setup - ask if you want to go further down that road. Messages only reach
numbers you've explicitly allowlisted (max 5) - sending to anyone else will fail with a clear error.

## Spotify (optional, free - search only)

Spotify's playback-control API (play/pause/skip) requires a Premium subscription; without it,
OMAI can search and hand you a link instead of starting playback itself.

1. Go to developer.spotify.com/dashboard -> **Create app**.
2. Name/description: anything. Redirect URI: `http://localhost` (required field, unused here).
3. Tick that you agree to the terms, **Save**.
4. Open the app -> **Settings** -> copy the **Client ID** and **Client Secret**.
5. In `.env`:
   ```
   SPOTIFY_CLIENT_ID=...
   SPOTIFY_CLIENT_SECRET=...
   ```

Try: *"Find the song Blinding Lights."* - it replies with a link you tap to actually play it.

## Zomato / recurring orders (no integration needed - just use memory)

Zomato has no public ordering API for individual developers, and there is no free, legitimate way
for OMAI to place an order or tap through the app for you - any approach that did that would mean
automating button-presses on your phone, which is fragile and against most apps' terms of service.

What *does* work, with nothing new to set up: tell OMAI your usual order and it remembers it.
*"Remember that my usual Zomato order is a chicken biryani from <restaurant>."* Later, *"What's my
usual order?"* gets it back instantly so you can place it yourself in a couple of taps.

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
| Provider fallback | `omai/llm.py` (`FallbackOpenAIBackend`) | Auto-switches to the next free provider on a rate-limit/overload error |
| WhatsApp | `omai/whatsapp_tools.py` | Meta test number; send text to allowlisted contacts (`CONFIRM`) |
| Spotify | `omai/spotify_tools.py` | Client Credentials flow (no login); search only, since playback needs Premium |

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
- [x] Phase 5 (partial) — WhatsApp send via Meta's free test number (`CONFIRM`)
- [x] Phase 7 (search half) — Spotify search (free, no Premium needed; playback control needs Premium)
- [ ] Phase 5/6 — Instagram (needs a Meta Business setup), X (no free tier anymore), Reddit/Spotify (free, need OAuth like Gmail), voice, browser/files, remote deployment

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
