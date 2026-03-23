import "./SlashMenu.css";

export default function SlashMenu({ commands = [], query, activeIndex, onSelect }) {
  const filtered = query === "/"
    ? commands
    : commands.filter((c) => c.cmd.startsWith(query));

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
