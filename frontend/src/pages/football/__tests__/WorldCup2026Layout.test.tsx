import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { HelmetProvider } from 'react-helmet-async';
import WorldCup2026Layout from '../WorldCup2026Layout';
import SchedulePage from '../SchedulePage';
import LiveMatchPage from '../LiveMatchPage';
import TrackRecordPage from '../TrackRecordPage';
import * as useFixturesModule from '../../../football/hooks/useFixtures';
import * as useAccuracyModule from '../../../football/hooks/useAccuracy';
import { AFFixture } from '../../../football/types/fixture';

jest.mock('../../../football/hooks/useFixtures');
jest.mock('../../../football/hooks/useAccuracy');

const mockUseFixtures = useFixturesModule.useFixtures as jest.Mock;
const mockUseAccuracy = useAccuracyModule.useAccuracy as jest.Mock;

function makeFixture(id: number, statusShort: string): AFFixture {
  return {
    fixture: {
      id,
      referee: null,
      timezone: 'UTC',
      date: '2026-06-11T18:00:00+00:00',
      timestamp: 1781362800,
      venue: { id: null, name: null, city: null },
      status: { long: statusShort, short: statusShort, elapsed: null, extra: null },
    },
    league: { id: 1, name: 'World Cup', country: null, logo: null, flag: null, season: 2026, round: null },
    teams: {
      home: { id: 1, name: 'Team A', logo: null, winner: null },
      away: { id: 2, name: 'Team B', logo: null, winner: null },
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

const renderLayout = (initialPath = '/football/world-cup-2026') =>
  render(
    <HelmetProvider>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path="/football/world-cup-2026" element={<WorldCup2026Layout />}>
            <Route index element={<SchedulePage />} />
            <Route path="live" element={<LiveMatchPage />} />
            <Route path="track-record" element={<TrackRecordPage />} />
          </Route>
          <Route
            path="/football/match/:fixtureId"
            element={<div data-testid="match-page">Match</div>}
          />
        </Routes>
      </MemoryRouter>
    </HelmetProvider>,
  );

describe('WorldCup2026Layout', () => {
  beforeEach(() => {
    mockUseFixtures.mockReturnValue({
      fixtures: [makeFixture(1, 'NS')],
      loading: false,
      error: null,
    });
    mockUseAccuracy.mockReturnValue({
      rollups: [],
      loading: false,
      error: null,
    });
  });

  afterEach(() => {
    jest.resetAllMocks();
  });

  test('renders page title', () => {
    renderLayout();
    expect(screen.getByText('FIFA World Cup 2026')).toBeInTheDocument();
  });

  test('renders three tabs', () => {
    renderLayout();
    expect(screen.getByTestId('tab-schedule')).toBeInTheDocument();
    expect(screen.getByTestId('tab-live')).toBeInTheDocument();
    expect(screen.getByTestId('tab-track-record')).toBeInTheDocument();
  });

  test('Schedule tab is active by default on index route', () => {
    renderLayout();
    const tab = screen.getByTestId('tab-schedule');
    expect(tab).toHaveAttribute('aria-selected', 'true');
  });

  test('clicking Live Match tab navigates to /live', async () => {
    renderLayout();

    await userEvent.click(screen.getByTestId('tab-live'));

    expect(screen.getByTestId('tab-live').closest('[role="tab"]')).toHaveAttribute(
      'aria-selected',
      'true',
    );
  });

  test('clicking Track Record tab renders track record content', async () => {
    renderLayout();

    await userEvent.click(screen.getByTestId('tab-track-record'));

    expect(screen.getByTestId('empty-state')).toBeInTheDocument();
    expect(screen.getByText('No accuracy data yet')).toBeInTheDocument();
  });

  test('Live tab shows pulsing dot when fixtures are in-play', () => {
    mockUseFixtures.mockReturnValue({
      fixtures: [makeFixture(1, '1H'), makeFixture(2, 'NS')],
      loading: false,
      error: null,
    });

    renderLayout();

    expect(screen.getByTestId('live-tab-dot')).toBeInTheDocument();
  });

  test('Live tab has no dot when no fixtures are in-play', () => {
    mockUseFixtures.mockReturnValue({
      fixtures: [makeFixture(1, 'NS'), makeFixture(2, 'FT')],
      loading: false,
      error: null,
    });

    renderLayout();

    expect(screen.queryByTestId('live-tab-dot')).not.toBeInTheDocument();
  });

  test('direct navigation to /live renders LiveMatchPage', () => {
    renderLayout('/football/world-cup-2026/live');

    expect(screen.getByTestId('tab-live').closest('[role="tab"]')).toHaveAttribute(
      'aria-selected',
      'true',
    );
    expect(screen.getByTestId('live-empty-state')).toBeInTheDocument();
  });

  test('direct navigation to /track-record renders TrackRecordPage', () => {
    renderLayout('/football/world-cup-2026/track-record');

    expect(screen.getByTestId('tab-track-record').closest('[role="tab"]')).toHaveAttribute(
      'aria-selected',
      'true',
    );
    expect(screen.getByText('No accuracy data yet')).toBeInTheDocument();
  });

  describe.each([
    ['/football/world-cup-2026', 'FIFA World Cup 2026 Schedule'],
    ['/football/world-cup-2026/live', 'Live Matches'],
    ['/football/world-cup-2026/track-record', 'Prediction Track Record'],
  ])('title at %s', (path, expected) => {
    test(`sets title containing "${expected}"`, async () => {
      renderLayout(path);
      await waitFor(() => {
        expect(document.title).toContain(expected);
      });
    });
  });
});
