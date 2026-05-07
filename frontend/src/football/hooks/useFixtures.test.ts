import { renderHook, waitFor, act } from '@testing-library/react';
import { useFixtures } from './useFixtures';
import api from '../../api';

jest.mock('../../api');
const mockedApi = api as jest.Mocked<typeof api>;

describe('useFixtures', () => {
  afterEach(() => {
    jest.resetAllMocks();
  });

  test('starts in loading state with empty fixtures', () => {
    // Never-resolving promise keeps the hook in loading state
    mockedApi.get.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useFixtures());
    expect(result.current.loading).toBe(true);
    expect(result.current.fixtures).toEqual([]);
    expect(result.current.error).toBeNull();
  });

  test('returns fixtures after successful fetch', async () => {
    const mockFixtures = [
      {
        fixture: {
          id: 1234,
          referee: null,
          timezone: 'UTC',
          date: '2026-06-11T18:00:00+00:00',
          timestamp: 1781362800,
          venue: { id: 1, name: 'MetLife Stadium', city: 'East Rutherford' },
          status: { long: 'Not Started', short: 'NS', elapsed: null, extra: null },
        },
        league: {
          id: 1,
          name: 'World Cup',
          country: null,
          logo: null,
          flag: null,
          season: 2026,
          round: 'Group A - 1',
        },
        teams: {
          home: { id: 1, name: 'USA', logo: null, winner: null },
          away: { id: 2, name: 'Brazil', logo: null, winner: null },
        },
        goals: { home: null, away: null },
        score: {
          halftime: { home: null, away: null },
          fulltime: { home: null, away: null },
          extratime: { home: null, away: null },
          penalty: { home: null, away: null },
        },
      },
    ];

    mockedApi.get.mockResolvedValueOnce({
      data: { count: 1, fixtures: mockFixtures },
    });

    const { result } = renderHook(() => useFixtures());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.fixtures).toEqual(mockFixtures);
    expect(result.current.error).toBeNull();
    expect(mockedApi.get).toHaveBeenCalledWith(
      '/api/football/fixtures',
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    );
  });

  test('sets error on network failure', async () => {
    mockedApi.get.mockRejectedValueOnce(new Error('Network Error'));

    const { result } = renderHook(() => useFixtures());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.error).toBe('Network Error');
    expect(result.current.fixtures).toEqual([]);
  });

  test('returns empty array for zero fixtures', async () => {
    mockedApi.get.mockResolvedValueOnce({
      data: { count: 0, fixtures: [] },
    });

    const { result } = renderHook(() => useFixtures());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.fixtures).toEqual([]);
    expect(result.current.error).toBeNull();
  });

  test('handles malformed response gracefully', async () => {
    // Missing fixtures key — hook should default to empty array
    mockedApi.get.mockResolvedValueOnce({
      data: { count: 5 },
    });

    const { result } = renderHook(() => useFixtures());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.fixtures).toEqual([]);
    expect(result.current.error).toBeNull();
  });

  test('does not refetch on re-render', async () => {
    mockedApi.get.mockResolvedValueOnce({
      data: { count: 0, fixtures: [] },
    });

    const { result, rerender } = renderHook(() => useFixtures());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    rerender();

    expect(mockedApi.get).toHaveBeenCalledTimes(1);
  });

  test('does not warn when unmounted before fetch resolves', async () => {
    const errorSpy = jest.spyOn(console, 'error').mockImplementation(() => {});
    const warnSpy = jest.spyOn(console, 'warn').mockImplementation(() => {});

    // Never-resolving promise — fetch stays in-flight
    mockedApi.get.mockReturnValue(new Promise(() => {}));

    const { unmount } = renderHook(() => useFixtures());

    // Capture the signal passed to api.get
    const signal = mockedApi.get.mock.calls[0][1]?.signal as AbortSignal;
    expect(signal).toBeInstanceOf(AbortSignal);
    expect(signal.aborted).toBe(false);

    unmount();

    // Cleanup should have aborted the controller
    expect(signal.aborted).toBe(true);

    // Flush any pending microtasks / timers
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 50));
    });

    expect(errorSpy).not.toHaveBeenCalled();
    expect(warnSpy).not.toHaveBeenCalled();

    errorSpy.mockRestore();
    warnSpy.mockRestore();
  });
});
