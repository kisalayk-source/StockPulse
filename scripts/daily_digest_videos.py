"""Turn a daily digest into faceless voiceover scripts and chart PNGs.

Example:
    python scripts/daily_digest_videos.py --date 2026-09-24 --out content/daily-digest
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.content.daily_digest import digest_payload, digest_today  # noqa: E402
from app.content.voiceover import write_story_assets  # noqa: E402
from app.db import init_db  # noqa: E402
from app.config import get_settings  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Write a voiceover script and chart PNG for each digest story.")
    parser.add_argument("--date", dest="day", default=None, help="Calendar day YYYY-MM-DD. Default is today in America/Los_Angeles.")
    parser.add_argument("--json", dest="json_path", default=None, help="Digest JSON file. Skips the database when set.")
    parser.add_argument("--out", default=str(ROOT / "content" / "daily-digest"), help="Output directory.")
    args = parser.parse_args()

    if args.json_path:
        payload = json.loads(Path(args.json_path).read_text(encoding="utf-8"))
    else:
        day = date.fromisoformat(args.day) if args.day else digest_today()
        engine = init_db(get_settings())
        from sqlalchemy.orm import Session

        with Session(engine) as session:
            payload = digest_payload(session, day)

    out_root = Path(args.out) / str(payload["date"])
    written: list[dict[str, str]] = []
    for story in payload.get("stories") or []:
        ticker = story.get("ticker") or "story"
        folder = out_root / f"{int(story['rank']):02d}-{ticker.lower()}-{story['kind']}"
        written.append(write_story_assets(story, folder))
    print(json.dumps({"date": payload.get("date"), "count": len(written), "files": written}, indent=2))


if __name__ == "__main__":
    main()
