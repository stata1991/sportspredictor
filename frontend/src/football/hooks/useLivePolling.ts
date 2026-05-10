import { useState, useEffect, useRef, useCallback } from 'react';
import api from '../../api';

export interface UseLivePollingOptions<T> {
  url: string;
  intervalMs: number;
  enabled: boolean;
  maxBackoffMs?: number;
  parseResponse?: (raw: unknown) => T;
}

export interface UseLivePollingResult<T> {
  data: T | null;
  error: Error | null;
  isPolling: boolean;
  lastUpdated: Date | null;
  refetch: () => Promise<void>;
}

const DEFAULT_MAX_BACKOFF = 300_000;

export function useLivePolling<T>(
  opts: UseLivePollingOptions<T>,
): UseLivePollingResult<T> {
  const { url, intervalMs, enabled, maxBackoffMs = DEFAULT_MAX_BACKOFF, parseResponse } = opts;

  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [isPolling, setIsPolling] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  // Mutable refs to avoid stale closures
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const controllerRef = useRef<AbortController | null>(null);
  const requestIdRef = useRef(0);
  const consecutiveFailuresRef = useRef(0);
  const mountedRef = useRef(true);
  const lastUpdatedRef = useRef<Date | null>(null);
  const parseResponseRef = useRef(parseResponse);
  parseResponseRef.current = parseResponse;

  // Keep refs in sync for visibility handler
  const enabledRef = useRef(enabled);
  enabledRef.current = enabled;
  const intervalMsRef = useRef(intervalMs);
  intervalMsRef.current = intervalMs;
  const urlRef = useRef(url);
  urlRef.current = url;

  const clearPending = useCallback(() => {
    if (timeoutRef.current !== null) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
    if (controllerRef.current) {
      controllerRef.current.abort();
      controllerRef.current = null;
    }
  }, []);

  const getBackoff = useCallback(() => {
    const failures = consecutiveFailuresRef.current;
    if (failures === 0) return intervalMsRef.current;
    const backoff = intervalMsRef.current * Math.pow(2, failures);
    return Math.min(backoff, maxBackoffMs);
  }, [maxBackoffMs]);

  const doFetch = useCallback(async () => {
    if (!mountedRef.current) return;

    // Abort any previous in-flight request
    if (controllerRef.current) {
      controllerRef.current.abort();
    }

    const controller = new AbortController();
    controllerRef.current = controller;
    const id = ++requestIdRef.current;

    try {
      const res = await api.get(urlRef.current, { signal: controller.signal });

      // Race-safe: only commit if this is still the latest request
      if (id !== requestIdRef.current || !mountedRef.current) return;

      const parsed = parseResponseRef.current
        ? parseResponseRef.current(res.data)
        : (res.data as T);

      setData(parsed);
      setError(null);
      const now = new Date();
      setLastUpdated(now);
      lastUpdatedRef.current = now;
      consecutiveFailuresRef.current = 0;
    } catch (err: unknown) {
      if (controller.signal.aborted) return;
      if (id !== requestIdRef.current || !mountedRef.current) return;

      consecutiveFailuresRef.current += 1;
      setError(err instanceof Error ? err : new Error(String(err)));
    }
  }, []);

  const schedulePoll = useCallback(() => {
    if (!mountedRef.current || !enabledRef.current) return;

    const delay = getBackoff();
    timeoutRef.current = setTimeout(async () => {
      timeoutRef.current = null;
      await doFetch();
      // Schedule next only if still enabled and mounted
      if (mountedRef.current && enabledRef.current) {
        schedulePoll();
      }
    }, delay);
  }, [doFetch, getBackoff]);

  // Manual refetch — skips backoff, resets failure count
  const refetch = useCallback(async () => {
    clearPending();
    consecutiveFailuresRef.current = 0;
    await doFetch();
    if (mountedRef.current && enabledRef.current) {
      schedulePoll();
    }
  }, [clearPending, doFetch, schedulePoll]);

  // Main effect: start/stop polling when enabled or url changes
  useEffect(() => {
    mountedRef.current = true;

    if (!enabled) {
      clearPending();
      setIsPolling(false);
      return;
    }

    setIsPolling(true);
    consecutiveFailuresRef.current = 0;

    // Initial fetch immediate
    (async () => {
      await doFetch();
      if (mountedRef.current && enabledRef.current) {
        schedulePoll();
      }
    })();

    return () => {
      mountedRef.current = false;
      clearPending();
      setIsPolling(false);
    };
  }, [enabled, url, clearPending, doFetch, schedulePoll]);

  // Visibility handler
  useEffect(() => {
    if (!enabled) return;

    const handleVisibility = () => {
      if (document.hidden) {
        // Tab hidden: stop polling, abort in-flight
        clearPending();
      } else {
        // Tab visible: resume
        if (!enabledRef.current || !mountedRef.current) return;

        const now = Date.now();
        const last = lastUpdatedRef.current
          ? lastUpdatedRef.current.getTime()
          : 0;
        const elapsed = now - last;

        if (elapsed >= intervalMsRef.current) {
          // Stale — fetch immediately then resume schedule
          (async () => {
            await doFetch();
            if (mountedRef.current && enabledRef.current) {
              schedulePoll();
            }
          })();
        } else {
          // Schedule remaining time
          const remaining = intervalMsRef.current - elapsed;
          timeoutRef.current = setTimeout(async () => {
            timeoutRef.current = null;
            await doFetch();
            if (mountedRef.current && enabledRef.current) {
              schedulePoll();
            }
          }, remaining);
        }
      }
    };

    document.addEventListener('visibilitychange', handleVisibility);
    return () => {
      document.removeEventListener('visibilitychange', handleVisibility);
    };
  }, [enabled, clearPending, doFetch, schedulePoll]);

  return { data, error, isPolling, lastUpdated, refetch };
}
