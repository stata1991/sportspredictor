import { useState, useEffect } from 'react';
import api from '../../api';
import { AFFixture } from '../types/fixture';

export interface H2HSummary {
  wins: number;
  draws: number;
  losses: number;
}

export interface UseHeadToHeadResult {
  fixtures: AFFixture[];
  summary: H2HSummary | null;
  loading: boolean;
  error: string | null;
}

/**
 * Fetches the head-to-head record between two teams.
 * Returns empty results until both team IDs are available.
 */
export function useHeadToHead(
  homeTeamId: number | null,
  awayTeamId: number | null,
): UseHeadToHeadResult {
  const [fixtures, setFixtures] = useState<AFFixture[]>([]);
  const [summary, setSummary] = useState<H2HSummary | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!homeTeamId || !awayTeamId) {
      setFixtures([]);
      setSummary(null);
      return;
    }

    const controller = new AbortController();

    const fetchH2H = async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await api.get<{
          team1_id: number;
          team2_id: number;
          count: number;
          summary: H2HSummary;
          fixtures: AFFixture[];
        }>('/api/football/head-to-head', {
          params: { team1: homeTeamId, team2: awayTeamId, last: 5 },
          signal: controller.signal,
        });

        if (!controller.signal.aborted) {
          setFixtures(res.data.fixtures);
          setSummary(res.data.summary);
        }
      } catch (err: unknown) {
        if (controller.signal.aborted) return;
        const msg = err instanceof Error ? err.message : String(err);
        setError(msg);
        setFixtures([]);
        setSummary(null);
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      }
    };

    fetchH2H();

    return () => {
      controller.abort();
    };
  }, [homeTeamId, awayTeamId]);

  return { fixtures, summary, loading, error };
}
