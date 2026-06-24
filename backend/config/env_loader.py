import os
import json
from io import StringIO
from pathlib import Path
from dotenv import load_dotenv


def _normalise_env_text(candidate: Path) -> str:
    """Compact pretty-printed GOOGLE_SERVICE_ACCOUNT_JSON blocks before dotenv parsing."""
    text = candidate.read_text(encoding="utf-8")
    if not candidate.exists():
        return text

    lines = text.splitlines()
    collected = []
    output = []
    inside_block = False
    brace_balance = 0

    for line in lines:
        if not inside_block:
            if not line.startswith("GOOGLE_SERVICE_ACCOUNT_JSON="):
                output.append(line)
                continue

            value = line.split("=", 1)[1].strip()
            if not value.startswith("{"):
                output.append(line)
                continue

            collected.append(value)
            brace_balance += value.count("{") - value.count("}")
            inside_block = brace_balance > 0
            if not inside_block:
                try:
                    compact_json = json.dumps(json.loads(value), separators=(",", ":"))
                except json.JSONDecodeError:
                    output.append(line)
                else:
                    output.append(f"GOOGLE_SERVICE_ACCOUNT_JSON={compact_json}")
                collected = []
                continue
            continue

        collected.append(line)
        brace_balance += line.count("{") - line.count("}")
        if brace_balance <= 0:
            raw_json = "\n".join(collected)
            try:
                compact_json = json.dumps(json.loads(raw_json), separators=(",", ":"))
            except json.JSONDecodeError:
                output.extend(collected)
            else:
                output.append(f"GOOGLE_SERVICE_ACCOUNT_JSON={compact_json}")
            collected = []
            inside_block = False
            continue

    if inside_block and collected:
        output.extend(collected)

    return "\n".join(output) + "\n"


def load_env() -> None:
    """Load .env reliably from the project root.

    Uvicorn may change the working directory depending on how it's launched.
    This loader explicitly targets the .env that sits next to the project root.
    """

    # backend/config/env_loader.py -> backend/config -> backend -> project root
    project_root = Path(__file__).resolve().parents[2]
    candidate = project_root / ".env"

    # Fall back to cwd-based lookup for compatibility.
    if candidate.exists():
        env_text = _normalise_env_text(candidate)
        load_dotenv(stream=StringIO(env_text), override=True)
    else:
        load_dotenv(override=True)

    # Do not raise for missing AI keys; scoring still works without AI features.
    os.environ.setdefault("APP_ENV", os.getenv("APP_ENV", "development"))
