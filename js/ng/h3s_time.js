// View coordinates only. Render-part timing remains the planner's responsibility.
const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
export function timeView(value = {}) {
  return { zoom: Number.isFinite(value.zoom) ? clamp(value.zoom, 1, 32) : 1,
    scroll: Number.isFinite(value.scroll) ? clamp(value.scroll, 0, 1) : 0 };
}

export function zoomView(current, zoom) {
  const before = timeView(current), next = timeView({ zoom });
  const middle = before.scroll * (1 - 1 / before.zoom) + 0.5 / before.zoom;
  next.scroll = next.zoom === 1 ? 0 : clamp((middle - 0.5 / next.zoom) / (1 - 1 / next.zoom), 0, 1);
  return next;
}

export function fitRange(range, duration) {
  if (!range || !(range[1] > range[0]) || !(duration > 0)) return timeView();
  const next = timeView({ zoom: duration / ((range[1] - range[0]) * 1.25) });
  const middle = (range[0] + range[1]) / (2 * duration);
  next.scroll = next.zoom === 1 ? 0 : clamp((middle - 0.5 / next.zoom) / (1 - 1 / next.zoom), 0, 1);
  return next;
}

export function tickTimes(duration, zoom = 1) {
  const visible = duration / timeView({ zoom }).zoom;
  const step = [0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 30, 60, 120, 300, 600].find((n) => n >= visible / 8) || 600;
  return Array.from({ length: Math.floor(duration / step) + 1 }, (_, index) => Math.round(index * step * 1e6) / 1e6);
}
