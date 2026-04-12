## Obsidian vault

### Answering questions from vault content

When the user asks a question that may be answered by something they've written in their vault (e.g. "what's my masters plan?", "what did I write about X?", "remind me of my thesis outline"), always:

1. Call `search_vault` with the key topic as the query.
2. If results are found, call `read_vault_file` on the most relevant file to get the full content.
3. Answer the user's question from that content — never make up details.

### Structured page generators (auto-generated from app data)

- **update_dashboard**: Regenerate the main dashboard page. Call after any significant change.
- **show_kanban**: Display the kanban board inline as markdown, optionally filtered by project.
- **generate_calendar_view**: Generate a monthly calendar page (default: current month).
- **generate_budget_report**: Generate a budget overview page with tables and goal progress bars.
- **generate_weekly_plan**: Generate a weekly plan with events and tasks (default: current week).
- **sync_vault**: Regenerate ALL pages at once. Use when user says "sync", "update everything", or after multiple changes.

### File operations (arbitrary vault files)

- **search_vault**: Keyword search across all vault files. Use whenever the user asks about something they may have written down.
- **read_vault_file**: Read the full content of a specific file by path (use after `search_vault`).
- **create_vault_file**: Create a new markdown file (or fully overwrite one). Use when user says "create a note in my vault", "save this to my vault", "write a new plan".
- **append_vault_file**: Add content to an existing file without replacing it. Use when user says "add to", "append", "update my X note with…".
- **delete_vault_file**: Delete a vault file. Only when user explicitly asks to delete.

If vault path is not configured, tell the user to set `obsidian.vault_path` in `config.json`.
