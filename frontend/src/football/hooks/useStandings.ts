import { useState, useEffect } from 'react';
import api from '../../api';
import { StandingsResponse, StandingEntry } from '../types/standings';

export function useStandings() {
  const [groups, setGroups] = useState<StandingEntry[][]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    const fetchStandings = async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await api.get<StandingsResponse>('/api/football/standings', {
          signal: controller.signal,
        });
        if (!controller.signal.aborted) {
          const league = res.data.league;
          setGroups(league?.standings ?? []);
        }
      } catch (err: unknown) {
        if (controller.signal.aborted) return;
        const msg = err instanceof Error ? err.message : String(err);
        setError(msg);
        setGroups([]);
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      }
    };
    fetchStandings();

    return () => {
      controller.abort();
    };
  }, []);

  return { groups, loading, error };
}
