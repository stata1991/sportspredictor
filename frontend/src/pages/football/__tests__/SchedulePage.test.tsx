import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route, Outlet } from 'react-router-dom';
import { HelmetProvider } from 'react-helmet-async';
import SchedulePage from '../SchedulePage';
import { WorldCupOutletContext } from '../../../football/types/outletContext';
import { AFFixture } from '../../../football/types/fixture';

function makeFixture(id: number, homeName: string, awayName: string): AFFixture {
  return {
    fixture: {
      id,
      referee: null,
      timezone: 'UTC',
      date: '2026-06-11T18:00:00+00:00',
      timestamp: 1781362800,
      venue: { id: null, name: null, city: null },
      status: { long: 'Not Started', short: 'NS', elapsed: null, extra: null },
    },
    league: { id: 1, name: 'World Cup', country: null, logo: null, flag: null, season: 2026, round: null },
    teams: {
      home: { id: 1, name: homeName, logo: null, winner: null },
      away: { id: 2, name: awayName, logo: null, winner: null },
    },
    goals: { home: null, away: null },
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

  return render(
    <HelmetProvider>
      <MemoryRouter initialEntries={['/test']}>
        <Routes>
          <Route path="/test" element={<ContextWrapper context={fullContext} />}>
            <Route index element={<SchedulePage />} />
          </Route>
        </Routes>
      </MemoryRouter>
    </HelmetProvider>,
  );
};

describe('SchedulePage', () => {
  test('shows loading skeletons when loading', () => {
    renderWithContext({ loading: true });
    expect(screen.getByTestId('loading-state')).toBeInTheDocument();
  });

  test('shows error state with retry button', async () => {
    const onRetry = jest.fn();
    renderWithContext({ error: 'Server down', onRetry });

    expect(screen.getByTestId('error-state')).toBeInTheDocument();
    expect(screen.getByText('Server down')).toBeInTheDocument();

    await userEvent.click(screen.getByText('Retry'));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  test('shows empty state when no fixtures', () => {
    renderWithContext({ fixtures: [] });
    expect(screen.getByTestId('empty-state')).toBeInTheDocument();
    expect(
      screen.getByText('Fixtures publish closer to kickoff. Check back soon.'),
    ).toBeInTheDocument();
  });

  test('renders fixture list when fixtures exist', () => {
    const fixtures = [
      makeFixture(1, 'France', 'Germany'),
      makeFixture(2, 'Brazil', 'Argentina'),
    ];
    renderWithContext({ fixtures });

    expect(screen.getByText('France')).toBeInTheDocument();
    expect(screen.getByText('Germany')).toBeInTheDocument();
    expect(screen.getByText('Brazil')).toBeInTheDocument();
    expect(screen.getByText('Argentina')).toBeInTheDocument();
  });

});
