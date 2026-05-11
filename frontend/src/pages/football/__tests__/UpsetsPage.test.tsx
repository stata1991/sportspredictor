import React from 'react';
import { render, screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { HelmetProvider } from 'react-helmet-async';
import UpsetsPage from '../UpsetsPage';
import { useUpsets } from '../../../football/hooks/useUpsets';

jest.mock('../../../football/hooks/useUpsets');
const mockedUseUpsets = useUpsets as jest.MockedFunction<typeof useUpsets>;

const renderUpsetsPage = () =>
  render(
    <HelmetProvider>
      <MemoryRouter initialEntries={['/football/upsets']}>
        <Routes>
          <Route path="/football/upsets" element={<UpsetsPage />} />
          <Route
            path="/football/match/:fixtureId"
            element={<div data-testid="match-page">Match</div>}
          />
        </Routes>
      </MemoryRouter>
    </HelmetProvider>,
  );

const makeUpset = (overrides: Partial<{
  fixture_id: number;
  home_team: string;
  away_team: string;
  kickoff: string;
  upset_index: number;
  status: string;
  round: string;
  upset_paths: string[];
  home_logo: string | null;
  away_logo: string | null;
}> = {}) => ({
  fixture_id: overrides.fixture_id ?? 100,
  home_team: overrides.home_team ?? 'Germany',
  away_team: overrides.away_team ?? 'Curaçao',
  home_logo: overrides.home_logo ?? null,
  away_logo: overrides.away_logo ?? null,
  kickoff: overrides.kickoff ?? '2026-06-14T19:00:00+02:00',
  status: overrides.status ?? 'NS',
  round: overrides.round ?? 'Group E - 1',
  upset_index: overrides.upset_index ?? 0.54,
  upset_paths: overrides.upset_paths ?? ['Curaçao win'],
});

describe('UpsetsPage', () => {
  afterEach(() => {
    jest.resetAllMocks();
  });

  test('shows loading state while fetching', () => {
    mockedUseUpsets.mockReturnValue({ upsets: [], loading: true, error: null });
    renderUpsetsPage();

    expect(screen.getByTestId('loading-state')).toBeInTheDocument();
  });

  test('shows error state with retry button', () => {
    mockedUseUpsets.mockReturnValue({
      upsets: [],
      loading: false,
      error: 'fetch failed',
    });
    renderUpsetsPage();

    expect(screen.getByTestId('error-state')).toBeInTheDocument();
    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    expect(screen.getByText('fetch failed')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
  });

  test('shows empty state when no upsets qualify', () => {
    mockedUseUpsets.mockReturnValue({ upsets: [], loading: false, error: null });
    renderUpsetsPage();

    expect(screen.getByTestId('empty-state')).toBeInTheDocument();
    expect(screen.getByText('No upset alerts right now.')).toBeInTheDocument();
    expect(
      screen.getByText('Check back closer to kickoff.'),
    ).toBeInTheDocument();
  });

  test('renders a single upset with badge', () => {
    mockedUseUpsets.mockReturnValue({
      upsets: [makeUpset()],
      loading: false,
      error: null,
    });
    renderUpsetsPage();

    expect(screen.getByText('Germany')).toBeInTheDocument();
    expect(screen.getByText('Curaçao')).toBeInTheDocument();
    expect(screen.getByTestId('upset-badge')).toHaveTextContent(
      'Upset risk: 54.0%',
    );
  });

  test('groups upsets by date with chronological headers', () => {
    mockedUseUpsets.mockReturnValue({
      upsets: [
        makeUpset({
          fixture_id: 1,
          home_team: 'A',
          away_team: 'B',
          kickoff: '2026-06-15T18:00:00+00:00',
          upset_index: 0.5,
        }),
        makeUpset({
          fixture_id: 2,
          home_team: 'C',
          away_team: 'D',
          kickoff: '2026-06-14T18:00:00+00:00',
          upset_index: 0.6,
        }),
        makeUpset({
          fixture_id: 3,
          home_team: 'E',
          away_team: 'F',
          kickoff: '2026-06-15T20:00:00+00:00',
          upset_index: 0.7,
        }),
      ],
      loading: false,
      error: null,
    });
    renderUpsetsPage();

    const headers = screen.getAllByTestId('day-header');
    expect(headers).toHaveLength(2);
    // June 14 should come before June 15
    expect(headers[0].textContent).toMatch(/June 14/);
    expect(headers[1].textContent).toMatch(/June 15/);
  });

  test('sorts within date group by upset_index descending', () => {
    mockedUseUpsets.mockReturnValue({
      upsets: [
        makeUpset({
          fixture_id: 1,
          home_team: 'Low',
          away_team: 'Risk',
          kickoff: '2026-06-14T18:00:00+00:00',
          upset_index: 0.48,
        }),
        makeUpset({
          fixture_id: 2,
          home_team: 'High',
          away_team: 'Risk',
          kickoff: '2026-06-14T20:00:00+00:00',
          upset_index: 0.72,
        }),
      ],
      loading: false,
      error: null,
    });
    renderUpsetsPage();

    const badges = screen.getAllByTestId('upset-badge');
    expect(badges).toHaveLength(2);
    // Higher upset index first
    expect(badges[0]).toHaveTextContent('72.0%');
    expect(badges[1]).toHaveTextContent('48.0%');
  });

  test('clicking a card navigates to match page', async () => {
    mockedUseUpsets.mockReturnValue({
      upsets: [makeUpset({ fixture_id: 42 })],
      loading: false,
      error: null,
    });
    renderUpsetsPage();

    const button = screen.getByRole('button');
    await userEvent.click(button);

    expect(screen.getByTestId('match-page')).toBeInTheDocument();
  });

  test('sets correct page title', async () => {
    mockedUseUpsets.mockReturnValue({ upsets: [], loading: false, error: null });
    renderUpsetsPage();
    await waitFor(() => {
      expect(document.title).toContain('Upset Watch');
    });
  });
});
