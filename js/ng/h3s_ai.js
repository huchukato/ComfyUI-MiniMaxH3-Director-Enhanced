// The Studio's two AI actions over the existing /ng/direct route: split the Prompt into shots, and
// suggest a better text per shot. Nothing changes until the user presses Accept.
import { aiAction } from "./ng_ai_request.js";
import { connectedProvider, readContexts } from "./ng_read.js";
import { values } from "./ng_widgets.js";
import { readProject, writeProject, clipToFit } from "./h3s_model.js";

// A failed or empty answer stays on screen until it is dismissed; the user may have scrolled away meanwhile.
function failure(error, provider) {
  if (error.message === "AI action cancelled.") return { text: "AI cancelled, nothing changed.", error: false };
  const slow = /did not answer within/i.test(error.message) ? ` The AI Loader's Timeout is ${provider.timeout_seconds || 120} s; a large model may need more.` : "";
  return { text: `AI failed: ${error.message}${slow}`, error: true };
}

function buildFailure(error, provider, undo) {
  const notice = failure(error, provider);
  if (!undo) return notice;
  const text = error.message === "AI action cancelled." ? "AI cancelled." : notice.text;
  return { ...notice, text: text + " The plan was applied; Undo restores the previous project.", undo };
}

// What an answer was asked about. If any of it changed while the AI worked, the answer no longer fits and is dropped.
// Shots are left out for text proposals: their own shot's text is checked on Accept, and accepting one text must not
// invalidate the proposals for the other shots.
export function basis(node, withShots = true) {
  const now = values(node);
  return JSON.stringify([now.idea, withShots ? now.shots : null, now.project_seconds, now.mode, now.soundscape, now.music,
    readContexts(node), connectedProvider(node)]);
}

// The dialogue the user wrote, inline ("@Mage says: ...") or as spoken lines: a split starts from the prompt, so these
// are sent along and take the place of whatever the AI makes the same speaker say.
export function ownLines(S) {
  const name = (id) => (id ? `@${S.byId?.get(id)?.name || id}` : "Narrator");
  return S.shots.flatMap((shot) => [...(shot.text || "").split("\n").filter((line) => /^\s*@?[\p{L}\p{N}_-]+\s+says:/iu.test(line)).map((line) => line.trim()),
    ...(shot.spoken || []).filter((line) => line.text?.trim()).map((line) => `${name(line.speaker_id)} says: ${line.text.trim()}`)]).join("\n");
}

export function studioAI(S, app, api, done) {
  let controller = null, serial = 0, buildUndo = null;

  async function run(kind, shots, keep = "") {
    const provider = connectedProvider(S.node);
    if (!provider || S.busy) return null;
    controller = new AbortController();
    const mine = ++serial;
    S.busy = kind; S.aiStarted = Date.now(); S.aiTimeout = provider.timeout_seconds || 120; S.notice = null; done();
    const before = basis(S.node);
    try {
      // A split starts from the Prompt, but takes the audio lanes along: the plan then knows when the song sings each line.
      const payload = { director: { ...values(S.node), shots: writeProject({ shots: shots || [], audio: S.audio, lanes: S.lanes, control: S.control }) },
        contexts: readContexts(S.node), provider, mode: "auto", keep };
      const data = await aiAction(app, api, "direct", payload, controller.signal);
      if (mine !== serial) return null;
      if (basis(S.node) !== before) {
        S.notice = { text: "The project changed while the AI was working, so its answer no longer fits and was discarded. Ask again.", error: false };
        return null;
      }
      return data.suggestion;
    } catch (error) {
      if (mine === serial) S.notice = failure(error, provider);
      return null;
    } finally {
      if (mine === serial) { S.busy = ""; controller = null; done(); }
    }
  }

  return {
    async split() {
      const suggestion = await run("split", null, ownLines(S));
      if (!suggestion) return;
      const proposed = clipToFit(readProject(suggestion.shots || "").shots, S.values.project_seconds);
      S.ghosts = proposed.map(({ start, end, text, spoken }) => ({ start, end, text, spoken: spoken || [] }));
      S.ghostSound = { soundscape: suggestion.soundscape || "", music: suggestion.music || "", look: suggestion.look || "" };
      S.ghostBasis = basis(S.node, true);
      if (!S.ghosts.length) S.notice = { text: "The AI answered, but proposed no shots. Try again or split by hand.", error: true };
      else {
        const notes = [suggestion.kept_dialogue?.length && `your own dialogue (${suggestion.kept_dialogue.length} line${suggestion.kept_dialogue.length === 1 ? "" : "s"}) replaces what the AI wrote for those speakers`,
          suggestion.timing_adjusted && "its shot times were laid end to end over the whole project",
          suggestion.unknown_mentions?.length && `${suggestion.unknown_mentions.map((name) => "@" + name).join(", ")} is no Content here and stays a plain word`];
        const said = notes.filter(Boolean).join("; ");
        if (said) S.notice = { text: `${said[0].toUpperCase()}${said.slice(1)}. Check the proposal before you accept it.`, error: false };
      }
      done();
    },
    async suggest(shotId) {
      const suggestion = await run("suggest", S.shots);
      if (!suggestion) return;
      // A stored text lock (locked_fields) still protects a shot from AI text, even without a lock control in the Studio.
      const open = new Map(S.shots.filter((shot) => !(shot.locked_fields || []).includes("text")).map((shot) => [shot.id, shot.text]));
      const texts = (suggestion.patches || []).filter((patch) => open.has(patch.shot_id) && typeof patch.fields?.text === "string" && patch.fields.text.trim());
      for (const patch of texts) { S.suggestions[patch.shot_id] = patch.fields.text.trim(); (S.suggestionBase ||= {})[patch.shot_id] = open.get(patch.shot_id); }
      S.suggestionBasis = basis(S.node, false);
      if (!S.suggestions[shotId]) S.notice = { text: "The AI answered, but suggested no new text for this shot.", error: true };
      done();
    },
    // One render part written out by the AI from its compiled prompt; the server has checked it, Accept stores it.
    async writePart(index) {
      const provider = connectedProvider(S.node);
      if (!provider || S.busy) return false;
      controller = new AbortController();
      const mine = ++serial;
      S.busy = `write${index}`; S.aiStarted = Date.now(); S.aiTimeout = provider.timeout_seconds || 120; S.notice = null; done();
      try {
        const data = await aiAction(app, api, "write", { director: values(S.node), contexts: readContexts(S.node), provider, part: index, quick: S.quick }, controller.signal);
        if (mine !== serial) return false;
        S.partDrafts[index] = data.suggestion;
        return true;
      } catch (error) {
        if (mine === serial) S.notice = failure(error, provider);
        return false;
      } finally {
        if (mine === serial) { S.busy = ""; controller = null; done(); }
      }
    },
    // Make H3 prompt: plan the whole video, put the plan in (apply returns the Studio's undo), then write
    // every part out and keep each checked answer. A refused or unchanged part keeps its compiled prompt.
    async build(apply, replan, keep, describe) {
      const provider = connectedProvider(S.node);
      if (!provider || S.busy) return null;
      controller = new AbortController();
      const mine = ++serial, signal = controller.signal;
      buildUndo = null;
      const step = (text) => { S.buildStep = text; S.aiStarted = Date.now(); done(); };
      S.busy = "build"; S.aiTimeout = provider.timeout_seconds || 120; S.notice = null; step("Planning the shots …");
      try {
        const director = { ...values(S.node), shots: writeProject({ shots: [], audio: S.audio, lanes: S.lanes, control: S.control }) };
        const ask = () => aiAction(app, api, "build", { director, contexts: readContexts(S.node), provider, quick: S.quick }, signal);
        // A small model sometimes answers with broken JSON; one more try is cheaper than sending the user back.
        const plan = await ask().catch((error) => { if (/JSON/.test(error.message) && mine === serial) return ask(); throw error; });
        if (mine !== serial) return null;
        buildUndo = apply(plan.suggestion);
        // A picture still without a description (the plan's answer may leave "describe" out) is analyzed like ✦ Analyze.
        await describe(async (extra) => {
          if (mine !== serial) throw new Error("AI action cancelled.");
          step("Describing the pictures …");
          const data = await aiAction(app, api, "analyze", { ...extra, provider }, signal);
          if (mine !== serial) throw new Error("AI action cancelled.");
          return data;
        });
        if (mine !== serial) return null;
        const view = await replan();
        if (mine !== serial) return null;
        const result = { parts: view.chunks.length, written: 0, refused: 0, unchanged: 0, unseen: plan.suggestion.unseen_pictures || [] };
        for (const chunk of view.chunks) {
          step(view.chunks.length > 1 ? `Writing part ${chunk.index + 1} of ${view.chunks.length} …` : "Writing the prompt …");
          const write = () => aiAction(app, api, "write", { director: values(S.node), contexts: readContexts(S.node), provider,
            part: chunk.index, quick: S.quick }, signal);
          let draft = (await write()).suggestion;
          if (mine !== serial) return null;
          // A refused or unchanged part gets a second try (qwen3.5:9b: about one part in five on the first).
          if (draft.problems.length || draft.unchanged) { draft = (await write()).suggestion; if (mine !== serial) return null; }
          if (draft.problems.length) result.refused++;
          else if (draft.unchanged || draft.key !== chunk.prompt_key) result.unchanged++;
          else { keep(chunk.index, draft); result.written++; }
        }
        await replan(); // the parts' own prompts are in now; without this the drawer showed "outdated" until the next plan
        return mine === serial ? result : null;
      } catch (error) {
        if (mine === serial) S.notice = buildFailure(error, provider, buildUndo);
        return null;
      } finally {
        if (mine === serial) { S.busy = ""; S.buildStep = ""; controller = null; buildUndo = null; done(); }
      }
    },
    cancel() { serial++; controller?.abort(); controller = null; S.busy = ""; S.buildStep = "";
      S.notice = buildFailure(new Error("AI action cancelled."), connectedProvider(S.node) || {}, buildUndo); buildUndo = null; done(); },
    dispose() { serial++; controller?.abort(); },
  };
}
