// Drawing the H3 Storyboard on a 2D canvas: one panel's picture (its layers, bottom to top) and the whole sheet in the
// look of the user's ChatGPT boards (title line, numbered panels with time and title on the picture, caption below).
// The editor's views and the pictures handed to ComfyUI are drawn by the same functions, so what is seen is what renders.
import { layerBox, panelTimes, fmtSeconds, srcUrl } from "./h3b_model.js";

const FONT = '"IBM Plex Sans","Segoe UI",system-ui,sans-serif';
export const COLORS = { sheet: "#0B1222", card: "#0F1729", border: "#56688E", empty: "#141B2B", text: "#E6EAF2",
  sub: "#C3CBDA", band: "rgba(8,12,24,0.80)" };

// Pictures by URL; a picture still loading draws as a frame and calls onload (the view redraws).
export function pictureCache(onload) {
  const cache = new Map();
  return {
    get(src) {
      const url = srcUrl(src);
      if (!url) return null;
      if (!cache.has(url)) {
        const img = new Image();
        img.onload = () => onload?.();
        img.onerror = () => { img.failed = true; onload?.(); };
        img.src = url;
        cache.set(url, img);
      }
      const img = cache.get(url);
      return img.complete && img.naturalWidth ? img : null;
    },
    failed(src) { return Boolean(cache.get(srcUrl(src))?.failed); },
    // Resolves once every picture of the board (and optional cast bar) has loaded or failed, for drawing the final sheet.
    async ready(board, cast = []) {
      const items = [...board.panels.flatMap((p) => p.layers).filter((l) => l.kind === "image" && l.src),
        ...(Array.isArray(cast) ? cast.filter((c) => c?.src) : [])];
      const waits = items.map((item) => {
        this.get(item.src);
        const img = cache.get(srcUrl(item.src));
        return img.complete ? null : new Promise((resolve) => {
          img.addEventListener("load", resolve, { once: true }); img.addEventListener("error", resolve, { once: true });
        });
      }).filter(Boolean);
      await Promise.all(waits);
    },
  };
}

function wrap(ctx, text, width, maxLines) {
  const out = [];
  for (const paragraph of String(text || "").split("\n")) {
    let line = "";
    for (const word of paragraph.split(/\s+/).filter(Boolean)) {
      const next = line ? `${line} ${word}` : word;
      if (ctx.measureText(next).width > width && line) { out.push(line); line = word; } else line = next;
    }
    if (line) out.push(line);
  }
  if (out.length > maxLines) { out.length = maxLines; out[maxLines - 1] = out[maxLines - 1].replace(/\s*\S*$/, "") + " …"; }
  return out;
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath();
}

// One panel's picture in the rectangle {x, y, w, h}.
export function drawPicture(ctx, panel, rect, pictures, { placeholder = "" } = {}) {
  ctx.save();
  ctx.beginPath(); ctx.rect(rect.x, rect.y, rect.w, rect.h); ctx.clip();
  ctx.fillStyle = COLORS.empty; ctx.fillRect(rect.x, rect.y, rect.w, rect.h);
  const visible = panel.layers.filter((layer) => !layer.hidden);
  for (const layer of visible) {
    const img = layer.kind === "image" ? pictures.get(layer.src) : null;
    const box = layerBox(layer, rect.w, rect.h, img ? [img.naturalWidth, img.naturalHeight] : [16, 9]);
    ctx.save();
    ctx.globalAlpha = layer.opacity;
    ctx.translate(rect.x + box.cx, rect.y + box.cy);
    ctx.rotate(layer.rotation * Math.PI / 180);
    if (layer.flip) ctx.scale(-1, 1);
    if (layer.kind === "fill") { ctx.fillStyle = layer.color; ctx.fillRect(-box.w / 2, -box.h / 2, box.w, box.h); }
    else if (layer.kind === "image") {
      if (img) ctx.drawImage(img, -box.w / 2, -box.h / 2, box.w, box.h);
      else if (placeholder) {
        ctx.strokeStyle = pictures.failed(layer.src) ? "#E5484D" : "#56688E"; ctx.setLineDash([6, 4]);
        ctx.strokeRect(-box.w / 2, -box.h / 2, box.w, box.h);
      }
    } else {
      const size = layer.size * rect.h;
      ctx.font = `700 ${size}px ${FONT}`; ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillStyle = layer.color;
      ctx.shadowColor = "rgba(0,0,0,0.65)"; ctx.shadowBlur = size * 0.25;
      const lines = String(layer.text || "").split("\n");
      lines.forEach((line, i) => ctx.fillText(line, 0, (i - (lines.length - 1) / 2) * size * 1.2));
    }
    ctx.restore();
  }
  if (!visible.length && placeholder) {
    ctx.fillStyle = "#5C6A84"; ctx.font = `500 ${Math.max(12, rect.h * 0.06)}px ${FONT}`;
    ctx.textAlign = "center"; ctx.textBaseline = "middle"; ctx.fillText(placeholder, rect.x + rect.w / 2, rect.y + rect.h / 2);
  }
  ctx.restore();
}

function panelHeader(ctx, number, time, title, pic) {
  const band = Math.max(26, Math.min(48, pic.h * 0.12)), pad = band * 0.18;
  const titleFont = `600 ${band * 0.42}px ${FONT}`, timeFont = `600 ${band * 0.46}px ${FONT}`;
  ctx.font = timeFont; const timeW = ctx.measureText(time).width;
  ctx.font = titleFont; const titleW = title ? ctx.measureText(title).width : 0;
  const box = band - 2 * pad, width = Math.min(pic.w, pad + box + pad * 2 + timeW + pad * 2 + (title ? titleW + pad * 3 : 0));
  ctx.fillStyle = COLORS.band;
  ctx.beginPath(); ctx.moveTo(pic.x, pic.y); ctx.lineTo(pic.x + width, pic.y); ctx.lineTo(pic.x + width - band * 0.3, pic.y + band);
  ctx.lineTo(pic.x, pic.y + band); ctx.closePath(); ctx.fill();
  ctx.strokeStyle = "#E8ECF5"; ctx.lineWidth = Math.max(1.5, band * 0.05);
  ctx.fillStyle = "#0E1630"; ctx.fillRect(pic.x + pad, pic.y + pad, box, box); ctx.strokeRect(pic.x + pad, pic.y + pad, box, box);
  ctx.fillStyle = "#FFFFFF"; ctx.font = `700 ${box * 0.55}px ${FONT}`; ctx.textAlign = "center"; ctx.textBaseline = "middle";
  ctx.fillText(String(number).padStart(2, "0"), pic.x + pad + box / 2, pic.y + band / 2);
  ctx.textAlign = "left"; ctx.font = timeFont;
  const timeX = pic.x + pad + box + pad * 2;
  ctx.fillText(time, timeX, pic.y + band / 2);
  if (title) {
    const sep = timeX + timeW + pad * 1.5;
    ctx.strokeStyle = "rgba(232,236,245,0.55)"; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(sep + band * 0.15, pic.y + pad); ctx.lineTo(sep - band * 0.15, pic.y + band - pad); ctx.stroke();
    ctx.font = titleFont; ctx.fillStyle = "#F2F4F8";
    ctx.fillText(title.toUpperCase(), sep + pad * 1.5, pic.y + band / 2, pic.w - (sep - pic.x) - pad * 3);
  }
}

// The whole sheet into a canvas of layout.width x layout.height.
export function drawSheet(ctx, board, layout, pictures, { placeholder = false, selected = -1 } = {}) {
  ctx.fillStyle = COLORS.sheet; ctx.fillRect(0, 0, layout.width, layout.height);
  if (layout.title) {
    ctx.textAlign = "center"; ctx.textBaseline = "alphabetic"; ctx.fillStyle = "#F4F6FA";
    ctx.font = `700 30px ${FONT}`; ctx.fillText((board.title || "").toUpperCase(), layout.width / 2, 40, layout.width - 40);
    ctx.fillStyle = COLORS.sub; ctx.font = `500 15px ${FONT}`; ctx.fillText((board.subtitle || "").toUpperCase(), layout.width / 2, 62, layout.width - 40);
  }
  (layout.cast || []).forEach((actor) => {
    ctx.save();
    roundRect(ctx, actor.x, actor.y, actor.w, actor.h, 8);
    ctx.fillStyle = COLORS.card; ctx.fill();
    ctx.strokeStyle = COLORS.border; ctx.lineWidth = 1.5; ctx.stroke();
    ctx.clip();
    const pad = 6, size = actor.h - 2 * pad, img = pictures.get(actor.src);
    ctx.fillStyle = COLORS.empty; ctx.fillRect(actor.x + pad, actor.y + pad, size, size);
    if (img) {
      const s = Math.min(img.naturalWidth || size, img.naturalHeight || size);
      const sx = ((img.naturalWidth || size) - s) / 2, sy = Math.max(0, ((img.naturalHeight || size) - s) * 0.15);
      ctx.drawImage(img, sx, sy, s, s, actor.x + pad, actor.y + pad, size, size);
    }
    ctx.fillStyle = COLORS.text; ctx.font = `700 16px ${FONT}`; ctx.textAlign = "left"; ctx.textBaseline = "middle";
    ctx.fillText(`@${actor.name}`, actor.x + pad + size + 10, actor.y + actor.h * 0.4, actor.w - size - pad * 2 - 14);
    ctx.fillStyle = COLORS.sub; ctx.font = `500 12px ${FONT}`;
    ctx.fillText("CHARACTER", actor.x + pad + size + 10, actor.y + actor.h * 0.68, actor.w - size - pad * 2 - 14);
    ctx.restore();
  });
  const times = panelTimes(board);
  board.panels.forEach((panel, index) => {
    const box = layout.panels[index];
    ctx.save();
    roundRect(ctx, box.x, box.y, box.w, box.h, 8); ctx.fillStyle = COLORS.card; ctx.fill(); ctx.clip();
    drawPicture(ctx, panel, box.pic, pictures, { placeholder: placeholder ? `Panel ${index + 1}` : "" });
    panelHeader(ctx, index + 1, `${fmtSeconds(times[index][0])}–${fmtSeconds(times[index][1])} s`, panel.title, box.pic);
    ctx.fillStyle = COLORS.text; ctx.font = `400 17px ${FONT}`; ctx.textAlign = "left"; ctx.textBaseline = "top";
    wrap(ctx, panel.caption, box.cap.w - 28, 3).forEach((line, i) => ctx.fillText(line, box.cap.x + 14, box.cap.y + 10 + i * 21));
    ctx.restore();
    roundRect(ctx, box.x + 0.5, box.y + 0.5, box.w - 1, box.h - 1, 8);
    ctx.strokeStyle = index === selected ? "#8FC1FF" : COLORS.border; ctx.lineWidth = index === selected ? 4 : 1.5; ctx.stroke();
  });
}
