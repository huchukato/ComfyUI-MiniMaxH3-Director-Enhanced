"""BUG-018: ein gespeichertes Preset darf die Identitaet der Context-Karte nicht veraendern.

widget_values() schreibt context_id = item.id. Das Item bekommt seine ID aber erst, wenn
keine context_id im Widget stand (context_build.slug). Ein Preset, das von einer Karte ohne
ID gespeichert wurde, traegt beim Laden also eine erfundene ID (image_mage) zurueck und
macht die Karte zu einem anderen Objekt: alte Shot-Bindungen zeigen danach ins Leere.
Kein Fix, nur Beleg.
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _pack import module  # noqa: E402

context_build = module("ng.core.context_build")
core_presets = module("ng.core.presets")
context_mod = module("ng.core.context")

WIDGETS = {"image": "mage.png", "name": "Mage", "content": "character", "usage": "reference",
           "preserve": "high", "description": "A mage"}


class PresetIdentity(unittest.TestCase):
    def preset_from(self, widgets):
        item = context_build.item_from_widgets("image", widgets)
        return item, core_presets.ContextPreset.from_dict(
            {"schema_version": 1, "name": "Meine Mage", "item": item.to_dict()})

    def test_control_a_card_with_an_explicit_id_keeps_it(self):
        item, preset = self.preset_from({**WIDGETS, "context_id": "ctx_abc123"})
        self.assertEqual(item.id, "ctx_abc123")
        restored = core_presets.widget_values(preset.item)
        self.assertEqual(restored["context_id"], "ctx_abc123")

    def test_bug_018_saving_a_card_without_an_id_invents_one_on_load(self):
        # Die Karte bekommt beim ersten Speichern eine abgeleitete ID.
        item, _ = self.preset_from(WIDGETS)
        self.assertEqual(item.id, "image_mage")

        # Das Preset traegt diese abgeleitete ID zurueck in die Karte und macht sie zu einem
        # anderen Objekt als jede bestehende Bindung erwartet.
        _, preset = self.preset_from(WIDGETS)
        restored = core_presets.widget_values(preset.item)
        self.assertEqual(restored["context_id"], "",
                         "a preset must not write an invented context_id back into the card")

    def test_control_two_cards_without_ids_collide_and_are_reported_loudly(self):
        # Zwei Karten mit demselben Namen bekommen dieselbe abgeleitete ID. Das ist kein stiller
        # Fehler: require_unique() beim Verbinden benennt ihn. Dieser Test haelt fest, dass die
        # ID aus Name und Medium entsteht - nicht aus dem Inhalt.
        first, _ = self.preset_from(WIDGETS)
        second, _ = self.preset_from({**WIDGETS, "content": "outfit"})
        self.assertEqual(first.id, second.id)
        items = (first, second)
        with self.assertRaises(Exception) as caught:
            context_mod.require_unique(items)
        self.assertIn("image_mage", str(caught.exception))


if __name__ == "__main__":
    unittest.main()