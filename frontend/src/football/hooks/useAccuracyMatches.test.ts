import { renderHook, waitFor, act } from '@testing-library/react';
import { useAccuracyMatches } from './useAccuracyMatches';
import api from '../../api';
import { MatchReceipt } from '../types/accuracy';

jest.mock('../../api');
const mockedApi = api as jest.Mocked<typeof api>;

function receipt(fixture_id: number, home: string): MatchReceipt {
  return {
    fixture_id,
    kickoff: '2026-06-20T00:30:00Z',
    round: null,
    home_team: home,
    away_team: 'Foe',
    final_score: '2-0',
    decided_by: null,
    winner_pick: home,
    winner_actual: home,
    winner_correct: true,
    goals_pick: 'Over 2.5',
    goals_actual: 2,
    goals_correct: true,
    is_friendly: false,
  };
}

describe('useAccuracyMatches', () => {
  afterEach(() => jest.clearAllMocks());

  it('loads receipts on mount (newest first)', async () => {
    mockedApi.get.mockResolvedValueOnce({ data: { matches: [receipt(1, 'Brazil')] } });

    const { result } = renderHook(() => useAccuracyMatches());

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.matches).toHaveLength(1);
    expect(result.current.matches[0].home_team).toBe('Brazil');
    expect(mockedApi.get).toHaveBeenCalledTimes(1);
  });

  // EVAL-3 / TRACK-4 #3: the writer advances outcomes in the background; an
  // open tab must self-heal on focus rather than need a manual reload.
  it('refetches silently when the tab regains focus', async () => {
    mockedApi.get
      .mockResolvedValueOnce({ data: { matches: [receipt(1, 'Brazil')] } })
      .mockResolvedValueOnce({
        data: { matches: [receipt(2, 'Turkiye'), receipt(1, 'Brazil')] },
      });

    const { result } = renderHook(() => useAccuracyMatches());
    await waitFor(() => expect(result.current.matches).toHaveLength(1));

    act(() => {
      window.dispatchEvent(new Event('focus'));
    });

    await waitFor(() => expect(result.current.matches).toHaveLength(2));
    expect(mockedApi.get).toHaveBeenCalledTimes(2);
    // Silent: the refetch never flips loading back to true.
    expect(result.current.loading).toBe(false);
    expect(result.current.matches[0].home_team).toBe('Turkiye');
  });

  // A failed silent refetch must NOT wipe already-rendered receipts.
  it('preserves prior receipts when a focus refetch fails', async () => {
    mockedApi.get
      .mockResolvedValueOnce({ data: { matches: [receipt(1, 'Brazil')] } })
      .mockRejectedValueOnce(new Error('network blip'));

    const { result } = renderHook(() => useAccuracyMatches());
    await waitFor(() => expect(result.current.matches).toHaveLength(1));

    act(() => {
      window.dispatchEvent(new Event('focus'));
    });

    await waitFor(() => expect(mockedApi.get).toHaveBeenCalledTimes(2));
    expect(result.current.matches).toHaveLength(1);
    expect(result.current.error).toBeNull();
  });
});
