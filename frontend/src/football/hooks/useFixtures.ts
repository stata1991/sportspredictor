import { useState, useEffect, useRef, useCallback } from 'react';
import api from '../../api';
import { AFFixture, FixturesResponse } from '../types/fixture';
import { isInPlay } from '../utils/fixtureStatus';

// Cadence while a match is live — frequent enough to keep score/minute fresh.
const LIVE_REFRESH_INTERVAL_MS = 60_000;
// Cadence while idle. The poll KEEPS RUNNING when nothing is live (slower),
// so a kickoff is discovered within a couple of minutes — the LIVETAB-2
// cold-start fix. Before this, scheduling was gated on anyLive(): an all-NS
// snapshot armed no timer and the Live tab stayed frozen until a manual
// reload. The fixtures list is one shared, short-TTL-cached backend key, so
// idle polling is not per-user upstream load.
const IDLE_REFRESH_INTERVAL_MS = 150_000;

export interface UseFixturesOptions {
  /** Cadence while a match is live. Defaults to 60s; tests inject a short value. */
  liveRefreshIntervalMs?: number;
  /** Cadence while idle (discovery). Defaults to 150s; tests inject a short value. */
  idleRefreshIntervalMs?: number;
}

export function useFixtures(options?: UseFixturesOptions) {
  const liveIntervalMs =
    options?.liveRefreshIntervalMs ?? LIVE_REFRESH_INTERVAL_MS;
  const idleIntervalMs =
    options?.idleRefreshIntervalMs ?? IDLE_REFRESH_INTERVAL_MS;
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

  // Always arm the next poll while the tab is visible; anyLive() only picks
  // the CADENCE, not whether to poll. This is the fix: an idle list keeps
  // polling (slowly), so it can transition idle → live and discover a
  // kickoff instead of freezing on the pre-match snapshot. clearTimer()
  // first guarantees a single in-flight timer (no stacking).
  const scheduleNext = useCallback(() => {
    clearTimer();
    if (!mountedRef.current || document.hidden) return;
    const delay = anyLive() ? liveIntervalMs : idleIntervalMs;
    timeoutRef.current = setTimeout(async () => {
      timeoutRef.current = null;
      if (!mountedRef.current || document.hidden) return;
      await fetchFixtures(true);
      scheduleNext();
    }, delay);
  }, [anyLive, clearTimer, fetchFixtures, liveIntervalMs, idleIntervalMs]);

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

  // Pause when the tab is hidden; on becoming visible, refetch immediately
  // (a match may have kicked off while hidden — refetch regardless of the
  // last-known live state) and resume scheduling.
  useEffect(() => {
    const handleVisibility = () => {
      if (document.hidden) {
        clearTimer();
      } else if (mountedRef.current) {
        (async () => {
          await fetchFixtures(true);
          scheduleNext();
        })();
      }
    };
    document.addEventListener('visibilitychange', handleVisibility);
    return () =>
      document.removeEventListener('visibilitychange', handleVisibility);
  }, [clearTimer, fetchFixtures, scheduleNext]);

  return { fixtures, loading, error };
}
