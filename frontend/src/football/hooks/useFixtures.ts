import { useState, useEffect } from 'react';
import api from '../../api';
import { AFFixture, FixturesResponse } from '../types/fixture';

export function useFixtures() {
  const [fixtures, setFixtures] = useState<AFFixture[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    const fetchFixtures = async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await api.get<FixturesResponse>('/api/football/fixtures', {
          signal: controller.signal,
        });
        if (!controller.signal.aborted) {
          setFixtures(Array.isArray(res.data.fixtures) ? res.data.fixtures : []);
        }
      } catch (err: unknown) {
        if (controller.signal.aborted) return;
        const msg = err instanceof Error ? err.message : String(err);
        setError(msg);
        setFixtures([]);
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      }
    };
    fetchFixtures();

    return () => {
      controller.abort();
    };
  }, []);

  return { fixtures, loading, error };
}
