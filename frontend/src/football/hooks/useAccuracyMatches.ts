import { useState, useEffect } from 'react';
import api from '../../api';
import { MatchReceipt, AccuracyMatchesResponse } from '../types/accuracy';

/** Fetch the match-wise Track Record receipts (newest first). */
export function useAccuracyMatches() {
  const [matches, setMatches] = useState<MatchReceipt[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    const fetchMatches = async () => {
      setLoading(true);
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
        setError(err instanceof Error ? err.message : String(err));
        setMatches([]);
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    };
    fetchMatches();

    return () => controller.abort();
  }, []);

  return { matches, loading, error };
}
