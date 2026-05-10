import { renderHook, waitFor, act } from '@testing-library/react';
import { useAccuracy } from './useAccuracy';
import api from '../../api';

jest.mock('../../api');
const mockedApi = api as jest.Mocked<typeof api>;

describe('useAccuracy', () => {
  afterEach(() => {
    jest.resetAllMocks();
  });

  test('starts in loading state with empty rollups', () => {
    mockedApi.get.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useAccuracy());
    expect(result.current.loading).toBe(true);
    expect(result.current.rollups).toEqual([]);
    expect(result.current.error).toBeNull();
  });

  test('returns rollups after successful fetch', async () => {
    const mockRollups = [
      {
        window: 'all_time',
        prediction_type: 'winner',
        total_predictions: 42,
        brier_score: 0.215,
        log_loss: 0.68,
        top_pick_hit_rate: 0.71,
        computed_at: '2026-05-09T12:00:00Z',
      },
      {
        window: 'last_7d',
        prediction_type: 'winner',
        total_predictions: 8,
        brier_score: 0.198,
        log_loss: 0.62,
        top_pick_hit_rate: 0.75,
        computed_at: '2026-05-09T12:00:00Z',
      },
    ];

    mockedApi.get.mockResolvedValueOnce({
      data: { rollups: mockRollups },
    });

    const { result } = renderHook(() => useAccuracy());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.rollups).toEqual(mockRollups);
    expect(result.current.error).toBeNull();
    expect(mockedApi.get).toHaveBeenCalledWith(
      '/api/football/accuracy',
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
  });

  test('sets error on network failure', async () => {
    mockedApi.get.mockRejectedValueOnce(new Error('Network Error'));

    const { result } = renderHook(() => useAccuracy());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.error).toBe('Network Error');
    expect(result.current.rollups).toEqual([]);
  });

  test('returns empty array when backend returns empty rollups', async () => {
    mockedApi.get.mockResolvedValueOnce({
      data: { rollups: [], message: 'No accuracy rollups computed yet.' },
    });

    const { result } = renderHook(() => useAccuracy());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.rollups).toEqual([]);
    expect(result.current.error).toBeNull();
  });

  test('handles malformed response gracefully', async () => {
    mockedApi.get.mockResolvedValueOnce({
      data: { rollups: undefined },
    });

    const { result } = renderHook(() => useAccuracy());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.rollups).toEqual([]);
    expect(result.current.error).toBeNull();
  });

  test('does not refetch on re-render', async () => {
    mockedApi.get.mockResolvedValueOnce({
      data: { rollups: [] },
    });

    const { result, rerender } = renderHook(() => useAccuracy());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    rerender();

    expect(mockedApi.get).toHaveBeenCalledTimes(1);
  });

  test('aborts on unmount', async () => {
    mockedApi.get.mockReturnValue(new Promise(() => {}));

    const { unmount } = renderHook(() => useAccuracy());

    const signal = mockedApi.get.mock.calls[0][1]?.signal as AbortSignal;
    expect(signal.aborted).toBe(false);

    unmount();

    expect(signal.aborted).toBe(true);
  });
});
