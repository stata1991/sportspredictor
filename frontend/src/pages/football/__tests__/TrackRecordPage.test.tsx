import React from 'react';
import { render, screen, within } from '@testing-library/react';
import TrackRecordPage from '../TrackRecordPage';
import * as useAccuracyModule from '../../../football/hooks/useAccuracy';

jest.mock('../../../football/hooks/useAccuracy');
const mockUseAccuracy = useAccuracyModule.useAccuracy as jest.Mock;

describe('TrackRecordPage', () => {
  afterEach(() => {
    jest.resetAllMocks();
  });

  test('shows loading skeletons when loading', () => {
    mockUseAccuracy.mockReturnValue({
      rollups: [],
      loading: true,
      error: null,
    });

    render(<TrackRecordPage />);
    expect(screen.getByTestId('loading-state')).toBeInTheDocument();
  });

  test('shows error state when error set', () => {
    mockUseAccuracy.mockReturnValue({
      rollups: [],
      loading: false,
      error: 'Server error',
    });

    render(<TrackRecordPage />);
    expect(screen.getByTestId('error-state')).toBeInTheDocument();
    expect(screen.getByText('Could not load accuracy data')).toBeInTheDocument();
  });

  test('shows empty state when rollups is empty', () => {
    mockUseAccuracy.mockReturnValue({
      rollups: [],
      loading: false,
      error: null,
    });

    render(<TrackRecordPage />);
    expect(screen.getByTestId('empty-state')).toBeInTheDocument();
    expect(screen.getByText('No accuracy data yet')).toBeInTheDocument();
  });

  test('renders KPI cards from all_time + winner rollup', () => {
    mockUseAccuracy.mockReturnValue({
      rollups: [
        {
          window: 'all_time',
          prediction_type: 'winner',
          total_predictions: 42,
          brier_score: 0.215,
          log_loss: 0.68,
          top_pick_hit_rate: 0.71,
          computed_at: '2026-05-09T12:00:00Z',
        },
      ],
      loading: false,
      error: null,
    });

    render(<TrackRecordPage />);

    const kpiSection = screen.getByTestId('kpi-section');
    expect(kpiSection).toBeInTheDocument();
    const kpiCards = screen.getAllByTestId('kpi-card');
    expect(kpiCards).toHaveLength(3);

    const kpi = within(kpiSection);
    expect(kpi.getByText('Top Pick Hit Rate')).toBeInTheDocument();
    expect(kpi.getByText('71%')).toBeInTheDocument();
    expect(kpi.getByText('42')).toBeInTheDocument();
    expect(kpi.getByText('0.215')).toBeInTheDocument();
  });

  test('hides KPI section when no all_time + winner rollup', () => {
    mockUseAccuracy.mockReturnValue({
      rollups: [
        {
          window: 'last_7d',
          prediction_type: 'winner',
          total_predictions: 8,
          brier_score: 0.198,
          log_loss: 0.62,
          top_pick_hit_rate: 0.75,
          computed_at: '2026-05-09T12:00:00Z',
        },
      ],
      loading: false,
      error: null,
    });

    render(<TrackRecordPage />);

    expect(screen.queryByTestId('kpi-section')).not.toBeInTheDocument();
    // Table still renders
    expect(screen.getByTestId('accuracy-table')).toBeInTheDocument();
  });

  test('renders breakdown table with all rollups', () => {
    mockUseAccuracy.mockReturnValue({
      rollups: [
        {
          window: 'all_time',
          prediction_type: 'winner',
          total_predictions: 42,
          brier_score: 0.215,
          log_loss: 0.68,
          top_pick_hit_rate: 0.71,
          computed_at: null,
        },
        {
          window: 'last_7d',
          prediction_type: 'total_goals',
          total_predictions: 8,
          brier_score: 0.241,
          log_loss: 0.71,
          top_pick_hit_rate: 0.54,
          computed_at: null,
        },
      ],
      loading: false,
      error: null,
    });

    render(<TrackRecordPage />);

    expect(screen.getByTestId('accuracy-table')).toBeInTheDocument();
    expect(screen.getByText('All Time')).toBeInTheDocument();
    expect(screen.getByText('Last 7 Days')).toBeInTheDocument();
    expect(screen.getByText('Winner')).toBeInTheDocument();
    expect(screen.getByText('Total Goals')).toBeInTheDocument();
  });

  test('handles null metric values with dashes', () => {
    mockUseAccuracy.mockReturnValue({
      rollups: [
        {
          window: 'all_time',
          prediction_type: 'winner',
          total_predictions: 5,
          brier_score: null,
          log_loss: null,
          top_pick_hit_rate: null,
          computed_at: null,
        },
      ],
      loading: false,
      error: null,
    });

    render(<TrackRecordPage />);

    const dashes = screen.getAllByText('--');
    expect(dashes.length).toBeGreaterThanOrEqual(3);
  });
});
