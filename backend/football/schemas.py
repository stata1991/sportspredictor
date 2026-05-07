"""Pydantic v2 models for API-Football responses and our domain objects.

Two families of models live here:

1. **AF* models** — mirror the JSON shapes returned by api-sports.io.
   They use ``extra="ignore"`` so new upstream fields never break parsing.

2. **Domain models** (FixtureListItem, FixtureDetail, CoverageStatus) —
   our own simplified representations used by route handlers.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.football.constants import EXPECTED_COVERAGE

# ═══════════════════════════════════════════════════════════════════════
# AF* models — mirrors of the API-Football JSON response shapes
# ═══════════════════════════════════════════════════════════════════════

# ── Primitives / reusable pieces ──────────────────────────────────────


class AFTeam(BaseModel):
    """Team reference (used in fixtures, events, lineups, injuries)."""

    model_config = ConfigDict(extra="ignore")

    id: int
    name: str
    logo: str | None = None
    winner: bool | None = None


class AFVenue(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int | None = None
    name: str | None = None
    city: str | None = None


class AFGoals(BaseModel):
    """Home/away goal pair — reused in top-level goals and score periods."""

    model_config = ConfigDict(extra="ignore")

    home: int | None = None
    away: int | None = None


# ── Fixture ───────────────────────────────────────────────────────────


class AFFixtureStatus(BaseModel):
    model_config = ConfigDict(extra="ignore")

    long: str
    short: str
    elapsed: int | None = None
    extra: int | None = None


class AFFixtureInfo(BaseModel):
    """The ``fixture`` sub-object inside a fixture response item."""

    model_config = ConfigDict(extra="ignore")

    id: int
    referee: str | None = None
    timezone: str = "UTC"
    date: datetime
    timestamp: int
    venue: AFVenue = Field(default_factory=AFVenue)
    status: AFFixtureStatus


class AFLeagueRef(BaseModel):
    """League reference as it appears inside a fixture response."""

    model_config = ConfigDict(extra="ignore")

    id: int
    name: str
    country: str | None = None
    logo: str | None = None
    flag: str | None = None
    season: int
    round: str | None = None


class AFTeams(BaseModel):
    model_config = ConfigDict(extra="ignore")

    home: AFTeam
    away: AFTeam


class AFScore(BaseModel):
    model_config = ConfigDict(extra="ignore")

    halftime: AFGoals = Field(default_factory=AFGoals)
    fulltime: AFGoals = Field(default_factory=AFGoals)
    extratime: AFGoals = Field(default_factory=AFGoals)
    penalty: AFGoals = Field(default_factory=AFGoals)


class AFFixture(BaseModel):
    """A single fixture item from the ``/fixtures`` response array."""

    model_config = ConfigDict(extra="ignore")

    fixture: AFFixtureInfo
    league: AFLeagueRef
    teams: AFTeams
    goals: AFGoals = Field(default_factory=AFGoals)
    score: AFScore = Field(default_factory=AFScore)


# ── Coverage (leagues endpoint) ──────────────────────────────────────


class AFFixturesCoverage(BaseModel):
    """Nested ``coverage.fixtures`` sub-object."""

    model_config = ConfigDict(extra="ignore")

    events: bool = False
    lineups: bool = False
    statistics_fixtures: bool = False
    statistics_players: bool = False


class AFCoverage(BaseModel):
    """Coverage flags — flattened from the nested API shape.

    The API nests fixture-related flags under ``coverage.fixtures.*``.
    A ``model_validator`` hoists them to ``fixtures_events``, etc. so
    downstream code sees a flat namespace.
    """

    model_config = ConfigDict(extra="ignore")

    fixtures_events: bool = False
    fixtures_lineups: bool = False
    fixtures_statistics_fixtures: bool = False
    fixtures_statistics_players: bool = False
    standings: bool = False
    players: bool = False
    top_scorers: bool = False
    top_assists: bool = False
    top_cards: bool = False
    injuries: bool = False
    predictions: bool = False
    odds: bool = False

    @model_validator(mode="before")
    @classmethod
    def _flatten_fixtures(cls, data: Any) -> Any:
        """Hoist ``fixtures.events`` → ``fixtures_events``, etc."""
        if isinstance(data, dict) and "fixtures" in data:
            fixtures = data.pop("fixtures", {})
            if isinstance(fixtures, dict):
                for key, val in fixtures.items():
                    data[f"fixtures_{key}"] = val
        return data


class AFLeagueInfo(BaseModel):
    """Minimal league object from the ``/leagues`` endpoint."""

    model_config = ConfigDict(extra="ignore")

    id: int
    name: str
    type: str | None = None
    logo: str | None = None


class AFCountry(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    code: str | None = None
    flag: str | None = None


class AFLeagueSeason(BaseModel):
    model_config = ConfigDict(extra="ignore")

    year: int
    start: str | None = None
    end: str | None = None
    current: bool = False
    coverage: AFCoverage = Field(default_factory=AFCoverage)


class AFLeagueWithSeasons(BaseModel):
    """Top-level item from ``/leagues`` response array."""

    model_config = ConfigDict(extra="ignore")

    league: AFLeagueInfo
    country: AFCountry | None = None
    seasons: list[AFLeagueSeason] = []


# ── Events ────────────────────────────────────────────────────────────


class AFEventTime(BaseModel):
    model_config = ConfigDict(extra="ignore")

    elapsed: int | None = None
    extra: int | None = None


class AFPlayerRef(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int | None = None
    name: str | None = None


class AFEvent(BaseModel):
    """A single match event (goal, card, substitution)."""

    model_config = ConfigDict(extra="ignore")

    time: AFEventTime = Field(default_factory=AFEventTime)
    team: AFTeam
    player: AFPlayerRef = Field(default_factory=AFPlayerRef)
    assist: AFPlayerRef = Field(default_factory=AFPlayerRef)
    type: str | None = None
    detail: str | None = None
    comments: str | None = None


# ── Lineups ───────────────────────────────────────────────────────────


class AFLineupPlayer(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    name: str
    number: int | None = None
    pos: str | None = None
    grid: str | None = None


class AFLineupEntry(BaseModel):
    """Wrapper: each startXI / substitutes item is ``{"player": ...}``."""

    model_config = ConfigDict(extra="ignore")

    player: AFLineupPlayer


class AFCoach(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int | None = None
    name: str | None = None
    photo: str | None = None


class AFLineup(BaseModel):
    model_config = ConfigDict(extra="ignore")

    team: AFTeam
    formation: str | None = None
    startXI: list[AFLineupEntry] = []  # noqa: N815
    substitutes: list[AFLineupEntry] = []
    coach: AFCoach | None = None


# ── Injuries ──────────────────────────────────────────────────────────


class AFInjuryPlayer(BaseModel):
    """Player sub-object in injuries — carries ``type`` and ``reason``."""

    model_config = ConfigDict(extra="ignore")

    id: int
    name: str
    photo: str | None = None
    type: str | None = None
    reason: str | None = None


class AFInjuryFixture(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    date: str | None = None
    timestamp: int | None = None


class AFInjuryLeague(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    name: str | None = None
    country: str | None = None
    season: int | None = None


class AFInjury(BaseModel):
    model_config = ConfigDict(extra="ignore")

    player: AFInjuryPlayer
    team: AFTeam
    fixture: AFInjuryFixture
    league: AFInjuryLeague


# ── Odds (shallow) ────────────────────────────────────────────────────


class AFOddValue(BaseModel):
    model_config = ConfigDict(extra="ignore")

    value: str
    odd: str


class AFBet(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    name: str
    values: list[AFOddValue] = []


class AFBookmaker(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    name: str
    bets: list[AFBet] = []


class AFOdds(BaseModel):
    """Odds for a single fixture — kept shallow for now."""

    model_config = ConfigDict(extra="ignore")

    bookmakers: list[AFBookmaker] = []


# ── Predictions ───────────────────────────────────────────────────────


class AFPredictionWinner(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int | None = None
    name: str | None = None
    comment: str | None = None


class AFPredictionPercent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    home: str | None = None
    draw: str | None = None
    away: str | None = None


class AFPredictionGoals(BaseModel):
    model_config = ConfigDict(extra="ignore")

    home: str | None = None
    away: str | None = None


class AFPredictionDetail(BaseModel):
    """The ``predictions`` sub-object inside a prediction response."""

    model_config = ConfigDict(extra="ignore")

    winner: AFPredictionWinner | None = None
    win_or_draw: bool | None = None
    under_over: str | None = None
    goals: AFPredictionGoals | None = None
    advice: str | None = None
    percent: AFPredictionPercent | None = None


class AFComparison(BaseModel):
    """Statistical comparison between home and away teams."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    form: dict[str, str] | None = None
    att: dict[str, str] | None = None
    def_: dict[str, str] | None = Field(None, alias="def")
    poisson_distribution: dict[str, str] | None = None
    h2h: dict[str, str] | None = None
    goals: dict[str, str] | None = None
    total: dict[str, str] | None = None


class AFPrediction(BaseModel):
    """Top-level prediction response item."""

    model_config = ConfigDict(extra="ignore")

    predictions: AFPredictionDetail | None = None
    comparison: AFComparison | None = None
    h2h: list[dict[str, Any]] | None = None


# ═══════════════════════════════════════════════════════════════════════
# Domain models — our own API response shapes
# ═══════════════════════════════════════════════════════════════════════


class TeamSummary(BaseModel):
    """Minimal team info for fixture list / detail views."""

    id: int
    name: str
    logo: str | None = None


class FixtureListItem(BaseModel):
    """Simplified fixture for list endpoints."""

    fixture_id: int
    home_team: TeamSummary
    away_team: TeamSummary
    kickoff: datetime
    status: str  # short code: NS, 1H, HT, 2H, FT, AET, PEN, …
    status_long: str
    round: str | None = None
    venue: str | None = None
    home_goals: int | None = None
    away_goals: int | None = None


class FixtureDetail(FixtureListItem):
    """Full fixture detail — extends FixtureListItem."""

    referee: str | None = None
    venue_city: str | None = None
    elapsed: int | None = None
    score: AFScore | None = None


class UpsetListItem(BaseModel):
    """Single fixture in the upset watch list."""

    fixture_id: int
    home_team: str
    away_team: str
    home_logo: str | None = None
    away_logo: str | None = None
    kickoff: str  # ISO 8601 from API-Football
    status: str  # NS, 1H, HT, 2H, ET, etc.
    round: str | None = None
    upset_index: float
    upset_paths: list[str]


class UpsetListResponse(BaseModel):
    """Response envelope for GET /api/football/upsets."""

    count: int
    threshold: float
    upsets: list[UpsetListItem]


class CoverageStatus(BaseModel):
    """Flat coverage flags with warnings for expected-but-missing coverage."""

    fixtures_events: bool = False
    fixtures_lineups: bool = False
    fixtures_statistics_fixtures: bool = False
    fixtures_statistics_players: bool = False
    standings: bool = False
    players: bool = False
    top_scorers: bool = False
    top_assists: bool = False
    top_cards: bool = False
    injuries: bool = False
    predictions: bool = False
    odds: bool = False
    warnings: list[str] = []

    @classmethod
    def from_af_coverage(cls, cov: AFCoverage) -> CoverageStatus:
        """Build from an AFCoverage, adding warnings for expected gaps."""
        flags = {
            "fixtures_events": cov.fixtures_events,
            "fixtures_lineups": cov.fixtures_lineups,
            "fixtures_statistics_fixtures": cov.fixtures_statistics_fixtures,
            "fixtures_statistics_players": cov.fixtures_statistics_players,
            "standings": cov.standings,
            "players": cov.players,
            "top_scorers": cov.top_scorers,
            "top_assists": cov.top_assists,
            "top_cards": cov.top_cards,
            "injuries": cov.injuries,
            "predictions": cov.predictions,
            "odds": cov.odds,
        }
        missing = sorted(k for k in EXPECTED_COVERAGE if not flags[k])
        warnings: list[str] = []
        if missing:
            warnings.append(
                "WC 2026 coverage gap: "
                + ", ".join(f"{k}=false" for k in missing)
            )
        return cls(**flags, warnings=warnings)
