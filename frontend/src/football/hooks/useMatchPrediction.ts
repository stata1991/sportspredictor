import { useState, useEffect } from 'react';
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

export type ErrorKind = 'completed' | 'not_predictable' | 'not_found' | 'network' | 'unknown';

export interface UseMatchPredictionResult {
  prediction: DeterministicPrediction | null;
  reasoning: Reasoning | null;
  upset: Upset | null;
  stage: FixtureStage | null;
  homeTeam: string | null;
  awayTeam: string | null;
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
  homeTeam: null,
  awayTeam: null,
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
 *   422 + detail contains "not predictable" → 'not_predictable'
 *   422 (other, e.g. live redirect)         → 'not_predictable'
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
      if (detail.includes('not predictable')) return 'not_predictable';
      // Live redirect also comes as 422
      return 'not_predictable';
    }
    if (status !== undefined) return 'network'; // 500, 502, 503, etc.
    // No response — true network failure
    return 'network';
  }
  return 'unknown';
}

// ── Hook ───────────────────────────────────────────────────────────

export function useMatchPrediction(
  fixtureId: string | undefined,
): UseMatchPredictionResult {
  const [result, setResult] = useState<UseMatchPredictionResult>(
    // Skip fetch if fixtureId is absent
    fixtureId ? { ...IDLE, loading: true } : IDLE,
  );

  useEffect(() => {
    if (!fixtureId) {
      setResult(IDLE);
      return;
    }

    const controller = new AbortController();

    const fetchPrediction = async () => {
      setResult((prev) => ({ ...prev, loading: true, error: null, errorKind: null }));

      try {
        const res = await api.get<PreMatchPredictionResponse>(
          `/api/football/predict/pre-match/${fixtureId}`,
          { signal: controller.signal },
        );

        if (controller.signal.aborted) return;

        const data = res.data;

        // Determine if we have a partial agent result
        const hasReasoning = data.reasoning !== null && data.reasoning !== undefined;

        setResult({
          prediction: data.predictions,
          reasoning: data.reasoning ?? null,
          upset: data.upset ?? null,
          stage: data.stage,
          homeTeam: data.home_team,
          awayTeam: data.away_team,
          partialAgent: !hasReasoning,
          loading: false,
          error: null,
          errorKind: null,
        });
      } catch (err: unknown) {
        if (controller.signal.aborted) return;

        const errorKind = classifyError(err);
        const message = err instanceof Error ? err.message : String(err);

        setResult({
          prediction: null,
          reasoning: null,
          upset: null,
          stage: null,
          homeTeam: null,
          awayTeam: null,
          partialAgent: false,
          loading: false,
          error: new Error(message),
          errorKind,
        });
      }
    };

    fetchPrediction();

    return () => {
      controller.abort();
    };
  }, [fixtureId]);

  return result;
}
