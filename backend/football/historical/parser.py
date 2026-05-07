"""Parse raw API-Football fixture JSON into a clean pandas DataFrame.

Filtering rules:
- ``FT``  → include, use ``score.fulltime`` goals
- ``AET`` → include, use ``score.fulltime`` goals (regulation-time result)
- ``PEN`` → include, use ``score.fulltime`` goals (regulation-time draw)
- All other statuses (NS, PST, CANC, ABD, INT, SUSP, …) → excluded

For AET/PEN matches the *fulltime* score reflects the 90-minute outcome.
Dixon-Coles is a 90-minute model; extra-time and penalty results are not
training signal.
"""

from __future__ import annotations

import logging
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

COMPLETED_STATUSES = frozenset({"FT", "AET", "PEN"})


def parse_fixtures(
    raw_fixtures: list[dict[str, Any]],
    *,
    source_label: str = "",
) -> pd.DataFrame:
    """Convert a list of raw API-Football fixture dicts to a DataFrame.

    Parameters
    ----------
    raw_fixtures:
        List of dicts as returned by ``ingestor.ingest_league_season``
        or loaded from a raw JSON file on disk.
    source_label:
        Optional label for log messages (e.g. "league=1 season=2018").

    Returns
    -------
    DataFrame with one row per completed fixture and columns:
        fixture_id, league_id, season, kickoff_utc,
        home_team_id, home_team_name, away_team_id, away_team_name,
        home_goals, away_goals, ht_home_goals, ht_away_goals,
        status_short
    """
    rows: list[dict[str, Any]] = []
    status_counts: Counter[str] = Counter()

    for item in raw_fixtures:
        fixture = item.get("fixture", {})
        league = item.get("league", {})
        teams = item.get("teams", {})
        score = item.get("score", {})

        status_short = fixture.get("status", {}).get("short", "")
        status_counts[status_short] += 1

        if status_short not in COMPLETED_STATUSES:
            continue

        fulltime = score.get("fulltime", {})
        halftime = score.get("halftime", {})
        home_goals = fulltime.get("home")
        away_goals = fulltime.get("away")

        if home_goals is None or away_goals is None:
            logger.warning(
                "Completed fixture %s has null fulltime score, skipping",
                fixture.get("id"),
            )
            continue

        rows.append({
            "fixture_id": fixture.get("id"),
            "league_id": league.get("id"),
            "season": league.get("season"),
            "kickoff_utc": fixture.get("date"),
            "home_team_id": teams.get("home", {}).get("id"),
            "home_team_name": teams.get("home", {}).get("name"),
            "away_team_id": teams.get("away", {}).get("id"),
            "away_team_name": teams.get("away", {}).get("name"),
            "home_goals": int(home_goals),
            "away_goals": int(away_goals),
            "ht_home_goals": int(halftime["home"]) if halftime.get("home") is not None else None,
            "ht_away_goals": int(halftime["away"]) if halftime.get("away") is not None else None,
            "status_short": status_short,
        })

    # Log status distribution.
    total = sum(status_counts.values())
    included = sum(status_counts[s] for s in COMPLETED_STATUSES)
    excluded = total - included
    label = f" [{source_label}]" if source_label else ""

    logger.info(
        "Parse%s: %d total, %d included (%s), %d excluded",
        label, total, included,
        ", ".join(f"{s}={status_counts[s]}" for s in sorted(COMPLETED_STATUSES) if status_counts[s]),
        excluded,
    )
    if excluded:
        excluded_detail = {s: c for s, c in status_counts.items() if s not in COMPLETED_STATUSES}
        logger.info("  Excluded statuses: %s", excluded_detail)

    # Sanity check: warn if >5% filtered out.
    if total > 0 and excluded / total > 0.05:
        logger.warning(
            "More than 5%% of fixtures excluded (%d/%d = %.1f%%)",
            excluded, total, 100 * excluded / total,
        )

    df = pd.DataFrame(rows)
    if not df.empty:
        df["kickoff_utc"] = pd.to_datetime(df["kickoff_utc"], utc=True)
        df = df.sort_values("kickoff_utc").reset_index(drop=True)
    return df


def parse_all_raw_files(raw_dir: Path | str) -> pd.DataFrame:
    """Parse every raw JSON file in a directory and concatenate.

    Returns a single sorted DataFrame across all league/season pairs.
    """
    raw_dir = Path(raw_dir)
    frames: list[pd.DataFrame] = []

    for path in sorted(raw_dir.glob("fixtures_league*_season*.json")):
        import json
        with open(path) as f:
            raw = json.load(f)
        df = parse_fixtures(raw, source_label=path.stem)
        frames.append(df)

    if not frames:
        logger.warning("No raw JSON files found in %s", raw_dir)
        return pd.DataFrame()

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values("kickoff_utc").reset_index(drop=True)

    # Deduplicate by fixture_id (a fixture could theoretically appear
    # in overlapping league/season queries).
    before = len(combined)
    combined = combined.drop_duplicates(subset="fixture_id").reset_index(drop=True)
    if len(combined) < before:
        logger.info(
            "Removed %d duplicate fixtures (by fixture_id)",
            before - len(combined),
        )

    logger.info(
        "Combined DataFrame: %d matches, %d unique teams, date range %s → %s",
        len(combined),
        combined["home_team_id"].nunique() + combined["away_team_id"].nunique(),
        combined["kickoff_utc"].min().date() if not combined.empty else "N/A",
        combined["kickoff_utc"].max().date() if not combined.empty else "N/A",
    )
    return combined
