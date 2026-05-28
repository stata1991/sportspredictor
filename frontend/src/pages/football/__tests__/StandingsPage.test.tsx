import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { HelmetProvider } from 'react-helmet-async';
import StandingsPage from '../StandingsPage';
import { useStandings } from '../../../football/hooks/useStandings';
import { StandingEntry } from '../../../football/types/standings';

jest.mock('../../../football/hooks/useStandings');
const mockedUseStandings = useStandings as jest.MockedFunction<typeof useStandings>;

const renderStandingsPage = () =>
  render(
    <HelmetProvider>
      <MemoryRouter initialEntries={['/football/world-cup-2026/standings']}>
        <Routes>
          <Route
            path="/football/world-cup-2026/standings"
            element={<StandingsPage />}
          />
        </Routes>
      </MemoryRouter>
    </HelmetProvider>,
  );

function makeEntry(
  rank: number,
  teamName: string,
  teamId: number = rank,
  opts: Partial<{ points: number; goalsDiff: number; played: number }> = {},
): StandingEntry {
  return {
    rank,
    team: { id: teamId, name: teamName, logo: null },
    points: opts.points ?? 0,
    goalsDiff: opts.goalsDiff ?? 0,
    group: 'Group A',
    form: null,
    status: null,
    description: null,
    all: {
      played: opts.played ?? 0,
      win: 0,
      draw: 0,
      lose: 0,
      goals: { for: 0, against: 0 },
    },
    home: {
      played: 0,
      win: 0,
      draw: 0,
      lose: 0,
      goals: { for: 0, against: 0 },
    },
    away: {
      played: 0,
      win: 0,
      draw: 0,
      lose: 0,
      goals: { for: 0, against: 0 },
    },
    update: null,
  };
}

describe('StandingsPage', () => {
  afterEach(() => {
    jest.resetAllMocks();
  });

  test('shows loading state while fetching', () => {
    mockedUseStandings.mockReturnValue({ groups: [], loading: true, error: null });
    renderStandingsPage();

    expect(screen.getByTestId('standings-loading')).toBeInTheDocument();
  });

  test('shows error state with retry button', () => {
    mockedUseStandings.mockReturnValue({
      groups: [],
      loading: false,
      error: 'Network error',
    });
    renderStandingsPage();

    expect(screen.getByTestId('standings-error')).toBeInTheDocument();
    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    expect(screen.getByText('Network error')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
  });

  test('shows empty state when no groups', () => {
    mockedUseStandings.mockReturnValue({ groups: [], loading: false, error: null });
    renderStandingsPage();

    expect(screen.getByTestId('standings-empty')).toBeInTheDocument();
    expect(
      screen.getByText('Standings will be available once the group stage begins.'),
    ).toBeInTheDocument();
  });

  test('renders group cards with team names', () => {
    const group: StandingEntry[] = [
      makeEntry(1, 'France', 10, { points: 9, goalsDiff: 5, played: 3 }),
      makeEntry(2, 'Argentina', 20, { points: 6, goalsDiff: 2, played: 3 }),
      makeEntry(3, 'Iraq', 30, { points: 3, goalsDiff: -3, played: 3 }),
      makeEntry(4, 'New Zealand', 40, { points: 0, goalsDiff: -4, played: 3 }),
    ];
    mockedUseStandings.mockReturnValue({ groups: [group], loading: false, error: null });
    renderStandingsPage();

    expect(screen.getByTestId('standings-grid')).toBeInTheDocument();
    expect(screen.getAllByTestId('group-card')).toHaveLength(1);
    expect(screen.getByText('Group A')).toBeInTheDocument();
    expect(screen.getByText('France')).toBeInTheDocument();
    expect(screen.getByText('Argentina')).toBeInTheDocument();
    expect(screen.getByText('Iraq')).toBeInTheDocument();
    expect(screen.getByText('New Zealand')).toBeInTheDocument();
  });

  test('renders multiple group cards', () => {
    const groupA: StandingEntry[] = [
      { ...makeEntry(1, 'France', 10), group: 'Group A' },
      { ...makeEntry(2, 'Argentina', 20), group: 'Group A' },
    ];
    const groupB: StandingEntry[] = [
      { ...makeEntry(1, 'Brazil', 30), group: 'Group B' },
      { ...makeEntry(2, 'Germany', 40), group: 'Group B' },
    ];
    mockedUseStandings.mockReturnValue({
      groups: [groupA, groupB],
      loading: false,
      error: null,
    });
    renderStandingsPage();

    expect(screen.getAllByTestId('group-card')).toHaveLength(2);
    expect(screen.getByText('Group A')).toBeInTheDocument();
    expect(screen.getByText('Group B')).toBeInTheDocument();
  });

  test('displays points and goal difference', () => {
    const group: StandingEntry[] = [
      makeEntry(1, 'France', 10, { points: 9, goalsDiff: 5, played: 3 }),
    ];
    mockedUseStandings.mockReturnValue({ groups: [group], loading: false, error: null });
    renderStandingsPage();

    // Points column shows 9
    expect(screen.getByText('9')).toBeInTheDocument();
    // GD column shows 5
    expect(screen.getByText('5')).toBeInTheDocument();
    // P column shows 3
    expect(screen.getByText('3')).toBeInTheDocument();
  });

  test('sets correct page title', async () => {
    mockedUseStandings.mockReturnValue({ groups: [], loading: false, error: null });
    renderStandingsPage();
    await waitFor(() => {
      expect(document.title).toContain('Group Standings');
    });
  });
});
