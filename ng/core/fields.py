"""Small readers used by every from_dict: they name the path of a bad field instead of raising a bare KeyError."""
import math

from .issues import SchemaError


def need_dict(value, path):
    if not isinstance(value, dict):
        raise SchemaError(path, "expected an object, got %s" % type(value).__name__)
    return value


def read_str(data, key, path, default=None):
    if key not in data:
        if default is None:
            raise SchemaError("%s.%s" % (path, key), "is required")
        return default
    value = data[key]
    if not isinstance(value, str):
        raise SchemaError("%s.%s" % (path, key), "expected text, got %s" % type(value).__name__)
    return value


def read_number(data, key, path, default=None, minimum=None):
    if key not in data:
        if default is None:
            raise SchemaError("%s.%s" % (path, key), "is required")
        return default
    value = data[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SchemaError("%s.%s" % (path, key), "expected a number, got %s" % type(value).__name__)
    if not math.isfinite(value):
        raise SchemaError("%s.%s" % (path, key), "must be a finite number")
    if minimum is not None and value < minimum:
        raise SchemaError("%s.%s" % (path, key), "must be at least %s, got %s" % (minimum, value))
    return value


def read_choice(data, key, path, choices, default):
    value = data.get(key, default)
    if value not in choices:
        raise SchemaError("%s.%s" % (path, key), "must be one of %s, got %r" % (", ".join(choices), value))
    return value


def read_texts(data, key, path):
    value = data.get(key, [])
    if not isinstance(value, (list, tuple)) or not all(isinstance(v, str) for v in value):
        raise SchemaError("%s.%s" % (path, key), "expected a list of texts")
    return tuple(value)


def read_list(data, key, path):
    value = data.get(key, [])
    if not isinstance(value, (list, tuple)):
        raise SchemaError("%s.%s" % (path, key), "expected a list")
    return value


def check_version(data, path, supported):
    version = data.get("schema_version")
    if version != supported:
        raise SchemaError("%s.schema_version" % path, "expected %s, got %r" % (supported, version))
