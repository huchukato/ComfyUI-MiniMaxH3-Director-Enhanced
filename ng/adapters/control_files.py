"""Import a generated control video from our output subfolder into the Context cards' input folder."""
import os
import shutil
import uuid

import folder_paths


def import_video(filename, subfolder):
    if not isinstance(filename, str) or os.path.basename(filename) != filename or any(c in filename for c in ("/", "\\", ":")):
        raise ValueError("Choose a generated control video filename.")
    if os.path.splitext(filename)[1].lower() not in (".mp4", ".mkv", ".webm"):
        raise ValueError("The generated control result must be a video.")
    root = os.path.realpath(folder_paths.get_output_directory())
    source = os.path.realpath(os.path.join(root, subfolder, filename))
    control_root = os.path.realpath(os.path.join(root, "h3-control"))
    if os.path.commonpath((root, control_root)) != root or os.path.commonpath((control_root, source)) != control_root:
        raise ValueError("Choose a generated video inside output/h3-control.")
    inputs = os.path.realpath(folder_paths.get_input_directory())
    destination = os.path.realpath(os.path.join(inputs, "h3-control"))
    if os.path.commonpath((inputs, destination)) != inputs:
        raise ValueError("The h3-control input folder must stay inside input.")
    os.makedirs(destination, exist_ok=True)
    name = "control_" + uuid.uuid4().hex + os.path.splitext(filename)[1].lower()
    with open(source, "rb") as src, open(os.path.join(destination, name), "xb") as dst:
        shutil.copyfileobj(src, dst)
    return os.path.join("h3-control", name)


PICTURE_FOLDER = "h3-picture-edit"     # the Image card's editor: masks, structure pictures, character sheets
PICTURE_KINDS = ("mask", "canny", "pose", "depth", "sheet")


def import_picture(filename, subfolder, kind):
    """A picture the card's editor made (output/h3-picture-edit) copied into input/h3-picture-edit, named by its kind."""
    if kind not in PICTURE_KINDS:
        raise ValueError("Unknown picture kind.")
    if not isinstance(filename, str) or os.path.basename(filename) != filename or any(c in filename for c in ("/", "\\", ":")):
        raise ValueError("Choose a generated picture filename.")
    if os.path.splitext(filename)[1].lower() not in (".png", ".jpg", ".jpeg", ".webp"):
        raise ValueError("The generated result must be a picture.")
    root = os.path.realpath(folder_paths.get_output_directory())
    source = os.path.realpath(os.path.join(root, subfolder, filename))
    own = os.path.realpath(os.path.join(root, PICTURE_FOLDER))
    if os.path.commonpath((own, source)) != own:
        raise ValueError("Choose a generated picture inside output/%s." % PICTURE_FOLDER)
    inputs = os.path.realpath(folder_paths.get_input_directory())
    destination = os.path.join(inputs, PICTURE_FOLDER)
    os.makedirs(destination, exist_ok=True)
    name = "%s_%s%s" % (kind, uuid.uuid4().hex[:12], os.path.splitext(filename)[1].lower())
    with open(source, "rb") as src, open(os.path.join(destination, name), "xb") as dst:
        shutil.copyfileobj(src, dst)
    return os.path.join(PICTURE_FOLDER, name)
