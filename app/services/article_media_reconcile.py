"""Report/remove crashed imports; never remove any recorded media asset.

Run `python -m app.services.article_media_reconcile` to inspect, add --apply to
remove aged temporary/unrecorded files. No article media retention policy is
inferred here: even deleted articles' recorded images remain available.
"""

import argparse
import asyncio
from datetime import datetime, timezone
from pathlib import Path
import re
import shutil

from app.db.query.article_image import storage_paths
from app.db.session import SessionLocal
from app.services.article_media_service import STORAGE_NAME, media_root


def reconciliation_candidates(root: Path, recorded: set[str], *, cutoff: float):
    root = root.resolve()
    candidates = []
    staging = root / ".staging"
    if staging.is_dir() and not staging.is_symlink():
        for path in staging.iterdir():
            if path.is_dir() and not path.is_symlink() and re.fullmatch(r"[0-9a-f]{32}", path.name) and path.stat().st_mtime < cutoff:
                candidates.append(path)
    articles = root / "articles"
    if articles.is_dir() and not articles.is_symlink():
        for directory in articles.iterdir():
            if not directory.is_dir() or directory.is_symlink() or not directory.name.isdigit():
                continue
            for path in directory.iterdir():
                relative = path.relative_to(root).as_posix()
                if path.is_file() and not path.is_symlink() and STORAGE_NAME.fullmatch(path.name) and relative not in recorded and path.stat().st_mtime < cutoff:
                    candidates.append(path)
    return candidates


async def reconcile(*, apply=False, minimum_age_hours=24):
    if minimum_age_hours < 24:
        raise ValueError("Keep a minimum 24-hour grace period for active or uncertain imports.")
    root = media_root()
    async with SessionLocal() as db:
        recorded = await storage_paths(db)
    cutoff = datetime.now(timezone.utc).timestamp() - minimum_age_hours * 3600
    candidates = reconciliation_candidates(root, recorded, cutoff=cutoff)
    for path in candidates:
        # Validate the resolved target again immediately before any deletion.
        path.resolve().relative_to(root)
        if path.is_symlink():
            continue
        print(f"{'Removing' if apply else 'Would remove'} {path.relative_to(root).as_posix()}")
        if apply:
            if path.is_dir():
                await asyncio.to_thread(shutil.rmtree, path)
            else:
                await asyncio.to_thread(path.unlink)
    missing = sorted(relative for relative in recorded if not (root / relative).is_file())
    for relative in missing:
        print(f"Missing recorded file: {relative}")
    print(f"{len(candidates)} orphan candidates; {len(missing)} missing recorded files. {'Applied' if apply else 'Dry run'}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--minimum-age-hours", type=int, default=24)
    arguments = parser.parse_args()
    asyncio.run(reconcile(apply=arguments.apply, minimum_age_hours=arguments.minimum_age_hours))
