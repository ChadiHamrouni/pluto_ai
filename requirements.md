# Personal AI Assistant — Software Requirements Document

## 1. Project Overview

**Objective:**  
Develop a **local-first AI assistant** that:

- Runs efficiently on a personal computer using **Ollama `qwen3.5:4b`**.
- Provides a **single LLM instance** backend with multi-agent orchestration.
- Supports structured memory and retrieval (SQLite + RAG embeddings).
- Automates common tasks including:
  - Notes management
  - Slide generation from Markdown to PDF (Marp-based)
  - Lab/code snippet generation
- Offers a backend API for potential UI integration.
- Maintains persistent, categorized memory with context awareness.
- Provides configurable hyperparameters for agents, RAG, and memory settings.

**Primary Users:**  
- Researcher / student managing teaching, personal, and career tasks.
- Users who require local, secure AI assistance without cloud dependency.

---

## 2. Key Features

1. **Memory System**
   - Structured memory stored in SQLite.
   - Semantic retrieval using vector embeddings (RAG).
   - Rule-based + LLM-assisted decision pipeline for what to store.
   - Automatic categorization: teaching, research, career, personal, ideas.
   - Memory pruning and deduplication to avoid bloat.
   - Retrieval supports context-aware queries (e.g., teaching vs research).

2. **Agents**
   - Multi-agent architecture using **OpenAI Agents SDK**.
   - Agents handle task-specific responsibilities:
     - NotesAgent
     - SlidesAgent
     - MemoryAgent
   - All agents route through a central orchestrator to avoid loading multiple LLM instances unnecessarily.
   - Agents do not maintain memory themselves; they call tools for all storage/retrieval.

3. **Tools**
   - Pure function modules called by agents.
   - Responsibilities:
     - Memory storage and retrieval
     - File handling (Markdown/PDF)
     - RAG and embedding management
     - LLM calls and prompt handling
   - Deterministic and lightweight to minimize CPU/GPU/RAM footprint.

4. **Configuration**
   - Centralized JSON configuration file.
   - Includes:
     - Agent model names
     - Temperature, max tokens
     - RAG parameters (top_k, chunk size, embedding model)
     - Other hyperparameters
   - Allows easy tuning without changing code.

5. **API Layer**
   - Backend exposes endpoints for interaction:
     - `/chat` — main assistant interface
     - `/note` — explicit note creation
     - `/memory/search` — query memory for relevant content
   - Supports streaming responses for long outputs.
   - UI-agnostic: can support multiple frontends (ImGui, Tauri, web) later.

6. **Persistence**
   - Notes and other long-term information are stored locally.
   - Embeddings are stored separately for efficient RAG queries.
   - Memory is normalized and chunked to avoid duplicates and irrelevant storage.

7. **Operational Principles**
   - Single model instance is loaded at startup.
   - Sub-agents are routed internally; no multiple models loaded simultaneously.
   - All decision logic regarding memory storage is deterministic with optional LLM scoring.
   - Backend handles all intelligence; UI is only responsible for input/output rendering.

---

## 3. Non-Functional Requirements

- **Performance:** Fast local response; minimal RAM and GPU usage.
- **Scalability:** Designed for multi-agent orchestration without increasing memory footprint unnecessarily.
- **Extensibility:** New agents and tools can be added without changing core orchestrator.
- **Reliability:** Deterministic memory storage and retrieval; avoids duplication.
- **Security:** All data stored locally; no cloud dependencies.
- **Maintainability:** Clear folder separation (models, agents, tools, routes, helpers).

---

## 4. System Architecture

### 4.1 High-Level Overview


User Interface (future)
↓
Backend API (FastAPI)
↓
Orchestrator
↓
Task-Specific Agents
↓
Tool Layer (memory, files, RAG, LLM calls)
↓
Persistent Storage (SQLite + Vector DB)


### 4.2 Memory Decision Pipeline

1. **Rule-based filter** — discard obvious irrelevant data.
2. **Optional LLM scoring** — only for ambiguous or candidate content.
3. **Memory Writer Tool** — deterministic, stores cleaned content.
4. **Embedding pipeline** — chunks text and stores embeddings for RAG retrieval.
5. **Memory retrieval** — context-aware query with top-K results.

---

## 5. Folder / Module Structure

- `main.py` — backend startup
- `config.json` — hyperparameters and agent settings
- `models/` — Pydantic data models for validation
- `agents/` — agent definitions and orchestrator
- `tools/` — pure function modules for memory, files, LLM, RAG
- `routes/` — API endpoints
- `helpers/` — generic helper functions (logging, prompt formatting, utilities)
- `requirements.txt` — Python dependencies
- `.gitignore` — ignored files

---

## 6. Agent Design

- Agents are responsible for task-specific operations.
- Agents **do not** store memory directly.
- Central orchestrator manages agent execution and ensures only one LLM instance is active.
- Each agent references the **tools layer** for all file and memory operations.
- Agents’ behavior and hyperparameters are defined in the configuration file.

---

## 7. Memory / RAG Design

- Memory split into:
  - Structured database (SQLite)
  - Vector embeddings for semantic retrieval
- Only normalized, high-value content is stored.
- Memory is chunked, tagged, and categorized.
- Retrieval is context-aware: filters by category, mode, and user query intent.
- Periodic pruning to avoid memory growth and duplication.

---

## 8. Configuration Management

- JSON file defines:
  - Agent models, temperature, max tokens
  - RAG parameters (chunk size, top K, embedding model)
  - Other system-wide hyperparameters
- Allows agents and tools to be updated or tuned without code changes.

---

## 9. Future UI Integration

- Backend exposes clean API for potential UI:
  - ImGui (C++) or Tauri (Rust + Web) or Web frontend
- UI handles only input/output; no logic.
- Supports streaming output for long responses.
- File outputs (slides, labs) are saved locally; UI may read and render.

---

## 10. Success Criteria

- Local AI assistant runs on a Windows machine with minimal RAM/GPU usage.
- Single LLM instance with multi-agent orchestration functions correctly.
- Notes and slides can be stored, retrieved, and categorized reliably.
- RAG retrieval returns relevant results based on query context.
- Configuration allows easy tuning of agents and system parameters.
- System is modular and ready for future UI integration.

---

## 11. Constraints

- Model limited to `qwen3.5:4b` for memory footprint.
- Only local storage (no cloud dependency for now).
- Streaming support required for smooth user experience.
- Deterministic memory storage to avoid inconsistencies.

---

**End of Requirements Document**