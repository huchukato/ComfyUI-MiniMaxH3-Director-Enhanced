# Native AI in H3 Director NG

Use a generative text/vision encoder for assistance. The H3 conditioning CLIP remains a separate connection at the Context Connector.

Open `example_workflows/H3 Director NG - native AI.json` for a minimal Load CLIP → AI Loader → Text Context example. Choose your installed model, then use **✦ Analyze** (on "Use as") on the Text card. This example needs no H3 diffusion model.

1. Add **Load CLIP** and choose an installed generative encoder (`qwen3vl_4b_bf16`, type `stable_diffusion`, is the tested choice).
2. Connect CLIP to **H3 AI Loader** and select **CLIP / Encoder**. Without Load CLIP, choose the installed encoder on the same card; it is loaded only inside the AI job.
3. Connect the AI Loader to a Context card, or to the Context Connector for the Studio and every card behind it.
4. Run the action, read the suggestion, then **Accept** or **Discard**. **Cancel** stops a running action and leaves nothing in the queue.

**Local** (Ollama, LM Studio, llama.cpp, custom) and **API** (OpenAI, Anthropic, Gemini, OpenRouter, custom) use HTTP. API keys are set on the AI Loader and kept in ComfyUI's user settings, never in the workflow. Without a key the request is refused and the card says where to set it.

Connecting or restoring nodes loads no assistant model. Rendering creates no assistant request. Native AI actions queue only the AI Loader's upstream graph and Generate Text; every click runs again (no cached "finished without a suggestion").

Images are bounded for analysis. Video analysis uses three ordered stills from at most the first 15 seconds; it cannot observe full motion. Audio analysis needs a model that accepts audio and **Audio** switched on at the AI Loader; Qwen3-VL cannot hear, and the Ollama transport sends no audio. If Vision or Audio is off, the card says so instead of guessing.

**Choose a generative model.** H3's conditioning encoder (`qwen3vl_32b_minimax_h3_*`, 50 of 64 layers, no output head) cannot write text; an AI job on it stops at once and says so. **Ollama:** check that the model really sees pictures. `huihui_ai/gemma-4-abliterated:e4b` is listed as vision-capable, but in this installation it answered "I cannot see the image" directly and invented descriptions through the card; `qwen3.5:9b` described the same picture correctly. For text, gemma e4b works well.

## What each AI function does (tested 2026-10-05)

| Where | Action | Result | Tested with |
|---|---|---|---|
| Image card | ✦ Analyze → Accept | description, content (e.g. Character), Use as (e.g. Reference) | Qwen3-VL 4B (CLIP and installed), Ollama qwen3.5:9b |
| Video card | ✦ Analyze → Accept | description of the three stills as one, content (e.g. Character motion), Use as | Qwen3-VL 4B, Ollama qwen3.5:9b |
| Audio card | ✦ Analyze | with a model that hears: description, content, Use as; otherwise a clear refusal | refusal checked with Qwen3-VL 4B and Ollama |
| Text card | ✦ Analyze → Accept | Use as (Character, Camera rule, Constraint, …); a Text card has no description field | Qwen3-VL 4B, Ollama gemma e4b |
| Studio | AI: split into shots → Accept | dashed proposal: shots with action, camera and every spoken or sung line as its own entry, plus Look, ambience and music; lines a timed song already sings are not repeated | Ollama qwen3.5:9b (elf song: 3 shots, one per view), earlier format also Qwen3-VL 4B |
| Studio | Prompts per render part → Write with AI → Accept | the part's prompt written out (250-390 words per part); cut times, `<d>` lines, speaker IDs and labels are checked against the plan, small slips are repaired, the rest refused | Ollama qwen3.5:9b, 15 of 15 parts accepted after the repairs (9 by script, 6 in the Studio) |
| Audio card | ⟳ Time with Whisper | the Lyrics' own words get the times Whisper heard; without lines, a transcript | Whisper small (local file), 27 s song in 5-7 s on the GPU |
| Studio | AI: improve text → Accept | a new text for the selected shot | Qwen3-VL 4B, Ollama gemma e4b |
| Enhance Prompt (Legacy) | run the node | global or storyboard block from idea and pictures | Ollama qwen3.5:9b |

What a small model really answers is accepted where it can be: a role the card cannot hold is named and left out, a video answered per still becomes one description, a role written as a key is read as the role, gaps or a short end in a shot split are laid end to end over the project (with a note), an `@word` that is no Content becomes a plain word, and in a proposal with one bad extra field the rest is kept. **Your own dialogue always wins**: in a split, the lines you wrote take the place of what the AI wrote for that speaker. Every such repair is named in the suggestion or the Studio's notice; nothing changes until you accept.

The answers' quality depends on the model. Qwen3-VL 4B follows the format but writes thin texts and sometimes repeats the request instead of answering (the card says so; ask again). Nothing here is a guarantee about other models.

## Several voices for one figure

A figure can own more than one voice card. H3 has one voice slot per subject, so the first card fills that slot and every further card is still sent as an additional reference. Each further card is named in the plan's warnings, so a second take is never silently demoted to "some audio".

The **Speaker / Voice** menu only offers figures – image cards holding a file with the content role character, face or animal. It stores the context ID, not the name, because that is what the compiler resolves. A speaker that is no longer connected stays visible in the menu instead of disappearing from the workflow. When more than one voice card names the same figure, the card says which one fills the slot.

## First Frame and Last Frame

An image card set to **First Frame** opens the clip, one set to **Last Frame** closes it. A first frame only reaches the first chunk and a last frame only the last one, so a long project never sends the guide twice.

H3 takes exactly one image per frame role. If you set two Last Frames, only the first one is sent and the plan names the ones it ignored – the same for two First Frames. An image can be both a Reference and a Last Frame at once; the two roles stay independent.

Frame guides are matched by role, not by file name: two cards pointing at the same picture still each keep their own role. A frame guide also switches the run to the frame model (FL2VA); without it the planner would fall back to a text-only run and ignore the frame.

**Verified by rendering.** With the installed int8 FL2VA model, a 4-second run with a Last Frame ended 2.19 (mean pixel difference, 0 = identical) from the target picture, starting at 37.30; the same run without any context ended at 93.44. The model follows the frame. First Frame, interruption and the continuity-mode comparison have not been measured.
