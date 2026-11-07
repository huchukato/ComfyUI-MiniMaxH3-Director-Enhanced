"""GUIDE.md at the repository root: every chapter of the H3 Guide in one file, to read on GitHub or offline.
The chapters in js/guide/en stay the source; run `python js/guide/make_guide.py` after changing one
(tests/ng/test_product_workflows.py fails while GUIDE.md is out of date)."""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(HERE, "..", "..", "GUIDE.md")


def anchor(title):
    """GitHub's heading anchor: lower case, punctuation dropped, spaces to hyphens."""
    return re.sub(r"\s", "-", re.sub(r"[^\w\s-]", "", title.lower()))


def build():
    with open(os.path.join(HERE, "guide.json"), encoding="utf-8") as file:
        chapters = json.load(file)["chapters"]
    head = ["# H3 Director — the guide", "",
            "The same guide the **H3 Guide** node shows inside ComfyUI, all chapters in one file. Agents: see "
            "[SKILL.md](SKILL.md).", "", "## Contents", ""]
    body = []
    for chapter in chapters:
        with open(os.path.join(HERE, chapter["file"]), encoding="utf-8") as file:
            text = file.read().replace("../images/", "js/guide/images/")
        lines = text.strip().splitlines()
        title = lines[0].lstrip("#").strip()
        head.append("- [%s](#%s)" % (title, anchor(title)))
        # one level down: a chapter's title becomes ##, its sections ###
        body += ["", "---", ""] + ["#" + line if line.startswith("#") else line for line in lines]
    return "\n".join(head + body) + "\n"


if __name__ == "__main__":
    with open(TARGET, "w", encoding="utf-8", newline="\n") as file:
        file.write(build())
    print("wrote", os.path.normpath(TARGET))
