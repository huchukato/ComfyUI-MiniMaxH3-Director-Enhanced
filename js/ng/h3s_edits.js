import { editHistory } from "./h3s_history.js";
import { dragTo } from "./h3s_model.js";

export function timelineEditor(S, { actions, write, plan, render, reload }) {
  const snapshot = () => ({ shots: S.values.shots || "", project_seconds: S.values.project_seconds });
  const history = editHistory(snapshot());
  S.history = history;
  function restore(back) {
    if (S.docError || S.dragging || S.busy) return;
    const value = back ? history.undo() : history.redo();
    if (!value) return;
    write(value); S.node.graph?.change?.(); reload();
    S.ghosts = []; S.suggestions = {}; S.partDrafts = {}; S.notice = null;
    // An undone deletion may bring a selected item back; a redone deletion clears its selection.
    const list = S.selected?.kind === "shot" ? S.shots : S.selected?.kind === "control" ? S.control : S.audio;
    if (!list.some((item) => item.id === S.selected?.id)) S.selected = null;
    plan(); render();
  }
  function key(event) {
    if (event.target.closest?.("input,textarea,[contenteditable=true]")) return false;
    const key = event.key.toLowerCase();
    if ((event.ctrlKey || event.metaKey) && ["z", "y"].includes(key)) {
      event.preventDefault(); event.stopPropagation(); restore(key === "z" && !event.shiftKey); return true;
    }
    if (event.target.closest?.("select") || event.ctrlKey || event.metaKey || event.altKey || !S.selected || S.dragging) return false;
    const kind = S.selected.kind, list = kind === "shot" ? S.shots : kind === "control" ? S.control : S.audio;
    const item = list.find((entry) => entry.id === S.selected.id);
    if (!item || !["ArrowLeft", "ArrowRight", "Delete", "Backspace"].includes(event.key)) return false;
    event.preventDefault(); event.stopPropagation();
    S.timelineFocus = { ...S.selected };
    if (["Delete", "Backspace"].includes(event.key)) {
      actions[kind === "shot" ? "deleteShot" : kind === "control" ? "deleteControl" : "deleteClip"](item.id);
    } else {
      const siblings = kind === "clip" ? list.filter((entry) => entry.lane === item.lane) : list;
      const delta = (event.key === "ArrowLeft" ? -1 : 1) * (event.shiftKey ? 1 : 0.1);
      const moved = dragTo(siblings, { id: item.id, mode: "move", start: item.start, end: item.end }, delta, S.duration).items;
      actions[kind === "shot" ? "setShots" : kind === "control" ? "setControls" : "setClips"](
        kind === "clip" ? moved.concat(list.filter((entry) => entry.lane !== item.lane)) : moved, item.id);
    }
    return true;
  }
  return { undo: () => restore(true), redo: () => restore(false), key,
    record: () => history.record(snapshot()),
    refresh() { if (JSON.stringify(snapshot()) !== JSON.stringify(history.value)) history.reset(snapshot()); } };
}
