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

  test('friendlies are filtered out of the list and headline (WC-only)', () => {
    set([
      receipt({ fixture_id: 1, home_team: 'Mexico', is_friendly: false,
                round: 'Group Stage - 1', winner_correct: true, goals_correct: true }),
      receipt({ fixture_id: 2, home_team: 'Germany', is_friendly: true,
                round: 'Club Friendlies - 1', winner_correct: true, goals_correct: false }),
    ]);
    render(<TrackRecordPage />);

    // Only the WC match renders; the warm-up is absent from the DOM.
    const cards = screen.getAllByTestId('match-receipt');
    expect(cards).toHaveLength(1);
    expect(cards[0].textContent).toContain('Mexico');
    expect(document.body.textContent).not.toContain('Germany');
    expect(within(cards[0]).getByTestId('round-badge')).toHaveTextContent('MD1');
    // The Warm-up chip is gone entirely (dead UI removed).
    expect(screen.queryByTestId('warmup-chip')).not.toBeInTheDocument();
    // Headline counts only the WC match.
    expect(screen.getByTestId('headline')).toHaveTextContent('Winners called right: 1 of 1');
    expect(screen.getByTestId('headline')).toHaveTextContent('Goals calls: 1 of 1');
  });

  test('only-friendlies payload renders the empty state', () => {
    set([
      receipt({ fixture_id: 1, is_friendly: true }),
      receipt({ fixture_id: 2, is_friendly: true }),
    ]);
    render(<TrackRecordPage />);
    expect(screen.getByTestId('empty-state')).toBeInTheDocument();
    expect(screen.queryByTestId('track-record-content')).not.toBeInTheDocument();
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
