import { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import api from '../../api';
import {
  DeterministicPrediction,
  FixtureStage,
  Reasoning,
  Upset,
  PreMatchPredictionResponse,
} from '../types/prediction';

// ── Public types ───────────────────────────────────────────────────

export type ErrorKind = 'completed' | 'live' | 'not_predictable' | 'not_found' | 'network' | 'unknown';

export interface UseMatchPredictionResult {
  prediction: DeterministicPrediction | null;
  reasoning: Reasoning | null;
  upset: Upset | null;
  stage: FixtureStage | null;
  round: string | null;
  fixtureStatus: string | null;
  homeTeam: string | null;
  awayTeam: string | null;
  homeTeamId: number | null;
  awayTeamId: number | null;
  partialAgent: boolean;
  loading: boolean;
  error: Error | null;
  errorKind: ErrorKind | null;
}

// ── Initial state ──────────────────────────────────────────────────

const IDLE: UseMatchPredictionResult = {
  prediction: null,
  reasoning: null,
  upset: null,
  stage: null,
  round: null,
  fixtureStatus: null,
  homeTeam: null,
  awayTeam: null,
  homeTeamId: null,
  awayTeamId: null,
  partialAgent: false,
  loading: false,
  error: null,
  errorKind: null,
};

// ── Error kind discriminator ───────────────────────────────────────

/**
 * Classify an axios error into an ErrorKind.
 *
 * Mapping (verified against live backend):
 *   422 + detail contains "live"            → 'live'
 *   422 + detail contains "not predictable" → 'not_predictable'
 *   404                                     → 'not_found'
 *   Other 4xx / 5xx                         → 'network'
 *   No response (network failure)           → 'network'
 *   Anything else                           → 'unknown'
 */
function classifyError(err: unknown): ErrorKind {
  if (axios.isAxiosError(err)) {
    const status = err.response?.status;
    // FastAPI may return detail as a list of objects for pydantic validation
    // errors, so guard against non-string values to avoid .includes() crash.
    const rawDetail = err.response?.data?.detail;
    const detail: string = typeof rawDetail === 'string' ? rawDetail : '';

    if (status === 404) return 'not_found';
    if (status === 422) {
      if (detail.includes('live')) return 'live';
      return 'not_predictable';
    }
    if (status !== undefined) return 'network'; // 500, 502, 503, etc.
    // No response — true network failure
    return 'network';
  }
  return 'unknown';
}

/**
 * Extract the fixture status code from a 422 error detail string.
 * e.g. "Fixture status 'PST' is not predictable" → 'PST'
 */
function parseFixtureStatusFromError(err: unknown): string | null {
  if (axios.isAxiosError(err)) {
    const rawDetail = err.response?.data?.detail;
    if (typeof rawDetail === 'string') {
      const match = rawDetail.match(/'(\w+)'/);
      return match ? match[1] : null;
    }
  }
  return null;
}

// ── Transition refresh (POLL-FIX-1) ────────────────────────────────

// While the detail is open + visible, re-check on this cadence so the page
// discovers NS→live and live→FT without a manual reload — the LIVETAB-2
// cadence-not-gate fix, on the detail path. Polling STOPS once a terminal
// state is reached (don't poll a finished match forever — the inverse
// hazard). Backed by the 15s live-aware get_fixture TTL (POLL-FIX-1 #1),
// so a real FT is visible within ~15-30s.
const DEFAULT_POLL_INTERVAL_MS = 30_000;

export interface UseMatchPredictionOptions {
  /** Transition-refresh cadence. Defaults to 30s; tests inject a short value. */
  pollIntervalMs?: number;
}

function isTerminal(r: UseMatchPredictionResult): boolean {
  // A finished match, a missing fixture, or a non-predictable status are
  // terminal — nothing left to transition to, so stop refreshing.
  return (
    r.stage === 'completed' ||
    r.errorKind === 'not_found' ||
    r.errorKind === 'not_predictable'
  );
}

// ── Hook ───────────────────────────────────────────────────────────

export function useMatchPrediction(
  fixtureId: string | undefined,
  options?: UseMatchPredictionOptions,
): UseMatchPredictionResult {
  const intervalMs = options?.pollIntervalMs ?? DEFAULT_POLL_INTERVAL_MS;
  const [result, setResult] = useState<UseMatchPredictionResult>(
    // Skip fetch if fixtureId is absent
    fixtureId ? { ...IDLE, loading: true } : IDLE,
  );
  // Kept fresh inside the fetch so the poll loop's terminal check never
  // reads a stale render.
  const resultRef = useRef(result);

  useEffect(() => {
    if (!fixtureId) {
      setResult(IDLE);
      return;
    }

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let controller: AbortController | null = null;

    const clearTimer = () => {
      if (timer !== null) {
        clearTimeout(timer);
        timer = null;
      }
    };

    const commit = (next: UseMatchPredictionResult) => {
      resultRef.current = next;
      setResult(next);
    };

    // `silent` skips the loading flicker on refresh polls (only the first
    // load shows a spinner) and preserves prior data on a transient network
    // blip instead of blowing the live view away.
    const fetchOnce = async (silent: boolean) => {
      if (controller) controller.abort();
      controller = new AbortController();
      const signal = controller.signal;

      if (!silent) {
        commit({ ...resultRef.current, loading: true, error: null, errorKind: null });
      }

      try {
        const res = await api.get<PreMatchPredictionResponse>(
          `/api/football/predict/pre-match/${fixtureId}`,
          { signal },
        );
        if (cancelled || signal.aborted) return;

        const data = res.data;
        const hasReasoning = data.reasoning !== null && data.reasoning !== undefined;

        commit({
          prediction: data.predictions,
          reasoning: data.reasoning ?? null,
          upset: data.upset ?? null,
          stage: data.stage,
          round: data.round ?? null,
          fixtureStatus: data.status,
          homeTeam: data.home_team,
          awayTeam: data.away_team,
          homeTeamId: data.home_team_id ?? null,
          awayTeamId: data.away_team_id ?? null,
          partialAgent: !hasReasoning,
          loading: false,
          error: null,
          errorKind: null,
        });
      } catch (err: unknown) {
        if (cancelled || signal.aborted) return;

        const errorKind = classifyError(err);
        // A transient blip on a silent refresh must not destroy the live
        // view — keep prior state and let the next tick retry. Meaningful
        // status errors (422 live/not_predictable, 404) DO apply, since
        // they ARE the transition we're watching for.
        if (silent && errorKind === 'network') return;

        const fixtureStatus = parseFixtureStatusFromError(err);
        const message = err instanceof Error ? err.message : String(err);

        commit({
          prediction: null,
          reasoning: null,
          upset: null,
          stage: null,
          round: null,
          fixtureStatus,
          homeTeam: null,
          awayTeam: null,
          homeTeamId: null,
          awayTeamId: null,
          partialAgent: false,
          loading: false,
          error: new Error(message),
          errorKind,
        });
      }
    };

    const schedule = () => {
      clearTimer();
      if (cancelled || document.hidden || isTerminal(resultRef.current)) return;
      timer = setTimeout(async () => {
        timer = null;
        if (cancelled || document.hidden || isTerminal(resultRef.current)) return;
        await fetchOnce(true);
        schedule();
      }, intervalMs);
    };

    (async () => {
      await fetchOnce(false);
      schedule();
    })();

    // Pause while hidden; on becoming visible, refresh once (a transition
    // may have happened while hidden) and resume — unless terminal.
    const handleVisibility = () => {
      if (document.hidden) {
        clearTimer();
      } else if (!cancelled && !isTerminal(resultRef.current)) {
        (async () => {
          await fetchOnce(true);
          schedule();
        })();
      }
    };
    document.addEventListener('visibilitychange', handleVisibility);

    return () => {
      cancelled = true;
      clearTimer();
      if (controller) controller.abort();
      document.removeEventListener('visibilitychange', handleVisibility);
    };
  }, [fixtureId, intervalMs]);

  return result;
}
