import { useState, useEffect } from 'react';
import api from '../../api';
import { AccuracyRollup, AccuracyResponse } from '../types/accuracy';

export function useAccuracy() {
  const [rollups, setRollups] = useState<AccuracyRollup[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    const fetchAccuracy = async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await api.get<AccuracyResponse>('/api/football/accuracy', {
          signal: controller.signal,
        });
        if (!controller.signal.aborted) {
          setRollups(Array.isArray(res.data.rollups) ? res.data.rollups : []);
        }
      } catch (err: unknown) {
        if (controller.signal.aborted) return;
        const msg = err instanceof Error ? err.message : String(err);
        setError(msg);
        setRollups([]);
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      }
    };
    fetchAccuracy();

    return () => {
      controller.abort();
    };
  }, []);

  return { rollups, loading, error };
}
