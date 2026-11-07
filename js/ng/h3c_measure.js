// Measure the content, not the allocated widget height, so resizing can grow and shrink without feeding back on itself.
export function cardContentHeight(root) {
  const last = root.lastElementChild, rect = root.getBoundingClientRect();
  if (!last || !root.offsetHeight || !rect.height) return 0;
  const scale = rect.height / root.offsetHeight;
  const padding = Number.parseFloat(getComputedStyle(root).paddingBottom) || 0;
  return Math.ceil((last.getBoundingClientRect().bottom - rect.top) / scale + padding) + 8;
}
