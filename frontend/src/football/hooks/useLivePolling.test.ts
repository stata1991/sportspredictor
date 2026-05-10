import { renderHook, waitFor, act } from '@testing-library/react';
import { useLivePolling } from './useLivePolling';
import api from '../../api';

jest.mock('../../api');
const mockedApi = api as jest.Mocked<typeof api>;

describe('useLivePolling', () => {
  beforeEach(() => {
    jest.resetAllMocks();
    Object.defineProperty(document, 'hidden', {
      writable: true,
      configurable: true,
      value: false,
    });
  });

  // Short intervals for fast tests
  const shortOpts = {
    url: '/api/football/predict/live/100',
    intervalMs: 80,
    enabled: true,
  };

  test('initial fetch fires immediately on mount', async () => {
    mockedApi.get.mockResolvedValueOnce({ data: { score: '1-0' } });

    const { result } = renderHook(() => useLivePolling(shortOpts));

    await waitFor(() => {
      expect(result.current.data).toEqual({ score: '1-0' });
    });

    expect(mockedApi.get).toHaveBeenCalledTimes(1);
    expect(result.current.isPolling).toBe(true);
    expect(result.current.lastUpdated).toBeInstanceOf(Date);
    expect(result.current.error).toBeNull();
  });

  test('subsequent polls fire at intervalMs cadence', async () => {
    mockedApi.get
      .mockResolvedValueOnce({ data: { poll: 1 } })
      .mockResolvedValueOnce({ data: { poll: 2 } })
      .mockResolvedValueOnce({ data: { poll: 3 } });

    const { result } = renderHook(() => useLivePolling(shortOpts));

    // Initial fetch
    await waitFor(() => {
      expect(result.current.data).toEqual({ poll: 1 });
    });
    expect(mockedApi.get).toHaveBeenCalledTimes(1);

    // Second poll after ~intervalMs
    await waitFor(
      () => {
        expect(result.current.data).toEqual({ poll: 2 });
      },
      { timeout: 500 },
    );
    expect(mockedApi.get).toHaveBeenCalledTimes(2);

    // Third poll
    await waitFor(
      () => {
        expect(result.current.data).toEqual({ poll: 3 });
      },
      { timeout: 500 },
    );
    expect(mockedApi.get).toHaveBeenCalledTimes(3);
  });

  test('enabled: false stops scheduling and aborts in-flight', async () => {
    // Never-resolving promise keeps fetch in flight
    mockedApi.get.mockReturnValueOnce(new Promise(() => {}) as never);

    const { result, rerender } = renderHook(
      ({ enabled }) => useLivePolling({ ...shortOpts, enabled }),
      { initialProps: { enabled: true } },
    );

    // Capture the abort signal
    await waitFor(() => {
      expect(mockedApi.get).toHaveBeenCalledTimes(1);
    });
    const signal = mockedApi.get.mock.calls[0][1]?.signal as AbortSignal;
    expect(signal.aborted).toBe(false);

    // Disable
    rerender({ enabled: false });

    expect(signal.aborted).toBe(true);
    expect(result.current.isPolling).toBe(false);

    // Wait — no new fetches should fire
    await act(async () => {
      await new Promise((r) => setTimeout(r, 200));
    });
    expect(mockedApi.get).toHaveBeenCalledTimes(1);
  });

  test('enabled toggling false → true resumes polling', async () => {
    mockedApi.get.mockResolvedValueOnce({ data: { v: 1 } });

    const { result, rerender } = renderHook(
      ({ enabled }) => useLivePolling({ ...shortOpts, enabled }),
      { initialProps: { enabled: true } },
    );

    await waitFor(() => {
      expect(result.current.data).toEqual({ v: 1 });
    });

    // Disable
    rerender({ enabled: false });
    expect(result.current.isPolling).toBe(false);

    // Re-enable
    mockedApi.get.mockResolvedValueOnce({ data: { v: 2 } });
    rerender({ enabled: true });

    await waitFor(() => {
      expect(result.current.data).toEqual({ v: 2 });
    });
    expect(result.current.isPolling).toBe(true);
  });

  test('visibility hidden clears timeout; visible resumes', async () => {
    mockedApi.get
      .mockResolvedValueOnce({ data: { vis: 1 } })
      .mockResolvedValueOnce({ data: { vis: 2 } });

    renderHook(() => useLivePolling(shortOpts));

    // Wait for initial fetch
    await waitFor(() => {
      expect(mockedApi.get).toHaveBeenCalledTimes(1);
    });

    // Simulate tab hidden
    Object.defineProperty(document, 'hidden', {
      value: true,
      configurable: true,
    });
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
    });

    // Wait — should NOT trigger a new fetch while hidden
    await act(async () => {
      await new Promise((r) => setTimeout(r, 200));
    });
    expect(mockedApi.get).toHaveBeenCalledTimes(1);

    // Simulate tab visible (stale — enough time has passed)
    Object.defineProperty(document, 'hidden', {
      value: false,
      configurable: true,
    });
    act(() => {
      document.dispatchEvent(new Event('visibilitychange'));
    });

    await waitFor(
      () => {
        expect(mockedApi.get).toHaveBeenCalledTimes(2);
      },
      { timeout: 500 },
    );
  });

  test('consecutive failures increase backoff, capped at maxBackoffMs', async () => {
    // Use very short intervals for backoff testing
    const backoffOpts = {
      url: '/api/football/predict/live/100',
      intervalMs: 30,
      enabled: true,
      maxBackoffMs: 120, // cap at 120ms
    };
    mockedApi.get.mockRejectedValue(new Error('server down'));

    const { result } = renderHook(() => useLivePolling(backoffOpts));

    // Initial fetch (immediate) — failure 1
    await waitFor(() => {
      expect(result.current.error?.message).toBe('server down');
    });
    expect(mockedApi.get).toHaveBeenCalledTimes(1);

    // After failure 1: delay = 30 * 2^1 = 60ms
    // After failure 2: delay = 30 * 2^2 = 120ms (at cap)
    // After failure 3: delay = min(30 * 2^3, 120) = 120ms (capped)
    // Wait long enough for several retries
    await waitFor(
      () => {
        expect(mockedApi.get.mock.calls.length).toBeGreaterThanOrEqual(4);
      },
      { timeout: 2000 },
    );
  });

  test('one success after failures resets backoff to base', async () => {
    const backoffOpts = {
      url: '/api/football/predict/live/100',
      intervalMs: 40,
      enabled: true,
      maxBackoffMs: 500,
    };

    mockedApi.get
      .mockRejectedValueOnce(new Error('fail 1'))
      .mockResolvedValueOnce({ data: { recovered: true } })
      .mockResolvedValueOnce({ data: { next: true } });

    const { result } = renderHook(() => useLivePolling(backoffOpts));

    // Initial fetch — fail 1
    await waitFor(() => {
      expect(result.current.error?.message).toBe('fail 1');
    });

    // Second fetch — success (after backoff = 80ms)
    await waitFor(
      () => {
        expect(result.current.data).toEqual({ recovered: true });
      },
      { timeout: 500 },
    );
    expect(result.current.error).toBeNull();

    // Third fetch — after base interval (40ms), not backed-off
    await waitFor(
      () => {
        expect(result.current.data).toEqual({ next: true });
      },
      { timeout: 500 },
    );
  });

  test('unmount aborts in-flight and clears timeout', async () => {
    // Never-resolving promise
    mockedApi.get.mockReturnValueOnce(new Promise(() => {}) as never);

    const { unmount } = renderHook(() => useLivePolling(shortOpts));

    await waitFor(() => {
      expect(mockedApi.get).toHaveBeenCalledTimes(1);
    });

    const signal = mockedApi.get.mock.calls[0][1]?.signal as AbortSignal;
    expect(signal.aborted).toBe(false);

    unmount();

    expect(signal.aborted).toBe(true);

    // Wait — no new fetches should fire after unmount
    await new Promise((r) => setTimeout(r, 200));
    expect(mockedApi.get).toHaveBeenCalledTimes(1);
  });

  test('stale fetch resolving after newer fetch does not overwrite data', async () => {
    // First call: never resolves (will be aborted by refetch)
    mockedApi.get.mockReturnValueOnce(new Promise(() => {}) as never);

    const { result } = renderHook(() => useLivePolling(shortOpts));

    await waitFor(() => {
      expect(mockedApi.get).toHaveBeenCalledTimes(1);
    });

    // The first request's signal
    const firstSignal = mockedApi.get.mock.calls[0][1]?.signal as AbortSignal;

    // Setup second call to resolve with version 2
    mockedApi.get.mockResolvedValueOnce({ data: { version: 2 } });

    // Manual refetch — aborts the first, starts a second
    await act(async () => {
      await result.current.refetch();
    });

    // First request was aborted
    expect(firstSignal.aborted).toBe(true);

    // Data should be version 2
    expect(result.current.data).toEqual({ version: 2 });
  });

  test('parseResponse transforms raw data', async () => {
    mockedApi.get.mockResolvedValueOnce({
      data: { predictions: { live_winner: { p_home: 0.6 } } },
    });

    const { result } = renderHook(() =>
      useLivePolling({
        ...shortOpts,
        parseResponse: (raw: unknown) =>
          (raw as { predictions: { live_winner: unknown } }).predictions
            .live_winner,
      }),
    );

    await waitFor(() => {
      expect(result.current.data).toEqual({ p_home: 0.6 });
    });
  });
});
