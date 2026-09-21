"""Create the first release or advance its minor version and date."""

import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


VERSION_FILE = Path(__file__).resolve().parents[1] / "version.json"


def next_name(current: str | None) -> str:
    if current is None:
        return "1.0v"
    match = re.fullmatch(r"(\d+)\.(\d+)v", current)
    if not match:
        raise ValueError(f"Nieznany format wersji: {current}")
    return f"{match.group(1)}.{int(match.group(2)) + 1}v"


def main() -> None:
    previous = json.loads(VERSION_FILE.read_text(encoding="utf-8"))["name"] if VERSION_FILE.exists() else None
    release = {
        "name": next_name(previous),
        "released_at": datetime.now(ZoneInfo("Europe/Warsaw")).isoformat(timespec="minutes"),
    }
    VERSION_FILE.write_text(json.dumps(release, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{release['name']} - {release['released_at']}")


if __name__ == "__main__":
    main()
