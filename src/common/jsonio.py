"""Serialize a frozen-dataclass tree to JSON with camelCase keys.

Generalizes the PaddyPower output writer. The caller supplies a
snake→camel field-name map (each package owns its own). Enum values and
enum dict-keys are emitted as their `.name`. Written atomically."""

from __future__ import annotations

import enum
import json
import os
from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import Any, Mapping


def _key(k: Any) -> Any:
    return k.name if isinstance(k, enum.Enum) else k


def to_camel_dict(obj: Any, rename: Mapping[str, str]) -> Any:
    """Recursively convert `obj` into JSON-ready primitives.

    - dataclass → dict with field names renamed via `rename` (unmapped
      names pass through unchanged), declaration order preserved.
    - Enum → its `.name`.
    - dict → dict with Enum keys converted to `.name`, values recursed.
    - list/tuple → list of recursed elements.
    - everything else (str/int/float/bool/None) → unchanged."""
    if is_dataclass(obj) and not isinstance(obj, type):
        out: dict[str, Any] = {}
        for f in fields(obj):
            out[rename.get(f.name, f.name)] = to_camel_dict(getattr(obj, f.name), rename)
        return out
    if isinstance(obj, enum.Enum):
        return obj.name
    if isinstance(obj, dict):
        return {_key(k): to_camel_dict(v, rename) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_camel_dict(x, rename) for x in obj]
    return obj


def write_json(obj: Any, rename: Mapping[str, str], path: Path | str) -> None:
    """Serialize `obj` to `path` as 2-space-indented JSON, atomically
    (write to `{path}.tmp`, then os.replace)."""
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    payload = to_camel_dict(obj, rename)
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    os.replace(tmp, path)
