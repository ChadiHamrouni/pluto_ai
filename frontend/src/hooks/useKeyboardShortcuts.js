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
        if (condition !== undefined && !condition) continue;
        // combo can be [modifier, key] or just [key] for bare keys like "Escape"
        const [modifierOrKey, key] = combo;
        const matches = key !== undefined
          ? e[modifierOrKey] && e.key === key
          : e.key === modifierOrKey;
        if (matches) {
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
