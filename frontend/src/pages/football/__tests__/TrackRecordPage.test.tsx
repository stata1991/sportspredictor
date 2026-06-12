import React from 'react';
import { render, screen, within } from '@testing-library/react';
import TrackRecordPage from '../TrackRecordPage';
import * as useAccuracyMatchesModule from '../../../football/hooks/useAccuracyMatches';
import { MatchReceipt } from '../../../football/types/accuracy';

jest.mock('../../../football/hooks/useAccuracyMatches');
const mockHook = useAccuracyMatchesModule.useAccuracyMatches as jest.Mock;

function receipt(over: Partial<MatchReceipt> = {}): MatchReceipt {
  return {
    fixture_id: 1, kickoff: '2026-06-11T19:00:00+00:00', round: 'Group Stage - 1',
    home_team: 'Mexico', away_team: 'South Africa', final_score: '2-0',
    winner_pick: 'Mexico', winner_actual: 'Mexico', winner_correct: true,
    goals_pick: 'Under 2.5', goals_actual: 2, goals_correct: true,
    is_friendly: false, ...over,
  };
}

const set = (matches: MatchReceipt[]) =>
  mockHook.mockReturnValue({ matches, loading: false, error: null });

afterEach(() => jest.resetAllMocks());

describe('TrackRecordPage', () => {
  test('shows loading skeletons when loading', () => {
    mockHook.mockReturnValue({ matches: [], loading: true, error: null });
    render(<TrackRecordPage />);
    expect(screen.getByTestId('loading-state')).toBeInTheDocument();
  });

  test('headline math is correct from the payload', () => {
    set([
      receipt({ fixture_id: 1, winner_correct: true, goals_correct: true }),
      receipt({ fixture_id: 2, winner_correct: true, goals_correct: false }),
      receipt({ fixture_id: 3, winner_correct: false, winner_pick: 'France',
                winner_actual: 'Ivory Coast', goals_correct: true }),
    ]);
    render(<TrackRecordPage />);

    const headline = screen.getByTestId('headline');
    expect(headline).toHaveTextContent('Winners called right: 2 of 3 (67%)');
    expect(headline).toHaveTextContent('Goals calls: 2 of 3');
  });

  test('renders hit and miss markers', () => {
    set([
      receipt({ fixture_id: 1, winner_correct: true, goals_correct: true }),
      receipt({ fixture_id: 2, winner_correct: false, winner_pick: 'France',
                winner_actual: 'Ivory Coast', goals_correct: false }),
    ]);
    render(<TrackRecordPage />);

    expect(screen.getAllByTestId('hit-mark').length).toBe(2);   // m1 winner+goals
    expect(screen.getAllByTestId('miss-mark').length).toBe(2);  // m2 winner+goals
  });

  test('miss line names the actual winner', () => {
    set([receipt({ winner_correct: false, winner_pick: 'France', winner_actual: 'Ivory Coast' })]);
    render(<TrackRecordPage />);
    expect(screen.getByTestId('called-line')).toHaveTextContent('Called: France');
    expect(screen.getByTestId('called-line')).toHaveTextContent('(Ivory Coast won)');
  });

  test('WC match shows round badge; friendly shows Warm-up chip, no round badge', () => {
    set([
      receipt({ fixture_id: 1, is_friendly: false, round: 'Group Stage - 1' }),
      receipt({ fixture_id: 2, is_friendly: true, round: 'Club Friendlies - 1' }),
    ]);
    render(<TrackRecordPage />);

    const cards = screen.getAllByTestId('match-receipt');
    expect(within(cards[0]).getByTestId('round-badge')).toHaveTextContent('MD1');
    expect(within(cards[0]).queryByTestId('warmup-chip')).not.toBeInTheDocument();
    expect(within(cards[1]).getByTestId('warmup-chip')).toBeInTheDocument();
    expect(within(cards[1]).queryByTestId('round-badge')).not.toBeInTheDocument();
  });

  test('no statistical jargon appears anywhere on the page', () => {
    set([receipt(), receipt({ fixture_id: 2, winner_correct: false, goals_correct: false })]);
    const { container } = render(<TrackRecordPage />);
    const text = container.textContent || '';
    for (const forbidden of [
      'Brier', 'log loss', 'Log Loss', 'first_to_score', 'ht_score',
      'all_time', 'last_7d', 'last_30d',
    ]) {
      expect(text).not.toContain(forbidden);
    }
  });

  test('empty state when no evaluated matches', () => {
    set([]);
    render(<TrackRecordPage />);
    expect(screen.getByTestId('empty-state')).toBeInTheDocument();
    expect(
      screen.getByText('Track record will appear after completed matches are evaluated.'),
    ).toBeInTheDocument();
  });

  test('error state renders retry', () => {
    mockHook.mockReturnValue({ matches: [], loading: false, error: 'boom' });
    render(<TrackRecordPage />);
    expect(screen.getByTestId('error-state')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
  });
});
