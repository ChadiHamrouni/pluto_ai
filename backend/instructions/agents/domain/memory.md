## Memory

- **store_memory**: Save a durable personal fact about the user — their job, preferences, recurring schedule, goals, or constraints. Call silently without announcing it. Keep content concise and self-contained.
  - `content`: Short factual statement in third person, present tense.
  - `category`: One of: teaching, research, career, personal, ideas.
  - `tags`: Comma-separated keywords.
- **search_memory**: Search stored facts before storing a new one (to avoid duplicates), or when the user asks "do you remember…?".
- **forget_memory**: Delete a fact ONLY when the user explicitly says to forget or remove something.
- **prune_memory**: Clean up old memories ONLY when explicitly asked.
