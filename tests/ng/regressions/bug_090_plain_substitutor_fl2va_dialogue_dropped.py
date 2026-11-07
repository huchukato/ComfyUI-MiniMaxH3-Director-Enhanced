r"""Regression test for BUG-090: _plain_substitutor in FL2VA mode populates voices exclusively from reference subjects, which is empty in FL2VA, dropping all spoken dialogue into visual prose without <d> tags or speaker IDs.

Where:
- ng/core/legacy_bridge.py:117-133 (`_plain_substitutor`)
- ng/core/legacy_bridge.py:301-304 (`build_timeline`)
- ng/core/legacy_bridge.py:112-114 (`_tag_substitutor`)
- Downstream impact:
  - minimax_plan.py:866-869 (`DIALOGUE_RE` strictly matches only `@ref\d+`, `@voice(...)`, `@audio\d+`)
  - minimax_plan.py:896-923 (`split_dialogue` returns `events: []` when dialogue regex fails)
  - ng/core/compile.py:110-128 (`compile_chunk` generates no `<d>` tags, no `(S1)` speaker IDs, and dumps dialogue as visual scene prose)
  - docs/NG.md:217 (violates explicit documentation: "In First / last frame mode the prompt carries no @refN tags: mentions become plain names and a spoken line becomes @voice(Name) says:.")

Contrast with:
- docs/NG.md:217:
  "In First / last frame mode the prompt carries no @refN tags: mentions become plain names and a spoken line becomes @voice(Name) says:."
- ng/core/legacy_bridge.py:118 (docstring of _plain_substitutor):
  "Without reference slots there is no <Subject N> to point at: a mention is the name, a spoken line names its voice."
- ng/core/legacy_bridge.py:127-130:
  "# '@Name [German] says: ...' is a spoken line; a sentence before the first colon ... is prose"
  "dialogue = colon and not re.search(r'[.!?]', bare) and plan.DIALOGUE_RE.match(spoken.strip())"
- Ref2VA mode with reference Subject card:
  When a card is a reference Subject image (`usage: ('reference',)`), `_tag_substitutor` converts `@Hero` to `@ref1`,
  `DIALOGUE_RE` recognizes it, and `plan.plan_timeline` outputs `<Subject 1> (S1) says, <d>[English] Stand back!</d>`.

User workflow:
1. In ComfyUI Director Studio (or via API / NGH3Director), the user creates a project in First/last frame mode (FL2VA).
   The character is defined using a first-frame image card (e.g. "First frame: Alice", `usage: ("first_frame",)`).
2. The user specifies dialogue for the character:
   - In Director Prompt (`idea`): `@Alice [English] says: Hello from wonderland!`
   - Or in timed text (`shots_text`): `0-5: @Alice [English] says: Hello from wonderland!`
   - Or in shot text (`shot.text`): `@Alice says: Hello from wonderland!`
3. The user compiles the project via `compile_chunk` / `plan_project` for rendering with MiniMax H3.

What happens (Ist):
1. In `ng/core/legacy_bridge.py:301-304`:
   `subjects = [i for i in context.by_media("image") if "reference" in i.effective_usage and i.source and not i.subject_ids]`
   In FL2VA mode, image cards have `usage: ("first_frame",)` or `("last_frame",)`.
   None have `"reference" in i.effective_usage`.
   Therefore, `subjects` evaluates to `[]`.
2. `legacy_bridge.py:304` calls:
   `substitute = _plain_substitutor(subjects, context)` with `subjects = []`.
3. Inside `_plain_substitutor` (lines 119-120):
   `names, voices = {s.name: s.name for s in subjects}, {s.name: "@voice(%s)" % s.name for s in subjects}`
   Because `subjects` is empty, `voices` is empty `{}`!
4. When `substitute(text)` processes `@Alice [English] says: Hello from wonderland!`:
   `replace_mentions(head, voices, known)` does nothing because `Alice` is not in `voices`.
   `head` remains `@Alice [English] says`.
   `plan.DIALOGUE_RE.match(spoken.strip())` evaluates to `None` because `DIALOGUE_RE` requires `@ref\d+`, `@voice(...)`, or `@audio\d+`.
   `dialogue` evaluates to `False`.
   Line 131 falls back to treating the line as plain prose.
5. In `compile_chunk` / `plan.plan_timeline`:
   `split_dialogue` finds no dialogue events (`events: []`).
   No `<d>` tag is generated; no speaker ID `(S1)` is assigned.
   The prompt sent to the video generator dumps the spoken line as visual scene description:
   `integrated_multimodal_description: [Shot 1] Alice, shown in <Picture 1>, [English] says: Hello from wonderland!`
   The character never speaks, and voice synthesis is completely skipped.
6. Similarly, in Ref2VA mode, `_tag_substitutor` only maps reference Subject cards (`slot_items`).
   Spoken lines for non-reference characters (First Frame cards like `@King` or uncarded figures like `@Guard`)
   are never converted to `@voice(...)`, causing them to also be dropped into visual scene prose without speech.

What should happen (Soll):
1. In `_plain_substitutor`, `voices` must include all figure context items in `context.items` (such as First Frame cards):
   `voices = {item.name: "@voice(%s)" % item.name for item in context.items}`.
2. In FL2VA mode, `@Alice [English] says: Hello from wonderland!` must be substituted to `@voice(Alice) [English] says: Hello from wonderland!`.
3. `plan.DIALOGUE_RE` must match the substituted line, producing a dialogue event for `Alice`.
4. The compiled prompt must contain active dialogue tags:
   `Alice (S1) says, <d>[English] Hello from wonderland!</d>`.
5. Non-reference figures in prompt dialogue must be recognized as voice speakers instead of being discarded into visual prose.
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _pack import module  # noqa: E402

bridge = module("ng.core.legacy_bridge")
compile_mod = module("ng.core.compile")
context_mod = module("ng.core.context")
chunks_mod = module("ng.core.chunks")
project_mod = module("ng.core.project")
plan_mod = module("minimax_plan")


class TestBug090PlainSubstitutorFL2VADialogue(unittest.TestCase):
    """Regression test suite for BUG-090."""

    # -------------------------------------------------------------------------
    # Green Control Tests: Verify expected behavior under supported conditions
    # -------------------------------------------------------------------------

    def test_control_ref2va_reference_subject_dialogue_compiles_d_tag(self):
        """Control: In Ref2VA mode, dialogue for a reference Subject image compiles to <d> tag with (S1)."""
        hero = context_mod.ContextItem(id="img_hero", name="Hero", media="image", source="hero.png", usage=("reference",))
        ctx = context_mod.DirectorContext(
            project_seconds=5.0,
            mode="ref2va",
            idea="@Hero [English] says: Stand back and let me handle this!",
            items=(hero,),
        )
        proj = project_mod.plan_project(ctx, 10.0, chunks_mod.ContinuityPlan(mode="none"))
        compiled = proj.compiled[0]

        self.assertEqual(compiled.mode, "ref2va")
        self.assertIn("<d>[English] Stand back and let me handle this!</d>", compiled.prompt)
        self.assertIn("(S1)", compiled.prompt)
        self.assertIn("<Subject 1>", compiled.prompt)

    def test_control_fl2va_explicit_voice_syntax_compiles_d_tag(self):
        """Control: In FL2VA mode, if dialogue is manually written as @voice(Alice), DIALOGUE_RE recognizes it."""
        alice = context_mod.ContextItem(id="f1", name="Alice", media="image", source="alice.png", usage=("first_frame",))
        ctx = context_mod.DirectorContext(
            project_seconds=5.0,
            mode="fl2va",
            idea="@voice(Alice) [English] says: The adventure begins!",
            items=(alice,),
        )
        proj = project_mod.plan_project(ctx, 10.0, chunks_mod.ContinuityPlan(mode="none"))
        compiled = proj.compiled[0]

        self.assertEqual(compiled.mode, "fl2va")
        self.assertIn("<d>[English] The adventure begins!</d>", compiled.prompt)
        self.assertIn("(S1)", compiled.prompt)
        self.assertIn("Alice (S1) says,", compiled.prompt)

    def test_control_fl2va_structured_shot_spoken_compiles_d_tag(self):
        """Control: In FL2VA mode, dialogue placed in structured shot.spoken generates <d> tags via spoken_text."""
        doc = {
            "format": "h3-director-shots",
            "schema_version": 1,
            "shots": [
                {
                    "id": "s1", "start": 0.0, "end": 5.0, "text": "Alice looks forward.", "media": [],
                    "spoken": [
                        {"schema_version": 1, "text": "I am ready.", "speaker_id": "f1", "voice": "Alice", "language": "English", "delivery": "says"}
                    ]
                }
            ]
        }
        alice = context_mod.ContextItem(id="f1", name="Alice", media="image", source="alice.png", usage=("first_frame",))
        ctx = context_mod.DirectorContext(
            project_seconds=5.0,
            mode="fl2va",
            shots_text=json.dumps(doc),
            items=(alice,),
        )
        proj = project_mod.plan_project(ctx, 10.0, chunks_mod.ContinuityPlan(mode="none"))
        compiled = proj.compiled[0]

        self.assertEqual(compiled.mode, "fl2va")
        self.assertIn("<d>[English] I am ready.</d>", compiled.prompt)
        self.assertIn("(S1)", compiled.prompt)

    # -------------------------------------------------------------------------
    # Red Regression Tests: Expose the defect in real unmodified product code
    # -------------------------------------------------------------------------

    def test_defect_1_fl2va_prompt_idea_dialogue_dropped_to_visual_prose(self):
        """Defect: In FL2VA mode, @Alice [English] says: ... in Director Prompt (idea) is not converted to @voice(Alice)

        because _plain_substitutor populates voices only from subjects (which is empty in FL2VA).
        Dialogue is lost from speech synthesis and emitted as visual prose without <d> tags or (S1).
        """
        alice = context_mod.ContextItem(id="f1", name="Alice", media="image", source="alice.png", usage=("first_frame",))
        ctx = context_mod.DirectorContext(
            project_seconds=5.0,
            mode="fl2va",
            idea="@Alice [English] says: Hello from the first frame!",
            items=(alice,),
        )
        proj = project_mod.plan_project(ctx, 10.0, chunks_mod.ContinuityPlan(mode="none"))
        compiled = proj.compiled[0]

        # IST (Defect): The dialogue line is not converted to @voice(Alice) and ends up as plain scene prose:
        # 'integrated_multimodal_description: [Shot 1] Alice, shown in <Picture 1>, [English] says: Hello from the first frame!'
        # SOLL: The prompt must carry real dialogue tags with (S1) and <d> tags:
        # 'Alice (S1) says, <d>[English] Hello from the first frame!</d>'
        self.assertIn("<d>[English] Hello from the first frame!</d>", compiled.prompt,
                      "BUG-090: Dialogue line '@Alice [English] says:' in FL2VA prompt must be compiled into <d> dialogue tag")
        self.assertIn("(S1)", compiled.prompt,
                      "BUG-090: Spoken line in FL2VA must be assigned a speaker ID (S1)")
        self.assertNotIn("Alice, shown in <Picture 1>, [English] says:", compiled.prompt,
                         "BUG-090: Dialogue must not be dumped as visual prose description")

    def test_defect_2_fl2va_timed_text_dialogue_dropped_to_visual_prose(self):
        """Defect: In FL2VA mode, timed text '0-5: @Alice says: ...' in shots_text is not converted to @voice(Alice).

        _plain_substitutor has empty voices, plan.DIALOGUE_RE fails, and the line becomes visual prose.
        """
        alice = context_mod.ContextItem(id="f1", name="Alice", media="image", source="alice.png", usage=("first_frame",))
        ctx = context_mod.DirectorContext(
            project_seconds=5.0,
            mode="fl2va",
            shots_text="0-5: @Alice says: Welcome to our kingdom!",
            items=(alice,),
        )
        proj = project_mod.plan_project(ctx, 10.0, chunks_mod.ContinuityPlan(mode="none"))
        compiled = proj.compiled[0]

        # IST: Emitted as '[Shot 1] Alice, shown in <Picture 1>, says: Welcome to our kingdom!' without <d> tag
        # SOLL: Must compile to '<d>[English] Welcome to our kingdom!</d>' with speaker (S1)
        self.assertIn("<d>[English] Welcome to our kingdom!</d>", compiled.prompt,
                      "BUG-090: Timed-text dialogue in FL2VA must produce a <d> dialogue tag")
        self.assertIn("(S1)", compiled.prompt,
                      "BUG-090: Timed-text dialogue in FL2VA must produce speaker (S1)")

    def test_defect_3_fl2va_shot_text_description_dialogue_dropped(self):
        """Defect: In FL2VA mode, dialogue written in shot.text is not converted to @voice(Alice) by _shot_text.

        _shot_text calls substitute(shot.text). In FL2VA, _plain_substitutor fails to substitute @Alice,
        and split_dialogue treats it as prose.
        """
        doc = {
            "format": "h3-director-shots",
            "schema_version": 1,
            "shots": [
                {
                    "id": "s1", "start": 0.0, "end": 5.0,
                    "text": "The camera pushes in on Alice. @Alice [English] says: We must hurry!",
                    "media": [], "spoken": []
                }
            ]
        }
        alice = context_mod.ContextItem(id="f1", name="Alice", media="image", source="alice.png", usage=("first_frame",))
        ctx = context_mod.DirectorContext(
            project_seconds=5.0,
            mode="fl2va",
            shots_text=json.dumps(doc),
            items=(alice,),
        )
        proj = project_mod.plan_project(ctx, 10.0, chunks_mod.ContinuityPlan(mode="none"))
        compiled = proj.compiled[0]

        # IST: 'The camera pushes in on Alice. Alice, shown in <Picture 1>, [English] says: We must hurry!'
        # SOLL: Must extract dialogue: '<d>[English] We must hurry!</d>'
        self.assertIn("<d>[English] We must hurry!</d>", compiled.prompt,
                      "BUG-090: Dialogue written in shot.text in FL2VA must produce <d> tag")
        self.assertIn("(S1)", compiled.prompt,
                      "BUG-090: Dialogue written in shot.text in FL2VA must assign speaker ID (S1)")

    def test_defect_4_ref2va_first_frame_or_uncarded_dialogue_dropped(self):
        """Defect: In Ref2VA mode, _tag_substitutor only maps reference Subjects, dropping dialogue of First Frame cards and uncarded figures.

        When a project has a reference Subject (@Hero) and a First Frame character (@King) or uncarded figure (@Guard),
        _tag_substitutor only substitutes @Hero to @ref1. Spoken lines for @King and @Guard are left as '@King says:'
        which DIALOGUE_RE rejects, causing King and Guard to never speak.
        """
        hero = context_mod.ContextItem(id="img_hero", name="Hero", media="image", source="hero.png", usage=("reference",))
        king = context_mod.ContextItem(id="img_king", name="King", media="image", source="king.png", usage=("first_frame",))
        ctx = context_mod.DirectorContext(
            project_seconds=5.0,
            mode="ref2va",
            idea="@Hero [English] says: We serve the crown!\n@King [English] says: Defend the city gates!",
            items=(hero, king),
        )
        proj = project_mod.plan_project(ctx, 10.0, chunks_mod.ContinuityPlan(mode="none"))
        compiled = proj.compiled[0]

        # Hero has reference card -> converted to <Subject 1> (S1) says, <d>[English] We serve the crown!</d>
        self.assertIn("<d>[English] We serve the crown!</d>", compiled.prompt)
        self.assertIn("(S1)", compiled.prompt)

        # IST: King dialogue is NOT converted to @voice(King), so it becomes plain prose:
        # 'detailed_description: ... King, shown in <Picture 2>, [English] says: Defend the city gates!'
        # SOLL: King must speak with @voice(King) and receive a dialogue tag <d>[English] Defend the city gates!</d>
        self.assertIn("<d>[English] Defend the city gates!</d>", compiled.prompt,
                      "BUG-090: First-frame character dialogue in Ref2VA must produce a <d> dialogue tag")
        self.assertIn("(S2)", compiled.prompt,
                      "BUG-090: Second speaker must receive speaker ID (S2)")


if __name__ == "__main__":
    unittest.main()
