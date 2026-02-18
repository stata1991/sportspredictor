import os

CACHE_ENABLED = os.getenv("CACHE_ENABLED", "true").lower() in {"1", "true", "yes"}
REDIS_URL = os.getenv("REDIS_URL")
CACHE_NAMESPACE = os.getenv("CACHE_NAMESPACE", "sportspredictor")
CACHE_VERSION = os.getenv("CACHE_VERSION", "v1")

SERIES_TTL = 3600
SERIES_SCHEDULE_TTL = 86400  # 24h — tournament schedule rarely changes
MATCH_INFO_TTL = 30
COMPLETED_MATCH_TTL = 86400  # 24h — completed match data never changes
OVERS_TTL = 8
COMMENTARY_TTL = 8
SCORECARD_TTL = 10
FEATURE_TTL = 3600
PREDICTION_PRE_TTL = 120
PREDICTION_LIVE_TTL = 8

# Match list per date: volatility depends on date relative to today
MATCH_LIST_TODAY_TTL = 3600    # today's matches: 1 hour
MATCH_LIST_PAST_TTL = 86400   # past dates: 24 hours (schedule is final)
MATCH_LIST_FUTURE_TTL = 1800  # future dates: 30 min (schedule could update)

# Pre-match prediction TTLs: volatility depends on match state
PRED_PRE_TOSS_TTL = 1800      # 30 min — nothing changes until toss
PRED_POST_TOSS_TTL = 300      # 5 min — confidence bump from toss, re-check soon
PRED_COMPLETED_TTL = 86400    # 24h — result is final
PRED_IN_PROGRESS_TTL = 30     # 30s — match started, redirect to live
