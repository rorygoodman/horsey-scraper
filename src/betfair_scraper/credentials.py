"""Load and validate ~/.horsey-scraper/credentials.json. Port of Credentials.kt."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Credentials:
    username: str
    password: str
    app_key: str


def parse_credentials(text: str) -> Credentials:
    """JSON object with string fields username, password, appKey. Extra
    fields ignored. Missing/non-string fields → ValueError listing all."""
    try:
        root = json.loads(text)
        if not isinstance(root, dict):
            raise ValueError("not an object")
    except ValueError as e:
        raise ValueError(f"credentials JSON is not a valid object: {e}")
    missing: list[str] = []

    def s(key: str) -> "str | None":
        v = root.get(key)
        if not isinstance(v, str):
            missing.append(key)
            return None
        return v

    username, password, app_key = s("username"), s("password"), s("appKey")
    if missing:
        raise ValueError(
            f"credentials JSON missing or non-string fields: {','.join(missing)}"
        )
    return Credentials(username, password, app_key)


def default_credentials_path() -> Path:
    return Path.home() / ".horsey-scraper" / "credentials.json"


def load_credentials(path: Path | str) -> Credentials:
    path = Path(path)
    if not path.exists():
        raise ValueError(f"credentials file not found: {path}")
    _warn_if_world_readable(path)
    try:
        text = path.read_text()
    except OSError as e:
        raise ValueError(f"failed to read {path}: {e}")
    return parse_credentials(text)


def _warn_if_world_readable(path: Path) -> None:
    try:
        mode = os.stat(path).st_mode
    except OSError:
        return
    if mode & 0o077:
        print(
            f"Warning: {path} is readable by group/others; recommend `chmod 600`.",
            file=sys.stderr,
        )
