# Carryover Inspection Report

**Date:** 2026-05-29

---

## 1. Three Paths to Upset

### Status: **Complete**

The feature is fully implemented across the entire stack. No gaps.

### Backend generation

The Anthropic agent generates `upset_paths` — exactly 0 or 3 entries — via prompt instructions in `backend/football/agent/prompts.py:162-166`:

```
6. **Upset paths are conditional**: Only include upset_paths (exactly 3 entries)
when the favourite's win probability exceeds 65%. In all other cases, set
upset_paths to an empty array `[]`. Each upset path must be a concrete scenario
grounded in tool results.
```

Parsing in `backend/football/agent/client.py:504-522` enforces the 0-or-3 constraint:

```python
upset_paths = data.get("upset_paths")
if not isinstance(upset_paths, list):
    raise AgentParseError(raw_text, "'upset_paths' must be an array")
if len(upset_paths) not in (0, 3):
    raise AgentParseError(
        raw_text,
        f"'upset_paths' must have 0 or 3 entries, got {len(upset_paths)}",
    )
```

### Backend gating

`backend/football/agent/upset.py:74-75` defines `UPSET_PATHS_THRESHOLD = 0.65`. In `compute_upset_index()` (line 196), paths are only passed through when the favourite's win probability exceeds 65%:

```python
paths: list[str] = []
if _favourite_exceeds_threshold(bundle) and reasoning.upset_paths:
    paths = reasoning.upset_paths
```

### API response

Routes include `upset_paths` in both:
- `/predict/pre-match/{id}` → `_upset_to_dict()` in `routes.py:121-133`
- `/upsets` → `pred.payload.get("upset_paths", [])` in `routes.py:341`

### Frontend rendering

`frontend/src/football/components/whypanel/UpsetSection.tsx` renders the section on MatchPage:
- Gate: `favouriteProbability > 0.65 && upset.upset_paths.length > 0`
- Heading: "Three paths to {favouriteTeam} losing this."
- Three numbered cards (1, 2, 3) with agent-generated text
- Share button (native on mobile, clipboard on desktop)
- `data-testid="upset-heading"`, `data-testid="upset-path-0"` through `upset-path-2`

Integrated in `WhyPanel.tsx:32-82` which derives favouriteProbability and passes to `<UpsetSection>`.

UpsetsPage (`UpsetsPage.tsx:209`) shows upset_index badge only — clicking navigates to MatchPage for the full three-paths view.

### Test coverage

`frontend/src/football/components/whypanel/__tests__/UpsetSection.test.tsx` covers:
- Renders nothing when `upset_paths` empty even if probability > 0.65
- Renders nothing when probability <= 0.65 even with paths
- Renders three numbered cards when both gates pass
- Heading uses favourite team name

### Finding

Nothing to do. Feature is complete end-to-end: agent prompt → parsing with validation → gating on 65% threshold → API response → frontend conditional rendering with tests.

---

## 2. Upset Watch Threshold

### Status: **Complete, with minor tech debt**

The threshold is **0.45** (not 0.5). It's applied correctly but repeated in 4 locations without a single named constant.

### Authoritative declaration

`backend/football/routes.py:282`:

```python
@router.get("/upsets")
async def list_upsets(
    response: Response,
    threshold: float = Query(0.45, ge=0.0, le=1.0),
    ...
```

### Database query

`backend/football/persistence.py:144-146`:

```python
async def get_upsets_above_threshold(
    session: AsyncSession,
    threshold: float = 0.45,
) -> list[Prediction]:
```

Filters with `Prediction.upset_index >= threshold_decimal` (line 177).

### Frontend hook

`frontend/src/football/hooks/useUpsets.ts:5`:

```typescript
export function useUpsets(threshold: number = 0.45) {
```

### Frontend page

`frontend/src/pages/football/UpsetsPage.tsx:169`:

```typescript
const { upsets, loading, error } = useUpsets(0.45);
```

### Where the threshold is NOT

- `backend/shared/settings.py` — no upset threshold setting
- `backend/football/constants.py` — no named constant
- No environment variable controls it

### Distinction from other constants

`backend/football/agent/upset.py` contains calculation-related constants that are NOT the filter threshold:
- `FAVOURITE_FLOOR = 0.55` — gate for upset_index computation
- `FAVOURITE_CEILING = 0.85` — full vulnerability ceiling
- `UPSET_PATHS_THRESHOLD = 0.65` — gate for generating three paths
- `LOW_SCORING_THRESHOLD = 3.0` — expected goals threshold

These are internal computation parameters, not the user-facing filter threshold.

### Finding

The threshold is correctly 0.45 (not 0.5 as the handoff assumed), uses `>=`, and is consistently applied. The operator is correct: `>=` means a match with upset_index of exactly 0.45 qualifies.

**Tech debt:** The value `0.45` is hardcoded in 4 locations. A centralized `UPSET_WATCH_DEFAULT_THRESHOLD = 0.45` constant in `constants.py` would be cleaner, but this is cosmetic — all 4 locations agree, the route accepts a query param override (`?threshold=0.6`), and the value is unlikely to change during the tournament.

---

## 3. Recommendation

**Both items are clean.** No gaps require fixing before the May 31 freeze.

- **Three Paths to Upset:** Fully complete. No action needed.
- **Upset Watch threshold:** Operationally complete at 0.45 with `>=`. The 4-location repetition is tech debt worth noting but not worth a code change during freeze prep — it doesn't affect correctness, and the route already supports override via query param. If the threshold needs to change during the tournament, updating 4 literals takes 30 seconds.

**Proceed directly to P1.6.**
