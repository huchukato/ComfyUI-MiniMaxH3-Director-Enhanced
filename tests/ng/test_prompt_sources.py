"""Each render part says what its prompt is made from (Studio, "Prompts per render part"; user 2026-10-18)."""
import json
import unittest
from dataclasses import replace

from _pack import module

ctx, chunks, project = module("ng.core.context"), module("ng.core.chunks"), module("ng.core.project")


def plan(**changes):
    document = json.dumps({"format": "h3-director-shots", "schema_version": 1, "look": "Dark gothic hall, warm candle light.",
                           "shots": [{"id": "s1", "start": 0, "end": 5, "text": "@Hero walks in.", "media": []}]})
    items = (ctx.ContextItem("hero", "Hero", "image", "hero.png", usage=("reference",), description="A knight in silver armour."),
             ctx.ContextItem("rule", "Look rule", "text", "Always anime CGI.", usage=("style",)))
    context = ctx.DirectorContext(shots_text=document, items=items, project_seconds=5, mode="ref2va", soundscape="Quiet hall.",
                                  music="N/A")
    return project.plan_project(replace(context, **changes), 5, chunks.ContinuityPlan("video_audio")).compiled[0]


class PromptSources(unittest.TestCase):
    def test_a_part_names_its_shot_look_rule_card_and_settings(self):
        sources = plan().sources
        by_kind = {}
        for entry in sources:
            by_kind.setdefault(entry["kind"], []).append(entry)
        self.assertEqual(by_kind["look"][0]["text"], "Dark gothic hall, warm candle light.")
        self.assertEqual((by_kind["shot"][0]["label"], by_kind["shot"][0]["id"]), ("Shot 1", "s1"))
        self.assertIn("walks in", by_kind["shot"][0]["text"])
        self.assertEqual((by_kind["rule"][0]["label"], by_kind["rule"][0]["text"]), ("Look rule", "Always anime CGI."))
        self.assertEqual(by_kind["picture"][0]["label"], "Hero")
        self.assertIn("A knight in silver armour.", by_kind["picture"][0]["text"])
        self.assertEqual([e["label"] for e in by_kind["setting"]], ["Ambience"], "Music N/A is no source")

    def test_a_manual_prompt_is_the_only_source(self):
        sources = plan(prompt_override="My whole prompt.").sources
        self.assertEqual([(e["kind"], e["text"]) for e in sources], [("manual", "My whole prompt.")])

    def test_sources_survive_the_saved_part(self):
        compiled = plan()
        again = module("ng.core.compile").CompiledChunk.from_dict(compiled.to_dict())
        self.assertEqual(again.sources, compiled.sources)


if __name__ == "__main__":
    unittest.main()
