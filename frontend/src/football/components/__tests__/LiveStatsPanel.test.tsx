import React from 'react';
import { render, screen } from '@testing-library/react';
import LiveStatsPanel from '../LiveStatsPanel';
import { FixtureStatistics } from '../../types/statistics';

const FULL_STATS: FixtureStatistics = {
  home: {
    possession: 60,
    shots_total: 11,
    shots_on_goal: 5,
    corners: 7,
    fouls: 9,
    yellow_cards: 2,
    red_cards: 0,
    goalkeeper_saves: 3,
  },
  away: {
    possession: 40,
    shots_total: 6,
    shots_on_goal: 2,
    corners: 3,
    fouls: 14,
    yellow_cards: 3,
    red_cards: 1,
    goalkeeper_saves: 4,
  },
};

const EMPTY_TEAM = {
  possession: null,
  shots_total: null,
  shots_on_goal: null,
  corners: null,
  fouls: null,
  yellow_cards: null,
  red_cards: null,
  goalkeeper_saves: null,
};

const baseProps = { homeTeam: 'Brazil', awayTeam: 'Germany' };

describe('LiveStatsPanel', () => {
  test('renders possession split bar and paired stat rows', () => {
    render(<LiveStatsPanel stats={FULL_STATS} {...baseProps} />);

    expect(screen.getByTestId('live-stats-panel')).toBeInTheDocument();
    expect(screen.getByTestId('possession-bar')).toBeInTheDocument();
    expect(screen.getByTestId('possession-home-pct')).toHaveTextContent('60%');
    expect(screen.getByTestId('possession-away-pct')).toHaveTextContent('40%');

    const shots = screen.getByTestId('stat-row-shots_total');
    expect(shots).toHaveTextContent('11');
    expect(shots).toHaveTextContent('6');
    expect(screen.getByTestId('stat-row-shots_on_goal')).toHaveTextContent('5');
    expect(screen.getByTestId('stat-row-corners')).toBeInTheDocument();
    expect(screen.getByTestId('stat-row-red_cards')).toBeInTheDocument();
  });

  test('possession split bar uses home/away colors and no green', () => {
    const { container } = render(
      <LiveStatsPanel stats={FULL_STATS} {...baseProps} />,
    );

    const homeSeg = screen.getByTestId('possession-bar-home');
    const awaySeg = screen.getByTestId('possession-bar-away');
    // MUI sx → inline styles; rgb equivalents of #ff6f00 / #ec407a.
    expect(homeSeg).toHaveStyle('background-color: #ff6f00');
    expect(awaySeg).toHaveStyle('background-color: #ec407a');
    // Proportional widths via flexGrow.
    expect(homeSeg).toHaveStyle('flex-grow: 60');
    expect(awaySeg).toHaveStyle('flex-grow: 40');

    // Guard: no green anywhere in the rendered markup.
    const html = container.innerHTML.toLowerCase();
    expect(html).not.toMatch(/#4caf50|#00c853|#2e7d32|green/);
  });

  test('omits a row when both sides are null (no fake zeros)', () => {
    const stats: FixtureStatistics = {
      home: { ...FULL_STATS.home, corners: null },
      away: { ...FULL_STATS.away, corners: null },
    };
    render(<LiveStatsPanel stats={stats} {...baseProps} />);

    expect(screen.queryByTestId('stat-row-corners')).not.toBeInTheDocument();
    // Other rows still present.
    expect(screen.getByTestId('stat-row-shots_total')).toBeInTheDocument();
  });

  test('shows en-dash for the null side when only one side has a value', () => {
    const stats: FixtureStatistics = {
      home: { ...FULL_STATS.home, goalkeeper_saves: 2 },
      away: { ...FULL_STATS.away, goalkeeper_saves: null },
    };
    render(<LiveStatsPanel stats={stats} {...baseProps} />);

    const row = screen.getByTestId('stat-row-goalkeeper_saves');
    expect(row).toHaveTextContent('2');
    expect(row).toHaveTextContent('–');
  });

  test('possession bar hidden unless both sides have possession', () => {
    const stats: FixtureStatistics = {
      home: { ...EMPTY_TEAM, possession: 55, shots_total: 4 },
      away: { ...EMPTY_TEAM, possession: null, shots_total: 2 },
    };
    render(<LiveStatsPanel stats={stats} {...baseProps} />);

    expect(screen.queryByTestId('possession-bar')).not.toBeInTheDocument();
    // But the shots row still renders.
    expect(screen.getByTestId('stat-row-shots_total')).toBeInTheDocument();
  });

  test('shows "coming in" when stats are null (early match)', () => {
    render(<LiveStatsPanel stats={null} {...baseProps} />);

    expect(screen.getByTestId('live-stats-pending')).toHaveTextContent(
      /coming in/i,
    );
    expect(screen.queryByTestId('possession-bar')).not.toBeInTheDocument();
  });

  test('shows "coming in" when every field is null on both sides', () => {
    const stats: FixtureStatistics = { home: EMPTY_TEAM, away: EMPTY_TEAM };
    render(<LiveStatsPanel stats={stats} {...baseProps} />);

    expect(screen.getByTestId('live-stats-pending')).toBeInTheDocument();
  });
});
