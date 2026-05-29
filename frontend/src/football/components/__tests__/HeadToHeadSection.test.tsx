import React from 'react';
import { render, screen } from '@testing-library/react';
import HeadToHeadSection from '../HeadToHeadSection';
import { AFFixture } from '../../types/fixture';
import { H2HSummary } from '../../hooks/useHeadToHead';

function makeFixture(
  id: number,
  homeName: string,
  awayName: string,
  homeGoals: number | null,
  awayGoals: number | null,
  homeId: number = 10,
  awayId: number = 20,
): AFFixture {
  return {
    fixture: {
      id,
      referee: null,
      timezone: 'UTC',
      date: '2025-10-15T18:00:00+00:00',
      timestamp: 1729015200,
      venue: { id: 1, name: 'Stadium', city: 'City' },
      status: { long: 'Match Finished', short: 'FT', elapsed: 90, extra: null },
    },
    league: {
      id: 1,
      name: 'Friendly',
      country: null,
      logo: null,
      flag: null,
      season: 2025,
      round: null,
    },
    teams: {
      home: { id: homeId, name: homeName, logo: null, winner: homeGoals !== null && awayGoals !== null ? homeGoals > awayGoals : null },
      away: { id: awayId, name: awayName, logo: null, winner: homeGoals !== null && awayGoals !== null ? awayGoals > homeGoals : null },
    },
    goals: { home: homeGoals, away: awayGoals },
    score: {
      halftime: { home: null, away: null },
      fulltime: { home: homeGoals, away: awayGoals },
      extratime: { home: null, away: null },
      penalty: { home: null, away: null },
    },
  };
}

const defaultSummary: H2HSummary = { wins: 2, draws: 1, losses: 1 };

describe('HeadToHeadSection', () => {
  test('renders empty state when no fixtures', () => {
    render(
      <HeadToHeadSection
        fixtures={[]}
        summary={{ wins: 0, draws: 0, losses: 0 }}
        loading={false}
        error={null}
        homeTeam="Brazil"
        awayTeam="Germany"
      />,
    );

    expect(screen.getByTestId('h2h-empty')).toBeInTheDocument();
    expect(
      screen.getByText('First meeting between these sides.'),
    ).toBeInTheDocument();
  });

  test('renders loading spinner', () => {
    render(
      <HeadToHeadSection
        fixtures={[]}
        summary={null}
        loading={true}
        error={null}
        homeTeam="Brazil"
        awayTeam="Germany"
      />,
    );

    expect(screen.getByTestId('h2h-loading')).toBeInTheDocument();
  });

  test('renders nothing on error', () => {
    const { container } = render(
      <HeadToHeadSection
        fixtures={[]}
        summary={null}
        loading={false}
        error="Network error"
        homeTeam="Brazil"
        awayTeam="Germany"
      />,
    );

    expect(container.innerHTML).toBe('');
  });

  test('renders summary stats', () => {
    const fixtures = [
      makeFixture(1, 'Brazil', 'Germany', 2, 1),
    ];
    render(
      <HeadToHeadSection
        fixtures={fixtures}
        summary={defaultSummary}
        loading={false}
        error={null}
        homeTeam="Brazil"
        awayTeam="Germany"
      />,
    );

    expect(screen.getByTestId('h2h-summary')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument(); // wins
    expect(screen.getByText('Brazil wins')).toBeInTheDocument();
    expect(screen.getByText('Germany wins')).toBeInTheDocument();
    expect(screen.getByText('Draws')).toBeInTheDocument();
  });

  test('renders fixture cards with scores', () => {
    const fixtures = [
      makeFixture(1, 'Brazil', 'Germany', 2, 1),
      makeFixture(2, 'Germany', 'Brazil', 0, 0),
    ];
    render(
      <HeadToHeadSection
        fixtures={fixtures}
        summary={{ wins: 1, draws: 1, losses: 0 }}
        loading={false}
        error={null}
        homeTeam="Brazil"
        awayTeam="Germany"
      />,
    );

    const cards = screen.getAllByTestId('h2h-fixture');
    expect(cards).toHaveLength(2);

    const scores = screen.getAllByTestId('h2h-score');
    expect(scores[0].textContent).toContain('2');
    expect(scores[0].textContent).toContain('1');
  });

  test('renders heading text', () => {
    render(
      <HeadToHeadSection
        fixtures={[makeFixture(1, 'Brazil', 'Germany', 1, 0)]}
        summary={{ wins: 1, draws: 0, losses: 0 }}
        loading={false}
        error={null}
        homeTeam="Brazil"
        awayTeam="Germany"
      />,
    );

    expect(screen.getByText('Head-to-Head')).toBeInTheDocument();
  });
});
