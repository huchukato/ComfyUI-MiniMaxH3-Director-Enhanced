// Video size choices, taken over from the Legacy Director's settings panel (js/minimax_director.js): the same
// presets, the same ratio list and the same /32 fit for a ratio and a megapixel budget.

export const NATIVE_MP = 1344 * 768 / 1e6;

const NATIVE = [["21:9", 1344, 576], ["2:1", 1344, 672], ["16:9", 1344, 768], ["3:2", 1152, 768], ["4:3", 1024, 768],
  ["5:4", 960, 768], ["1:1", 992, 992], ["4:5", 768, 960], ["3:4", 768, 1024], ["2:3", 768, 1152],
  ["9:16", 768, 1344], ["1:2", 672, 1344], ["9:21", 576, 1344]];
const FAST = [["21:9", 1120, 480], ["2:1", 960, 480], ["16:9", 864, 480], ["3:2", 736, 480], ["4:3", 640, 480],
  ["5:4", 608, 480], ["1:1", 640, 640], ["4:5", 480, 608], ["3:4", 480, 640], ["2:3", 480, 736],
  ["9:16", 480, 864], ["1:2", 480, 960], ["9:21", 480, 1120]];

export const PRESET_GROUPS = [
  ["Native · short side 768", NATIVE],
  ["Fast · short side 480", FAST],
  ["Above native · slow, more memory", [["16:9", 1920, 1088]]],
];
export const ASPECTS = NATIVE.map(([label]) => { const [a, b] = label.split(":").map(Number); return [label, a / b]; });
export const RESIZE = [["crop", "Crop"], ["stretch to fit", "Stretch"], ["pad", "Pad"], ["pad green", "Pad green"]];

const PRESET_KEYS = new Set(PRESET_GROUPS.flatMap(([, list]) => list.map(([, w, h]) => `${w}x${h}`)));

export const isAuto = (width, height) => !(width > 0 && height > 0);

// The first picture's shape at three sizes, as the Legacy Director offered (user, 2026-10-18: "smaller, but keep the aspect").
// Native follows the server's own picture size (ng/core/project.py h3_canvas): short side 768, at most the area of 1344×768.
export const PICTURE_TIERS = [["small", "Small", 480], ["native", "Native", 768], ["large", "Large (slow)", 1088]];

export function pictureSize(ratio, tier) {
  const short = PICTURE_TIERS.find(([key]) => key === tier)?.[2] || 768;
  let [w, hh] = ratio >= 1 ? [short * ratio, short] : [short, short / ratio];
  if (tier === "native" && w * hh > NATIVE_MP * 1e6) { const scale = Math.sqrt(NATIVE_MP * 1e6 / (w * hh)); w *= scale; hh *= scale; }
  return [snap32(w), snap32(hh)];
}

export function presetValue(width, height, ratio = 0) {
  if (isAuto(width, height)) return "auto";
  const tier = ratio > 0 && PICTURE_TIERS.find(([key]) => pictureSize(ratio, key).join("x") === `${width}x${height}`);
  if (tier) return `picture:${tier[0]}`;
  return PRESET_KEYS.has(`${width}x${height}`) ? `${width}x${height}` : "custom";
}

export const snap32 = (value) => Math.max(32, Math.round(value / 32) * 32);

// Best pair of /32 edges around the ideal one: ratio error first, overshooting the budget costs twice undershooting.
export function fitAspect(pixels, ratio) {
  const edges = (v) => [...new Set([Math.max(32, Math.floor(v / 32) * 32), Math.max(32, Math.ceil(v / 32) * 32)])];
  let best = [768, 768], bestScore = Infinity;
  for (const w of edges(Math.sqrt(pixels * ratio))) for (const h of edges(Math.sqrt(pixels / ratio))) {
    const score = Math.abs(w / h - ratio) / ratio + (w * h > pixels ? 0.5 : 0.25) * Math.abs(w * h - pixels) / pixels;
    if (score < bestScore) { bestScore = score; best = [w, h]; }
  }
  return best;
}

// The ratio a /32 canvas was picked from; within 4 %, which holds every fit in the list.
export function nearestAspect(width, height) {
  if (isAuto(width, height)) return "";
  let best = "", error = 0.04;
  for (const [label, ratio] of ASPECTS) {
    const e = Math.abs(width / height - ratio) / ratio;
    if (e < error) { error = e; best = label; }
  }
  return best;
}

export function canvasInfo(width, height) {
  if (isAuto(width, height)) return ["H3 takes the size from the first picture: short side 768, at most the area of 1344×768.", ""];
  if (width * height / 1e6 > NATIVE_MP * 1.05)
    return ["Above H3 native (1.03 MP): much slower, more memory and outside what H3 was trained on.", "warn"];
  if (Math.min(width, height) <= 512) return ["Fast size: good for trying things out, less detail.", ""];
  return ["Within H3's native range. Edges are multiples of 32.", ""];
}
