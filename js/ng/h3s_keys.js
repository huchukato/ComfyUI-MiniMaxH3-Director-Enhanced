// ComfyUI's ChangeTracker captures keydown at window level, then calls undoRedo in
// requestAnimationFrame. Stopping propagation in the Studio cannot cancel that
// already scheduled call. Its public compatibility API lets us exclude exactly
// the event the Studio handled, without changing graph undo anywhere else.
const consumed = new WeakSet();
const guarded = new WeakSet();

export function bindTimelineKeys(root, key, tracker = globalThis.window?.comfyAPI?.changeTracker?.ChangeTracker) {
  const prototype = tracker?.prototype;
  if (typeof prototype?.undoRedo === "function" && !guarded.has(prototype)) {
    const original = prototype.undoRedo;
    prototype.undoRedo = function (event, ...args) {
      return consumed.has(event) ? true : original.call(this, event, ...args);
    };
    guarded.add(prototype);
  }
  const capture = (event) => { if (key(event)) consumed.add(event); };
  root.addEventListener("keydown", capture, true);
  return () => root.removeEventListener("keydown", capture, true);
}
