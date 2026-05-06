import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import MatchPage from '../MatchPage';
import api from '../../../api';
import { FULL_RESPONSE } from '../../../football/__fixtures__/sampleResponse';

jest.mock('../../../api');
const mockedApi = api as jest.Mocked<typeof api>;

const renderMatchPage = (fixtureId = '1489369') =>
  render(
    <MemoryRouter initialEntries={[`/football/match/${fixtureId}`]}>
      <Routes>
        <Route path="/football/match/:fixtureId" element={<MatchPage />} />
        <Route
          path="/football/world-cup-2026"
          element={<div data-testid="fixtures-page">Fixtures</div>}
        />
      </Routes>
    </MemoryRouter>,
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

  test('shows not-predictable error for 422', async () => {
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
      expect(screen.getByTestId('error-not-predictable')).toBeInTheDocument();
    });

    expect(screen.getByText('Not Predictable')).toBeInTheDocument();
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

    expect(mockedApi.get).toHaveBeenCalledTimes(2);
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

  test('back button navigates to fixtures page', async () => {
    mockedApi.get.mockReturnValue(new Promise(() => {}));

    renderMatchPage();

    await userEvent.click(screen.getByText('Back to Fixtures'));

    await waitFor(() => {
      expect(screen.getByTestId('fixtures-page')).toBeInTheDocument();
    });
  });
});
