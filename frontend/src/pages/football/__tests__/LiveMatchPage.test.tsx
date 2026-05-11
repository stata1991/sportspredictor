import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route, Outlet } from 'react-router-dom';
import { HelmetProvider } from 'react-helmet-async';
import LiveMatchPage from '../LiveMatchPage';
import { WorldCupOutletContext } from '../../../football/types/outletContext';
import { AFFixture } from '../../../football/types/fixture';

function makeFixture(
  id: number,
  statusShort: string,
  homeName = 'Team A',
  awayName = 'Team B',
  elapsed: number | null = null,
  goalsHome: number | null = null,
  goalsAway: number | null = null,
): AFFixture {
  return {
    fixture: {
      id,
      referee: null,
      timezone: 'UTC',
      date: '2026-06-11T18:00:00+00:00',
      timestamp: 1781362800,
      venue: { id: null, name: null, city: null },
      status: { long: statusShort, short: statusShort, elapsed, extra: null },
    },
    league: { id: 1, name: 'World Cup', country: null, logo: null, flag: null, season: 2026, round: null },
    teams: {
      home: { id: 1, name: homeName, logo: null, winner: null },
      away: { id: 2, name: awayName, logo: null, winner: null },
    },
    goals: { home: goalsHome, away: goalsAway },
    score: {
      halftime: { home: null, away: null },
      fulltime: { home: null, away: null },
      extratime: { home: null, away: null },
      penalty: { home: null, away: null },
    },
  };
}

const ContextWrapper: React.FC<{ context: WorldCupOutletContext }> = ({ context }) => (
  <Outlet context={context} />
);

const renderWithContext = (context: Partial<WorldCupOutletContext>) => {
  const fullContext: WorldCupOutletContext = {
    fixtures: [],
    loading: false,
    error: null,
    onRetry: jest.fn(),
    onFixtureClick: jest.fn(),
    ...context,
  };

  return {
    ...render(
      <HelmetProvider>
        <MemoryRouter initialEntries={['/test']}>
          <Routes>
            <Route path="/test" element={<ContextWrapper context={fullContext} />}>
              <Route index element={<LiveMatchPage />} />
            </Route>
          </Routes>
        </MemoryRouter>
      </HelmetProvider>,
    ),
    context: fullContext,
  };
};

describe('LiveMatchPage', () => {
  test('shows loading state when loading', () => {
    renderWithContext({ loading: true });
    expect(screen.getByTestId('loading-state')).toBeInTheDocument();
  });

  test('shows error state when error set', () => {
    renderWithContext({ error: 'Server error' });
    expect(screen.getByTestId('error-state')).toBeInTheDocument();
  });

  test('shows empty state when no in-play fixtures', () => {
    const fixtures = [
      makeFixture(1, 'NS'),
      makeFixture(2, 'FT'),
      makeFixture(3, 'PST'),
    ];
    renderWithContext({ fixtures });

    expect(screen.getByTestId('live-empty-state')).toBeInTheDocument();
    expect(
      screen.getByText('No matches are live right now'),
    ).toBeInTheDocument();
  });

  test('renders live fixture cards for in-play fixtures', () => {
    const fixtures = [
      makeFixture(1, '1H', 'France', 'Germany', 30, 1, 0),
      makeFixture(2, 'NS', 'Brazil', 'Argentina'),
      makeFixture(3, '2H', 'USA', 'Mexico', 67, 2, 1),
    ];
    renderWithContext({ fixtures });

    expect(screen.getByTestId('live-match-list')).toBeInTheDocument();
    expect(screen.getByText('France')).toBeInTheDocument();
    expect(screen.getByText('USA')).toBeInTheDocument();
    // NS fixture excluded
    expect(screen.queryByText('Brazil')).not.toBeInTheDocument();
  });

  test('shows correct count — plural', () => {
    const fixtures = [
      makeFixture(1, '1H', 'A', 'B', 20, 0, 0),
      makeFixture(2, 'HT', 'C', 'D', null, 1, 1),
    ];
    renderWithContext({ fixtures });

    expect(screen.getByText('2 matches live')).toBeInTheDocument();
  });

  test('shows correct count — singular', () => {
    const fixtures = [makeFixture(1, '2H', 'A', 'B', 55, 0, 0)];
    renderWithContext({ fixtures });

    expect(screen.getByText('1 match live')).toBeInTheDocument();
  });

  test('card click calls onFixtureClick with fixture id', async () => {
    const onFixtureClick = jest.fn();
    const fixtures = [
      makeFixture(42, '1H', 'France', 'Germany', 30, 1, 0),
    ];
    renderWithContext({ fixtures, onFixtureClick });

    await userEvent.click(screen.getByText('France'));
    expect(onFixtureClick).toHaveBeenCalledWith(42);
  });

  test('renders LiveBadge with elapsed minute', () => {
    const fixtures = [
      makeFixture(1, '2H', 'A', 'B', 67, 2, 1),
    ];
    renderWithContext({ fixtures });

    expect(screen.getByTestId('live-label')).toHaveTextContent("LIVE 67'");
  });

});
