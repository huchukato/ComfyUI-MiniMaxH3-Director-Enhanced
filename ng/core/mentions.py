"""Use the same Unicode name equivalence as Context uniqueness, including case expansions."""
import re


def replace_mentions(text, names, known_names=()):
    if not names:
        return text
    folded = {name.casefold(): label for name, label in names.items()}
    # Every Context name participates in matching, even if this pass cannot resolve it.
    # Otherwise an earlier Subject/audio pass can consume the prefix of a longer guide/lock.
    known = set(known_names)
    forms = set(names) | set(folded) | known | {name.casefold() for name in known}
    pattern = re.compile(r"@(%s)(?![\w])" % "|".join(re.escape(name) for name in sorted(forms, key=len, reverse=True)),
                         re.IGNORECASE)
    # IGNORECASE also matches dotted/dotless I aliases which are not casefold-equivalent.
    return pattern.sub(lambda match: folded.get(match.group(1).casefold(), match.group(0)), text)
