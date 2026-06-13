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

  // ── Live polling (LIVE-1) ──────────────────────────────────────

  const fx = (
    id: number, status: string, elapsed: number | null,
    home: number | null, away: number | null,
  ) => ({
    fixture: {
      id, referee: null, timezone: 'UTC', date: '2026-06-11T18:00:00+00:00',
      timestamp: 1781362800, venue: { id: null, name: null, city: null },
      status: { long: status, short: status, elapsed, extra: null },
    },
    league: { id: 1, name: 'World Cup', country: null, logo: null, flag: null, season: 2026, round: null },
    teams: {
      home: { id: 1, name: 'A', logo: null, winner: null },
      away: { id: 2, name: 'B', logo: null, winner: null },
    },
    goals: { home, away },
    score: {
      halftime: { home: null, away: null }, fulltime: { home: null, away: null },
      extratime: { home: null, away: null }, penalty: { home: null, away: null },
    },
  });

  beforeEach(() => {
    Object.defineProperty(document, 'hidden', {
      writable: true, configurable: true, value: false,
    });
  });

  test('refreshes score/minute on a poll tick when a match is live', async () => {
    // Initial load: 0-0, LIVE 6'. Every poll after: 1-0, LIVE 30'.
    mockedApi.get
      .mockResolvedValueOnce({ data: { count: 1, fixtures: [fx(1, '1H', 6, 0, 0)] } })
      .mockResolvedValue({ data: { count: 1, fixtures: [fx(1, '1H', 30, 1, 0)] } });

    const { result } = renderHook(() =>
      useFixtures({ liveRefreshIntervalMs: 40 }),
    );

    // After a poll tick the shared source reflects the updated score + minute.
    await waitFor(
      () => {
        expect(result.current.fixtures[0]?.fixture.status.elapsed).toBe(30);
      },
      { timeout: 500 },
    );
    expect(result.current.fixtures[0]?.goals).toEqual({ home: 1, away: 0 });
    expect(mockedApi.get).toHaveBeenCalledWith(
      '/api/football/fixtures?live=1',
      expect.anything(),
    );
  });

  // ── Cold-start discovery (LIVETAB-2) — the headline regression ─────

  test('COLD START: a poll is armed even when nothing is live', async () => {
    // The bug: before the fix, an all-NS mount armed NO timer and stayed at
    // 1 call forever. Now the idle poll keeps running so a kickoff can be
    // discovered. (This test would FAIL against the buggy implementation.)
    mockedApi.get.mockResolvedValue({
      data: { count: 1, fixtures: [fx(1, 'NS', null, null, null)] },
    });

    renderHook(() => useFixtures({ idleRefreshIntervalMs: 20 }));

    await waitFor(
      () => expect(mockedApi.get.mock.calls.length).toBeGreaterThan(1),
      { timeout: 500 },
    );
  });

  test('DISCOVERY: idle poll transitions idle → live without a reload', async () => {
    // Mount with nothing live; the next poll returns a fixture now in 2H.
    mockedApi.get
      .mockResolvedValueOnce({
        data: { count: 1, fixtures: [fx(1, 'NS', null, null, null)] },
      })
      .mockResolvedValue({
        data: { count: 1, fixtures: [fx(1, '2H', 50, 1, 0)] },
      });

    const { result } = renderHook(() =>
      useFixtures({ idleRefreshIntervalMs: 20, liveRefreshIntervalMs: 20 }),
    );

    // Starting from an all-NS mount (nothing live), the list ends up showing
    // the 2H fixture. Its ONLY data source is a poll, so reaching 2H proves
    // the idle→live discovery that was impossible before the fix.
    await waitFor(
      () => expect(result.current.fixtures[0]?.fixture.status.short).toBe('2H'),
      { timeout: 500 },
    );
    // Mount used the plain endpoint; discovery came via the live-poll path.
    expect(mockedApi.get).toHaveBeenCalledWith(
      '/api/football/fixtures',
      expect.anything(),
    );
    expect(mockedApi.get).toHaveBeenCalledWith(
      '/api/football/fixtures?live=1',
      expect.anything(),
    );
  });

  test('cadence: idle uses the idle interval, not the live interval', async () => {
    // idle long, live short. An all-NS mount must wait the IDLE interval, so
    // within a short window past the (short) live interval there is no poll.
    mockedApi.get.mockResolvedValue({
      data: { count: 1, fixtures: [fx(1, 'NS', null, null, null)] },
    });

    renderHook(() =>
      useFixtures({ idleRefreshIntervalMs: 10_000, liveRefreshIntervalMs: 20 }),
    );

    await waitFor(() => expect(mockedApi.get).toHaveBeenCalledTimes(1));
    // Past the live interval (20ms) but well short of the idle interval (10s):
    // no extra poll, proving idle cadence is in effect.
    await new Promise((r) => setTimeout(r, 120));
    expect(mockedApi.get).toHaveBeenCalledTimes(1);
  });

  test('visibility: becoming visible refetches even when nothing was live', async () => {
    mockedApi.get.mockResolvedValue({
      data: { count: 1, fixtures: [fx(1, 'NS', null, null, null)] },
    });

    renderHook(() => useFixtures({ idleRefreshIntervalMs: 10_000 }));
    await waitFor(() => expect(mockedApi.get).toHaveBeenCalledTimes(1));

    // Hide, then show — a match may have kicked off while hidden. The old
    // code gated this on anyLive() (false for NS) and never refetched.
    await act(async () => {
      (document as unknown as { hidden: boolean }).hidden = true;
      document.dispatchEvent(new Event('visibilitychange'));
      (document as unknown as { hidden: boolean }).hidden = false;
      document.dispatchEvent(new Event('visibilitychange'));
    });

    await waitFor(() =>
      expect(mockedApi.get.mock.calls.length).toBeGreaterThan(1),
    );
  });

  test('document.hidden halts polling (battery/quota guard)', async () => {
    mockedApi.get.mockResolvedValue({
      data: { count: 1, fixtures: [fx(1, '1H', 10, 0, 0)] },
    });

    renderHook(() => useFixtures({ liveRefreshIntervalMs: 20 }));
    await waitFor(() =>
      expect(mockedApi.get.mock.calls.length).toBeGreaterThan(1),
    );

    await act(async () => {
      (document as unknown as { hidden: boolean }).hidden = true;
      document.dispatchEvent(new Event('visibilitychange'));
    });
    const callsWhenHidden = mockedApi.get.mock.calls.length;

    // No further polls while hidden.
    await new Promise((r) => setTimeout(r, 120));
    expect(mockedApi.get.mock.calls.length).toBe(callsWhenHidden);

    // Restore for following tests.
    (document as unknown as { hidden: boolean }).hidden = false;
  });

  test('a poll tick only ever hits the fixtures endpoint (no prediction calls)', async () => {
    mockedApi.get.mockResolvedValue({
      data: { count: 1, fixtures: [fx(1, '1H', 10, 0, 0)] },
    });

    renderHook(() => useFixtures({ liveRefreshIntervalMs: 30 }));

    await waitFor(() => expect(mockedApi.get.mock.calls.length).toBeGreaterThan(1));
    // INVARIANT: refresh never touches prediction endpoints, so it cannot
    // overwrite or re-trigger prediction generation for a live fixture.
    for (const call of mockedApi.get.mock.calls) {
      expect(String(call[0])).toMatch(/^\/api\/football\/fixtures/);
      expect(String(call[0])).not.toMatch(/predict/);
    }
  });

  test('stops polling after unmount', async () => {
    mockedApi.get.mockResolvedValue({
      data: { count: 1, fixtures: [fx(1, '1H', 10, 0, 0)] },
    });

    const { unmount } = renderHook(() =>
      useFixtures({ liveRefreshIntervalMs: 30 }),
    );

    await waitFor(() => expect(mockedApi.get.mock.calls.length).toBeGreaterThanOrEqual(1));
    unmount();
    const callsAtUnmount = mockedApi.get.mock.calls.length;

    await new Promise((r) => setTimeout(r, 150));
    expect(mockedApi.get.mock.calls.length).toBe(callsAtUnmount);
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
