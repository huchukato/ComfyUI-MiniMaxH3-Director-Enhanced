// The existing Comfy widgets remain the serialized values; this module provides the visible controls.
import { element } from "./ng_widgets.js";
import { icon } from "./ng_icons.js";

export function hideNative(node, names) {
  for (const widget of node.widgets || []) {
    if (!names.includes(widget.name)) continue;
    const input = node.inputs?.find((entry) => entry.widget?.name === widget.name);
    if (input?.link != null) continue;
    widget.hidden = true;
    widget.options ||= {};
    widget.options.hidden = true;
    widget.computeSize = () => [0, -4];
    widget.computeLayoutSize = () => ({minHeight:0,maxHeight:0,minWidth:0});
    widget.draw = () => {};
    widget.drawWidget = () => {};
    if (widget.element) widget.element.style.display = "none";
  }
  // Preserve real model/context ports and any connected widget inputs.
  for (let i = (node.inputs?.length || 0) - 1; i >= 0; i--) {
    const input = node.inputs[i];
    if (names.includes(input.widget?.name) && input.link == null) node.removeInput(i);
  }
}

export function control(node, name, labelText, options = {}) {
  const widget = node.widgets?.find((entry) => entry.name === name);
  const label = element("label", options.tile ? "ng-field ng-field-tile" : "ng-field");
  const choices = options.choices || widget?.options?.values;
  // The help marker is a button so keyboard and touch reach it too. It starts hidden and is filled
  // in from the registry, because the same field is explained differently for Ollama and for
  // Claude - a seed is a real control on one and absent on the other.
  const marker = element("button", "ng-field-help", "?");
  marker.type = "button";
  marker.hidden = true;
  if (options.tile) {
    const head = element("span", "ng-field-head");
    head.append(icon(options.icon, "ng-field-icon"), element("span", "ng-field-label", labelText), marker);
    label.append(head);
  } else label.append(element("span", "ng-field-label", labelText), marker);
  const field = element(options.multiline ? "textarea" : Array.isArray(choices) ? "select" : "input");
  field.setAttribute("aria-label", labelText);
  if (Array.isArray(choices) && !options.multiline) {
    for (const value of choices) {
      const option = element("option", "", String(value).replaceAll("_", " "));
      option.value = value; field.append(option);
    }
  } else if (options.boolean) {
    field.type = "checkbox";
  } else if (options.number) {
    field.type = "number"; field.step = options.step || "any";
    if (widget?.options?.min !== undefined) field.min = widget.options.min;
    if (widget?.options?.max !== undefined) field.max = widget.options.max;
  }
  const sync = () => {
    if (Array.isArray(choices) && !options.multiline && widget?.value && !Array.from(field.children).some((option) => option.value === widget.value)) {
      const option = element("option", "", String(widget.value)); option.value = widget.value; field.append(option);
    }
    if (options.boolean) field.checked = !!widget?.value;
    else if (document.activeElement !== field) field.value = widget?.value ?? "";
    field.disabled = !widget || node.inputs?.some((entry) => entry.widget?.name === name && entry.link != null);
  };
  sync();
  field.oninput = () => {
    if (!widget || field.disabled) return;
    if (options.number && (field.value === "" || !field.checkValidity())) return;
    widget.value = options.boolean ? field.checked : options.number ? Number(field.value) : field.value;
    widget.callback?.(widget.value);
    node.graph?.change(); node.setDirtyCanvas?.(true, true);
  };
  const original = widget?.callback;
  if (widget) widget.callback = function (...args) { const result = original?.apply(this, args); sync(); return result; };
  label.append(field);
  // `name` lets the panel fill in the help from the registry without repeating which widget a field
  // belongs to. The marker stays hidden while there is nothing to say, so a field the chosen
  // provider does not have does not carry an empty "?" around.
  const setHelp = (text) => {
    marker.hidden = !text;
    if (text) { marker.title = text; marker.setAttribute("aria-label", text); }
  };
  return { label, field, sync, name, setHelp };
}

// The API key is deliberately NOT a control() over a widget: every widget is serialised into each
// saved workflow, and a key in a workflow is a key on disk and in every export. This control has no
// widget behind it and nothing to write back - the secret goes to /ng/keys, and the input is
// emptied again the moment it was accepted.
export function secretControl(labelText, options = {}) {
  const label = element("div", "ng-field ng-field-tile ng-field-secret");
  const head = element("span", "ng-field-head");
  head.append(icon(options.icon || "key", "ng-field-icon"), element("span", "ng-field-label", labelText));
  const field = element("input", "ng-secret");
  field.type = "password";
  field.autocomplete = "new-password";
  field.spellcheck = false;
  field.setAttribute("aria-label", labelText);
  const actions = element("div", "ng-field-actions");
  const status = element("small", "ng-field-status");
  label.append(head, field, actions, status);
  return {
    label, field, actions, status,
    // The server never sends a stored key back, not even partially, so the strongest true statement
    // the panel can make is "a key is stored for this provider".
    setState(state, text) {
      status.textContent = text || "";
      status.dataset.state = state || "";
      field.classList.toggle("ng-secret-stored", state === "stored");
    },
    clear() { field.value = ""; },
  };
}

export function actionButton(text, onClick, options = {}) {
  const button = element("button", "ng-action " + (options.className || ""));
  button.type = "button";
  if (options.icon) button.append(icon(options.icon, "ng-action-icon"));
  button.append(element("span", "ng-action-text", text));
  if (options.title) { button.title = options.title; button.setAttribute("aria-label", options.title); }
  button.addEventListener("click", (event) => { event.preventDefault(); onClick(button); });
  return button;
}

export function section(title, className = "", options = {}) {
  const root = element("section", "ng-section " + className);
  const caption = element("h3", "ng-section-title", title);
  if (!options.icon) { root.append(caption); return root; }
  // The heading becomes icon + caption + help so the section explains itself without a tooltip the
  // panel has to keep in sync. The help marker is a button, so keyboard and touch reach it too.
  const head = element("div", "ng-section-head");
  head.append(icon(options.icon, "ng-section-icon"), caption);
  if (options.help) {
    const help = element("button", "ng-section-help", "?");
    help.type = "button";
    help.title = options.help;
    help.setAttribute("aria-label", options.help);
    head.append(help);
  }
  root.append(head);
  return root;
}
