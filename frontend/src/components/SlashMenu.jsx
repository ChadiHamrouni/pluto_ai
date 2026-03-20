const COMMANDS = [
  { cmd: "/note",     desc: "Create or manage notes" },
  { cmd: "/slides",   desc: "Generate a slide presentation" },
  { cmd: "/remember", desc: "Save something to memory" },
  { cmd: "/forget",   desc: "Delete a memory" },
];

export { COMMANDS };

export default function SlashMenu({ query, activeIndex, onSelect }) {
  const filtered = query === "/"
    ? COMMANDS
    : COMMANDS.filter((c) => c.cmd.startsWith(query));

  if (!filtered.length) return null;

  return (
    <div className="slash-menu">
      {filtered.map((c, i) => (
        <button
          key={c.cmd}
          className={`slash-item${i === activeIndex ? " slash-item--active" : ""}`}
          onMouseDown={(e) => { e.preventDefault(); onSelect(c.cmd); }}
        >
          <span className="slash-cmd">{c.cmd}</span>
          <span className="slash-desc">{c.desc}</span>
        </button>
      ))}
    </div>
  );
}
