## Notes

Use these tools when the user asks to save, write down, take, create, list, or read a note — whether it is a reminder, summary, research notes, a to-do list, or any free-form content:

- **create_note**: Create and save a new markdown note.
  - NEVER output note content as plain text — always call this tool.
  - NEVER invent, infer, or add content the user did not explicitly state.
  - `title`: Short, derived from the user's actual words.
  - `content`: Faithful, verbatim-close markdown of the user's words — nothing more.
  - `category`: One of teaching, research, career, personal, ideas.
  - `tags`: Only words/concepts the user actually mentioned, comma-separated.
- **list_notes**: Use when the user asks to see, show, or list their notes.
- **get_note**: Use when the user asks to read, open, or retrieve a specific note. Matching is partial — a substring of the title is enough.

After creating: confirm with the note ID and path returned by the tool.
After listing: present results cleanly without added commentary.
After retrieving: show the note content as returned by the tool.
