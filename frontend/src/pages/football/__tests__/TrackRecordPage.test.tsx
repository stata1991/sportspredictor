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
    decided_by: null,
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

  test('headline math is correct from the payload (all decisive)', () => {
    set([
      receipt({ fixture_id: 1, winner_correct: true, goals_correct: true }),
      receipt({ fixture_id: 2, winner_correct: true, goals_correct: false }),
      receipt({ fixture_id: 3, winner_correct: false, winner_pick: 'France',
                winner_actual: 'Ivory Coast', goals_correct: true }),
    ]);
    render(<TrackRecordPage />);

    const headline = screen.getByTestId('headline');
    expect(headline).toHaveTextContent('Winners called right: 2 of 3 decisive matches (67%)');
    expect(headline).toHaveTextContent('Goals calls: 2 of 3');
    // No draws → no draw line.
    expect(screen.queryByTestId('draw-line')).not.toBeInTheDocument();
  });

  test('draws are excluded from the headline denominator and own a separate line', () => {
    // 15 decisive (13 correct) + 9 draws (all misses, as a real model produces)
    // → headline must read 13 of 15 decisive (87%), NOT 13 of 24.
    const decisive = Array.from({ length: 15 }, (_, i) =>
      receipt({ fixture_id: 100 + i, winner_correct: i < 13,
                winner_pick: 'Spain', winner_actual: i < 13 ? 'Spain' : 'Cape Verde' }),
    );
    const draws = Array.from({ length: 9 }, (_, i) =>
      receipt({ fixture_id: 200 + i, final_score: '1-1',
                winner_pick: 'Spain', winner_actual: 'Draw', winner_correct: false,
                goals_correct: true }),
    );
    set([...decisive, ...draws]);
    render(<TrackRecordPage />);

    const headline = screen.getByTestId('headline');
    expect(headline).toHaveTextContent('Winners called right: 13 of 15 decisive matches (87%)');
    expect(screen.getByTestId('draw-line')).toHaveTextContent(
      '9 matches drawn — a draw is rarely the top call for any model.',
    );
    // Every match still renders — draws are owned, not hidden.
    expect(screen.getAllByTestId('match-receipt')).toHaveLength(24);
  });

  test('a single decisive match reads "1 decisive match" (singular)', () => {
    set([receipt({ winner_correct: true })]);
    render(<TrackRecordPage />);
    expect(screen.getByTestId('headline')).toHaveTextContent(
      'Winners called right: 1 of 1 decisive match (100%)',
    );
  });

  test('a single drawn match reads "1 match drawn"', () => {
    set([
      receipt({ fixture_id: 1, winner_correct: true }),
      receipt({ fixture_id: 2, final_score: '1-1', winner_actual: 'Draw',
                winner_correct: false }),
    ]);
    render(<TrackRecordPage />);
    expect(screen.getByTestId('draw-line')).toHaveTextContent('1 match drawn');
  });

  test('drawn match still renders its receipt with the drawn outcome', () => {
    set([
      receipt({ fixture_id: 2, home_team: 'Brazil', away_team: 'Morocco',
                final_score: '1-1', winner_pick: 'Brazil', winner_actual: 'Draw',
                winner_correct: false, goals_correct: true }),
    ]);
    render(<TrackRecordPage />);
    const card = screen.getByTestId('match-receipt');
    expect(card).toHaveTextContent('Called: Brazil');
    expect(within(card).getByTestId('miss-mark')).toBeInTheDocument();
    expect(card).toHaveTextContent('(drawn)');
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
    expect(screen.getByTestId('headline')).toHaveTextContent('Winners called right: 1 of 1 decisive match');
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

  test('no statistical jargon appears anywhere on the page (incl. the draw line)', () => {
    set([
      receipt(),
      receipt({ fixture_id: 2, winner_correct: false, goals_correct: false }),
      // include a draw so the draw line is in the DOM and gets scanned too
      receipt({ fixture_id: 3, final_score: '1-1', winner_actual: 'Draw',
                winner_correct: false }),
    ]);
    const { container } = render(<TrackRecordPage />);
    const text = container.textContent || '';
    for (const forbidden of [
      'Brier', 'log loss', 'Log Loss', 'first_to_score', 'ht_score',
      'all_time', 'last_7d', 'last_30d',
      'the model', 'xG', 'expected goals', 'probability',  // narration-forbidden vocab
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

  // ── Knockout advance-based receipts (EVAL-2) ──────────────────────

  test('KO penalties hit: "advanced on penalties" + pens score tag, no "Draw"', () => {
    set([
      receipt({
        fixture_id: 1, home_team: 'Argentina', away_team: 'France',
        final_score: '2-2', round: 'Final', decided_by: 'penalties',
        winner_pick: 'Argentina', winner_actual: 'Argentina', winner_correct: true,
      }),
    ]);
    render(<TrackRecordPage />);
    const called = screen.getByTestId('called-line');
    expect(called).toHaveTextContent('Called: Argentina');
    expect(called).toHaveTextContent('(advanced on penalties)');
    expect(within(called).getByTestId('hit-mark')).toBeInTheDocument();
    expect(screen.getByTestId('score-tag')).toHaveTextContent('pens');
    expect(screen.getByTestId('match-receipt').textContent).not.toContain('Draw');
    expect(screen.getByTestId('match-receipt').textContent).not.toContain('drawn');
  });

  test('KO penalties miss names the advancer, not a draw', () => {
    set([
      receipt({
        fixture_id: 1, home_team: 'Argentina', away_team: 'France',
        final_score: '2-2', round: 'Final', decided_by: 'penalties',
        winner_pick: 'France', winner_actual: 'Argentina', winner_correct: false,
      }),
    ]);
    render(<TrackRecordPage />);
    const called = screen.getByTestId('called-line');
    expect(called).toHaveTextContent('Called: France');
    expect(called).toHaveTextContent('(Argentina advanced on penalties)');
    expect(called.textContent).not.toContain('drawn');
  });

  test('KO extra time: "won in extra time" + ET tag', () => {
    set([
      receipt({
        fixture_id: 1, final_score: '1-1', round: 'Semi-finals',
        decided_by: 'extra_time', winner_pick: 'Mexico',
        winner_actual: 'Mexico', winner_correct: true,
      }),
    ]);
    render(<TrackRecordPage />);
    expect(screen.getByTestId('called-line')).toHaveTextContent('(won in extra time)');
    expect(screen.getByTestId('score-tag')).toHaveTextContent('ET');
  });

  test('KO regulation: "won", no score tag', () => {
    set([
      receipt({
        fixture_id: 1, final_score: '2-1', round: 'Round of 16',
        decided_by: 'regulation', winner_pick: 'Mexico',
        winner_actual: 'Mexico', winner_correct: true,
      }),
    ]);
    render(<TrackRecordPage />);
    expect(screen.getByTestId('called-line')).toHaveTextContent('(won)');
    expect(screen.queryByTestId('score-tag')).not.toBeInTheDocument();
  });

  test('group-stage card unchanged: no decided_by tag, draw still shown', () => {
    set([
      receipt({ fixture_id: 1, winner_correct: true }),  // hit, no parenthetical
      receipt({ fixture_id: 2, final_score: '1-1', winner_pick: 'Mexico',
                winner_actual: 'Draw', winner_correct: false }),
    ]);
    render(<TrackRecordPage />);
    expect(screen.queryByTestId('score-tag')).not.toBeInTheDocument();
    const cards = screen.getAllByTestId('called-line');
    expect(cards[1]).toHaveTextContent('(drawn)');  // group draw unchanged
  });
});
