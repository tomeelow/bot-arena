"""What the API sends and accepts. Everything a client sees goes through one of these."""

from pydantic import BaseModel, Field


class Health(BaseModel):
    status: str
    engine_version: str


class LadderRow(BaseModel):
    rank: int
    version_id: int
    bot_id: int
    bot: str
    owner: str
    mu: float
    sigma: float
    score: float = Field(description="mu - k sigma, what the ladder is sorted by")
    low: float = Field(description="mu - 2 sigma")
    high: float = Field(description="mu + 2 sigma")
    games: int
    provisional: bool
    p_above_next: float | None = Field(
        description="P(this bot's skill > the next bot down's): about skill, not the next game"
    )


class VersionView(BaseModel):
    id: int
    n: int
    status: str
    mu: float | None
    sigma: float | None
    games: int
    error: str | None = Field(None, description="why validation rejected it; owner only")


class MatchSummary(BaseModel):
    id: int
    kind: str
    status: str
    players: list[str]
    winner_seat: int | None
    reason: str | None


class BotView(BaseModel):
    id: int
    name: str
    owner: str
    versions: list[VersionView]
    recent_matches: list[MatchSummary]


class NewBot(BaseModel):
    name: str = Field(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9_-]+$")


class Created(BaseModel):
    id: int


class Upload(BaseModel):
    version_id: int
    status: str


class CompareRequest(BaseModel):
    challenger: int
    incumbent: int
    seed_pairs: int = Field(ge=1)


class ComparisonView(BaseModel):
    id: int
    challenger: int
    incumbent: int
    wins: int
    draws: int
    losses: int
    pending: int
    score: float
    low: float
    high: float
    p_better: float = Field(description="P(the challenger's true score > 50%)")
    lost: list[int] = Field(description="match ids the challenger lost")


class Player(BaseModel):
    seat: int
    version_id: int
    bot_id: int
    bot: str
    owner: str
    version: int


class Outcome(BaseModel):
    winner_seat: int | None
    reason: str
    turns: int


class MatchView(BaseModel):
    id: int
    kind: str
    status: str
    seed: int
    engine_version: str
    players: list[Player]
    result: Outcome | None
    void_reason: str | None


class MyBot(BaseModel):
    id: int
    name: str


class Account(BaseModel):
    handle: str
    bots: list[MyBot]


class RatingPoint(BaseModel):
    match_id: int
    version_id: int
    mu: float
    sigma: float


class InvalidOrderView(BaseModel):
    turn: int
    reason: str


class DayCount(BaseModel):
    day: str  # YYYY-MM-DD, UTC
    count: int


class Spread(BaseModel):
    """The median and 95th percentile of a sample, and how many values it had."""

    n: int
    p50: float | None
    p95: float | None


class UsageStats(BaseModel):
    submitted_bots: int
    active_players_7d: int
    versions_per_day: list[DayCount]
    matches_per_day: list[DayCount]
    converged_versions: int
    unconverged_versions: int
    games_to_converge: Spread
    hours_to_converge: Spread
    seconds_to_first_match: Spread
    rated_matches: int  # in the last stats_days, which sandbox_outcomes are shares of
    sandbox_outcomes: dict[str, float]


class HealthReport(BaseModel):
    window_h: int
    alerts: list[str]
    matches_finished: int
    platform_errors: int
    lease_expired: int
    platform_error_rate: float
    end_reasons: dict[str, int]
    match_seconds: Spread
    queue_depth: int
    oldest_queued_s: float | None
    queue_wait_s: Spread
    worker_utilisation: float | None
    disk_used_fraction: float
