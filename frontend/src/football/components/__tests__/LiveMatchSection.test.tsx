import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import LiveMatchSection from '../LiveMatchSection';
import type { LiveResponse } from '../LiveMatchSection';
import * as useLivePollingModule from '../../hooks/useLivePolling';

// Mock the hook so we control data/error/polling state directly
jest.mock('../../hooks/useLivePolling');
const mockUseLivePolling = useLivePollingModule.useLivePolling as jest.Mock;

const MOCK_LIVE_DATA: LiveResponse = {
  fixture_id: 100,
  home_team: 'France',
  away_team: 'Germany',
  status: '2H',
  stage: 'live',
  cached: false,
  confidence: 'low_data',
  predictions: {
    live_winner: {
      elapsed: 67,
      current_score: { home: 2, away: 1 },
      p_home_win: 0.72,
      p_draw: 0.18,
      p_away_win: 0.1,
      expected_total_goals: 3.8,
    },
  },
};

const defaultProps = {
  fixtureId: 100,
  initialStatus: '1H',
  homeTeam: 'France',
  awayTeam: 'Germany',
};

describe('LiveMatchSection', () => {
  const mockRefetch = jest.fn().mockResolvedValue(undefined);

  afterEach(() => {
    jest.resetAllMocks();
  });

  test('shows skeleton before first fetch resolves', () => {
    mockUseLivePolling.mockReturnValue({
      data: null,
      error: null,
      isPolling: true,
      lastUpdated: null,
      refetch: mockRefetch,
    });

    render(<LiveMatchSection {...defaultProps} />);

    expect(screen.getByTestId('live-skeleton')).toBeInTheDocument();
    // Team names shown even during loading
    expect(screen.getByText('France')).toBeInTheDocument();
    expect(screen.getByText('Germany')).toBeInTheDocument();
  });

  test('renders score and probabilities after first poll resolves', () => {
    mockUseLivePolling.mockReturnValue({
      data: MOCK_LIVE_DATA,
      error: null,
      isPolling: true,
      lastUpdated: new Date(),
      refetch: mockRefetch,
    });

    render(<LiveMatchSection {...defaultProps} />);

    expect(screen.getByTestId('live-match-section')).toBeInTheDocument();
    expect(screen.getByTestId('live-score')).toHaveTextContent('2 — 1');
    expect(screen.getByTestId('live-probability-bars')).toBeInTheDocument();
    expect(screen.getByText("LIVE 67'")).toBeInTheDocument();
    expect(screen.getByText('Expected total goals: 3.8')).toBeInTheDocument();
  });

  test('passes enabled=false to hook when status transitions to FT', () => {
    const ftData: LiveResponse = {
      ...MOCK_LIVE_DATA,
      status: 'FT',
      stage: 'completed',
    };

    mockUseLivePolling.mockReturnValue({
      data: ftData,
      error: null,
      isPolling: false,
      lastUpdated: new Date(),
      refetch: mockRefetch,
    });

    render(<LiveMatchSection {...defaultProps} />);

    // Verify the hook was called — the component's useEffect will have
    // set currentStatus to 'FT', causing a re-render with enabled=false.
    // Since the mock doesn't actually poll, we verify via the call args.
    const lastCall = mockUseLivePolling.mock.calls[
      mockUseLivePolling.mock.calls.length - 1
    ][0];
    expect(lastCall.enabled).toBe(false);
  });

  test('shows "Updated Xs ago" text when lastUpdated is set', () => {
    mockUseLivePolling.mockReturnValue({
      data: MOCK_LIVE_DATA,
      error: null,
      isPolling: true,
      lastUpdated: new Date(),
      refetch: mockRefetch,
    });

    render(<LiveMatchSection {...defaultProps} />);

    expect(screen.getByTestId('updated-ago')).toHaveTextContent(
      /Updated \d+s ago/,
    );
  });

  test('shows error with retry button when error before first success', async () => {
    mockUseLivePolling.mockReturnValue({
      data: null,
      error: new Error('Network Error'),
      isPolling: false,
      lastUpdated: null,
      refetch: mockRefetch,
    });

    render(<LiveMatchSection {...defaultProps} />);

    expect(screen.getByTestId('live-error')).toBeInTheDocument();
    expect(
      screen.getByText('Could not load live predictions.'),
    ).toBeInTheDocument();

    const retryBtn = screen.getByRole('button', { name: /retry/i });
    expect(retryBtn).toBeInTheDocument();

    await userEvent.click(retryBtn);
    expect(mockRefetch).toHaveBeenCalledTimes(1);
  });

  test('shows "Reconnecting" when error occurs after successful data', () => {
    mockUseLivePolling.mockReturnValue({
      data: MOCK_LIVE_DATA,
      error: new Error('temporary failure'),
      isPolling: true,
      lastUpdated: new Date(),
      refetch: mockRefetch,
    });

    render(<LiveMatchSection {...defaultProps} />);

    // Data still shows (not blown away)
    expect(screen.getByTestId('live-score')).toHaveTextContent('2 — 1');
    // Reconnecting indicator visible
    expect(screen.getByTestId('reconnecting')).toHaveTextContent(
      'Reconnecting',
    );
  });

  test('LiveBadge shows FT without pulse when match completes', () => {
    const ftData: LiveResponse = {
      ...MOCK_LIVE_DATA,
      status: 'FT',
      stage: 'completed',
    };

    mockUseLivePolling.mockReturnValue({
      data: ftData,
      error: null,
      isPolling: false,
      lastUpdated: new Date(),
      refetch: mockRefetch,
    });

    render(<LiveMatchSection {...defaultProps} />);

    expect(screen.getByTestId('live-label')).toHaveTextContent('FT');
  });

  test('passes correct url and intervalMs to hook', () => {
    mockUseLivePolling.mockReturnValue({
      data: null,
      error: null,
      isPolling: true,
      lastUpdated: null,
      refetch: mockRefetch,
    });

    render(<LiveMatchSection {...defaultProps} />);

    const callArgs = mockUseLivePolling.mock.calls[0][0];
    expect(callArgs.url).toBe('/api/football/predict/live/100');
    expect(callArgs.intervalMs).toBe(60_000);
  });

  // ── Live stats integration (STATS-A) ───────────────────────────────

  const STATS_DATA: LiveResponse = {
    ...MOCK_LIVE_DATA,
    statistics: {
      home: {
        possession: 58, shots_total: 9, shots_on_goal: 4, corners: 5,
        fouls: 7, yellow_cards: 1, red_cards: 0, goalkeeper_saves: 2,
      },
      away: {
        possession: 42, shots_total: 5, shots_on_goal: 1, corners: 2,
        fouls: 11, yellow_cards: 2, red_cards: 0, goalkeeper_saves: 3,
      },
    },
  };

  test('renders the live stats panel when statistics are present', () => {
    mockUseLivePolling.mockReturnValue({
      data: STATS_DATA,
      error: null,
      isPolling: true,
      lastUpdated: new Date(),
      refetch: mockRefetch,
    });

    render(<LiveMatchSection {...defaultProps} />);

    expect(screen.getByTestId('live-stats-panel')).toBeInTheDocument();
    expect(screen.getByTestId('possession-home-pct')).toHaveTextContent('58%');
    expect(screen.getByTestId('stat-row-shots_total')).toHaveTextContent('9');
  });

  test('stats panel shows "coming in" when statistics are null (early match)', () => {
    mockUseLivePolling.mockReturnValue({
      data: { ...MOCK_LIVE_DATA, statistics: null },
      error: null,
      isPolling: true,
      lastUpdated: new Date(),
      refetch: mockRefetch,
    });

    render(<LiveMatchSection {...defaultProps} />);

    expect(screen.getByTestId('live-stats-pending')).toBeInTheDocument();
  });

  test('renders the live note when present, absent when null', () => {
    mockUseLivePolling.mockReturnValue({
      data: {
        ...STATS_DATA,
        live_note: {
          text: 'Brazil are turning the screw and Germany can not get out.',
          trigger: 'goal',
          leaning_side: 'home',
          agrees_with_prediction: true,
          elapsed: 67,
        },
      },
      error: null,
      isPolling: true,
      lastUpdated: new Date(),
      refetch: mockRefetch,
    });
    const { rerender } = render(<LiveMatchSection {...defaultProps} />);
    expect(screen.getByTestId('live-note')).toBeInTheDocument();
    expect(screen.getByTestId('live-note-text')).toHaveTextContent(
      'turning the screw',
    );

    // No note yet (pre-trigger) → absent.
    mockUseLivePolling.mockReturnValue({
      data: { ...STATS_DATA, live_note: null },
      error: null,
      isPolling: true,
      lastUpdated: new Date(),
      refetch: mockRefetch,
    });
    rerender(<LiveMatchSection {...defaultProps} />);
    expect(screen.queryByTestId('live-note')).not.toBeInTheDocument();
  });

  test('live note updates on the same poll tick as the score', () => {
    mockUseLivePolling.mockReturnValue({
      data: {
        ...STATS_DATA,
        live_note: {
          text: 'A first goal for the hosts changes the complexion.',
          trigger: 'goal',
          leaning_side: 'home',
          agrees_with_prediction: true,
          elapsed: 40,
        },
      },
      error: null,
      isPolling: true,
      lastUpdated: new Date(),
      refetch: mockRefetch,
    });
    const { rerender } = render(<LiveMatchSection {...defaultProps} />);
    expect(screen.getByTestId('live-note-meta')).toHaveTextContent("· 40'");

    // Next tick: lean crosses; note + meta update together with the data.
    mockUseLivePolling.mockReturnValue({
      data: {
        ...STATS_DATA,
        live_note: {
          text: 'Germany have wrested back control despite trailing.',
          trigger: 'lean_cross',
          leaning_side: 'away',
          agrees_with_prediction: false,
          elapsed: 58,
        },
      },
      error: null,
      isPolling: true,
      lastUpdated: new Date(),
      refetch: mockRefetch,
    });
    rerender(<LiveMatchSection {...defaultProps} />);
    expect(screen.getByTestId('live-note-text')).toHaveTextContent(
      'wrested back control',
    );
    expect(screen.getByTestId('live-note-meta')).toHaveTextContent(
      'as the game shifts',
    );
  });

  test('stats refresh on the same poll tick as the score (single data source)', () => {
    // First tick: 2–1 with 58% possession.
    mockUseLivePolling.mockReturnValue({
      data: STATS_DATA,
      error: null,
      isPolling: true,
      lastUpdated: new Date(),
      refetch: mockRefetch,
    });
    const { rerender } = render(<LiveMatchSection {...defaultProps} />);
    expect(screen.getByTestId('live-score')).toHaveTextContent('2 — 1');
    expect(screen.getByTestId('possession-home-pct')).toHaveTextContent('58%');

    // Next poll tick delivers new score AND new stats together — one source.
    mockUseLivePolling.mockReturnValue({
      data: {
        ...STATS_DATA,
        predictions: {
          live_winner: {
            ...STATS_DATA.predictions.live_winner,
            current_score: { home: 3, away: 1 },
          },
        },
        statistics: {
          ...STATS_DATA.statistics!,
          home: { ...STATS_DATA.statistics!.home, possession: 63 },
          away: { ...STATS_DATA.statistics!.away, possession: 37 },
        },
      },
      error: null,
      isPolling: true,
      lastUpdated: new Date(),
      refetch: mockRefetch,
    });
    rerender(<LiveMatchSection {...defaultProps} />);

    expect(screen.getByTestId('live-score')).toHaveTextContent('3 — 1');
    expect(screen.getByTestId('possession-home-pct')).toHaveTextContent('63%');
  });
});
