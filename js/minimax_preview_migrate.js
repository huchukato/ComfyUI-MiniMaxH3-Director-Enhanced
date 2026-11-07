// Migrate saved widgets and link slots before native configure consumes positional data.
export const PREVIEW_FIELDS = ["max_resolution", "preview_fps", "jpeg_quality", "every_n_steps", "max_preview_overhead", "suppress_default_preview"];
export const PREVIEW_DEFAULTS = {max_resolution: 768, preview_fps: 24, jpeg_quality: 90,
  every_n_steps: 1, max_preview_overhead: 25, suppress_default_preview: true};
const OLD_FIELDS = ["decode", "preview_target", "max_resolution", "preview_frames", "preview_fps", "webp_quality", "every_n_steps", "max_preview_overhead", "suppress_default_preview", "playback"];
const REMOVED = new Set(["enabled", "decode", "preview_target", "preview_frames", "playback"]);
const TYPES = {model: "MODEL", vae: "VAE", max_resolution: "INT", preview_fps: "FLOAT", jpeg_quality: "INT", every_n_steps: "INT", max_preview_overhead: "INT", suppress_default_preview: "BOOLEAN"};
const isRecord = (value) => value && typeof value === "object" && !Array.isArray(value);
const getLink = (graph, id) => graph?.getLink?.(id) ?? graph?.links?.get?.(id) ?? graph?.links?.[id];
const sameId = (a, b) => String(a) === String(b);

export function previewSchemaDefaults(nodeData) {
  const inputs = {...nodeData?.input?.required, ...nodeData?.input?.optional};
  const defaults = {...PREVIEW_DEFAULTS};
  for (const name of PREVIEW_FIELDS) if (Object.hasOwn(inputs[name]?.[1] || {}, "default")) defaults[name] = inputs[name][1].default;
  return defaults;
}

export function previewValues(info = {}, defaults = PREVIEW_DEFAULTS) {
  const saved = Array.isArray(info.widgets_values) ? [...info.widgets_values] : [];
  const named = isRecord(info.widgets_values_named) ? {...info.widgets_values_named} : {};
  let fields = PREVIEW_FIELDS;
  if (typeof saved[0] === "string") {
    fields = [...OLD_FIELDS];
    // A short-lived release inserted playback immediately after preview_fps.
    if (["true speed", "source fps"].includes(saved[5])) {
      fields.splice(9, 1); fields.splice(5, 0, "playback");
    }
  } else if (typeof saved[0] === "boolean") fields = ["enabled", ...PREVIEW_FIELDS];
  const values = {...defaults, ...Object.fromEntries(saved.slice(0, fields.length).map((value, index) => [fields[index], value])), ...named};
  if (!Object.hasOwn(named, "jpeg_quality") && Object.hasOwn(named, "webp_quality")) values.jpeg_quality = named.webp_quality;
  else if (!Object.hasOwn(named, "jpeg_quality") && fields.includes("webp_quality")) values.jpeg_quality = values.webp_quality ?? defaults.jpeg_quality;
  return Object.fromEntries(PREVIEW_FIELDS.map((name) => [name, values[name] ?? defaults[name]]));
}

function forgetLink(node, id, oldInput) {
  const graph = node.graph, link = getLink(graph, id);
  if (link) {
    const origin = graph?.getNodeById?.(link.origin_id);
    const output = origin?.outputs?.[link.origin_slot];
    if (output?.links) output.links = output.links.filter((entry) => !sameId(entry, id));
    if (graph?.links?.delete) graph.links.delete(id);
    else if (graph?.links) delete graph.links[id];
    origin?.onConnectionsChange?.(2, link.origin_slot, false, link, output);
  }
  oldInput.link = null;
}

function migratePorts(node, info) {
  const old = info.inputs || [];
  const names = ["model", "vae", ...PREVIEW_FIELDS];
  const restored = new Map();
  for (const original of old) {
    const input = {...original, ...(original.widget ? {widget: {...original.widget}} : {})};
    if (REMOVED.has(input.name)) { if (input.link != null) forgetLink(node, input.link, input); continue; }
    const name = input.name === "webp_quality" ? "jpeg_quality" : input.name;
    if (!names.includes(name)) { if (input.link != null) forgetLink(node, input.link, input); continue; }
    input.name = name; input.type = TYPES[name];
    if (name === "vae") delete input.shape;
    if (input.widget) input.widget.name = name;
    if (input.localized_name) input.localized_name = name;
    restored.set(name, input);
  }
  return names.map((name, slot) => {
    // Native configure JSON-clones descriptors. Live slots and widgets own node back-references.
    const input = restored.get(name) ||
      {name, type: TYPES[name], link: null, ...(["model", "vae"].includes(name) ? {} : {widget: {name}})};
    if (input.link != null) {
      const link = getLink(node.graph, input.link);
      if (link) link.target_slot = slot;
    }
    return input;
  });
}

export function migratePreviewInfo(node, info = {}, defaults = PREVIEW_DEFAULTS) {
  const values = previewValues(info, defaults);
  const migrated = {...info, widgets_values: PREVIEW_FIELDS.map((name) => values[name]), widgets_values_named: {...values}};
  if (Array.isArray(info.inputs)) migrated.inputs = migratePorts(node, info);
  return {info: migrated, values};
}

export function configurePreviewType(nodeType, nodeData) {
  const configure = nodeType.prototype.configure;
  if (typeof configure !== "function") return;
  const defaults = previewSchemaDefaults(nodeData);
  nodeType.prototype.configure = function (info, ...args) {
    const migrated = migratePreviewInfo(this, info, defaults);
    const result = configure.call(this, migrated.info, ...args);
    for (const widget of this.widgets || []) if (Object.hasOwn(migrated.values, widget.name)) widget.value = migrated.values[widget.name];
    return result;
  };
}
