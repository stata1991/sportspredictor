import { useState, useEffect, useRef, useCallback } from 'react';
import api from '../../api';
import { MatchReceipt, AccuracyMatchesResponse } from '../types/accuracy';

/** Fetch the match-wise Track Record receipts (newest first).
 *
 * EVAL-3 / TRACK-4 #3: the writer (eval scheduler) advances the outcomes table
 * in the background, but this hook was one-shot + the endpoint has a 300s CDN
 * cache — so an already-open Track Record tab never picked up newly-graded
 * matches without a manual reload.  Mirrors the POLL-FIX-1 refetch-on-focus
 * pattern: a silent refetch when the tab regains focus / visibility, so an
 * open tab self-heals once the scheduler ingests new outcomes.  No polling
 * timer — the page isn't a live surface; focus is the right, cheap trigger.
 */
export function useAccuracyMatches() {
  const [matches, setMatches] = useState<MatchReceipt[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Track the in-flight controller so a focus-triggered refetch can supersede
  // an earlier one and unmount can abort whatever is open.
  const controllerRef = useRef<AbortController | null>(null);

  const fetchMatches = useCallback(async (silent: boolean) => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;

    // Initial load shows a spinner; focus refetches are silent (no flicker).
    if (!silent) setLoading(true);
    setError(null);
    try {
      const res = await api.get<AccuracyMatchesResponse>(
        '/api/football/accuracy/matches',
        { signal: controller.signal },
      );
      if (!controller.signal.aborted) {
        setMatches(Array.isArray(res.data.matches) ? res.data.matches : []);
      }
    } catch (err: unknown) {
      if (controller.signal.aborted) return;
      // A failed silent refetch must NOT blow away already-rendered receipts —
      // only surface the error on the initial load.
      if (!silent) {
        setError(err instanceof Error ? err.message : String(err));
        setMatches([]);
      }
    } finally {
      if (!controller.signal.aborted && !silent) setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchMatches(false);

    const onFocus = () => {
      if (!document.hidden) fetchMatches(true);
    };
    window.addEventListener('focus', onFocus);
    document.addEventListener('visibilitychange', onFocus);

    return () => {
      window.removeEventListener('focus', onFocus);
      document.removeEventListener('visibilitychange', onFocus);
      controllerRef.current?.abort();
    };
  }, [fetchMatches]);

  return { matches, loading, error };
}
