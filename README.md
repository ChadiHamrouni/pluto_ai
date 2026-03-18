# Personal AI Assistant

A local-first, multi-agent AI assistant built on [OpenAI Agents SDK](https://github.com/openai/openai-agents-python) and [Ollama](https://ollama.com). No cloud, no API keys — everything runs on your machine.

---

## Repository Structure

```
personal_ai/
├── backend/    # FastAPI backend — agents, tools, memory, auth
└── frontend/   # DearPyGui desktop client
```

---

## Backend

### Features

- **Orchestrator + specialist agents** — routes tasks between NotesAgent and SlidesAgent
- **Persistent memory** — ChatGPT-style flat fact injection via SQLite
- **Knowledge base RAG** — multimodal embeddings (text, images, PDFs) via `nomic-embed-multimodal-3b`
- **Notes** — structured markdown notes saved to disk with YAML front matter
- **Slides** — PDF presentations generated from outlines via Marp CLI
- **Slash commands** — `/note`, `/slides` for deterministic hard-routing
- **JWT auth** — access (15 min) + refresh (7 day) tokens, single-user

### Structure

```
backend/
├── main.py               # FastAPI entry point — lifespan, health, CORS
├── config.json           # All hyperparameters (models, memory, RAG, storage, auth)
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
│
├── agents/               # Agent definitions (OpenAI Agents SDK)
│   ├── orchestrator.py   # Central router — memory injection, slash commands, handoffs
│   ├── notes_agent.py    # Creates, lists, and retrieves markdown notes
│   └── slides_agent.py   # Generates Marp PDF presentations
│
├── tools/                # ONLY @function_tool decorated functions
│   ├── memory_tools.py   # store_memory, forget_memory, prune_memory
│   ├── notes_tools.py    # create_note, list_notes, get_note
│   ├── slides_tools.py   # generate_slides (Marp → PDF)
│   └── rag_tools.py      # store_embedding, search_embeddings (knowledge base only)
│
├── helpers/              # Pure helper functions — no @function_tool here
│   ├── core/             # Shared infrastructure
│   │   ├── config_loader.py
│   │   ├── db.py
│   │   └── logger.py
│   ├── agents/           # Agent-specific helpers
│   │   ├── ollama_client.py     # get_model(), centralised Ollama client
│   │   ├── command_parser.py    # Slash command parser
│   │   ├── instructions_loader.py
│   │   ├── prompt_utils.py
│   │   └── tracer.py
│   ├── tools/            # Helpers for tools/
│   │   ├── embedder.py   # ColQwen2_5 singleton — load_model(), embed(), is_ready()
│   │   ├── memory.py     # Flat memory CRUD
│   │   ├── notes.py      # Note file + DB helpers
│   │   └── slides.py     # Marp invocation helpers
│   └── routes/           # Helpers for routes/
│       ├── auth.py       # JWT creation/validation, password hashing
│       └── dependencies.py
│
├── instructions/         # Agent system prompts as markdown files
│   ├── orchestrator.md
│   ├── notes_agent.md
│   └── slides_agent.md
│
├── routes/               # FastAPI routers
│   ├── auth.py           # POST /auth/login, /auth/refresh, /auth/verify
│   └── chat.py           # POST /chat (JWT protected)
│
├── models/               # Pydantic request/response models
│
└── data/                 # Runtime data (gitignored)
    ├── memory.db
    ├── notes/
    ├── slides/
    ├── embeddings/
    └── files/
```

### Setup — Local (no Docker)

**1. Install dependencies**

```bash
cd backend
pip install -r requirements.txt
```

**2. Install and start Ollama, pull the LLM model**

```bash
ollama pull qwen3.5:2b
```

**3. Install Marp CLI (for slide generation)**

```bash
npm install -g @marp-team/marp-cli
```

**4. Start the server**

```bash
python main.py
```

API available at `http://localhost:8000`. Configure host/port in `config.json`.

### Setup — Docker (production-equivalent)

```bash
cd backend
docker compose build          # first run: bakes ~6GB embedding model into image
docker compose up -d          # start stack in background
docker compose exec ollama ollama pull qwen3.5:2b
curl http://localhost:8000/health   # wait for 200
```

The stack runs two containers: `ollama` (port 11434) and `app` (port 8000). GPU passthrough is enabled — requires NVIDIA driver ≥525 on the host.

### API

**Auth**

```
POST /auth/login    {"username": "...", "password": "..."}
POST /auth/refresh  {"refresh_token": "..."}
POST /auth/verify   {"token": "..."}
```

**Chat** — requires `Authorization: Bearer <access_token>`

```
POST /chat
{"message": "hi", "history": []}
```

**Health**

```
GET /health   → 503 while embedding model loading, 200 when ready
```

### Slash Commands

| Command | Routes to | Example |
|---|---|---|
| `/note`, `/notes` | NotesAgent | `/note meeting with supervisor tomorrow` |
| `/slides`, `/slide` | SlidesAgent | `/slides intro to neural networks` |

Without a slash command, the Orchestrator's LLM decides routing.

### Agent Architecture

```
User message
    │
    ├── /note or /slides? ──► hard-route to specialist (deterministic)
    │
    └── no command ──► Orchestrator
                            ├── general Q&A ──► answer directly
                            ├── note task   ──► handoff → NotesAgent
                            └── slides task ──► handoff → SlidesAgent

All paths: load all memories → inject into system prompt → agent runs
```

### Memory System

- **Storage**: SQLite `memories` table — content, category, tags, created_at
- **Retrieval**: all facts loaded on every turn and injected into the orchestrator system prompt (ChatGPT-style, no RAG on memory)
- **RAG is reserved for the knowledge base** — `data/files/` is embedded with `nomic-embed-multimodal-3b` (text, images, PDFs in a unified vector space)
- **Categories**: `teaching`, `research`, `career`, `personal`, `ideas`

---

## Frontend

A desktop client built with [DearPyGui](https://github.com/hoffstadt/DearPyGui).

### Features

- Black background with cyan neon aesthetic
- Login screen with JWT auth
- Scrollable chat history with labeled message bubbles
- Enter to send, auto token refresh, thinking indicator

### Structure

```
frontend/
├── app.py         # Main DearPyGui application
├── api.py         # HTTP client — login, refresh, send message
├── config.py      # API_BASE_URL
└── requirements.txt
```

### Setup

```bash
cd frontend
pip install -r requirements.txt
python app.py
```

Change `API_BASE_URL` in `config.py` if the backend runs on a different host or port.

---

## Inspecting the Database

```bash
sqlite3 backend/data/memory.db "SELECT id, category, substr(content,1,80) FROM memories;"
sqlite3 backend/data/memory.db "SELECT id, title, category, created_at FROM notes;"
```