import React from 'react';
import { render, screen } from '@testing-library/react';
import NumbersSection from '../NumbersSection';
import { FULL_PREDICTIONS } from '../../../__fixtures__/sampleResponse';

const defaultProps = {
  prediction: FULL_PREDICTIONS,
  stage: 'pre_lineup' as const,
  homeTeam: 'Mexico',
  awayTeam: 'South Africa',
};

describe('NumbersSection', () => {
  test('renders all six sub-sections', () => {
    render(<NumbersSection {...defaultProps} />);

    expect(screen.getByTestId('confidence-header')).toBeInTheDocument();
    expect(screen.getByTestId('winner-bars')).toBeInTheDocument();
    expect(screen.getByTestId('total-goals')).toBeInTheDocument();
    expect(screen.getByTestId('ht-scoreline-pills')).toBeInTheDocument();
    expect(screen.getByTestId('scoreline-heatmap')).toBeInTheDocument();
    expect(screen.getByTestId('first-to-score')).toBeInTheDocument();
  });

  test('confidence chip shows "Early estimate" for pre_lineup + low_data', () => {
    render(<NumbersSection {...defaultProps} />);

    expect(screen.getByTestId('confidence-chip')).toHaveTextContent('Early estimate');
  });

  test('confidence chip shows "Final — pre-match prediction" for completed stage', () => {
    render(<NumbersSection {...defaultProps} stage="completed" />);

    expect(screen.getByTestId('confidence-chip')).toHaveTextContent('Final — pre-match prediction');
  });

  test('confidence chip shows "Pre-match estimate" for pre_lineup + normal confidence', () => {
    const normalPrediction = {
      ...FULL_PREDICTIONS,
      winner: { ...FULL_PREDICTIONS.winner, confidence: 'normal' },
    };
    render(
      <NumbersSection
        {...defaultProps}
        prediction={normalPrediction}
      />,
    );

    expect(screen.getByTestId('confidence-chip')).toHaveTextContent('Pre-match estimate');
  });

  test('no stage chip — only one chip rendered', () => {
    render(<NumbersSection {...defaultProps} />);

    expect(screen.queryByTestId('stage-chip')).not.toBeInTheDocument();
  });

  test('winner bars display team names and integer percentages', () => {
    render(<NumbersSection {...defaultProps} />);

    const winnerBars = screen.getByTestId('winner-bars');
    expect(winnerBars).toHaveTextContent('Mexico');
    expect(winnerBars).toHaveTextContent('South Africa');
    expect(winnerBars).toHaveTextContent('Draw');
    // 0.414025 → "41%", 0.39356 → "39%", 0.192415 → "19%" (integer, no decimals)
    expect(winnerBars).toHaveTextContent('41%');
    expect(winnerBars).toHaveTextContent('39%');
    expect(winnerBars).toHaveTextContent('19%');
  });

  test('total goals shows expected total with 1 decimal', () => {
    render(<NumbersSection {...defaultProps} />);

    expect(screen.getByText('Expected: 1.4')).toBeInTheDocument();
  });

  test('total goals shows over/under 2.5 stacked bar and 1.5 secondary line', () => {
    render(<NumbersSection {...defaultProps} />);

    // Primary: Over/Under 2.5 as stacked bar
    expect(screen.getByText('Over 2.5')).toBeInTheDocument();
    expect(screen.getByText('Under 2.5')).toBeInTheDocument();

    // Secondary: 1.5 line inline
    const totalGoals = screen.getByTestId('total-goals');
    expect(totalGoals).toHaveTextContent('Over 1.5');
    expect(totalGoals).toHaveTextContent('Under 1.5');

    // Over 3.5 is dropped (too low to inform)
    expect(screen.queryByText('Over 3.5')).not.toBeInTheDocument();
  });

  test('HT scoreline pills render top 5 scorelines with integer percentages', () => {
    render(<NumbersSection {...defaultProps} />);

    const pillContainer = screen.getByTestId('ht-scoreline-pills');
    // The top HT scoreline is 0-0 (0.546437 ≈ 55%)
    expect(pillContainer).toHaveTextContent('0–0');
    expect(pillContainer).toHaveTextContent('55%');
  });

  test('first to score shows team names with integer percentages', () => {
    render(<NumbersSection {...defaultProps} />);

    const ftsSection = screen.getByTestId('first-to-score');
    expect(ftsSection).toHaveTextContent('Mexico');
    expect(ftsSection).toHaveTextContent('South Africa');
    expect(ftsSection).toHaveTextContent('No Goals');
    // 0.468261 → "47%"
    expect(ftsSection).toHaveTextContent('47%');
  });

  // ── Knockout (KO-2): binary bar + close-margin caveat ──────────

  const knockoutWinner = (pHome: number) => ({
    ...FULL_PREDICTIONS,
    winner: {
      ...FULL_PREDICTIONS.winner,
      is_knockout: true,
      p_home_win: pHome,
      p_draw: 0,
      p_away_win: 1 - pHome,
    },
  });

  test('group-stage renders three bars incl. Draw (is_knockout falsy)', () => {
    render(<NumbersSection {...defaultProps} />);
    const winnerBars = screen.getByTestId('winner-bars');
    expect(winnerBars).toHaveTextContent('Draw');
  });

  test('knockout renders two bars, no Draw segment', () => {
    render(
      <NumbersSection {...defaultProps} prediction={knockoutWinner(0.6)} />,
    );
    const winnerBars = screen.getByTestId('winner-bars');
    expect(winnerBars).toHaveTextContent('Mexico');
    expect(winnerBars).toHaveTextContent('South Africa');
    expect(winnerBars).not.toHaveTextContent('Draw');
    // Binary split shows as 60% / 40%.
    expect(winnerBars).toHaveTextContent('60%');
    expect(winnerBars).toHaveTextContent('40%');
  });

  test('no "draw" anywhere in the knockout winner render', () => {
    render(
      <NumbersSection {...defaultProps} prediction={knockoutWinner(0.6)} />,
    );
    const winnerBars = screen.getByTestId('winner-bars');
    expect(winnerBars.textContent?.toLowerCase()).not.toContain('draw');
  });

  test.each([0.5, 0.53, 0.55])(
    'close-margin caveat present at p_home_win=%s',
    (pHome) => {
      render(
        <NumbersSection {...defaultProps} prediction={knockoutWinner(pHome)} />,
      );
      expect(screen.getByTestId('close-margin-caveat')).toBeInTheDocument();
    },
  );

  test.each([0.56, 0.7])(
    'close-margin caveat absent at p_home_win=%s',
    (pHome) => {
      render(
        <NumbersSection {...defaultProps} prediction={knockoutWinner(pHome)} />,
      );
      expect(
        screen.queryByTestId('close-margin-caveat'),
      ).not.toBeInTheDocument();
    },
  );

  test('no caveat for group-stage even at a near-coinflip home prob', () => {
    const balancedGroup = {
      ...FULL_PREDICTIONS,
      winner: { ...FULL_PREDICTIONS.winner, p_home_win: 0.5 },
    };
    render(<NumbersSection {...defaultProps} prediction={balancedGroup} />);
    expect(
      screen.queryByTestId('close-margin-caveat'),
    ).not.toBeInTheDocument();
  });

  // ── Heatmap integration ────────────────────────────────────────

  test('heatmap toggle is rendered when scoreline_matrix is present', () => {
    render(<NumbersSection {...defaultProps} />);

    expect(screen.getByTestId('heatmap-toggle')).toBeInTheDocument();
  });

  test('heatmap toggle is NOT rendered when scoreline_matrix is missing', () => {
    const noMatrixPrediction = {
      ...FULL_PREDICTIONS,
      winner: { ...FULL_PREDICTIONS.winner, scoreline_matrix: undefined as unknown as number[][] },
    };
    render(
      <NumbersSection
        {...defaultProps}
        prediction={noMatrixPrediction}
      />,
    );

    expect(screen.queryByTestId('heatmap-toggle')).not.toBeInTheDocument();
  });
});
