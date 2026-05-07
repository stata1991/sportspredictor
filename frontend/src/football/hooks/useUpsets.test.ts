import { renderHook, waitFor, act } from '@testing-library/react';
import { useUpsets } from './useUpsets';
import api from '../../api';

jest.mock('../../api');
const mockedApi = api as jest.Mocked<typeof api>;

describe('useUpsets', () => {
  afterEach(() => {
    jest.resetAllMocks();
  });

  test('starts in loading state with empty upsets', () => {
    mockedApi.get.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useUpsets());
    expect(result.current.loading).toBe(true);
    expect(result.current.upsets).toEqual([]);
    expect(result.current.error).toBeNull();
  });

  test('returns upsets after successful fetch', async () => {
    const mockUpsets = [
      {
        fixture_id: 1234,
        home_team: 'Germany',
        away_team: 'Curaçao',
        home_logo: null,
        away_logo: null,
        kickoff: '2026-06-14T19:00:00+02:00',
        status: 'NS',
        round: 'Group E - 1',
        upset_index: 0.54,
        upset_paths: ['Curaçao win', 'Draw + low xG', 'Red card disruption'],
      },
    ];

    mockedApi.get.mockResolvedValueOnce({
      data: { count: 1, threshold: 0.45, upsets: mockUpsets },
    });

    const { result } = renderHook(() => useUpsets());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.upsets).toEqual(mockUpsets);
    expect(result.current.error).toBeNull();
    expect(mockedApi.get).toHaveBeenCalledWith(
      '/api/football/upsets',
      expect.objectContaining({
        params: { threshold: 0.45 },
        signal: expect.any(AbortSignal),
      }),
    );
  });

  test('sets error on network failure', async () => {
    mockedApi.get.mockRejectedValueOnce(new Error('Network Error'));

    const { result } = renderHook(() => useUpsets());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.error).toBe('Network Error');
    expect(result.current.upsets).toEqual([]);
  });

  test('returns empty array for zero upsets', async () => {
    mockedApi.get.mockResolvedValueOnce({
      data: { count: 0, threshold: 0.45, upsets: [] },
    });

    const { result } = renderHook(() => useUpsets());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.upsets).toEqual([]);
    expect(result.current.error).toBeNull();
  });

  test('refetches on threshold change', async () => {
    mockedApi.get.mockResolvedValue({
      data: { count: 0, threshold: 0.45, upsets: [] },
    });

    const { result, rerender } = renderHook(
      ({ threshold }) => useUpsets(threshold),
      { initialProps: { threshold: 0.45 } },
    );

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    rerender({ threshold: 0.5 });

    await waitFor(() => {
      expect(mockedApi.get).toHaveBeenCalledTimes(2);
    });

    expect(mockedApi.get).toHaveBeenLastCalledWith(
      '/api/football/upsets',
      expect.objectContaining({
        params: { threshold: 0.5 },
        signal: expect.any(AbortSignal),
      }),
    );
  });

  test('does not refetch on re-render with same threshold', async () => {
    mockedApi.get.mockResolvedValueOnce({
      data: { count: 0, threshold: 0.45, upsets: [] },
    });

    const { result, rerender } = renderHook(() => useUpsets(0.45));

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    rerender();

    expect(mockedApi.get).toHaveBeenCalledTimes(1);
  });

  test('does not warn when unmounted before fetch resolves', async () => {
    const errorSpy = jest.spyOn(console, 'error').mockImplementation(() => {});
    const warnSpy = jest.spyOn(console, 'warn').mockImplementation(() => {});

    mockedApi.get.mockReturnValue(new Promise(() => {}));

    const { unmount } = renderHook(() => useUpsets());

    const signal = mockedApi.get.mock.calls[0][1]?.signal as AbortSignal;
    expect(signal).toBeInstanceOf(AbortSignal);
    expect(signal.aborted).toBe(false);

    unmount();

    expect(signal.aborted).toBe(true);

    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 50));
    });

    expect(errorSpy).not.toHaveBeenCalled();
    expect(warnSpy).not.toHaveBeenCalled();

    errorSpy.mockRestore();
    warnSpy.mockRestore();
  });
});
