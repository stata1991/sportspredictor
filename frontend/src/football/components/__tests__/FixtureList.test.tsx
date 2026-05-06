import React from 'react';
import { render, screen } from '@testing-library/react';
import FixtureList from '../FixtureList';
import { AFFixture } from '../../types/fixture';

/** Helper — creates a minimal AFFixture with a given ISO date and id. */
const makeFixture = (id: number, isoDate: string, homeName: string, awayName: string): AFFixture => ({
  fixture: {
    id,
    referee: null,
    timezone: 'UTC',
    date: isoDate,
    timestamp: new Date(isoDate).getTime() / 1000,
    venue: { id: 1, name: 'Stadium', city: 'City' },
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
    home: { id: id * 10, name: homeName, logo: null, winner: null },
    away: { id: id * 10 + 1, name: awayName, logo: null, winner: null },
  },
  goals: { home: null, away: null },
  score: {
    halftime: { home: null, away: null },
    fulltime: { home: null, away: null },
    extratime: { home: null, away: null },
    penalty: { home: null, away: null },
  },
});

describe('FixtureList', () => {
  test('groups fixtures by date correctly (3 days)', () => {
    // Use dates at noon UTC — safe from timezone boundary issues in most locales
    const fixtures = [
      makeFixture(1, '2026-06-11T12:00:00Z', 'USA', 'Brazil'),
      makeFixture(2, '2026-06-12T12:00:00Z', 'Germany', 'Japan'),
      makeFixture(3, '2026-06-11T15:00:00Z', 'France', 'England'),
      makeFixture(4, '2026-06-13T12:00:00Z', 'Spain', 'Italy'),
      makeFixture(5, '2026-06-12T18:00:00Z', 'Argentina', 'Mexico'),
    ];

    render(<FixtureList fixtures={fixtures} onFixtureClick={jest.fn()} />);

    const headers = screen.getAllByTestId('day-header');
    expect(headers).toHaveLength(3);

    // Verify chronological order — June 11, 12, 13
    expect(headers[0].textContent).toMatch(/June\s+11/);
    expect(headers[1].textContent).toMatch(/June\s+12/);
    expect(headers[2].textContent).toMatch(/June\s+13/);
  });

  test('sticky headers appear in correct chronological order', () => {
    // Intentionally pass fixtures out of order
    const fixtures = [
      makeFixture(1, '2026-06-15T12:00:00Z', 'A', 'B'),
      makeFixture(2, '2026-06-11T12:00:00Z', 'C', 'D'),
      makeFixture(3, '2026-06-13T12:00:00Z', 'E', 'F'),
    ];

    render(<FixtureList fixtures={fixtures} onFixtureClick={jest.fn()} />);

    const headers = screen.getAllByTestId('day-header');
    expect(headers).toHaveLength(3);

    // Even though fixtures were passed in 15, 11, 13 order, headers should be 11, 13, 15
    expect(headers[0].textContent).toMatch(/June\s+11/);
    expect(headers[1].textContent).toMatch(/June\s+13/);
    expect(headers[2].textContent).toMatch(/June\s+15/);
  });

  test('empty fixtures array renders nothing (no crash)', () => {
    const { container } = render(
      <FixtureList fixtures={[]} onFixtureClick={jest.fn()} />,
    );
    // Should render nothing — no day headers, no cards
    expect(screen.queryAllByTestId('day-header')).toHaveLength(0);
    expect(screen.queryAllByTestId('fixture-card')).toHaveLength(0);
    // Container should be empty (FixtureList returns null)
    expect(container.innerHTML).toBe('');
  });

  test('fixtures within a day are sorted chronologically', () => {
    const fixtures = [
      makeFixture(1, '2026-06-11T20:00:00Z', 'Late', 'Game'),
      makeFixture(2, '2026-06-11T12:00:00Z', 'Early', 'Game'),
      makeFixture(3, '2026-06-11T16:00:00Z', 'Mid', 'Game'),
    ];

    render(<FixtureList fixtures={fixtures} onFixtureClick={jest.fn()} />);

    const cards = screen.getAllByTestId('fixture-card');
    expect(cards).toHaveLength(3);

    // Cards should be ordered: Early, Mid, Late
    expect(cards[0].textContent).toContain('Early');
    expect(cards[1].textContent).toContain('Mid');
    expect(cards[2].textContent).toContain('Late');
  });
});
