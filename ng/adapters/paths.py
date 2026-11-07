"""NG file references stay inside the configured input folder, including through symlinks."""
import ntpath
import os

import folder_paths


def input_path(source):
    if not isinstance(source, str):
        raise ValueError("The file reference must be a name inside ComfyUI's input folder.")
    name = source.replace(" [input]", "").strip().replace("\\", "/")
    if not name:
        return None
    if ntpath.splitdrive(name)[0] or name.startswith("/") or ".." in name.split("/"):
        raise ValueError("Choose a file inside ComfyUI's input folder.")
    root = os.path.realpath(folder_paths.get_input_directory())
    for relative in (name, "whatdreamscost/" + os.path.basename(name), os.path.basename(name)):
        path = os.path.realpath(os.path.join(root, relative))
        if os.path.commonpath((root, path)) != root:
            raise ValueError("Choose a file inside ComfyUI's input folder.")
        if os.path.isfile(path):
            return path
    return None
