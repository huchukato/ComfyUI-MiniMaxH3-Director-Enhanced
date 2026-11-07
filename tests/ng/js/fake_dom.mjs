// Just enough DOM for the Studio views to build and for a test to find, read and click their parts.
class FakeNode {}
class FakeText extends FakeNode {
  constructor(text) { super(); this.text = String(text); }
  get innerText() { return this.text; }
  all() { return []; }
}
class FakeElement extends FakeNode {
  constructor(tag) {
    super(); this.tagName = tag.toUpperCase(); this.children = []; this.style = { setProperty(key, value) { this[key] = value; } }; this.dataset = {}; this.attributes = {};
    this.className = ""; this.value = ""; this.disabled = false; this.hidden = false; this.title = "";
    const self = this;
    this.classList = { add: (c) => { if (!self.classList.contains(c)) self.className = `${self.className} ${c}`.trim(); },
      remove: (c) => { self.className = self.className.split(" ").filter((x) => x && x !== c).join(" "); },
      contains: (c) => self.className.split(" ").includes(c),
      toggle: (c, on = !self.classList.contains(c)) => { if (on) self.classList.add(c); else self.classList.remove(c); return on; } };
  }
  // Like the real DOM, appending an element that already has a parent moves it.
  append(...nodes) {
    for (const node of nodes) {
      const child = typeof node === "string" ? new FakeText(node) : node;
      if (child.parentNode && child.parentNode !== this) child.parentNode.children = child.parentNode.children.filter((entry) => entry !== child);
      child.parentNode = this; this.children.push(child);
    }
  }
  remove() { if (this.parentNode) this.parentNode.children = this.parentNode.children.filter((entry) => entry !== this); this.parentNode = null; }
  get childNodes() { return this.children; }
  removeChild(node) { this.children = this.children.filter((entry) => entry !== node); node.parentNode = null; return node; }
  insertBefore(node, anchor) {
    node.parentNode?.removeChild(node);
    this.children.splice(this.children.indexOf(anchor), 0, node); node.parentNode = this;
  }
  replaceChildren(...nodes) { this.children = []; this.append(...nodes); }
  setAttribute(key, value) { this.attributes[key] = String(value); }
  getAttribute(key) { return this.attributes[key]; }
  get textContent() { return this.innerText; }
  set textContent(value) { this.children = [new FakeText(value)]; }
  get innerText() { return this.children.map((child) => child.innerText).join(" ").replace(/\s+/g, " ").trim(); }
  all() { return [this, ...this.children.flatMap((child) => child.all())]; }
  find(predicate) { return this.all().filter((node) => node !== this && predicate(node)); }
  get parentElement() { return this.parentNode || null; }
  // class selectors only (".a" or ".a.b"), enough for the cards' own lookups
  querySelectorAll(selector) { const names = selector.split(".").filter(Boolean); return this.find((node) => names.every((name) => node.classList?.contains(name))); }
  byClass(name) { return this.find((node) => node.classList.contains(name)); }
  byTag(tag) { return this.find((node) => node.tagName === tag.toUpperCase()); }
  button(text) { return this.find((node) => node.tagName === "BUTTON" && node.innerText.startsWith(text))[0]; }
  getBoundingClientRect() { return { left: 0, x: 0, width: 1000, top: 0, y: 0, height: 40 }; }
  setPointerCapture() {}
  closest() { return null; }
  addEventListener(type, listener) { ((this.listeners ||= {})[type] ||= []).push(listener); }
  removeEventListener(type, listener) { this.listeners?.[type] && (this.listeners[type] = this.listeners[type].filter((entry) => entry !== listener)); }
  // Calls this element's listeners for one event (no bubbling in this fake).
  fire(type, event) { event.target ??= this; for (const listener of this.listeners?.[type] || []) listener(event); }
}

export function installDom() {
  globalThis.Node = FakeNode;
  globalThis.document = {
    createElement: (tag) => new FakeElement(tag),
    createElementNS: (_ns, tag) => new FakeElement(tag),
    createTextNode: (text) => new FakeText(text),
    getElementById: () => null, head: new FakeElement("head"), body: new FakeElement("body"),
    addEventListener() {}, removeEventListener() {}, dispatchEvent() {},
  };
  globalThis.CustomEvent = class { constructor(type) { this.type = type; } };
}
