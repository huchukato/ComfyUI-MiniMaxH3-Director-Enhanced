"""The H3 Storyboard: a sheet of numbered panels, each a stack of picture and text layers, with a time, a title, a caption
for the sheet and the shot text H3 renders.

The browser draws the sheet (js/ng/h3b_*.js) and hands the node the finished pictures; this module only reads the board
the Studio wrote and turns its panels into the Director's shot document. Panel times follow each other: panel 2 starts
where panel 1 ends, so a 2.5 s, a 5 s and a 2.5 s panel are the shots 0-2.5, 2.5-7.5 and 7.5-10 s.

Pure Python with no ComfyUI import."""
import json

from . import fields

FORMAT = "h3-storyboard"
MAX_PANELS = 9
ASPECTS = {"16:9": (16, 9), "9:16": (9, 16), "1:1": (1, 1), "4:3": (4, 3), "3:4": (3, 4), "21:9": (21, 9)}


def new_board():
    return {"format": FORMAT, "schema_version": 1, "title": "", "subtitle": "", "aspect": "16:9", "idea": "",
            "panels": [{"id": "p1", "seconds": 2.5, "title": "", "caption": "", "shot": "",
                        "first_frame": False, "last_frame": False, "layers": []}]}


def read_board(text):
    """The board of the node's widget; an empty widget is a new board. Raises ValueError for anything else."""
    if not str(text or "").strip():
        return new_board()
    try:
        data = json.loads(text)
    except ValueError as error:
        raise ValueError("The storyboard data is not readable JSON: %s" % error) from None
    fields.need_dict(data, "storyboard")
    if data.get("format") != FORMAT:
        raise ValueError("This is not H3 storyboard data.")
    fields.check_version(data, "storyboard", 1)
    if data.get("aspect", "16:9") not in ASPECTS:
        raise ValueError("Choose a panel format: %s." % ", ".join(ASPECTS))
    panels = fields.read_list(data, "panels", "storyboard")
    if not 1 <= len(panels) <= MAX_PANELS:
        raise ValueError("A storyboard has 1 to %d panels." % MAX_PANELS)
    for number, panel in enumerate(panels):
        path = "storyboard.panels[%d]" % number
        fields.need_dict(panel, path)
        fields.read_number(panel, "seconds", path, minimum=0.1)
        for name in ("title", "caption", "shot"):
            fields.read_str(panel, name, path, "")
        panel["first_frame"] = bool(panel.get("first_frame"))
        panel["last_frame"] = bool(panel.get("last_frame"))
        fields.read_list(panel, "layers", path)
    return data


def panel_times(board):
    """[(start s, end s)] of the panels, end to end from 0."""
    out, start = [], 0.0
    for panel in board["panels"]:
        end = round(start + float(panel["seconds"]), 3)
        out.append((round(start, 3), end))
        start = end
    return out


def shots_document(board):
    """The Director's shot document of the board: one shot per panel, its text the panel's shot text (or its caption)."""
    shots = [{"id": "sb-%s" % (panel.get("id") or number + 1), "start": start, "end": end,
              "text": (panel.get("shot") or panel.get("caption") or panel.get("title") or "").strip(),
              "media": [], "spoken": [], "locked_fields": [], "draft": None}
             for number, (panel, (start, end)) in enumerate(zip(board["panels"], panel_times(board)))]
    return json.dumps({"format": "h3-director-shots", "schema_version": 1, "shots": shots}, ensure_ascii=False)
