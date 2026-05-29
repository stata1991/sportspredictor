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
  opts: Partial<{ points: number; goalsDiff: number; played: number; group: string }> = {},
): StandingEntry {
  return {
    rank,
    team: { id: teamId, name: teamName, logo: null },
    points: opts.points ?? 0,
    goalsDiff: opts.goalsDiff ?? 0,
    group: opts.group ?? 'Group A',
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

function makeGroup(groupName: string): StandingEntry[] {
  return [
    makeEntry(1, `${groupName}-T1`, 100, { group: groupName }),
    makeEntry(2, `${groupName}-T2`, 200, { group: groupName }),
    makeEntry(3, `${groupName}-T3`, 300, { group: groupName }),
    makeEntry(4, `${groupName}-T4`, 400, { group: groupName }),
  ];
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

  test('loading skeleton includes ranking placeholder', () => {
    mockedUseStandings.mockReturnValue({ groups: [], loading: true, error: null });
    renderStandingsPage();

    expect(screen.getByTestId('ranking-skeleton')).toBeInTheDocument();
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
    const groupA = makeGroup('Group A');
    const groupB = makeGroup('Group B');
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
      makeEntry(2, 'Germany', 20),
      makeEntry(3, 'Brazil', 30),
      makeEntry(4, 'Spain', 40),
    ];
    mockedUseStandings.mockReturnValue({ groups: [group], loading: false, error: null });
    renderStandingsPage();

    // Points column shows 9
    expect(screen.getByText('9')).toBeInTheDocument();
    // GD column shows 5
    expect(screen.getByText('5')).toBeInTheDocument();
    // P column: "3" appears for both played and rank; verify at least one exists
    expect(screen.getAllByText('3').length).toBeGreaterThanOrEqual(1);
  });

  test('sets correct page title', async () => {
    mockedUseStandings.mockReturnValue({ groups: [], loading: false, error: null });
    renderStandingsPage();
    await waitFor(() => {
      expect(document.title).toContain('Group Standings');
    });
  });

  // ── Third-place ranking section ────────────────────────────────

  test('renders ranking section below grid when ranking exists', () => {
    const groupA = makeGroup('Group A');
    const ranking = Array.from({ length: 12 }, (_, i) =>
      makeEntry(i + 1, `Third-${i + 1}`, 500 + i, {
        group: 'Ranking of third-placed teams',
      }),
    );
    mockedUseStandings.mockReturnValue({
      groups: [groupA, ranking],
      loading: false,
      error: null,
    });
    renderStandingsPage();

    // Real group rendered
    expect(screen.getAllByTestId('group-card')).toHaveLength(1);
    // Ranking section rendered
    expect(screen.getByTestId('third-place-section')).toBeInTheDocument();
    expect(screen.getByTestId('third-place-card')).toBeInTheDocument();
    expect(screen.getByText('Third-Placed Team Rankings')).toBeInTheDocument();
    expect(
      screen.getByText('Best 8 of 12 third-placed teams advance to the Round of 32'),
    ).toBeInTheDocument();
  });

  test('does not render ranking section when no ranking exists', () => {
    const groupA = makeGroup('Group A');
    mockedUseStandings.mockReturnValue({
      groups: [groupA],
      loading: false,
      error: null,
    });
    renderStandingsPage();

    expect(screen.getAllByTestId('group-card')).toHaveLength(1);
    expect(screen.queryByTestId('third-place-section')).not.toBeInTheDocument();
  });

  test('ranking section contains team names from ranking entries', () => {
    const groupA = makeGroup('Group A');
    const ranking = [
      makeEntry(1, 'South Korea', 601, { group: 'Ranking of third-placed teams' }),
      makeEntry(2, 'Qatar', 602, { group: 'Ranking of third-placed teams' }),
      makeEntry(3, 'Haiti', 603, { group: 'Ranking of third-placed teams' }),
    ];
    mockedUseStandings.mockReturnValue({
      groups: [groupA, ranking],
      loading: false,
      error: null,
    });
    renderStandingsPage();

    expect(screen.getByText('South Korea')).toBeInTheDocument();
    expect(screen.getByText('Qatar')).toBeInTheDocument();
    expect(screen.getByText('Haiti')).toBeInTheDocument();
  });
});
