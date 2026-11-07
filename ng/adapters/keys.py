"""API keys, kept in the requesting user's folder and never in the workflow.

A widget value is serialised into every workflow the user saves and shares, so a key typed into
the AI Loader would travel with the file. Writing it here instead means the workflow carries only
the provider id and a field name, and the secret stays on this machine.

The same rule decides the panel: the API answers whether a key is set, never what it is.
"""
import json
import os
import tempfile

from .presets import _path  # the same containment check, so one rule governs every user file

FILENAME = "api_keys.json"


def _file(root):
    return _path(root, FILENAME)


def read(root):
    """{provider: {"env": name, "key": secret}}. A missing or damaged file reads as empty rather
    than raising: a broken key store must not stop the panel from opening."""
    try:
        with open(_file(root), encoding="utf8") as stream:
            data = json.load(stream)
    except (OSError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    clean = {}
    for provider, entry in data.items():
        if isinstance(entry, dict) and isinstance(entry.get("key"), str) and entry["key"]:
            clean[str(provider)] = {"env": str(entry.get("env") or ""), "key": entry["key"]}
    return clean


def _check(provider):
    """Only a registry provider may hold a key. A free-form name would create entries nothing ever
    reads, which is the same dead-field problem the custom source card used to be."""
    from ..core import providers
    if provider not in providers.PROVIDERS:
        raise ValueError("Choose a provider before saving a key.")
    return provider


def write(root, provider, key, env=""):
    """Store or clear one provider's key. Writing "" removes it, so there is a way to forget a key
    without hand-editing the file."""
    provider = _check(provider)
    # Checked before anything is stripped: a number would raise AttributeError deep inside, and a
    # caller sending the wrong type deserves to be told which field was wrong.
    if key is None:
        key = ""
    if not isinstance(key, str):
        raise ValueError("An API key must be text.")
    key = key.strip()
    if key and not 8 <= len(key) <= 400:
        raise ValueError("That does not look like an API key.")
    stored = read(root)
    if key:
        stored[provider] = {"env": (env or "").strip(), "key": key}
    else:
        stored.pop(provider, None)
    os.makedirs(root, exist_ok=True)
    target = _file(root)
    handle, temporary = tempfile.mkstemp(prefix=".api_keys_", suffix=".tmp", dir=root)
    try:
        with os.fdopen(handle, "w", encoding="utf8") as stream:
            json.dump(stored, stream, ensure_ascii=False, indent=2)
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)
    return provider in stored


def resolve(root, provider, fallback=None):
    """The secret for one provider, or None. `fallback` is the caller's already-resolved key, which
    keeps the existing env-var order working when no key was stored here."""
    entry = read(root).get(provider or "")
    return (entry or {}).get("key") or (fallback or None)


def describe(root):
    """What the panel is allowed to know: which providers have a key, never the key."""
    stored = read(root)
    return {provider: {"set": True, "env": entry["env"]} for provider, entry in sorted(stored.items())}