import React from 'react';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route, Outlet } from 'react-router-dom';
import { HelmetProvider } from 'react-helmet-async';
import KnockoutsPage from '../KnockoutsPage';
import { WorldCupOutletContext } from '../../../football/types/outletContext';
import { AFFixture } from '../../../football/types/fixture';

function makeFixture(
  id: number,
  homeName: string,
  awayName: string,
  round: string,
  statusShort = 'NS',
): AFFixture {
  return {
    fixture: {
      id, referee: null, timezone: 'UTC', date: '2026-07-04T19:00:00+00:00',
      timestamp: 1000 + id, venue: { id: null, name: null, city: null },
      status: { long: '', short: statusShort, elapsed: null, extra: null },
    },
    league: {
      id: 1, name: 'World Cup', country: null, logo: null, flag: null,
      season: 2026, round,
    },
    teams: {
      home: { id: id * 10, name: homeName, logo: null, winner: null },
      away: { id: id * 10 + 1, name: awayName, logo: null, winner: null },
    },
    goals: { home: null, away: null },
    score: {
      halftime: { home: null, away: null }, fulltime: { home: null, away: null },
      extratime: { home: null, away: null }, penalty: { home: null, away: null },
    },
  };
}

const renderWithContext = (context: Partial<WorldCupOutletContext>) => {
  const full: WorldCupOutletContext = {
    fixtures: [], loading: false, error: null,
    onRetry: jest.fn(), onFixtureClick: jest.fn(),
    ...context,
  };
  return render(
    <HelmetProvider>
      <MemoryRouter initialEntries={['/test']}>
        <Routes>
          <Route path="/test" element={<Outlet context={full} />}>
            <Route index element={<KnockoutsPage />} />
          </Route>
        </Routes>
      </MemoryRouter>
    </HelmetProvider>,
  );
};

describe('KnockoutsPage', () => {
  test('round-tab strip renders all six chips with short labels', () => {
    renderWithContext({ fixtures: [] });
    const chips = screen.getAllByTestId('round-chip');
    expect(chips).toHaveLength(6);
    ['R32', 'R16', 'QF', 'SF', '3rd', 'Final'].forEach((l) =>
      expect(screen.getByText(l)).toBeInTheDocument(),
    );
  });

  test('no knockout fixtures → calm placeholder, not an error', () => {
    // Group-stage fixtures present, but no knockout fixtures.
    renderWithContext({
      fixtures: [makeFixture(1, 'Mexico', 'South Africa', 'Group Stage - 1')],
    });
    expect(screen.getByTestId('knockouts-placeholder')).toBeInTheDocument();
    expect(
      screen.getByText(/Bracket fills in once the groups sort themselves out/i),
    ).toBeInTheDocument();
    expect(screen.queryByTestId('knockouts-error')).not.toBeInTheDocument();
    expect(screen.queryByTestId('knockout-fixtures')).not.toBeInTheDocument();
  });

  test('assigned knockout fixtures render as cards with round badge', () => {
    renderWithContext({
      fixtures: [
        makeFixture(1, 'Brazil', 'Germany', 'Round of 16'),
        makeFixture(2, 'France', 'Spain', 'Round of 16'),
      ],
    });
    const list = screen.getByTestId('knockout-fixtures');
    expect(within(list).getAllByTestId('fixture-card')).toHaveLength(2);
    expect(within(list).getByText('Brazil')).toBeInTheDocument();
    expect(within(list).getByText('Spain')).toBeInTheDocument();
    // Round badge (short label) present on the cards.
    expect(within(list).getAllByText('R16').length).toBeGreaterThanOrEqual(2);
  });

  test('assigned card click navigates via onFixtureClick (MatchPage route)', async () => {
    const onFixtureClick = jest.fn();
    renderWithContext({
      fixtures: [makeFixture(42, 'Brazil', 'Germany', 'Round of 16')],
      onFixtureClick,
    });
    const list = screen.getByTestId('knockout-fixtures');
    await userEvent.click(within(list).getByRole('button'));
    expect(onFixtureClick).toHaveBeenCalledWith(42);
  });

  test('selecting a round with zero fixtures shows the placeholder', async () => {
    renderWithContext({
      fixtures: [makeFixture(1, 'Brazil', 'Germany', 'Round of 16')],
    });
    // Default lands on R16 (has an unfinished match).
    expect(screen.getByTestId('knockout-fixtures')).toBeInTheDocument();
    // Switch to Final — no fixtures there.
    await userEvent.click(screen.getByText('Final'));
    expect(screen.getByTestId('knockouts-placeholder')).toBeInTheDocument();
    expect(screen.queryByTestId('knockout-fixtures')).not.toBeInTheDocument();
  });

  test('shows error state with retry', () => {
    const onRetry = jest.fn();
    renderWithContext({ error: 'boom', onRetry });
    expect(screen.getByTestId('knockouts-error')).toBeInTheDocument();
  });
});
