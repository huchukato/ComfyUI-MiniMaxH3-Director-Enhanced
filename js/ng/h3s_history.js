// Whole project documents preserve IDs, source clocks and bindings across an edit.
export function editHistory(initial, limit = 100) {
  let current = JSON.stringify(initial), past = [], future = [];
  return {
    get canUndo() { return past.length > 0; },
    get canRedo() { return future.length > 0; },
    get value() { return JSON.parse(current); },
    record(value) {
      const next = JSON.stringify(value);
      if (next === current) return;
      past.push(current); past = past.slice(-limit); current = next; future = [];
    },
    undo() {
      if (!past.length) return null;
      future.push(current); current = past.pop(); return JSON.parse(current);
    },
    redo() {
      if (!future.length) return null;
      past.push(current); current = future.pop(); return JSON.parse(current);
    },
    reset(value) { current = JSON.stringify(value); past = []; future = []; },
  };
}
