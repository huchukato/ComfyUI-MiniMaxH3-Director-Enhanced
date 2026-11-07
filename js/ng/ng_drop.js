// Files dragged from a folder (or a picture dragged from ComfyUI's queue) onto one of our DOM faces. The faces cover their
// node, so ComfyUI's own drop (canvas -> node.onDragDrop) never sees them and would add a new Load Image node instead;
// the element takes the drop itself and outlines while something is held over it.
const carriesFiles = (event) => [...(event.dataTransfer?.types || [])].some((type) => type === "Files" || type === "text/uri-list");

export function dropTarget(element, ondrop) {
  const mark = (on) => { element.style.outline = on ? "2px dashed #8FC1FF" : ""; element.style.outlineOffset = on ? "-4px" : ""; };
  element.addEventListener("dragover", (event) => {
    if (!carriesFiles(event)) return;
    event.preventDefault(); event.stopPropagation();
    event.dataTransfer.dropEffect = "copy"; mark(true);
  });
  element.addEventListener("dragleave", (event) => { if (!element.contains(event.relatedTarget)) mark(false); });
  element.addEventListener("drop", (event) => {
    mark(false);
    if (!carriesFiles(event)) return;
    event.preventDefault(); event.stopPropagation();
    ondrop(event);
  });
}

// A picture of this ComfyUI dragged as a /view link: { filename, subfolder, type }, or null.
export function viewSource(event) {
  try {
    const url = new URL(event.dataTransfer?.getData("text/uri-list")?.split("\n")[0].trim() || "", location.href);
    const filename = url.searchParams.get("filename");
    if (url.origin !== location.origin || !url.pathname.endsWith("/view") || !filename) return null;
    return { filename, subfolder: url.searchParams.get("subfolder") || "", type: url.searchParams.get("type") || "input" };
  } catch { return null; }
}
