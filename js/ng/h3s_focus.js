import { h } from "./h3s_dom.js";

function pathTo(node, root) {
  const path = [];
  for (let at = node; at; at = at.parentNode) {
    path.unshift(at);
    if (at === root) return path;
  }
  return [];
}

// Keep only the focused input's ancestor chain mounted; rebuild every other branch.
// Detaching/reinserting the same input still clears Chromium's native editing undo.
function keepInput(page, fresh, active, next) {
  const oldPath = pathTo(active, page), newPath = pathTo(next, fresh);
  if (!oldPath.length || oldPath.length !== newPath.length
    || oldPath.some((node, i) => node.tagName !== newPath[i].tagName || node.className !== newPath[i].className)) return false;
  for (let i = 0; i < oldPath.length - 1; i++) {
    const old = oldPath[i], replacement = newPath[i], kept = oldPath[i + 1], placeholder = newPath[i + 1];
    for (const child of [...old.childNodes]) if (child !== kept) old.removeChild(child);
    let after = false;
    for (const child of [...replacement.childNodes]) {
      if (child === placeholder) after = true;
      else if (after) old.append(child);
      else old.insertBefore(child, kept);
    }
  }
  return true;
}

export function updateStudioPage(page, children) {
  const fields = (root) => [...root.querySelectorAll("input,textarea,select")];
  const active = document.activeElement, before = fields(page), index = before.indexOf(active);
  const wasInside = pathTo(active, page).length > 0;
  const fresh = h("div", { class: page.className }, children), after = fields(fresh);
  const next = index >= 0 && before.length === after.length && active.tagName === after[index].tagName ? after[index] : null;
  const text = active?.tagName === "TEXTAREA" || (active?.tagName === "INPUT" && (active.getAttribute("type") || "text") === "text");
  if (next && text && next.value === active.value && keepInput(page, fresh, active, next)) return;
  const caret = index >= 0 && typeof active.selectionStart === "number" ? [active.selectionStart, active.selectionEnd] : null;
  const draft = next && active.getAttribute("type") === "number" ? active.value : null;
  page.replaceChildren(...fresh.childNodes);
  if (!next) { if (wasInside) page.parentNode?.focus?.({ preventScroll: true }); return; }
  if (draft !== null && next.getAttribute("type") === "number" && next.value !== draft) {
    const committed = next.value; next.value = draft;
    next.onblur = (event) => { if (next.isConnected && next.value !== committed) next.onchange?.(event); };
  }
  next.focus({ preventScroll: true });
  if (caret && next.setSelectionRange) try { next.setSelectionRange(...caret); } catch {}
}
