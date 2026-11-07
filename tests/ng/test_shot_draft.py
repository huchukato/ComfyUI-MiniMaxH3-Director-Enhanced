"""ID-addressed AI drafts must remain separate and preserve user-owned shot data."""
import copy
import json
import unittest
from unittest.mock import AsyncMock, patch
from _pack import module, comfy_available, stub_prompt_server

direction = module("ng.core.auto_direct")


def document():
    return {"format": "h3-director-shots", "schema_version": 1, "shots": [
        {"id": "a", "start": 0, "end": 4, "text": "Walk.\n@Alice says: Original words.",
         "media": [{"schema_version": 1, "context_id": "alice", "role": "reference"}],
         "spoken": [], "locked_fields": ["timing"], "draft": {"old": "retained"}},
        {"id": "b", "start": 4, "end": 8, "text": "Wait.", "media": [],
         "spoken": [{"schema_version": 1, "speaker_id": "alice", "text": "Mein Dialog."}], "locked_fields": []}]}


CONTEXTS = [{"media": "image", "widgets": {"context_id": "alice", "name": "Alice", "image": "private.png", "usage": "reference"}}]


def answer(**changes):
    return {"format": "h3-director-draft", "schema_version": 1,
            "patches": [{"shot_id": "a", "fields": {"text": "@Alice turns."}}], **changes}


class ShotDraft(unittest.TestCase):
    def parse(self, data):
        return direction.parse_direction(json.dumps(data), 8, CONTEXTS, json.dumps(document()))

    def test_id_draft_preserves_inline_words_without_mutating_source(self):
        source = document(); original = copy.deepcopy(source)
        result = direction.parse_direction(json.dumps(answer()), 8, CONTEXTS, json.dumps(source))
        self.assertEqual(source, original)
        self.assertEqual(result["patches"][0]["shot_id"], "a")
        self.assertEqual(result["patches"][0]["fields"]["text"], "@Alice turns.\n@Alice says: Original words.")
        self.assertNotIn("shots", result)

    def test_prompt_sends_existing_ids_bindings_locks_without_files(self):
        prompt = direction.direction_prompt("She walks.", 8, CONTEXTS, json.dumps(document()))
        for value in ("h3-director-draft", "shot_id", "alice", "timing", "Original words.", "Mein Dialog."):
            self.assertIn(value, prompt)
        self.assertNotIn("private.png", prompt)
        self.assertNotIn('"soundscape":"optional"', prompt)
        self.assertNotIn('"music":"optional"', prompt)

    def test_unknown_duplicate_ids_fields_and_replacement_are_rejected(self):
        bad = [answer(patches=[{"shot_id": "unknown", "fields": {"text": "x"}}]),
               answer(patches=answer()["patches"] * 2), answer(patches=[{"shot_id": "a", "fields": {"id": "new"}}]),
               answer(patches=[{"shot_id": "b", "fields": {"text": "Turn.", "locked_fields": []}}]),
               {"shots": [{"start_s": 0, "end_s": 8, "action": "Replacement"}]}]
        for data in bad:
            with self.subTest(data=data), self.assertRaises(ValueError): self.parse(data)

    def test_shot_times_stay_the_users_and_the_text_still_comes(self):
        result = self.parse(answer(patches=[{"shot_id": "b", "fields": {"text": "0–2s: A wide shot. 2–4s: A close-up.",
                                                                       "timing": {"start": 3, "end": 8}}}]))
        self.assertEqual(result["patches"], [{"shot_id": "b", "fields": {"text": "0–2s: A wide shot. 2–4s: A close-up."}}])
        self.assertEqual(result["dropped"], ["timing of b: shot times stay as set"])
        prompt = direction.direction_prompt("She walks.", 8, CONTEXTS, json.dumps(document()))
        self.assertIn("never propose timing", prompt)
        self.assertNotIn('"write_as_beats"', prompt, "4 s shots need no beats")

    def test_one_shots_fields_sent_as_two_patches_are_one_patch(self):
        # qwen3.5:9b sent shot b's text and its new line as two patches with the same ID (2026-10-13).
        spoken = document()["shots"][1]["spoken"] + [{"schema_version": 1, "speaker_id": "", "text": "New line."}]
        result = self.parse(answer(patches=[{"shot_id": "b", "fields": {"text": "She waits."}},
                                            {"shot_id": "b", "fields": {"spoken": spoken}}]))
        self.assertEqual(len(result["patches"]), 1)
        self.assertEqual(set(result["patches"][0]["fields"]), {"text", "spoken"})

    def test_a_long_shot_is_given_the_beats_of_its_own_length(self):
        long = document()
        long["shots"][1].update(start=4, end=14)
        long["shots"][0]["end"] = 4
        long["shots"].append(dict(long["shots"][1], id="c", start=14, end=26, locked_fields=["text"]))
        prompt = direction.direction_prompt("She walks.", 26, CONTEXTS, json.dumps(long))
        self.assertIn('"write_as_beats": "0–5s, 5–10s"', prompt)
        self.assertEqual(prompt.count('"write_as_beats"'), 1, "a shot whose text is locked gets none")
        share = module("ng.core.shot_share")
        self.assertEqual([share.beat_marks(s) for s in (2.5, 5, 7.5, 12)], ["", "", "0–3.8s, 3.8–7.5s", "0–4s, 4–8s, 8–12s"])

    def test_invalid_media_and_speakers_are_rejected(self):
        for field, value in [("media", [{"schema_version": 1, "context_id": "missing"}]),
                             ("media", [{"schema_version": 1, "context_id": "alice", "role": "copy"}]),
                             ("spoken", [{"schema_version": 1, "speaker_id": "missing", "text": "x"}])]:
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.parse(answer(patches=[{"shot_id": "b", "fields": {field: value}}]))

    def test_existing_structured_dialogue_cannot_be_rewritten_or_removed(self):
        for spoken in ([], [{"schema_version": 1, "speaker_id": "alice", "text": "Rewritten."}]):
            with self.assertRaises(ValueError): self.parse(answer(patches=[{"shot_id": "b", "fields": {"spoken": spoken}}]))
        spoken = document()["shots"][1]["spoken"] + [{"schema_version": 1, "speaker_id": "", "text": "New line."}]
        result = self.parse(answer(patches=[{"shot_id": "b", "fields": {"spoken": spoken}}]))
        self.assertEqual(result["patches"][0]["fields"]["spoken"][0]["text"], "Mein Dialog.")

    def test_a_bad_extra_field_is_dropped_with_its_reason_and_the_text_stays(self):
        # Real gemma answer to "AI: improve text": a good text plus a spoken line without schema_version.
        result = self.parse(answer(patches=[{"shot_id": "a", "fields": {"text": "@Alice turns slowly.", "spoken": [{"speaker_id": "", "text": "Hi"}]}}]))
        self.assertEqual(result["patches"], [{"shot_id": "a", "fields": {"text": "@Alice turns slowly.\n@Alice says: Original words."}}])
        self.assertEqual(len(result["dropped"]), 1)
        self.assertTrue(result["dropped"][0].startswith("spoken of a: "))
        with self.assertRaisesRegex(ValueError, "no usable changes: spoken of a"):
            self.parse(answer(patches=[{"shot_id": "a", "fields": {"spoken": [{"speaker_id": "", "text": "Hi"}]}}]))

    def test_legacy_shots_receive_the_existing_stable_ids(self):
        text = "0-4: Walk.\n@Alice says: Hello.\n4-8: Wait."
        data = answer(patches=[{"shot_id": "legacy-shot-1", "fields": {"text": "@Alice turns."}}])
        result = direction.parse_direction(json.dumps(data), 8, CONTEXTS, text)
        self.assertIn("@Alice says: Hello.", result["patches"][0]["fields"]["text"])

    def test_existing_shots_do_not_require_a_second_idea_text(self):
        self.assertIn("Existing Shots", direction.direction_prompt("", 8, CONTEXTS, json.dumps(document())))
        with self.assertRaises(ValueError): direction.direction_prompt("", 8, [])

    def test_non_json_model_output_has_an_actionable_error(self):
        with self.assertRaisesRegex(ValueError, "generative model"):
            direction.parse_direction("," * 1536, 8, CONTEXTS, json.dumps(document()))


@unittest.skipUnless(comfy_available(), "ComfyUI is not importable")
class Transports(unittest.IsolatedAsyncioTestCase):
    async def test_http_and_native_return_the_same_validated_id_draft(self):
        stub_prompt_server()
        native, http = module("ng.adapters.native_ai"), module("ng.adapters.auto_direct")
        payload = {"director": {"idea": "Walk.", "project_seconds": 8, "shots": json.dumps(document())},
                   "contexts": CONTEXTS, "provider": {"schema_version": 2, "provider": "ollama", "model": "fixture"}}
        raw = json.dumps(answer())
        with patch.object(http.legacy, "vlm_generate", new=AsyncMock(return_value=raw)):
            result = await http.direct(payload)
        self.assertEqual(result, native.parse_result(raw, "direct", json.dumps(payload)))
        self.assertEqual(result["format"], "h3-director-draft")


if __name__ == "__main__": unittest.main()
