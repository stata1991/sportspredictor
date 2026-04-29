"""CLI for historical football data ingestion.

Usage::

    python -m backend.football.historical.cli [--force]

Ingests configured league/season pairs from API-Football (or disk cache)
and writes the parsed DataFrame to ``backend/football/historical/data/matches.parquet``.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from backend.football.historical.ingestor import ingest_all, INGEST_PAIRS
from backend.football.historical.parser import parse_fixtures

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent / "data"
PARQUET_PATH = DATA_DIR / "matches.parquet"


async def _run(force: bool = False) -> None:
    # Load API key from environment / .env
    from backend.shared.settings import get_settings
    settings = get_settings()
    if not settings.api_football_key:
        logger.error("API_FOOTBALL_KEY not set in environment / .env")
        sys.exit(1)

    # Ingest all league/season pairs.
    all_raw = await ingest_all(settings.api_football_key, force=force)

    # Parse each league/season into DataFrames and concatenate.
    import pandas as pd
    frames = []
    for (league_id, season), raw in sorted(all_raw.items()):
        label = f"league={league_id} season={season}"
        df = parse_fixtures(raw, source_label=label)
        frames.append(df)
        logger.info("  %s → %d completed matches", label, len(df))

    if not frames:
        logger.error("No fixtures parsed — nothing to write")
        sys.exit(1)

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values("kickoff_utc").reset_index(drop=True)

    # Deduplicate by fixture_id.
    before = len(combined)
    combined = combined.drop_duplicates(subset="fixture_id").reset_index(drop=True)
    dupes = before - len(combined)

    # Write to parquet.
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(PARQUET_PATH, index=False)

    # Summary report.
    print("\n" + "=" * 60)
    print("INGEST COMPLETE")
    print("=" * 60)
    print(f"  League/season pairs ingested:  {len(all_raw)}")
    print(f"  API calls made (non-cached):   estimated from logs above")
    print(f"  Total completed matches:       {len(combined)}")
    print(f"  Duplicates removed:            {dupes}")
    print(f"  DataFrame shape:               {combined.shape}")
    print(f"  Date range:                    {combined['kickoff_utc'].min().date()} → {combined['kickoff_utc'].max().date()}")
    print(f"  Unique teams:                  {pd.concat([combined['home_team_id'], combined['away_team_id']]).nunique()}")
    print(f"  Output:                        {PARQUET_PATH}")

    # Status distribution.
    print(f"\n  Status distribution:")
    for status, count in combined["status_short"].value_counts().items():
        print(f"    {status}: {count}")

    # Null score check.
    null_home = combined["home_goals"].isna().sum()
    null_away = combined["away_goals"].isna().sum()
    if null_home or null_away:
        print(f"\n  WARNING: {null_home} null home_goals, {null_away} null away_goals")
    else:
        print(f"\n  Score data: complete (no nulls)")

    # Sample rows.
    print(f"\n  Sample (5 rows):")
    sample = combined.sample(5, random_state=42) if len(combined) >= 5 else combined
    cols = ["fixture_id", "kickoff_utc", "home_team_name", "away_team_name", "home_goals", "away_goals", "status_short"]
    print(sample[cols].to_string(index=False))

    print(f"\n  Parquet written to: {PARQUET_PATH}")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(description="Ingest historical football fixtures")
    parser.add_argument("--force", action="store_true", help="Re-fetch from API even if disk cache exists")
    args = parser.parse_args()

    asyncio.run(_run(force=args.force))


if __name__ == "__main__":
    main()
