// The Storyboard's jobs go through ComfyUI's own queue with ComfyUI's own nodes: a small prompt is queued, its saved picture
// comes back as a layer source. Qwen Image 2.1 is built as its templates build it (UNETLoader -> QwenImage21Cache, CLIPLoader
// qwen3vl_8b type qwen_image, TextEncodeQwenImage21 with the pictures as <image1>, <image2> ..., KSampler 25 steps Euler CFG 1).
import { missingText, modelState, resolveModel } from "./ng_models.js";

export const SUBFOLDER = "h3-storyboard";

export async function comboOptions(api, nodeClass, input) {
  try {
    const info = (await (await api.fetchApi(`/object_info/${nodeClass}`)).json())[nodeClass];
    const spec = info?.input?.required?.[input];
    if (Array.isArray(spec?.[0])) return spec[0];
    if (spec?.[0] === "COMBO") return spec[1]?.options || [];
  } catch { /* the list stays empty; the user is told where it matters */ }
  return [];
}

export function canvasOf(w, h) {
  const c = document.createElement("canvas");
  c.width = Math.round(w); c.height = Math.round(h);
  return c;
}

// Queues the prompt and waits for the picture its node `save` saves: { filename, subfolder, type }.
export async function runJob(api, prompt, save, seconds = 1800) {
  const response = await api.fetchApi("/prompt", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt, client_id: api.clientId }) });
  const queued = await response.json();
  if (!queued.prompt_id) throw new Error(queued.error?.message || JSON.stringify(queued.node_errors || {}).slice(0, 300));
  const deadline = Date.now() + seconds * 1000;
  while (Date.now() < deadline) {
    const entry = (await (await api.fetchApi(`/history/${encodeURIComponent(queued.prompt_id)}`)).json())[queued.prompt_id];
    const failed = (entry?.status?.messages || []).find(([type]) => type === "execution_error");
    if (failed) throw new Error(failed[1].exception_message || "The job failed.");
    if (entry?.status?.status_str === "error") throw new Error("The job failed or was interrupted in ComfyUI's queue.");
    const results = entry?.outputs?.[save]?.images || [];
    if (results.length > 1) throw new Error("The job saved several files. Split the source into shorter clips and generate them separately.");
    const saved = results[0];
    if (saved) return { filename: saved.filename, subfolder: saved.subfolder || "", type: saved.type || "output" };
    if (entry?.status?.completed) throw new Error("The job saved no result.");
    await new Promise((resolve) => setTimeout(resolve, 800));
  }
  throw new Error("The job took too long.");
}

// The Qwen Image 2.1 files (the Storyboard's Models menu choice, else the official names), or an error that names what is missing.
export async function qwenSetup(api, chosen = {}) {
  const purposes = ["qwen_image", "qwen_encoder", "qwen_vae"], state = await modelState(api, purposes);
  const [model, encoder, vae] = purposes.map((purpose) => resolveModel(state, purpose, chosen[purpose]));
  const lacking = purposes.filter((purpose) => !resolveModel(state, purpose, chosen[purpose])).map((purpose) => missingText(state[purpose]));
  if (lacking.length) throw new Error(lacking.join(" "));
  return { model, encoder, vae };
}

// A Qwen Image 2.1 prompt saving to output/h3-storyboard/<prefix>; its save node is "s". images: input names, <image1> first
// (without size, the picture takes image 1's size); opaque drops the alpha channel the VAE decodes, for a background.
export function qwenGraph(setup, { images = [], prompt, size = null, prefix, opaque = false }) {
  const graph = {
    u: { class_type: "UNETLoader", inputs: { unet_name: setup.model, weight_dtype: "default" } },
    q: { class_type: "QwenImage21Cache", inputs: { model: ["u", 0], device: "auto", dtype: "default" } },
    t: { class_type: "CLIPLoader", inputs: { clip_name: setup.encoder, type: "qwen_image", device: "default" } },
    v: { class_type: "VAELoader", inputs: { vae_name: setup.vae } },
    e: { class_type: "TextEncodeQwenImage21", inputs: { clip: ["t", 0], vae: ["v", 0], resolution: 1024, negative_prompt: "", prompt } },
    k: { class_type: "KSampler", inputs: { model: ["q", 0], positive: ["e", 0], negative: ["e", 1], latent_image: size ? ["l", 0] : ["e", 2],
      seed: Math.floor(Math.random() * 2 ** 32), steps: 25, cfg: 1, sampler_name: "euler", scheduler: "simple", denoise: 1 } },
    d: { class_type: "VAEDecode", inputs: { samples: ["k", 0], vae: ["v", 0] } },
    s: { class_type: "SaveImage", inputs: { images: opaque ? ["a", 0] : ["d", 0], filename_prefix: `${SUBFOLDER}/${prefix}` } },
  };
  if (size) graph.l = { class_type: "EmptyLatentImage", inputs: { width: size[0], height: size[1], batch_size: 1 } };
  if (opaque) graph.a = { class_type: "SplitImageWithAlpha", inputs: { image: ["d", 0] } };
  images.forEach((name, i) => {
    graph[`i${i + 1}`] = { class_type: "LoadImage", inputs: { image: name } };
    graph.e.inputs[`images.image_${i + 1}`] = [`i${i + 1}`, 0];
  });
  return graph;
}
