"""Ship ordinary workflows: the product chain with the guide, official model names with download links, consistent links,
and one custom sampling loop that closes its body."""
import json
from pathlib import Path
import re
import unittest

from _pack import REPO, comfy_available

if comfy_available():
    from comfy_execution.validation import validate_loops

FOLDER = Path(REPO) / "example_workflows"
GUIDE = json.loads((Path(REPO) / "js" / "guide" / "guide.json").read_text(encoding="utf8"))
ADVANCED = "H3 Director - 9 Custom sampling (advanced)"


class ProductWorkflows(unittest.TestCase):
    def examples(self):
        for path in sorted(FOLDER.glob("H3 Director - *.json")):
            yield path.stem, json.loads(path.read_text(encoding="utf8"))

    def test_the_numbered_set_is_shipped(self):
        names = [label for label, _ in self.examples()]
        self.assertEqual(len(names), 9)
        self.assertIn(ADVANCED, names)
        self.assertTrue((FOLDER / "MiniMax H3 Director (Legacy).json").exists())

    def test_every_example_has_its_own_id(self):
        # the frontend finds an open workflow by its id; four examples once shared one
        ids = [workflow["id"] for _, workflow in self.examples()]
        self.assertEqual(len(set(ids)), len(ids))

    def test_every_example_saves_under_its_own_name(self):
        # workflows 7 and 8 once saved as H3/characters_and_voice, copied from workflow 2
        prefixes = [node["widgets_values"][0] for _, workflow in self.examples() for node in workflow["nodes"]
                    if node["type"] in ("SaveVideo", "SaveImage")]
        self.assertEqual(len(set(prefixes)), len(prefixes), prefixes)

    def test_every_link_has_matching_native_slots_and_reciprocal_references(self):
        for label, workflow in self.examples():
            nodes = {node["id"]: node for node in workflow["nodes"]}
            links = {link[0]: link for link in workflow["links"]}
            self.assertEqual(len(links), len(workflow["links"]), label)
            for identifier, origin, slot, target, target_slot, type_ in links.values():
                output = nodes[origin]["outputs"][slot]
                input_ = nodes[target]["inputs"][target_slot]
                # the native loop's ports are wildcards ("*") in the frontend; the link carries the real type
                self.assertIn(output["type"], (type_, "*"), label)
                self.assertIn(input_["type"], (type_, "*"), label)
                self.assertEqual(input_["link"], identifier, label)
                self.assertIn(identifier, output["links"], label)

    def test_examples_use_the_product_chain_and_a_guide(self):
        chapters = {chapter["id"] for chapter in GUIDE["chapters"]}
        for label, workflow in self.examples():
            types = [node["type"] for node in workflow["nodes"]]
            for name in ("NGContextConnector", "NGH3Director", "NGGuide"):
                self.assertIn(name, types, label)
            guide = next(node for node in workflow["nodes"] if node["type"] == "NGGuide")
            self.assertIn(guide["widgets_values"][0], chapters, label)
            if label != ADVANCED:
                self.assertIn("NGProjectRender", types, label)
                self.assertTrue({"SaveVideo", "SaveImage"} & set(types), label)

    def test_values_saved_by_name_match_the_values(self):
        # the frontend saves widget values twice; an older copy by name once kept the lighthouse keeper's old shot text
        for label, workflow in self.examples():
            for node in workflow["nodes"]:
                named, values = node.get("widgets_values_named"), node.get("widgets_values")
                if isinstance(named, dict) and isinstance(values, list) and len(named) == len(values):
                    self.assertEqual(list(named.values()), values, "%s: %s" % (label, node["type"]))

    def test_every_chapter_and_its_pictures_exist(self):
        guide = Path(REPO) / "js" / "guide"
        for chapter in GUIDE["chapters"]:
            page = guide / chapter["file"]
            for picture in re.findall(r"!\[[^\]]*\]\(([^)\s]+)\)", page.read_text(encoding="utf8")):
                self.assertTrue((page.parent / picture).exists(), "%s: %s" % (chapter["id"], picture))

    def test_guide_md_is_made_from_the_current_chapters(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("make_guide", Path(REPO) / "js" / "guide" / "make_guide.py")
        make_guide = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(make_guide)
        self.assertEqual((Path(REPO) / "GUIDE.md").read_text(encoding="utf8"), make_guide.build(),
                         "GUIDE.md is out of date: run python js/guide/make_guide.py")

    def test_the_models_chapter_links_every_model_file(self):
        page = (Path(REPO) / "js" / "guide" / "en" / "02-models.md").read_text(encoding="utf8")
        for purpose, model in json.loads((Path(REPO) / "js" / "ng" / "models.json").read_text(encoding="utf8")).items():
            self.assertIn("[%s](%s)" % (model["file"], model["url"]) if model["url"] else model["file"], page, purpose)

    def test_models_carry_official_names_and_download_links(self):
        for label, workflow in self.examples():
            for node in workflow["nodes"]:
                if node["type"] not in ("UNETLoader", "CLIPLoader", "VAELoader", "LoraLoaderModelOnly"):
                    continue
                file = node["widgets_values"][0]
                self.assertNotIn("\\", file, label)
                self.assertNotIn("/", file, label)
                links = node["properties"]["models"]
                self.assertEqual(links[0]["name"], file, label)
                self.assertTrue(links[0]["url"].startswith(("https://huggingface.co/Comfy-Org/MiniMax-H3/resolve/main/",
                                                            "https://huggingface.co/Kijai/MiniMax-H3-TAE/resolve/main/")), label)
            text = json.dumps(workflow)
            self.assertNotIn("ng_lab", text, label)

    def loop(self):
        workflow = dict(self.examples())[ADVANCED]
        nodes = {n["id"]: n for n in workflow["nodes"]}
        links = {link[0]: link for link in workflow["links"]}
        one = lambda kind: next(n["id"] for n in nodes.values() if n["type"] == kind)

        def source(identifier, name):
            port = next(p for p in nodes[identifier]["inputs"] if p["name"] == name)
            return links[port["link"]][1:3]
        return workflow, nodes, links, one, source

    def test_the_custom_loop_closes_its_body_and_returns_the_last_sampler(self):
        _, nodes, _, one, source = self.loop()
        director, start, output, end = one("NGH3Director"), one("StartLoop"), one("NGDirectorOutput"), one("EndLoop")
        sampler, collect = one("SamplerCustomAdvanced"), one("NGCollect")
        self.assertEqual(source(start, "mode.list"), [director, 1], "chunks must originate at Director outside the loop")
        self.assertEqual(source(output, "result"), [director, 0])
        self.assertEqual(source(output, "loop_chunk"), [start, 3])
        self.assertEqual(source(output, "previous"), [start, 4])
        self.assertEqual(source(collect, "latents"), [end, 0])
        self.assertEqual(source(collect, "chunks"), [director, 1])
        for name in ("output_value", "next_iteration_value"):
            self.assertEqual(source(end, name), [sampler, 0])
        self.assertEqual(source(sampler, "latent_image")[0], output)
        self.assertEqual(source(sampler, "sigmas")[0], output, "the part's own turbo profile reaches the sampler")

    @unittest.skipUnless(comfy_available(), "ComfyUI is not importable")
    def test_native_validation_keeps_the_sampler_inside_the_loop(self):
        workflow, nodes, links, one, _ = self.loop()
        graph = {}
        for node in workflow["nodes"]:
            if node["type"] == "NGGuide":
                continue                    # a virtual node never reaches the server
            inputs = {}
            for port in node["inputs"]:
                if port["link"] is not None:
                    _, origin, slot, *_ = links[port["link"]]
                    inputs[port["name"]] = [str(origin), slot]
            graph[str(node["id"])] = dict(class_type=node["type"], inputs=inputs)
        save = str(one("SaveVideo"))
        validate_loops(graph, [save], graph.keys(), [str(one("StartLoop"))], [str(one("EndLoop"))])
        body = set(graph[str(one("StartLoop"))]["_loop_body"])
        self.assertTrue({str(one(k)) for k in ("NGDirectorOutput", "SamplerCustomAdvanced", "RandomNoise")} <= body)
        self.assertFalse({str(one(k)) for k in ("NGH3Director", "NGCollect", "SaveVideo")} & body)


if __name__ == "__main__":
    unittest.main()
