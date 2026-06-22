from __future__ import annotations

import os
from pathlib import Path

from .paths import PROJECT_ROOT


def load_env_file(path: Path | None = None) -> dict[str, str]:
    """Load a small .env file without requiring python-dotenv."""
    env_path = path or PROJECT_ROOT / ".env"
    if path is None and not env_path.exists():
        # Windows Notepad commonly creates ".env.txt" when file extensions are hidden.
        txt_env_path = PROJECT_ROOT / ".env.txt"
        if txt_env_path.exists():
            env_path = txt_env_path
    loaded: dict[str, str] = {}
    if not env_path.exists():
        return loaded

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
        loaded[key] = value
    return loaded


def get_env(name: str, default: str | None = None) -> str | None:
    load_env_file()
    value = os.environ.get(name)
    return value if value not in ("", None) else default
