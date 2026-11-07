"""Read one AI JSON object without mistaking conversational prose for a token cutoff."""
import json
import re

from . import fields


def _extra_object(text):
    decoder = json.JSONDecoder()
    for start in re.finditer(r"[\{\[]", text):
        try:
            value, _ = decoder.raw_decode(text[start.start():])
        except json.JSONDecodeError:
            continue
        if isinstance(value, (dict, list)):
            return True
    return False


def read_object(text, path, invalid_message):
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    fence = re.search(r"(?m)^[ \t]*```[^\n]*\n", text)
    if fence:
        text = text[fence.end():].strip()
    start = re.search(r"[\{\[]", text)
    candidate = text[start.start():] if start else text
    try:
        data, end = json.JSONDecoder().raw_decode(candidate)
    except json.JSONDecodeError as error:
        if candidate.startswith("{") and (error.msg.startswith("Unterminated string")
                                          or error.pos >= len(candidate.rstrip())):
            raise ValueError("The AI's answer stopped before its JSON was complete. Raise Max tokens on the AI Loader "
                             "and try again.") from None
        raise ValueError(invalid_message) from None
    if _extra_object(candidate[end:]):
        raise ValueError(invalid_message)
    return fields.need_dict(data, path)
