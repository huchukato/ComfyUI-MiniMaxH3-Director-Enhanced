// The Image card editor's jobs, queued with ComfyUI's own nodes: a SAM 3.1 mask, a structure picture (Canny, Pose, Depth) and
// an H3 character sheet. Results are saved to output/h3-picture-edit and copied into input/h3-picture-edit (/ng/picture/import).
import { request } from "./ng_widgets.js";
import { downstreamNodes } from "./ng_graph.js";
import { comboOptions, runJob } from "./h3b_queue.js";

export const FOLDER = "h3-picture-edit";
const node = (class_type, inputs) => ({ class_type, inputs });

// Measured 2026-10-19 (bild-test J): REF2VA circling the motionless figure once; these frames are front, left side, back,
// right side, three-quarter front and the face.
export const SHEET_FRAMES = [2, 24, 48, 72, 96, 120];
export const SHEET_PROMPT = "<Picture 1> A turnaround of the character from Picture 1: they stand completely still in a relaxed A-pose, "
  + "arms slightly away from the body, on a plain light grey studio floor against a plain light grey background. The same face, hair, "
  + "clothes and props as in Picture 1. The camera circles them once clockwise at the same height and distance, always showing the "
  + "full body: front view at 0 seconds, their left side at 1 second, their back at 2 seconds, their right side at 3 seconds, a "
  + "three-quarter front view at 4 seconds, then it stops on the face in a close-up at 5 seconds. Even soft studio light. Silence.";

// A place sheet (2026-10-21, tavern test): REF2VA keeps the room frozen and empty while the camera turns once on the spot in
// 10 s and ends where it began; these frames are six views around the room, laid out as two rows of three.
export const PLACE_FRAMES = [2, 40, 80, 120, 160, 200];
export const PLACE_PROMPT = "<Picture 1> The place from Picture 1, completely empty and frozen in time: nothing moves, no people. The same "
  + "room, furniture, materials and light as in Picture 1. The camera stands still in the middle of the place at eye height and pans "
  + "right in one slow, even full circle, showing each side in turn, and ends where it began. Silence.";
const SHEETS = { figure: { prompt: SHEET_PROMPT, width: 704, height: 1216, length: 124, frames: SHEET_FRAMES, perRow: 6, name: "sheet" },
  place: { prompt: PLACE_PROMPT, width: 1280, height: 704, length: 243, frames: PLACE_FRAMES, perRow: 3, name: "place_sheet" } };

export function maskGraph(image, prompt, checkpoint, prefix) {
  return {
    load: node("LoadImage", { image }), sam: node("CheckpointLoaderSimple", { ckpt_name: checkpoint }),
    text: node("CLIPTextEncode", { clip: ["sam", 1], text: prompt }),
    detect: node("SAM3_Detect", { model: ["sam", 0], image: ["load", 0], conditioning: ["text", 0], threshold: 0.5, refine_iterations: 2,
      individual_masks: false }),
    picture: node("MaskToImage", { mask: ["detect", 0] }),
    save: node("SaveImage", { images: ["picture", 0], filename_prefix: `${FOLDER}/${prefix}_mask` }),
  };
}

// The same preprocessors as the Video card's control clips (h3c_control_graph.js), on one picture.
export function structureGraph(kind, image, setup, prefix) {
  const graph = { load: node("LoadImage", { image }) };
  let result;
  if (kind === "canny") {
    graph.edges = node("Canny", { image: ["load", 0], low_threshold: 0.4, high_threshold: 0.8 });
    result = ["edges", 0];
  } else if (kind === "pose") {
    graph.detector = node("UNETLoader", { unet_name: setup.detector, weight_dtype: "default" });
    graph.boxes = node("RTDETR_detect", { model: ["detector", 0], image: ["load", 0], threshold: 0.5, class_name: "person", max_detections: 2 });
    graph.pose = node("CheckpointLoaderSimple", { ckpt_name: setup.pose });
    graph.points = node("SDPoseKeypointExtractor", { model: ["pose", 0], vae: ["pose", 2], image: ["load", 0], batch_size: 1, bboxes: ["boxes", 0] });
    graph.draw = node("SDPoseDrawKeypoints", { keypoints: ["points", 0], draw_body: true, draw_hands: true, draw_face: true, draw_feet: true,
      stick_width: 4, face_point_size: 2, score_threshold: 0.5, draw_head: true });
    result = ["draw", 0];
  } else {
    graph.depth = node("LoadMoGeModel", { model_name: setup.depth });
    graph.infer = node("MoGeInference", { moge_model: ["depth", 0], image: ["load", 0], resolution_level: 9, fov_x_degrees: 0, batch_size: 1,
      force_projection: true, apply_mask: true, refine_steps: 3 });
    graph.draw = node("MoGeRender", { moge_geometry: ["infer", 0], output: "depth" });
    result = ["draw", 0];
  }
  graph.save = node("SaveImage", { images: result, filename_prefix: `${FOLDER}/${prefix}_${kind}` });
  return graph;
}

// The H3 files of the Context Connector this card is connected to: the loader at the end of each model, CLIP and VAE link.
export function connectedH3(card) {
  const connector = downstreamNodes(card).find((entry) => entry.comfyClass === "NGContextConnector");
  if (!connector) throw new Error("Connect this card to a Context Connector with the H3 models first.");
  const graph = connector.graph;
  const origin = (from, name) => {
    const input = from?.inputs?.find((entry) => entry.name === name);
    const link = input?.link != null ? graph.links?.[input.link] ?? graph.getLink?.(input.link) : null;
    return link ? graph.getNodeById(link.origin_id) : null;
  };
  const file = (start, widget, through) => {
    for (let current = start, hops = 0; current && hops < 12; current = origin(current, through), hops += 1) {
      const value = current.widgets?.find((entry) => entry.name === widget)?.value;
      if (value) return value;
    }
    return "";
  };
  const ref2va = file(origin(connector, "model_ref2va"), "unet_name", "model");
  const model = ref2va || file(origin(connector, "model_fl2va"), "unet_name", "model");
  const clip = file(origin(connector, "clip"), "clip_name", "clip"), vae = file(origin(connector, "vae"), "vae_name", "vae");
  if (!model || !clip || !vae) throw new Error("The Context Connector needs loaders (UNETLoader, CLIPLoader, VAELoader) for the H3 model, CLIP and video VAE.");
  return { model, clip, vae, ref2va: Boolean(ref2va) };
}

// One H3 run circling the figure (or turning in the place), six frames side by side. With the official ref2v turbo LoRA
// installed: 6 steps (~4 min at 704x1216 on a 16 GB card; a place ~9 min), without it 20.
export async function sheetGraph(api, image, files, prefix, kind = "figure") {
  const sheet = SHEETS[kind];
  const loras = await comboOptions(api, "LoraLoaderModelOnly", "lora_name");
  const turbo = files.ref2va ? loras.find((name) => /ref2v_turbo/i.test(name)) : null;
  const graph = {
    unet: node("UNETLoader", { unet_name: files.model, weight_dtype: "default" }),
    clip: node("CLIPLoader", { clip_name: files.clip, type: "minimax", device: "default" }),
    vae: node("VAELoader", { vae_name: files.vae }),
    load: node("LoadImage", { image }),
    cond: node("MiniMaxH3ReferenceToVideo", { clip: ["clip", 0], vae: ["vae", 0], prompt: sheet.prompt, width: sheet.width, height: sheet.height, length: sheet.length,
      ref_image_size: "match", "ref_images.ref_image_0": ["load", 0] }),
    noise: node("RandomNoise", { noise_seed: Math.floor(Math.random() * 2 ** 32) }),
    sampler: node("KSamplerSelect", { sampler_name: "res_multistep" }),
    decode: node("VAEDecode", { samples: ["sample", 0], vae: ["vae", 0] }),
  };
  const model = turbo ? ["lora", 0] : ["unet", 0];
  if (turbo) graph.lora = node("LoraLoaderModelOnly", { model: ["unet", 0], lora_name: turbo, strength_model: 1.0 });
  graph.guider = node("BasicGuider", { model, conditioning: ["cond", 0] });
  graph.sigmas = node("BasicScheduler", { model, scheduler: "simple", steps: turbo ? 6 : 20, denoise: 1.0 });
  graph.sample = node("SamplerCustomAdvanced", { noise: ["noise", 0], guider: ["guider", 0], sampler: ["sampler", 0], sigmas: ["sigmas", 0],
    latent_image: ["cond", 1] });
  const stitch = (key, first, second, direction) => {
    graph[key] = node("ImageStitch", { image1: first, image2: second, direction, match_image_size: true, spacing_width: 8, spacing_color: "white" });
    return [key, 0];
  };
  let sheetImage = null, row = null;
  sheet.frames.forEach((frame, index) => {
    graph[`v${index}`] = node("ImageFromBatch", { image: ["decode", 0], batch_index: frame, length: 1 });
    row = row ? stitch(`s${index}`, row, [`v${index}`, 0], "right") : [`v${index}`, 0];
    if ((index + 1) % sheet.perRow === 0 || index === sheet.frames.length - 1) {
      sheetImage = sheetImage ? stitch(`r${index}`, sheetImage, row, "down") : row;
      row = null;
    }
  });
  graph.save = node("SaveImage", { images: sheetImage, filename_prefix: `${FOLDER}/${prefix}_${sheet.name}` });
  return graph;
}

// Queue a job, wait for its picture and copy it into the input folder; returns the name an Image card uses.
export async function runPictureJob(api, graph, kind, seconds = 1800) {
  const saved = await runJob(api, graph, "save", seconds);
  return (await request(api, "/ng/picture/import", { ...saved, kind })).source;
}
