import { useEffect } from "react";

/**
 * Registers global keyboard shortcuts.
 *
 * shortcuts: array of { keys: [modifier, key], handler, deps }
 * Example:
 *   useKeyboardShortcuts([
 *     { combo: ["ctrlKey", "i"], handler: handleExpand, deps: [expanded] },
 *     { combo: ["ctrlKey", "l"], handler: handleAutoToggle, deps: [] },
 *   ])
 */
export function useKeyboardShortcuts(shortcuts) {
  useEffect(() => {
    const handler = (e) => {
      for (const { combo, handler: cb, condition } of shortcuts) {
        const [modifier, key] = combo;
        if (e[modifier] && e.key === key) {
          if (condition !== undefined && !condition) continue;
          e.preventDefault();
          cb(e);
        }
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, shortcuts.flatMap((s) => s.deps ?? []));
}
