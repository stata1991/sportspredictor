import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { HelmetProvider } from 'react-helmet-async';
import MatchPage from '../MatchPage';
import api from '../../../api';
import { FULL_RESPONSE } from '../../../football/__fixtures__/sampleResponse';

jest.mock('../../../api');
const mockedApi = api as jest.Mocked<typeof api>;

// Mock LiveMatchSection to avoid real polling in MatchPage tests
jest.mock('../../../football/components/LiveMatchSection', () => {
  return function MockLiveMatchSection(props: {
    fixtureId: number;
    initialStatus: string;
  }) {
    return (
      <div
        data-testid="live-match-section"
        data-fixture-id={props.fixtureId}
        data-initial-status={props.initialStatus}
      />
    );
  };
});

const renderMatchPage = (fixtureId = '1489369') =>
  render(
    <HelmetProvider>
      <MemoryRouter initialEntries={[`/football/match/${fixtureId}`]}>
        <Routes>
          <Route path="/football/match/:fixtureId" element={<MatchPage />} />
          <Route
            path="/football/world-cup-2026"
            element={<div data-testid="fixtures-page">Fixtures</div>}
          />
        </Routes>
      </MemoryRouter>
    </HelmetProvider>,
  );

describe('MatchPage', () => {
  afterEach(() => {
    jest.resetAllMocks();
  });

  test('shows loading spinner while fetching', () => {
    mockedApi.get.mockReturnValue(new Promise(() => {}));
    renderMatchPage();

    expect(screen.getByText('Loading prediction…')).toBeInTheDocument();
  });

  test('renders WhyPanel on successful fetch', async () => {
    mockedApi.get.mockResolvedValueOnce({ data: FULL_RESPONSE });
    renderMatchPage();

    await waitFor(() => {
      expect(screen.getByTestId('why-panel')).toBeInTheDocument();
    });

    expect(screen.getByTestId('numbers-section')).toBeInTheDocument();
  });

  test('shows not-found error for 404', async () => {
    const notFoundError = Object.assign(new Error('Not Found'), {
      isAxiosError: true,
      response: { status: 404, data: { detail: 'Fixture 999 not found' } },
    });
    mockedApi.get.mockRejectedValueOnce(notFoundError);

    renderMatchPage('999');

    await waitFor(() => {
      expect(screen.getByTestId('error-not-found')).toBeInTheDocument();
    });

    expect(screen.getByText('Fixture Not Found')).toBeInTheDocument();
    expect(screen.getByText(/999/)).toBeInTheDocument();
  });

  test('shows MatchUnavailableSection for not-predictable 422', async () => {
    const axiosError = Object.assign(new Error('Unprocessable'), {
      isAxiosError: true,
      response: {
        status: 422,
        data: { detail: "Fixture status 'PST' is not predictable" },
      },
    });
    mockedApi.get.mockRejectedValueOnce(axiosError);

    renderMatchPage();

    await waitFor(() => {
      expect(screen.getByTestId('match-unavailable')).toBeInTheDocument();
    });

    expect(screen.getByText('Match Unavailable')).toBeInTheDocument();
    expect(
      screen.getByText('This match has been postponed.'),
    ).toBeInTheDocument();
  });

  test('renders LiveMatchSection for live 422', async () => {
    const liveError = Object.assign(new Error('Unprocessable'), {
      isAxiosError: true,
      response: {
        status: 422,
        data: {
          detail: 'Fixture is live. Use /predict/live/{fixture_id} instead.',
        },
      },
    });
    mockedApi.get.mockRejectedValueOnce(liveError);

    renderMatchPage('1536931');

    await waitFor(() => {
      expect(screen.getByTestId('live-match-section')).toBeInTheDocument();
    });

    const el = screen.getByTestId('live-match-section');
    expect(el).toHaveAttribute('data-fixture-id', '1536931');
    expect(el).toHaveAttribute('data-initial-status', '1H');
  });

  test('shows network error with retry for 500', async () => {
    const serverError = Object.assign(new Error('Internal Server Error'), {
      isAxiosError: true,
      response: { status: 500, data: 'Internal Server Error' },
    });
    mockedApi.get.mockRejectedValueOnce(serverError);

    renderMatchPage();

    await waitFor(() => {
      expect(screen.getByTestId('error-network')).toBeInTheDocument();
    });

    expect(screen.getByText('Connection Error')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
  });

  test('retry button re-fetches prediction', async () => {
    const serverError = Object.assign(new Error('Internal Server Error'), {
      isAxiosError: true,
      response: { status: 500, data: 'Internal Server Error' },
    });
    mockedApi.get.mockRejectedValueOnce(serverError);

    renderMatchPage();

    await waitFor(() => {
      expect(screen.getByTestId('error-network')).toBeInTheDocument();
    });

    // Second attempt succeeds
    mockedApi.get.mockResolvedValueOnce({ data: FULL_RESPONSE });

    await userEvent.click(screen.getByRole('button', { name: /retry/i }));

    await waitFor(() => {
      expect(screen.getByTestId('why-panel')).toBeInTheDocument();
    });

    // 2 prediction calls (initial + retry) + H2H call after retry succeeds
    expect(mockedApi.get).toHaveBeenCalledTimes(3);
  });

  test('shows partial agent notice when reasoning is missing', async () => {
    const partial = {
      ...FULL_RESPONSE,
      reasoning: null,
      upset: null,
    };
    mockedApi.get.mockResolvedValueOnce({ data: partial });

    renderMatchPage();

    await waitFor(() => {
      expect(screen.getByTestId('why-panel')).toBeInTheDocument();
    });

    expect(screen.getByTestId('partial-agent-notice')).toBeInTheDocument();
  });

  test('shows LiveBadge with FT for completed fixture', async () => {
    const completedResponse = {
      ...FULL_RESPONSE,
      status: 'FT',
      stage: 'completed',
      cached: true,
      message: 'Fixture already completed. Returning most recent pre-match predictions.',
    };
    mockedApi.get.mockResolvedValueOnce({ data: completedResponse });

    renderMatchPage();

    await waitFor(() => {
      expect(screen.getByTestId('why-panel')).toBeInTheDocument();
    });

    expect(screen.getByTestId('live-badge')).toBeInTheDocument();
    expect(screen.getByTestId('live-label')).toHaveTextContent('FT');
  });

  test('does not show LiveBadge for pre-match fixture', async () => {
    mockedApi.get.mockResolvedValueOnce({ data: FULL_RESPONSE });

    renderMatchPage();

    await waitFor(() => {
      expect(screen.getByTestId('why-panel')).toBeInTheDocument();
    });

    expect(screen.queryByTestId('live-badge')).not.toBeInTheDocument();
  });

  test('back button navigates to fixtures page', async () => {
    mockedApi.get.mockReturnValue(new Promise(() => {}));

    renderMatchPage();

    await userEvent.click(screen.getByText('Back to Fixtures'));

    await waitFor(() => {
      expect(screen.getByTestId('fixtures-page')).toBeInTheDocument();
    });
  });

  test('sets dynamic page title with team names after fetch', async () => {
    mockedApi.get.mockResolvedValueOnce({ data: FULL_RESPONSE });
    renderMatchPage();

    await waitFor(() => {
      expect(document.title).toContain('Mexico vs South Africa Prediction');
    });
  });

  // ── Round badge (KO-2) ─────────────────────────────────────────

  test('renders round badge with short label when round present', async () => {
    // FULL_RESPONSE carries round = "Group Stage - 1" → "MD1".
    mockedApi.get.mockResolvedValueOnce({ data: FULL_RESPONSE });
    renderMatchPage();

    await waitFor(() => {
      expect(screen.getByTestId('round-badge')).toBeInTheDocument();
    });
    expect(screen.getByTestId('round-badge')).toHaveTextContent('MD1');
  });

  test('renders knockout round badge (Final)', async () => {
    mockedApi.get.mockResolvedValueOnce({
      data: { ...FULL_RESPONSE, round: 'Final' },
    });
    renderMatchPage();

    await waitFor(() => {
      expect(screen.getByTestId('round-badge')).toHaveTextContent('Final');
    });
  });

  test('renders no round badge when round absent, page still renders', async () => {
    const { round, ...noRound } = FULL_RESPONSE;
    void round;
    mockedApi.get.mockResolvedValueOnce({ data: noRound });
    renderMatchPage();

    await waitFor(() => {
      expect(screen.getByTestId('why-panel')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('round-badge')).not.toBeInTheDocument();
  });
});
