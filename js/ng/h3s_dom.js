// A small element builder for the Studio: h("div", {class, style, onclick, ...}, ...children).
export function h(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "style" && typeof value === "object") Object.assign(node.style, value);
    else if (key === "dataset") Object.assign(node.dataset, value);
    else if (key.startsWith("on")) node[key.toLowerCase()] = value;
    // `list` (an input's datalist) is read-only as a property and exists only as an attribute.
    else if (key in node && !key.startsWith("aria") && key !== "role" && key !== "list") node[key] = value;
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

// Keys pressed inside a Studio or card in the graph stay there: with the node selected, Delete or Backspace on one of its
// buttons removed the whole node. Ctrl/Cmd shortcuts (save, queue) still reach ComfyUI.
export function keepKeys(element) {
  element.addEventListener("keydown", (event) => { if (!event.ctrlKey && !event.metaKey) event.stopPropagation(); });
  element.addEventListener("keyup", (event) => { if (!event.ctrlKey && !event.metaKey) event.stopPropagation(); });
}

const PATHS = {
  back: "M15 18l-6-6 6-6", plus: "M12 5v14M5 12h14", close: "M6 6l12 12M18 6L6 18", play: "M7 4v16l13-8z",
  doc: "M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9zM14 3v6h6M8 13h8M8 17h5",
  spark: "M12 3l1.8 4.7L18 9.5l-4.2 1.8L12 16l-1.8-4.7L6 9.5l4.2-1.8zM19 15l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8z",
  trash: "M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3", chevron: "M9 6l6 6-6 6",
  image: "M3 6a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2zM9 10m-2 0a2 2 0 1 0 4 0a2 2 0 1 0-4 0M21 17l-5-5-9 8",
  video: "M3 7a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2zM10 9l5 3-5 3z",
  audio: "M4 12h2M8 8v8M12 5v14M16 9v6M20 11v2", text: "M5 6h14M12 6v13M9 19h6",
  dice: "M4 7a3 3 0 0 1 3-3h10a3 3 0 0 1 3 3v10a3 3 0 0 1-3 3H7a3 3 0 0 1-3-3zM9 9h.01M15 15h.01M15 9h.01M9 15h.01",
  expand: "M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7",
  brush: "M18.4 2.6a2 2 0 0 1 2.9 2.9L11 15.8 8.2 13zM7 14.5a3 3 0 0 0-3 3c0 1.3-.8 2.2-2 2.8 3 .9 7-.2 7-3.3a3 3 0 0 0-2-2.5z",
  gear: "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 0 1-4 0v-.1A1.7 1.7 0 0 0 9 19.4a1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 0 1 0-4h.1A1.7 1.7 0 0 0 4.6 9a1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 0 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 0 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z",
};

export function icon(name, size = 16) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  for (const [key, value] of Object.entries({ width: size, height: size, viewBox: "0 0 24 24", fill: name === "play" ? "currentColor" : "none",
    stroke: "currentColor", "stroke-width": 2, "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true" }))
    svg.setAttribute(key, value);
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("d", PATHS[name]);
  svg.append(path);
  return svg;
}

export function field(label, control, extra = {}) {
  return h("label", { class: "h3s-field", ...extra }, h("span", { class: "h3s-lbl" }, label), control);
}

export function select(options, value, onchange, props = {}) {
  const node = h("select", { class: "h3s-in", onchange: (event) => onchange(event.target.value), ...props });
  for (const option of options) {
    if (option.group) {
      const group = h("optgroup", { label: option.group });
      for (const [v, l] of option.items) group.append(h("option", { value: v }, l));
      node.append(group);
    } else node.append(h("option", { value: option[0] }, option[1]));
  }
  node.value = String(value);
  return node;
}

// A short explanation that stays out of the way: hover (or focus) the small i to read it.
export function tip(text) {
  return h("span", { class: "h3s-tip", title: text, tabindex: "0", role: "note", "aria-label": text }, "i");
}
