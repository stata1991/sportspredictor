import { useState, useEffect, useRef, useCallback } from 'react';
import api from '../../api';
import { AFFixture, FixturesResponse } from '../types/fixture';
import { isInPlay } from '../utils/fixtureStatus';

// Conservative cadence — matches MatchPage's live polling (60s). The shared
// fixtures source refreshes (score/status/elapsed only) while at least one
// loaded fixture is in play AND the document is visible; idle otherwise.
const LIVE_REFRESH_INTERVAL_MS = 60_000;

export interface UseFixturesOptions {
  /** Live-refresh cadence. Defaults to 60s (matches MatchPage); tests inject
   *  a short value. */
  liveRefreshIntervalMs?: number;
}

export function useFixtures(options?: UseFixturesOptions) {
  const intervalMs = options?.liveRefreshIntervalMs ?? LIVE_REFRESH_INTERVAL_MS;
  const [fixtures, setFixtures] = useState<AFFixture[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Mutable refs to avoid stale closures inside the poll loop / listeners.
  const fixturesRef = useRef<AFFixture[]>([]);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const controllerRef = useRef<AbortController | null>(null);
  const requestIdRef = useRef(0);
  const mountedRef = useRef(true);

  const anyLive = useCallback(
    () => fixturesRef.current.some((f) => isInPlay(f.fixture.status.short)),
    [],
  );

  const clearTimer = useCallback(() => {
    if (timeoutRef.current !== null) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
  }, []);

  // Fetch the fixtures list. `live` only affects the cache TTL (?live=1),
  // never the data shape — this endpoint carries no prediction values, so a
  // refresh can never overwrite or re-trigger prediction generation.
  const fetchFixtures = useCallback(async (live: boolean) => {
    if (controllerRef.current) controllerRef.current.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    const id = ++requestIdRef.current;

    try {
      const res = await api.get<FixturesResponse>(
        live ? '/api/football/fixtures?live=1' : '/api/football/fixtures',
        { signal: controller.signal },
      );
      if (id !== requestIdRef.current || !mountedRef.current) return;
      const next = Array.isArray(res.data.fixtures) ? res.data.fixtures : [];
      fixturesRef.current = next;
      setFixtures(next);
      setError(null);
    } catch (err: unknown) {
      if (controller.signal.aborted) return;
      if (id !== requestIdRef.current || !mountedRef.current) return;
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      if (mountedRef.current && id === requestIdRef.current) setLoading(false);
    }
  }, []);

  // Schedule the next live refresh only while a match is live and visible.
  const scheduleNext = useCallback(() => {
    clearTimer();
    if (!mountedRef.current || !anyLive() || document.hidden) return;
    timeoutRef.current = setTimeout(async () => {
      timeoutRef.current = null;
      if (!mountedRef.current || !anyLive() || document.hidden) return;
      await fetchFixtures(true);
      scheduleNext();
    }, intervalMs);
  }, [anyLive, clearTimer, fetchFixtures, intervalMs]);

  // Initial load + start the refresh loop.
  useEffect(() => {
    mountedRef.current = true;
    (async () => {
      await fetchFixtures(false);
      scheduleNext();
    })();
    return () => {
      mountedRef.current = false;
      clearTimer();
      if (controllerRef.current) controllerRef.current.abort();
    };
  }, [fetchFixtures, scheduleNext, clearTimer]);

  // Pause when the tab is hidden, resume (and catch up) when visible again.
  useEffect(() => {
    const handleVisibility = () => {
      if (document.hidden) {
        clearTimer();
      } else if (mountedRef.current && anyLive()) {
        (async () => {
          await fetchFixtures(true);
          scheduleNext();
        })();
      }
    };
    document.addEventListener('visibilitychange', handleVisibility);
    return () =>
      document.removeEventListener('visibilitychange', handleVisibility);
  }, [anyLive, clearTimer, fetchFixtures, scheduleNext]);

  return { fixtures, loading, error };
}
