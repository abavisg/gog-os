"""Front matter for life/ and me/ content files: a deliberately small YAML subset.

Only what spec 2's schemas need, so no YAML dependency:

  key: value            scalar; digits parse to int, true/false to bool
  key: "quoted value"   JSON string (used whenever a bare value would be ambiguous)
  key: [a, "b c"]       inline list
  key: [[people/x]]     a bare wikilink stays a string

`dump` always writes values that `split` reads back identically. Absent values
are the literal string "none", as the schemas spell them.

Entry points:
  split(text) -> (meta, body)
  dump(meta) -> "---\\n...\\n---\\n"

Library module; no CLI.
"""
from __future__ import annotations

import json
import re

_KEY = re.compile(r"^([a-z_][a-z0-9_]*):(?: (.*))?$")
_INT = re.compile(r"^-?\d+$")
_BARE = re.compile(r"^[\w./@+-][\w ./@+()'-]*$")


class FrontMatterError(ValueError):
    """Front matter missing or malformed. `field` names the key when known."""

    def __init__(self, message: str, field: str | None = None) -> None:
        super().__init__(message)
        self.field = field


def _scalar(raw: str):
    raw = raw.strip()
    if raw.startswith('"'):
        return json.loads(raw)
    if _INT.match(raw):
        return int(raw)
    if raw in ("true", "false"):
        return raw == "true"
    return raw


def _value(raw: str, key: str):
    raw = raw.strip()
    try:
        if raw.startswith("[") and not raw.startswith("[["):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                pass
            inner = raw[1:-1].strip() if raw.endswith("]") else None
            if inner is None:
                raise FrontMatterError(f"unterminated list for '{key}'", key)
            return [_scalar(part) for part in inner.split(",")] if inner else []
        if raw.startswith("[[[") and raw.endswith("]"):
            # A list whose first element is a wikilink: [[[people/x]], y]
            return [_scalar(part) for part in raw[1:-1].split(",")]
        return _scalar(raw)
    except json.JSONDecodeError as exc:
        raise FrontMatterError(f"bad quoted value for '{key}': {exc}", key) from exc


def split(text: str) -> tuple[dict, str]:
    """Parse leading front matter -> (meta, body). Raises FrontMatterError."""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        raise FrontMatterError("no front matter (file must start with ---)")
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        raise FrontMatterError("front matter is not closed with ---") from None
    meta: dict = {}
    for line in lines[1:end]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = _KEY.match(line)
        if not m:
            raise FrontMatterError(f"cannot parse front matter line: {line!r}")
        meta[m.group(1)] = _value(m.group(2) or "", m.group(1))
    return meta, "\n".join(lines[end + 1:])


def _dump_scalar(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if value is None:
        return "none"
    s = str(value)
    if (_BARE.match(s) and s == s.strip() and not _INT.match(s)
            and s not in ("true", "false")):
        return s
    return json.dumps(s, ensure_ascii=False)


def _dump_list_item(value) -> str:
    if isinstance(value, str) and ("," in value or value.startswith("[")):
        return json.dumps(value, ensure_ascii=False)
    return _dump_scalar(value)


def dump(meta: dict) -> str:
    """Serialise meta as a front matter block, keys in the given order."""
    out = ["---"]
    for key, value in meta.items():
        if isinstance(value, list):
            out.append(f"{key}: [{', '.join(_dump_list_item(v) for v in value)}]")
        else:
            out.append(f"{key}: {_dump_scalar(value)}")
    out.append("---")
    return "\n".join(out) + "\n"
