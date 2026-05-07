import React from 'react';
import { render, screen } from '@testing-library/react';
import WhyPanel from '../WhyPanel';
import { FULL_PREDICTIONS, FULL_REASONING, FULL_UPSET } from '../../../__fixtures__/sampleResponse';
import { DeterministicPrediction, Upset } from '../../../types/prediction';

const baseProps = {
  prediction: FULL_PREDICTIONS,
  stage: 'pre_lineup' as const,
  homeTeam: 'Mexico',
  awayTeam: 'South Africa',
};

// Heavy favourite prediction: p_home_win = 0.865
const heavyFavPrediction: DeterministicPrediction = {
  ...FULL_PREDICTIONS,
  winner: {
    ...FULL_PREDICTIONS.winner,
    p_home_win: 0.865,
    p_draw: 0.107,
    p_away_win: 0.028,
  },
};

// Draw-dominant prediction: p_draw is highest
const drawDominantPrediction: DeterministicPrediction = {
  ...FULL_PREDICTIONS,
  winner: {
    ...FULL_PREDICTIONS.winner,
    p_home_win: 0.25,
    p_draw: 0.50,
    p_away_win: 0.25,
  },
};

const upsetWithPaths: Upset = {
  upset_index: 0.54,
  deterministic_component: 0.6,
  agent_component: 0.08,
  bounded_agent: 0.45,
  upset_signals: [],
  upset_paths: [
    'Path one scenario.',
    'Path two scenario.',
    'Path three scenario.',
  ],
};

describe('WhyPanel', () => {
  test('renders NumbersSection in all non-loading states', () => {
    render(
      <WhyPanel
        {...baseProps}
        reasoning={FULL_REASONING}
        upset={null}
        partialAgent={false}
      />,
    );

    expect(screen.getByTestId('numbers-section')).toBeInTheDocument();
  });

  test('renders ContextSection when reasoning is present', () => {
    render(
      <WhyPanel
        {...baseProps}
        reasoning={FULL_REASONING}
        upset={null}
        partialAgent={false}
      />,
    );

    expect(screen.getByTestId('context-section')).toBeInTheDocument();
    expect(screen.queryByTestId('partial-agent-notice')).not.toBeInTheDocument();
  });

  test('renders partialAgent notice when reasoning is null', () => {
    render(
      <WhyPanel
        {...baseProps}
        reasoning={null}
        upset={null}
        partialAgent={true}
      />,
    );

    expect(screen.getByTestId('partial-agent-notice')).toBeInTheDocument();
    expect(screen.queryByTestId('context-section')).not.toBeInTheDocument();
  });

  test('renders neither ContextSection nor notice when reasoning null and partialAgent false', () => {
    render(
      <WhyPanel
        {...baseProps}
        reasoning={null}
        upset={null}
        partialAgent={false}
      />,
    );

    expect(screen.queryByTestId('context-section')).not.toBeInTheDocument();
    expect(screen.queryByTestId('partial-agent-notice')).not.toBeInTheDocument();
  });

  test('renders NumbersSection even when reasoning is null', () => {
    render(
      <WhyPanel
        {...baseProps}
        reasoning={null}
        upset={null}
        partialAgent={true}
      />,
    );

    expect(screen.getByTestId('numbers-section')).toBeInTheDocument();
  });

  test('renders null when prediction is null', () => {
    const { container } = render(
      <WhyPanel
        {...baseProps}
        prediction={null}
        reasoning={null}
        upset={null}
        partialAgent={false}
      />,
    );

    expect(container.firstChild).toBeNull();
  });

  // ── UpsetSection integration tests ──────────────────────────────

  test('renders UpsetSection when favourite > 0.65 and upset_paths non-empty', () => {
    render(
      <WhyPanel
        {...baseProps}
        prediction={heavyFavPrediction}
        reasoning={FULL_REASONING}
        upset={upsetWithPaths}
        partialAgent={false}
      />,
    );

    expect(screen.getByTestId('upset-section')).toBeInTheDocument();
    expect(screen.getByTestId('upset-heading')).toHaveTextContent(
      'Three paths to Mexico losing this.',
    );
  });

  test('does not render UpsetSection when favourite <= 0.65', () => {
    render(
      <WhyPanel
        {...baseProps}
        reasoning={FULL_REASONING}
        upset={upsetWithPaths}
        partialAgent={false}
      />,
    );

    // FULL_PREDICTIONS has p_home_win=0.414 — below 0.65
    expect(screen.queryByTestId('upset-section')).not.toBeInTheDocument();
  });

  test('does not render UpsetSection when draw is highest probability', () => {
    render(
      <WhyPanel
        {...baseProps}
        prediction={drawDominantPrediction}
        reasoning={FULL_REASONING}
        upset={upsetWithPaths}
        partialAgent={false}
      />,
    );

    // p_draw=0.50 is highest → no favourite to upset → favouriteProbability set to 0
    expect(screen.queryByTestId('upset-section')).not.toBeInTheDocument();
  });
});
