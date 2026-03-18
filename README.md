# Personal AI Assistant

A local-first, multi-agent AI assistant built on [OpenAI Agents SDK](https://github.com/openai/openai-agents-python) running fully on [Ollama](https://ollama.com). No cloud, no API keys — everything runs on your machine.

---

## Features

- **Orchestrator + specialist agents** — routes tasks intelligently between NotesAgent and SlidesAgent
- **Persistent memory** — stores and retrieves facts via SQLite + vector embeddings (RAG)
- **Notes** — creates structured markdown notes, saved to disk with YAML front matter
- **Slides** — generates PDF presentations from outlines via Marp
- **Slash commands** — `/note`, `/slides` for deterministic hard-routing, bypassing LLM routing
- **Dev REPL** — interactive terminal for testing without starting the API server

---

## Project Structure

```
personal_ai/
├── main.py               # FastAPI server entry point
├── dev.py                # Standalone dev REPL (no API needed)
├── config.json           # All hyperparameters (models, RAG, memory, storage)
├── requirements.txt
│
├── my_agents/            # Agent definitions (OpenAI Agents SDK)
│   ├── orchestrator.py   # Central router — handles memory, hands off to specialists
│   ├── notes_agent.py    # Creates, lists, and retrieves markdown notes
│   └── slides_agent.py   # Generates Marp PDF presentations
│
├── tools/                # Pure function tools called by agents
│   ├── memory_tools.py   # store_memory, search_memory, prune_memory
│   ├── notes_tools.py    # create_note, list_notes, get_note
│   ├── slides_tools.py   # generate_slides (Marp → PDF)
│   └── rag_tools.py      # embed_text, chunk_text, search_embeddings
│
├── helpers/              # Infrastructure utilities
│   ├── config_loader.py  # Loads and caches config.json
│   ├── db.py             # SQLite init (memories + notes tables)
│   ├── logger.py         # Logging (LOG_LEVEL env var)
│   ├── command_parser.py # Slash command parser
│   ├── prompt_utils.py   # System prompt and chat history builders
│   └── tracer.py         # Rich trace output for agent runs
│
├── models/               # Pydantic models for data validation
│   ├── chat.py           # ChatRequest, ChatResponse
│   ├── memory.py         # MemoryEntry, MemoryCategory
│   ├── notes.py          # Note, NoteCreateRequest
│   └── slides.py         # SlideRequest, SlideResponse
│
├── routes/               # FastAPI route handlers
│   └── chat.py           # POST /chat
│
└── data/                 # Runtime data (gitignored)
    ├── memory.db         # SQLite database
    ├── embeddings/       # Vector embeddings (.npy files)
    ├── notes/            # Markdown note files
    └── slides/           # Generated Marp markdown + PDFs
```

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Install and start Ollama

```bash
ollama pull qwen3.5:4b
ollama pull qwen3-embedding:0.6b
```

### 3. Install Marp CLI (for slide generation)

```bash
npm install -g @marp-team/marp-cli
```

---

## Running

### Dev REPL (recommended for testing)

```bash
python dev.py
```

Interactive terminal session. Full agent behavior — tools, handoffs, memory — without the API server.

```
Personal AI — dev REPL  (Ctrl-C or blank line to quit)

you> hi
assistant> Hello! How can I help you today?
(9.84s)
```

Enable debug timers (memory fetch + agent run phases):

```bash
LOG_LEVEL=DEBUG python dev.py
```

### API Server

```bash
python main.py
```

Starts FastAPI at `http://localhost:8000`. Configure host/port in `config.json`.

**Endpoint:**

```
POST /chat
Content-Type: application/json

{
  "message": "I have a meeting tomorrow with my supervisor",
  "history": []
}
```

---

## Slash Commands

Slash commands bypass LLM routing — the target agent is invoked directly.

| Command | Routes to | Example |
|---|---|---|
| `/note`, `/notes` | NotesAgent | `/note meeting with supervisor tomorrow` |
| `/slides`, `/slide` | SlidesAgent | `/slides intro to neural networks` |

Without a slash command, the Orchestrator's LLM decides routing.

---

## Agent Architecture

```
User message
    │
    ├── /note or /slides? ──► hard-route to specialist agent (deterministic)
    │
    └── no command ──► Orchestrator (LLM routing)
                            │
                            ├── general Q&A ──► answer directly
                            ├── note task   ──► handoff → NotesAgent
                            └── slides task ──► handoff → SlidesAgent

All paths:
  1. Pre-fetch top-K memories via RAG → inject into system prompt
  2. Agent runs with tools / handoff
  3. Orchestrator stores notable facts via store_memory
```

**Orchestrator** tools: `store_memory`, `search_memory`, `prune_memory`

**NotesAgent** tools: `create_note`, `list_notes`, `get_note`

**SlidesAgent** tools: `generate_slides`

---

## Configuration

All hyperparameters live in `config.json`:

```json
{
  "orchestrator": { "model": "qwen3.5:4b", "temperature": 0.5, "max_tokens": 1024 },
  "notes_agent":  { "model": "qwen3.5:4b", "temperature": 0.5, "max_tokens": 1024 },
  "slides_agent": { "model": "qwen3.5:4b", "temperature": 0.6, "max_tokens": 1024 },
  "rag": {
    "embedding_model": "qwen3-embedding:0.6b",
    "top_k": 5,
    "similarity_threshold": 0.75
  },
  "memory": {
    "db_path": "data/memory.db",
    "categories": ["teaching", "research", "career", "personal", "ideas"],
    "prune_threshold_days": 90
  }
}
```

---

## Memory System

The assistant builds a persistent memory from conversations:

1. **SQLite** — stores content, category, tags, and metadata
2. **Vector embeddings** — `.npy` files generated by the Ollama embedding model

On each query, the top-K most semantically similar memories are retrieved and injected into the system prompt, giving the assistant personalised context without re-asking.

Memory categories: `teaching`, `research`, `career`, `personal`, `ideas`

---

## Inspecting the Database

```bash
# Row counts
sqlite3 data/memory.db "SELECT 'memories', COUNT(*) FROM memories UNION SELECT 'notes', COUNT(*) FROM notes;"

# All notes
sqlite3 data/memory.db "SELECT id, title, category, created_at FROM notes;"

# All memories
sqlite3 data/memory.db "SELECT id, category, substr(content,1,80) FROM memories;"
```
