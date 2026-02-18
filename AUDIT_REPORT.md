# Cricket Prediction System — Engineering Audit Report

**Date**: 2026-02-18
**Auditor**: ML/Backend Engineering Review
**Scope**: Full codebase — backend prediction logic, data providers, caching, frontend surfaces

---

## 0. Architecture Overview

### Two Parallel Prediction Systems Exist

| System | Entry Point | Status | Used By |
|--------|------------|--------|---------|
| **Legacy** | `prediction_engine.py` | **Dead code** — not called by any active route | Nothing (was used by old `/predict/winner` etc. before they were redirected) |
| **Active** | `prediction_engine_api.py` + `feature_store.py` | **Live** | `/predict/pre-match`, `/predict/live` |

The legacy `prediction_engine.py` (1,373 lines) is entirely unreachable from current API routes. Every deprecated endpoint (`/predict/winner`, `/predict/score`, etc.) delegates to `pre_match_predictions()` from `prediction_engine_api.py` (lines 174–253 of `main.py`).

**Critical finding**: `backend/deliveries.csv` is a **git-lfs pointer** (3 lines), not actual data. Every delivery-level computation in the legacy engine (`calculate_team_stats`, `calculate_bowler_impact`, `calculate_batting_strength`, etc.) would produce empty or fallback results even if called.

### Active Data Flow

```
Frontend → main.py routes → prediction_engine_api.py
                                ↓
                          feature_store.py (build_series_features)
                                ↓
                          live_data_provider.py (Cricbuzz API)
                                ↓
                          cache.py (in-memory / Redis)
```

### Active API Routes

| Route | Handler | Purpose |
|-------|---------|---------|
| `GET /predict/pre-match` | `pre_match_predictions()` | Pre-match predictions for any series |
| `GET /predict/live` | `live_predictions()` | Live in-match predictions |
| `GET /matches` | `fetch_live_data_for_series()` | List IPL matches for a date |
| `GET /t20wc/matches` | `fetch_live_data_for_series()` | List T20WC matches for a date |
| `POST /update-match-context` | `_match_info_from_series()` | Legacy context update (unused by active prediction path) |

---

## 1. Prediction Target Mapping

### 1A. Match Winner

| Attribute | Pre-match (`prediction_engine_api.py:60-174`) | Live (`prediction_engine_api.py:177-349`) |
|-----------|-------|------|
| **Logic location** | `prediction_engine_api.py:95-98` | `prediction_engine_api.py:278-294` |
| **Signals used** | Series win_rate only (wins/played from completed matches in series) | Same win_rate OR binary chase_outcome (can_chase / can't) |
| **Fallback chain** | If both teams have form data → ratio of win_rates. If either missing → 50/50 | Same + chase override |
| **Pre→Live transition** | If chase_outcome exists, it completely overrides form-based probability | Binary: batting team wins if projected >= target |
| **Confidence** | Hardcoded: 0.7 (venue), 0.58 (series), 0.48 (league) | Same + no live-state adjustment |

**Gaps identified**:
- **No head-to-head history** — `feature_store.py` collects team form but ignores H2H records
- **No toss impact** — toss_winner/toss_decision are fetched by `get_match_details()` but never fed into winner probability in the active system
- **No venue-specific win rates** — only series-wide win rates used
- **No current match state in live winner calc** — during 1st innings, winner is purely form-based (no run rate, no wickets in hand, no phase)
- **Chase winner is binary** — if projected_final >= target, batting team wins with 100% implied probability. No gradation.
- **Win probability is undefined during chase** — `win_probs` is `None` when `chase_outcome` exists (`prediction_engine_api.py:282-283`), so the response has `probability: null`

### 1B. Total Score Range

| Attribute | Pre-match | Live |
|-----------|-----------|------|
| **Logic location** | `prediction_engine_api.py:127-129` | `prediction_engine_api.py:271-276` |
| **Signals used** | `avg_innings_runs` ± `std_innings_runs` from venue/series/league priors | Identical — same priors, ignores live state |
| **Fallback chain** | venue → series → league (hardcoded `avg_runs=160, std_runs=25`) | Same |
| **Live adjustment** | None — pre-match and live return the **exact same range** | `projected_total` is computed separately but not fed back into `total_score` |

**Gaps identified**:
- **Live total_score ignores live data entirely** — `prediction_engine_api.py:276` uses the same `_range_from_stats(avg_runs, std_runs)` as pre-match
- **No phase-aware modeling** — powerplay/middle/death overs have very different run rates; a single average ignores this
- **No team-specific adjustments** — the same venue average applies regardless of which teams are playing
- **No batting-first vs chasing adjustment** — identical range for both innings
- **`projected_total` exists but is disconnected** from `total_score` in the response — two conflicting forecasts in the same payload

### 1C. Wickets Range

| Attribute | Pre-match | Live |
|-----------|-----------|------|
| **Logic location** | `prediction_engine_api.py:128` | `prediction_engine_api.py:272` |
| **Signals used** | `avg_innings_wkts` ± `std_innings_wkts` from venue/series/league | Same |
| **Live adjustment** | None | None — doesn't use current wickets, overs, or bowling matchup |

**Gaps identified**:
- **No bowling attack quality signal** — team bowling lineups are fetched but unused
- **No pitch condition signal** — venue priors are a blunt instrument (averages across all conditions)
- **Not conditioned on score trajectory** — high-scoring matches tend to have fewer wickets (aggressive batting succeeds) vs low-scoring (bowler-dominant)
- **No live wicket-rate extrapolation** — during a match, current wickets/overs ratio is ignored

### 1D. Powerplay Score Range

| Attribute | Pre-match | Live |
|-----------|-----------|------|
| **Logic location** | `prediction_engine_api.py:130-132` | `prediction_engine_api.py:273-275` |
| **Signals used** | `pp_ratio * innings_range` — a fixed ratio of the innings total | Same |
| **Fallback** | If pp_ratio is null → league default 0.28 | Same |

**Gaps identified**:
- **Powerplay is derived from innings total, not independently modeled** — it's literally `innings_range * 0.28`
- **No team-specific powerplay tendencies** — some teams consistently score 50+ in powerplay, others don't
- **No opening batsmen quality signal** — playing XI is fetched but unused
- **During live powerplay overs, actual score is ignored** — if 3 overs done at 40 runs, the prediction still shows the pre-match range

### 1E. Chase Outcome

| Attribute | Location |
|-----------|----------|
| **Logic** | `prediction_engine_api.py:202-240` |
| **Signals** | current_rr, remaining_overs, target, projected_final |
| **Model** | Linear extrapolation: `projected_final = runs + current_rr * remaining_overs` |

**Gaps identified**:
- **No wickets-in-hand factor** — team at 80/1 after 10 overs has very different chase outlook than 80/5
- **No required-rate-vs-current-rate pressure model** — when RRR > CRR by large margin, collapse probability increases
- **No phase-aware run rate** — death overs typically have higher run rates; simple linear extrapolation underestimates
- **No historical chase success rate by target band** — `feature_store.py:50-63` computes `chase_priors` by target band but **this data is never used** in `prediction_engine_api.py`
- **`finish_over` calculation assumes constant run rate** — doesn't account for acceleration

---

## 2. Feature Engineering Gaps

### 2A. Available from Cricbuzz API but NOT Used

| Signal | API Source | Currently Fetched? | Used in Predictions? | Improves |
|--------|-----------|-------------------|---------------------|----------|
| **Toss winner + decision** | `get_match_details()` → `tossResults` | Yes (`live_data_provider.py:286-288`) | **No** — fetched but unused in active prediction path | Winner, score (batting first vs chasing adjustment) |
| **Playing XI** | `get_match_details()` → `playerDetails` | Yes (`live_data_provider.py:300-313`) | **No** — fetched but unused | All targets (batting/bowling quality) |
| **Squads** | `get_match_details()` → `playerDetails` | Yes (`live_data_provider.py:296-299`) | **No** | Team strength proxy |
| **Scorecard per innings** | Scorecard endpoint | Yes (`live_data_provider.py:316-341`) | Only for innings score extraction | Detailed batting/bowling performance |
| **Powerplay actual data (ppData)** | Overs endpoint → `ppData` | Yes (`live_data_provider.py:358-380`) | Only in `powerplay` dict construction, never in predictions | Powerplay predictions during/after PP |
| **Match status string** | `matchInfo.status` | Yes | Only for "completed" check | State machine transitions |
| **Overs-level data** | Overs endpoint | Yes (fetched) | Not parsed per-over | Phase-specific run rates, partnership data |
| **Chase priors by target band** | Computed in `feature_store.py:97,133-135,169-172` | Yes (built) | **No** — `SeriesFeatures.chase_priors` is computed but never read by prediction_engine_api.py | Chase outcome probability |
| **Individual innings scores (1st vs 2nd)** | `_extract_match_scores()` in feature_store.py | Partially (team1/team2 runs) | Only for venue averages | 1st vs 2nd innings adjustment |
| **Match format** | `matchInfo.matchFormat` | Yes (filtered) | Only as filter | N/A |
| **Start time / day-night** | `matchInfo.startDate` | Yes | Only for display | Day/night venue effect |

### 2B. Signals Not Available but Valuable

| Signal | Source Required | Impact |
|--------|----------------|--------|
| Pitch report / conditions | Manual entry or external source | Score range, wickets |
| Weather (humidity, dew) | Weather API | Chase advantage, powerplay scoring |
| Player form (last 5 innings) | External stats API or manual | Individual contribution estimates |
| Batting order / impact player designation | Not available from current API | Score projections |

---

## 3. Live State Machine Completeness

### Expected States

```
PRE_TOSS → POST_TOSS → INNINGS_1_LIVE → INNINGS_BREAK → INNINGS_2_LIVE (CHASE) → COMPLETED
```

### Current Implementation

| State | Detected? | How | Features Updated? | Model Weights Changed? | Confidence Adjusted? |
|-------|-----------|-----|-------------------|----------------------|---------------------|
| **PRE_TOSS** | Yes | `prediction_stage = "pre_toss"` (`prediction_engine_api.py:142`) | venue/series/league priors | N/A | Yes (base confidence) |
| **POST_TOSS** | Partial | Checks if `toss_winner` or `toss_decision` exists (`prediction_engine_api.py:144-147`) | **No feature change** — same priors used | **No** — same model | +0.05 confidence bump only |
| **IN_PROGRESS (1st innings)** | Yes (pre-match redirects to "use Live tab") | Checks if any innings has overs > 0 (`prediction_engine_api.py:83`) | Live: uses current_rr for projected_total only | **No** — score/wickets/pp ranges unchanged | Same as pre-match |
| **INNINGS_BREAK** | **No** — not detected | Falls through to generic live handler | Not handled | Not handled | Not handled |
| **CHASE_LIVE (2nd innings)** | Partial | Detected when `batting_team != first_team` (`prediction_engine_api.py:204`) | Chase calculation added | Winner becomes binary (can_chase) | Not adjusted |
| **COMPLETED** | Yes | Status string contains "won by" etc. (`prediction_engine_api.py:71`) | Returns final status | N/A | N/A |

### Critical State Gaps

1. **INNINGS_BREAK not detected** (`prediction_engine_api.py:196-204`): When 1st innings ends and 2nd hasn't started, the code sees `current_innings` as the completed 1st innings and produces a live prediction as if 1st innings is still going. No target is set because `batting_team == first_team`.

2. **POST_TOSS doesn't adjust features**: Toss data is fetched (`prediction_engine_api.py:144-145`) but never used to modify winner probability. The only effect is `confidence += 0.05`.

3. **No SUPER_OVER state**: If a match goes to super over, the system will show "completed" or produce incorrect chase calculations.

4. **No DLS/rain interruption handling**: Revised targets under DLS are not modeled.

5. **Pre-match → live handoff is awkward**: `pre_match_predictions()` checks if the match has started and returns a redirect message (`prediction_engine_api.py:82-89`), but the frontend must know to switch tabs. There's no automatic transition.

---

## 4. Quota-Resilient Architecture

### 4A. Current Caching Layer

The caching system (`cache.py`) is well-structured with:
- In-memory `_MemoryCache` with TTL expiry
- Optional Redis backend
- Singleflight locks to prevent thundering herd
- `stale_while_revalidate` method (exists but **not used anywhere**)

**TTLs configured** (`config.py`):

| Data Type | TTL | Assessment |
|-----------|-----|------------|
| Series info | 600s (10 min) | **Too short** — series schedule changes rarely; should be 3600-86400s |
| Match info | 30s | Reasonable for pre-match; too long for live score updates |
| Overs data | 8s | Appropriate for live |
| Scorecard | 10s | Appropriate for live |
| Features | 60s | Reasonable |

### 4B. Redundant API Calls

| Issue | Location | Impact |
|-------|----------|--------|
| **`get_match_details()` called twice in pre-match** | `prediction_engine_api.py:80-81` (status check) then `prediction_engine_api.py:143-146` (toss check) | 2 API calls for same match_id; cache mitigates this but the 30s TTL means sequential calls may both miss |
| **`fetch_live_data_for_series()` called per-request** | Every `/predict/*` and `/matches` call | Series data is the **most expensive** call; 600s TTL helps but each new series_id is a cache miss |
| **`get_match_details()` called per match in `build_series_features()`** | `feature_store.py:139-140` — iterates ALL completed matches in series | For a 74-match IPL season, this could fire 74 `get_match_details()` calls on first request (before FEATURE_TTL caches) |
| **Feature build triggers nested API calls** | `build_series_features()` → `fetch_series_matches_for_id()` → then `get_match_details()` per match | Single prediction request can cascade into dozens of upstream calls |
| **Frontend calls `/update-match-context` then `/predict/pre-match`** | `PreMatchPage.tsx:66-73`, `T20WorldCupPage.tsx:117-123` | `update-match-context` calls `fetch_live_data_for_series` + `get_match_details`, then `predict/pre-match` calls them again |

### 4C. Recommendations

| Recommendation | Priority | Complexity |
|---------------|----------|------------|
| **Increase SERIES_TTL to 3600s** (or 86400s for non-live) | High | S |
| **Remove the `/update-match-context` call from frontend** — the predict endpoints already fetch everything needed | High | S |
| **Pre-warm `build_series_features()` at startup or on first request per day** | High | M |
| **Use `stale_while_revalidate` for series data** — it's already implemented in `cache.py:103-114` but never called | Medium | S |
| **Add request-coalescing layer** — currently each frontend poll triggers independent upstream calls. Multiple concurrent users would multiply calls. The singleflight lock helps per cache-key but not across different cache keys | Medium | M |
| **Separate live-score TTL from match-info TTL** — match info (teams, toss, playing XI) is static once set; live score changes every ball | Medium | S |
| **Add cache-hit/miss metrics** — currently no visibility into quota consumption | Medium | S |

### 4D. Recommended TTLs

| Data Type | Current TTL | Recommended TTL | Rationale |
|-----------|------------|----------------|-----------|
| Series schedule | 600s | 86400s (24h) | Changes only when new matches are added |
| Match info (toss, XI) | 30s | 300s (5 min) | Static once toss is done; only changes pre-toss |
| Live score (overs endpoint) | 8s | 8-15s | Appropriate for live |
| Scorecard | 10s | 15-30s | Appropriate for live; slight increase won't hurt UX |
| Features | 60s | 300s (5 min) | Built from completed matches; new data only after match ends |

---

## 5. Observability & Debuggability

### Current Response Payloads

**Pre-match response** (`prediction_engine_api.py:151-174`) includes:
- `prediction_stage` ✓
- `data_quality` ✓
- `fallback_level` ✓
- `confidence` ✓
- `uncertainty` ✓

**Missing from every prediction response:**

| Missing Field | Why It Matters | Location to Add |
|--------------|---------------|-----------------|
| **Features used** (exact values) | Can't debug why a prediction was wrong without knowing input values | `prediction_engine_api.py:151` and `:317` |
| **Fallback reason** (why venue/series/league was chosen) | "Was venue data missing, or was there not enough matches?" | `prediction_engine_api.py:100-123` |
| **Sample size** (N matches used for venue/series prior) | Low-N priors should be flagged | `feature_store.py:156-167` (venue_priors construction) |
| **Cache hit/miss per upstream call** | Can't diagnose quota consumption or stale data issues | `live_data_provider.py:20-35` |
| **Upstream call count** | How many Cricbuzz calls were made for this request | Needs request-scoped counter |
| **Request timestamp** | When was this prediction generated | `prediction_engine_api.py` response |
| **Data freshness** (age of cached data) | If series data is 9 minutes old on a 10-min TTL, that's worth knowing | `cache.py` doesn't expose age |
| **Chase priors used** | `chase_priors` are computed but never consumed — if they were, they'd need to appear | `feature_store.py:169-172` |
| **Win probability calibration info** | Is 0.65 actually calibrated or just a ratio? | All winner outputs |

### Logging Issues

| Issue | Location |
|-------|----------|
| **`print()` statements throughout** | `prediction_engine.py` (dozens), `live_data_provider.py:125,133,146-147` — these go to stdout, not structured logging |
| **No request-level correlation ID** | Can't trace a single user request through the call chain |
| **Sensitive data in logs** | `live_data_provider.py:50-54` logs last 4 chars of API key — minor but unnecessary |
| **Legacy engine logs mixed with active** | If `prediction_engine.py` is imported (it is, via `main.py` line 6 reference to `prediction_engine_api` which doesn't import it, but `prediction_engine.py` runs its module-level code on import if imported) | Actually, `prediction_engine.py` is NOT imported by `main.py` — only `prediction_engine_api.py` is. But it would be if any route used it. |

---

## 6. Test Coverage Map

### Backend

| Function / Module | Unit Test | Integration Test | Notes |
|-------------------|-----------|-----------------|-------|
| `prediction_engine_api.pre_match_predictions()` | **None** | **None** | Core prediction logic — zero tests |
| `prediction_engine_api.live_predictions()` | **None** | **None** | Core live logic — zero tests |
| `feature_store.build_series_features()` | **None** | **None** | Feature pipeline — zero tests |
| `feature_store._extract_match_scores()` | **None** | **None** | Data parsing — zero tests |
| `live_data_provider.fetch_live_data_for_series()` | **None** | **None** | API integration — zero tests |
| `live_data_provider.get_match_details()` | **None** | **None** | API integration — zero tests |
| `live_data_provider._cached_get_json()` | **None** | **None** | Caching wrapper — zero tests |
| `cache.CacheClient` | **None** | **None** | Cache layer — zero tests |
| `cache._MemoryCache` | **None** | **None** | Cache internals — zero tests |
| `config.py` | N/A | N/A | Static config |
| `utils.get_gmt_window()` | **None** | **None** | Date util — zero tests |
| `prediction_engine.py` (all functions) | **None** | **None** | Legacy dead code — zero tests |
| **main.py** route handlers | **None** | **None** | API routes — zero tests |

### Frontend

| Component | Test | Notes |
|-----------|------|-------|
| `App.test.tsx` | **Broken** — tests for "learn react" link that doesn't exist | Default CRA test, never updated |
| All pages | **None** | Zero component tests |

### Top 10 Highest-Value Test Cases (by silent regression risk)

| # | Test Case | Target Function | Risk |
|---|-----------|----------------|------|
| 1 | **`build_series_features()` returns correct venue priors from mock match data** | `feature_store.py:83` | If venue prior calculation breaks, ALL predictions use wrong base values — silent degradation |
| 2 | **`live_predictions()` correctly identifies 2nd innings and computes chase target** | `prediction_engine_api.py:196-204` | Wrong innings detection = wrong target = wrong chase = wrong winner |
| 3 | **`_cached_get_json()` returns cached value within TTL and fetches fresh after TTL** | `live_data_provider.py:20-35` | Cache bug = quota exhaustion or stale predictions |
| 4 | **`pre_match_predictions()` falls back venue → series → league correctly** | `prediction_engine_api.py:100-123` | Wrong fallback = wrong priors for unknown venues |
| 5 | **`pre_match_predictions()` returns "completed" stage for finished matches** | `prediction_engine_api.py:71-77` | If status parsing breaks, users see stale predictions for finished matches |
| 6 | **`_range_from_stats()` handles edge cases: zero std, negative avg, cap enforcement** | `prediction_engine_api.py:34-42` | Edge case = impossible ranges (negative scores) |
| 7 | **`live_predictions()` handles missing innings gracefully (falls back to pre-match)** | `prediction_engine_api.py:191-194` | Missing data = crash instead of graceful degradation |
| 8 | **`fetch_live_data_for_series()` correctly matches date format** | `live_data_provider.py:115-149` | Date format mismatch = "no matches found" for valid dates |
| 9 | **`CacheClient.with_singleflight_lock()` prevents concurrent duplicate fetches** | `cache.py:97-101` | Race condition = quota waste |
| 10 | **`get_match_details()` correctly parses toss, playing XI, and powerplay from API response** | `live_data_provider.py:273-393` | Parser breaks on API shape change = crash cascade |

---

## A. Model Intelligence Upgrades

### A1. Winner Probability — Not Using Live Match State

**File**: `prediction_engine_api.py:278-294`
**Current behavior**: During 1st innings, winner is purely form-based (`win_rate` ratio). During chase, it's binary (can_chase or can't).
**Should do**: Bayesian update on win probability using:
- Current run rate vs expected run rate for this phase
- Wickets in hand (10 - current_wickets)
- Historical win probability at this (overs, runs, wickets) state
- Required run rate delta (for chase)
**Complexity**: L

### A2. Winner Probability — No Toss Impact

**File**: `prediction_engine_api.py:95-98`
**Current behavior**: `win_probs` = ratio of win_rates. Toss data is fetched but ignored.
**Should do**: Apply venue-specific chase/bat-first win rate. The data is already computed in `feature_store.chase_priors` but never consumed.
**Complexity**: S

### A3. Score Range — No Phase-Aware Modeling

**File**: `prediction_engine_api.py:127-129`, `271-276`
**Current behavior**: `_range_from_stats(avg_runs, std_runs)` — single average for entire innings.
**Should do**: Phase-segmented run rate model:
- Powerplay (overs 1-6): typically 7-9 RPO
- Middle (overs 7-15): typically 6-8 RPO
- Death (overs 16-20): typically 9-12 RPO
- During live, use actual runs + phase-aware projected remaining
**Complexity**: M

### A4. Score Range — Live Doesn't Use Live Data

**File**: `prediction_engine_api.py:276`
**Current behavior**: `total_score_range` uses same pre-match priors during live. `projected_total` exists but is separate.
**Should do**: Replace `total_score_range` with `projected_total ± uncertainty` during live.
**Complexity**: S

### A5. Wickets — Not Conditioned on Bowling Quality

**File**: `prediction_engine_api.py:128`, `272`
**Current behavior**: Venue average wickets with no team-specific adjustment.
**Should do**: Adjust based on bowling attack composition from playing XI. Economy rate and strike rate data from historical series matches.
**Complexity**: M

### A6. Powerplay — Derived from Innings Total, Not Independent

**File**: `prediction_engine_api.py:130-132`
**Current behavior**: `pp_score = innings_range * pp_ratio` (fixed 0.28 default).
**Should do**: Independent powerplay model using team-specific powerplay averages from series history. Feature_store already collects `pp_ratio` per venue — use it with team adjustment.
**Complexity**: M

### A7. Chase Outcome — Missing Pressure Index

**File**: `prediction_engine_api.py:216-240`
**Current behavior**: Linear extrapolation: `projected = runs + current_rr * remaining_overs`.
**Should do**:
- Factor in wickets in hand (team at 100/2 chasing 180 is very different from 100/6)
- Use RRR/CRR ratio as pressure index
- Historical success rate for (target_band, overs_remaining, wickets_in_hand) triples
- Apply `chase_priors` data that's already computed but unused
**Complexity**: M

### A8. Hardcoded League Averages

**File**: `prediction_engine_api.py:10-16`
**Current behavior**: `LEAGUE_PRIORS = {"avg_runs": 160.0, "std_runs": 25.0, ...}` — static constants.
**Should do**: Derive from recent form (last N completed T20 matches across all series). Or at minimum, derive per-series from `build_series_features()` and only use league priors as absolute last resort.
**Complexity**: S

### A9. Random Jitter in Legacy Engine

**File**: `prediction_engine.py:539-541`, `688-693`, `698-703`
**Current behavior**: `random.uniform(-0.6, 0.6)` added to wickets, `random.uniform(-1.5, 1.5)` to powerplay runs. This was used to make repeated predictions look different.
**Should do**: This is in dead code, but if it ever gets revived: replace jitter with proper uncertainty quantification (confidence intervals from historical variance).
**Complexity**: S (delete the dead code)

### A10. Confidence Calculation is Hardcoded

**File**: `prediction_engine_api.py:139`, `300`
**Current behavior**: Confidence = 0.7 (venue), 0.58 (series), 0.48 (league). No adjustment for sample size, team quality, or match state.
**Should do**: Calibrated confidence based on:
- Sample size (N matches in venue/series prior)
- Variance of historical outcomes
- Match state (more data = higher confidence as match progresses)
- Prediction difficulty (close matchup = lower confidence)
**Complexity**: M

---

## B. Feature Engineering Gaps

(See Section 2A above for full table. Summary of highest-impact gaps:)

1. **Toss winner + decision** → already fetched, not used → impacts winner + score direction
2. **Playing XI** → already fetched, not used → impacts all targets via batting/bowling quality
3. **Chase priors by target band** → already computed in feature_store, not consumed → impacts chase outcome
4. **Powerplay actual data (ppData)** → already fetched and parsed, not used in predictions → impacts live powerplay
5. **1st vs 2nd innings scoring differential** → data available, not modeled → impacts score predictions

---

## C. Live State Machine Completeness

(See Section 3 above for full analysis. Critical gaps:)

1. **INNINGS_BREAK** is not detected — system treats it as 1st innings still in progress
2. **POST_TOSS** doesn't modify any prediction features
3. **No DLS/rain interruption handling**
4. **No SUPER_OVER state**
5. **Chase winner probability is binary (100% or 0%)** — should be gradated

---

## D. Quota-Resilient Architecture

(See Section 4 above for full analysis. Key actions:)

1. **Remove redundant `/update-match-context` frontend call** — saves 2 API calls per prediction request
2. **Increase series TTL from 600s to 3600s+**
3. **Use `stale_while_revalidate` for series data** (already implemented, not wired)
4. **Pre-warm features once per day**
5. **`build_series_features()` fires N `get_match_details()` calls** — batch or cache the features longer

---

## E. Observability & Debuggability

(See Section 5 above. Key additions needed:)

1. Add `features_used` dict to every prediction response
2. Add `fallback_reason` explaining why each fallback level was chosen
3. Add `sample_size` for venue/series priors
4. Add `cache_stats` (hit/miss per upstream call, data age)
5. Add `upstream_calls` count
6. Replace `print()` with structured `logger` calls throughout
7. Add request correlation IDs

---

## F. Test Coverage Map

(See Section 6 above. **Zero backend tests exist.** One broken frontend test.)

---

## 7. Additional Findings

### 7A. Dead Code (1,373 lines)

`prediction_engine.py` is entirely dead code. It:
- Imports `openai` and makes GPT-3.5 calls (`parse_query_with_gpt`, line 1258)
- Uses `eval()` on GPT output (line 1274) — **security vulnerability**
- Loads data at module level (line 180: `recent_matches_df, recent_deliveries_df = load_ipl_data()`)
- Contains NLP query handler with regex patterns (lines 1048-1141)
- Has duplicate function definitions (`load_2025_mock_data` at lines 75 and 730)

**Recommendation**: Delete `prediction_engine.py` entirely. If any functions are needed later, they should be rewritten.

### 7B. Security Issues

| Issue | Location | Severity |
|-------|----------|----------|
| `eval()` on GPT output | `prediction_engine.py:1274` | **High** (dead code, but dangerous if revived) |
| API key in `.env` committed to untracked files | `backend/.env` | Medium (listed in .gitignore presumably) |
| CORS allows only localhost:3000 | `main.py:18-24` | Fine for dev, needs update for production |
| No rate limiting on API endpoints | `main.py` | Medium — direct access could exhaust Cricbuzz quota |
| No authentication on prediction endpoints | `main.py` | Low — Firebase auth exists in frontend but backend doesn't verify tokens |

### 7C. Frontend Issues

| Issue | Location |
|-------|----------|
| **Hardcoded localhost URLs** | `LiveMatchPage.tsx:63,89`, `PreMatchPage.tsx:42,66,72`, `T20WorldCupPage.tsx:92` — should use `api.ts` |
| **`api.ts` exists but is unused** | `frontend/src/api.ts` configures axios but no page uses it |
| **IPL series_id hardcoded in multiple places** | `LiveMatchPage.tsx:36`, `PreMatchPage.tsx:9`, `T20WorldCupPage.tsx:59` |
| **Duplicate fetch patterns** | Each page reimplements the same fetch-matches + fetch-predictions pattern |
| **No auto-refresh for live predictions** | User must manually click buttons to refresh |
| **No loading state for match list** | `useEffect` fetches matches silently |

### 7D. Decision Engine Gap

`PRODUCT_TRUTH.md` describes the product as a "real-time fantasy decision assistant" with 15 defined decision moments, latent state layers (momentum, collapse risk, acceleration window), and counterfactual simulation. `IMPLEMENTATION_PLAN.md` references a `decision_engine.py` that was deleted (`git status` shows `D backend/decision_engine.py`).

**The entire decision-moment architecture described in the product docs is unimplemented.** The current system is a basic prediction app, not a decision assistant.

---

## 8. Prioritized Implementation Backlog

| # | Task | Target | Complexity | Impact | Depends On |
|---|------|--------|-----------|--------|------------|
| 1 | Delete `prediction_engine.py` (dead code with eval vulnerability) | Cleanup | S | High (security) | None |
| 2 | Write unit tests for top-10 test cases (Section 6) | All targets | M | High (regression safety) | None |
| 3 | Wire toss data into winner probability | Winner | S | High | None |
| 4 | Consume `chase_priors` in chase outcome calculation | Chase | S | High | None |
| 5 | Add innings-break state detection | State machine | S | High | None |
| 6 | Remove frontend `/update-match-context` redundant call | Quota | S | High | None |
| 7 | Increase SERIES_TTL and wire `stale_while_revalidate` | Quota | S | High | None |
| 8 | Use live data (runs, wickets, overs) to adjust `total_score_range` during live | Score | S | High | None |
| 9 | Add `features_used`, `fallback_reason`, `sample_size` to prediction responses | Observability | S | Medium | None |
| 10 | Replace `print()` with structured logging + add request correlation IDs | Observability | S | Medium | None |
| 11 | Factor wickets-in-hand into chase outcome | Chase | M | High | #4 |
| 12 | Add phase-aware run rate model (powerplay/middle/death) | Score, PP | M | High | None |
| 13 | Build independent powerplay prediction model | Powerplay | M | Medium | #12 |
| 14 | Adjust wickets prediction for bowling attack quality from playing XI | Wickets | M | Medium | None |
| 15 | Live winner probability using (overs, runs, wickets) historical lookup | Winner | L | High | #2, #12 |
| 16 | Pre-warm `build_series_features()` at startup / cron | Quota | M | Medium | #7 |
| 17 | Calibrated confidence from sample size + variance | All targets | M | Medium | #9 |
| 18 | Add request-coalescing layer for concurrent frontend polls | Quota | M | Medium | #7 |
| 19 | Fix frontend to use `api.ts` instead of hardcoded URLs | Frontend | S | Medium | None |
| 20 | Add auto-refresh (polling) for live predictions | Frontend | S | Medium | #18 |
| 21 | Implement decision-moment engine per PRODUCT_TRUTH.md | All | L | Critical (product-market fit) | #15, #12, #14 |
| 22 | Add rate limiting to API endpoints | Security | S | Medium | None |
| 23 | Add backend token verification for Firebase auth | Security | M | Medium | None |
| 24 | Handle DLS / rain interruption in live predictions | Chase, Score | M | Low (rare) | #5 |
| 25 | Add super-over state handling | State machine | S | Low (rare) | #5 |

### Recommended Sprint Groupings

**Sprint 1 — Foundations** (items 1, 2, 6, 7, 9, 10, 19): Remove dead code, add tests, fix redundant calls, improve observability. Zero prediction logic changes — pure reliability and debuggability.

**Sprint 2 — Quick Wins** (items 3, 4, 5, 8): Wire existing data that's already fetched but unused. Toss impact, chase priors, innings break, live score adjustment. Each is a small change with measurable prediction improvement.

**Sprint 3 — Model Upgrades** (items 11, 12, 13, 14, 17): Phase-aware scoring, wickets-in-hand for chase, bowling quality, calibrated confidence. This is where prediction quality makes a significant jump.

**Sprint 4 — Live Intelligence** (items 15, 16, 18, 20): Real-time win probability model, feature pre-warming, request coalescing, auto-refresh. This makes the live experience competitive.

**Sprint 5 — Decision Engine** (item 21): Implement the decision-moment architecture from PRODUCT_TRUTH.md. This is the largest effort and transforms the product from "predictor" to "decision assistant."
