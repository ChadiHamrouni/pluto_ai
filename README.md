# Jarvis — Local-First Personal AI Assistant

A production-grade personal AI assistant that runs **entirely on your machine** — no cloud, no API keys, no data leaving your device.

Built with **OpenAI Agents SDK**, **Ollama**, **FastAPI**, and **Tauri + React**. Designed for privacy, low latency, and offline-first use.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Tauri Desktop App                        │
│              React frontend · SSE streaming UI               │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTP / SSE
┌────────────────────────▼────────────────────────────────────┐
│                   FastAPI Backend                            │
│                                                              │
│  POST /chat          POST /chat/stream    GET /health        │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │                 text_handler                         │    │
│  │  parse_command() → hard-route OR LLM routing        │    │
│  │  Memory search (FTS5) → context injection           │    │
│  │  Upcoming events (24h) → proactive context          │    │
│  │  Context compaction when window fills               │    │
│  └───────────────────┬─────────────────────────────────┘    │
│                      │                                       │
│  ┌───────────────────▼─────────────────────────────────┐    │
│  │              Orchestrator Agent                      │    │
│  │  (OpenAI Agents SDK · Ollama local model)            │    │
│  │                                                      │    │
│  │  handoffs ──► NotesAgent                            │    │
│  │           ──► SlidesAgent                           │    │
│  │           ──► ResearchAgent                         │    │
│  │           ──► CalendarAgent                         │    │
│  │                                                      │    │
│  │  tools ──► store/forget/prune_memory                │    │
│  │        ──► web_search                               │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  LLM Output Guardrails (SDK OutputGuardrail)                 │
│    · RepetitionGuard — detects looping small-model output    │
│    · RelevanceGuard  — flags incoherent / off-topic replies  │
│                                                              │
│  SQLite (memory · notes · sessions · events)                 │
└─────────────────────────────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                  Ollama (local LLM)                          │
│           http://localhost:11434/v1  (OpenAI-compat)         │
└─────────────────────────────────────────────────────────────┘
```

---

## Features

| Feature | Details |
|---|---|
| **Multi-agent orchestration** | Orchestrator routes to specialist agents via SDK handoffs |
| **Streaming responses** | SSE token-by-token delivery with tool call + handoff visibility |
| **Hybrid routing** | Deterministic slash commands + LLM routing for ambiguous requests |
| **Persistent memory** | FTS5-indexed SQLite facts injected into every system prompt |
| **Context compaction** | Parallel fact extraction + summarisation when history overflows |
| **LLM guardrails** | SDK `OutputGuardrail` — repetition detection and coherence check |
| **Research agent** | Multi-step web search → read full pages → synthesise with citations |
| **Calendar agent** | Natural language scheduling, proactive 24h event context injection |
| **Notes agent** | Structured markdown notes with YAML front matter, SQLite index |
| **Slides agent** | Marp PDF presentations from natural language outlines |
| **Voice mode** | VAD + local TTS for hands-free interaction |
| **File attachments** | Images (multimodal), PDFs (OCR), and plain text |
| **Secrets via env vars** | Auth credentials override via `AUTH_SECRET_KEY`, `AUTH_PASSWORD_HASH`, `AUTH_USERNAME` |
| **100% local** | Zero cloud calls — Ollama + SQLite + local filesystem |

---

## Agent Map

```
/note, /notes  ──────────────────────────────► NotesAgent
/slides, /slide ─────────────────────────────► SlidesAgent
/research ───────────────────────────────────► ResearchAgent
/calendar, /schedule, /event ────────────────► CalendarAgent

(no slash command)
    └─► Orchestrator ──► LLM decides:
            ├── general Q&A       → answer directly + web_search
            ├── note task         → handoff → NotesAgent
            ├── slide task        → handoff → SlidesAgent
            ├── research task     → handoff → ResearchAgent
            └── calendar task     → handoff → CalendarAgent
```

---

## Design Decisions

### 1. Hybrid routing — fast AND flexible
Slash commands deterministically bypass the LLM for known intents (`/note`, `/slides`, etc.). Unknown or ambiguous requests go through LLM routing via Orchestrator handoffs. This gives sub-100ms routing for common tasks while preserving flexibility.

### 2. Context compaction with parallel fact extraction
When the conversation history approaches the model's context window, the compactor runs two parallel LLM calls: one to summarise the old messages, one to extract durable facts into permanent memory. The conversation continues seamlessly without losing long-term information.

### 3. Local-first architecture
Every component — LLM inference (Ollama), vector storage (SQLite), file storage — runs on-device. Privacy is guaranteed by design, not policy. Latency is bounded by local hardware, not network conditions.

### 4. LLM-based output guardrails
Rather than heuristic regex checks, two `OutputGuardrail` agents (SDK-native) evaluate every response before it reaches the user. `RepetitionGuard` detects looping output common in sub-7B models. `RelevanceGuard` flags incoherent responses. Both fail open — if the evaluator call fails, the response passes through.

### 5. Streaming SSE with agent visibility
The `/chat/stream` endpoint emits structured SSE events: `token` (text delta), `tool_call` (tool name + args), `agent_handoff` (which agent took over), and `done` (metadata). The frontend renders all of this in real time.

### 6. Memory as flat injection (not RAG)
Personal facts are stored in SQLite and injected verbatim into every orchestrator system prompt. No embedding overhead for memory retrieval — the full fact store fits in context for a personal assistant. RAG is reserved for the knowledge base (`data/files/`).

### 7. Proactive calendar context
The orchestrator system prompt is augmented with any events starting in the next 24 hours before every turn. No tool call needed — the model knows about upcoming commitments automatically.

---

## Quickstart

### Prerequisites

- [Ollama](https://ollama.com) installed and running
- Python 3.11+
- Node.js 18+ (for Marp CLI, optional)
- [Rust + Tauri CLI](https://tauri.app) (for desktop app)

### Backend

```bash
cd backend

# Copy and configure
cp config.example.json config.json
# Edit config.json: set your auth credentials or use env vars below

# Install dependencies
pip install -r requirements.txt

# Pull the LLM model
ollama pull qwen2.5:3b

# (Optional) Install Marp for slide generation
npm install -g @marp-team/marp-cli

# Start
python main.py
```

**Secrets via environment variables** (recommended over editing config.json):

```bash
export AUTH_SECRET_KEY="your-secret-key"
export AUTH_USERNAME="your-username"
export AUTH_PASSWORD_HASH="bcrypt-hash"
```

### Desktop App (Tauri)

```bash
cd frontend
npm install
npm run tauri dev      # dev mode
npm run tauri build    # production build → installers in src-tauri/target/release/bundle/
```

### Docker (backend only)

```bash
cd backend
docker compose build    # first run: builds image
docker compose up -d
docker compose exec ollama ollama pull qwen2.5:3b
curl http://localhost:8000/health
```

---

## API Reference

### Auth

```
POST /auth/login    body: username + password (form)
POST /auth/refresh  body: refresh_token (form)
POST /auth/verify   body: token (form)
```

### Chat

All chat endpoints require `Authorization: Bearer <access_token>`.

```
POST /chat
  Form: message (str), session_id (str, optional), attachments (files, optional)
  Response: { response, tools_used, agents_trace, file_url, attachments }

POST /chat/stream
  Form: message (str), session_id (str, optional)
  Response: text/event-stream
    event: token        data: {"delta": "..."}
    event: tool_call    data: {"tool": "...", "arguments": "..."}
    event: agent_handoff data: {"agent": "..."}
    event: done         data: {"response": "...", "tools_used": [...], "agents_trace": [...]}
    event: error        data: {"message": "..."}

POST /chat/session        → create session, returns session_id
GET  /chat/sessions       → list all sessions
GET  /chat/session/{id}/messages → full history for session
DELETE /chat/session/{id} → delete session
```

### Slash Commands

| Command | Agent | Example |
|---|---|---|
| `/note`, `/notes` | NotesAgent | `/note prep for astrophysics seminar` |
| `/slides`, `/slide` | SlidesAgent | `/slides dark matter detection methods` |
| `/research` | ResearchAgent | `/research latest JWST exoplanet findings` |
| `/calendar`, `/schedule`, `/event` | CalendarAgent | `/schedule paper deadline Friday 23:59` |
| `/remember`, `/memory` | Orchestrator (store) | `/remember I prefer Python over R` |
| `/forget` | Orchestrator (delete) | `/forget old email address` |

Without a slash command, the Orchestrator's LLM decides routing automatically.

---

## Repository Structure

```
personal_ai/
├── backend/
│   ├── main.py                    # FastAPI app — lifespan, CORS, error handlers
│   ├── config.json                # All hyperparameters
│   ├── config.example.json        # Safe-to-commit template (no secrets)
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── docker-compose.yml
│   │
│   ├── my_agents/                 # Agent definitions (OpenAI Agents SDK)
│   │   ├── orchestrator.py        # Central router with all handoffs
│   │   ├── notes_agent.py
│   │   ├── slides_agent.py
│   │   ├── research_agent.py
│   │   └── calendar_agent.py
│   │
│   ├── tools/                     # @function_tool wrappers only
│   │   ├── memory_tools.py
│   │   ├── notes_tools.py
│   │   ├── slides_tools.py
│   │   ├── calendar_tools.py
│   │   ├── research_tools.py
│   │   └── web_search.py
│   │
│   ├── helpers/
│   │   ├── core/                  # config_loader, db, logger, exceptions
│   │   ├── agents/                # runner, guardrails, compactor, command_parser
│   │   └── tools/                 # memory, notes, slides, calendar helpers
│   │
│   ├── handlers/                  # text_handler (routing + memory injection)
│   ├── instructions/              # Agent system prompts as markdown
│   ├── routes/                    # FastAPI routers (auth, chat, files, voice)
│   ├── models/                    # Pydantic schemas
│   └── tests/                     # pytest unit + integration tests
│
└── frontend/
    └── src/
        ├── hooks/useChat.js       # Streaming + non-streaming chat logic
        ├── hooks/useSessions.js   # Session state management
        └── api.js                 # streamMessage(), sendMessage()
```

---

## Running Tests

```bash
cd backend
pip install pytest pytest-asyncio
pytest
```

Tests are fully offline — no Ollama, no network. All LLM calls are mocked at the SDK boundary.
