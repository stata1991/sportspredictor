import { useState, useEffect } from 'react';
import api from '../../api';
import { UpsetListItem, UpsetListResponse } from '../types/upset';

export function useUpsets(threshold: number = 0.45) {
  const [upsets, setUpsets] = useState<UpsetListItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    const fetchUpsets = async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await api.get<UpsetListResponse>('/api/football/upsets', {
          params: { threshold },
          signal: controller.signal,
        });
        if (!controller.signal.aborted) {
          setUpsets(Array.isArray(res.data.upsets) ? res.data.upsets : []);
        }
      } catch (err: unknown) {
        if (controller.signal.aborted) return;
        const msg = err instanceof Error ? err.message : String(err);
        setError(msg);
        setUpsets([]);
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      }
    };
    fetchUpsets();

    return () => {
      controller.abort();
    };
  }, [threshold]);

  return { upsets, loading, error };
}
