import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import ScorelineHeatmap from '../ScorelineHeatmap';

// Synthetic 8×8 matrix — readable values, max at (0,0) = 30%.
const fixtureMatrix: number[][] = [
  [0.30, 0.10, 0.03, 0.005, 0, 0, 0, 0],
  [0.20, 0.12, 0.04, 0.005, 0, 0, 0, 0],
  [0.08, 0.05, 0.02, 0,     0, 0, 0, 0],
  [0.02, 0.01, 0,    0,     0, 0, 0, 0],
  [0,    0,    0,    0,     0, 0, 0, 0],
  [0,    0,    0,    0,     0, 0, 0, 0],
  [0,    0,    0,    0,     0, 0, 0, 0],
  [0,    0,    0,    0,     0, 0, 0, 0],
];

const baseProps = {
  matrix: fixtureMatrix,
  homeTeam: 'Mexico',
  awayTeam: 'South Africa',
};

/** Render and expand so content tests can inspect the grid. */
function renderExpanded(props = baseProps) {
  const result = render(<ScorelineHeatmap {...props} />);
  fireEvent.click(screen.getByTestId('heatmap-toggle'));
  return result;
}

describe('ScorelineHeatmap', () => {
  // ── Toggle behavior ─────────────────────────────────────────────

  test('renders toggle button by default', () => {
    render(<ScorelineHeatmap {...baseProps} />);

    expect(screen.getByTestId('heatmap-toggle')).toBeInTheDocument();
  });

  test('heatmap content is hidden by default', () => {
    const { container } = render(<ScorelineHeatmap {...baseProps} />);

    expect(container.querySelectorAll('[data-cell="true"]')).toHaveLength(0);
  });

  test('clicking toggle expands content', () => {
    const { container } = render(<ScorelineHeatmap {...baseProps} />);

    fireEvent.click(screen.getByTestId('heatmap-toggle'));

    expect(container.querySelectorAll('[data-cell="true"]')).toHaveLength(36);
  });

  test('clicking toggle twice collapses content', () => {
    const { container } = render(<ScorelineHeatmap {...baseProps} />);
    const toggle = screen.getByTestId('heatmap-toggle');

    fireEvent.click(toggle);
    expect(container.querySelectorAll('[data-cell="true"]')).toHaveLength(36);

    fireEvent.click(toggle);
    expect(container.querySelectorAll('[data-cell="true"]')).toHaveLength(0);
  });

  test('toggle text reflects state', () => {
    render(<ScorelineHeatmap {...baseProps} />);
    const toggle = screen.getByTestId('heatmap-toggle');

    expect(toggle).toHaveTextContent('▸');
    expect(toggle).toHaveTextContent('Full-time scorelines');

    fireEvent.click(toggle);

    expect(toggle).toHaveTextContent('▾');
    expect(toggle).toHaveTextContent('Full-time scorelines');
  });

  test('aria-expanded reflects state', () => {
    render(<ScorelineHeatmap {...baseProps} />);
    const toggle = screen.getByTestId('heatmap-toggle');

    expect(toggle).toHaveAttribute('aria-expanded', 'false');

    fireEvent.click(toggle);

    expect(toggle).toHaveAttribute('aria-expanded', 'true');
  });

  // ── Content (expanded) ──────────────────────────────────────────

  test('slices 8×8 input to 6×6 display — out-of-range data is not rendered', () => {
    const matrixWithOutlier = fixtureMatrix.map((row) => [...row]);
    matrixWithOutlier[7][7] = 0.50;

    renderExpanded({ ...baseProps, matrix: matrixWithOutlier });

    expect(screen.queryByText('50%')).not.toBeInTheDocument();
  });

  test('renders 36 data cells', () => {
    const { container } = renderExpanded();

    const allCells = container.querySelectorAll('[data-cell="true"]');
    expect(allCells).toHaveLength(36);
  });

  test('renders integer percent for cells ≥ 1%', () => {
    renderExpanded();

    expect(screen.getByText('30%')).toBeInTheDocument(); // (0,0)
    expect(screen.getByText('12%')).toBeInTheDocument(); // (1,1)
    expect(screen.getByText('10%')).toBeInTheDocument(); // (0,1)
    expect(screen.getByText('20%')).toBeInTheDocument(); // (1,0)
    expect(screen.getByText('5%')).toBeInTheDocument();  // (2,1)
    expect(screen.getByText('3%')).toBeInTheDocument();  // (0,2)
    expect(screen.getAllByText('2%')).toHaveLength(2);    // (2,2) and (3,0)
    expect(screen.getByText('1%')).toBeInTheDocument();  // (3,1)
  });

  test('renders blank for cells < 1%', () => {
    renderExpanded();

    expect(screen.getByTestId('heatmap-cell-0-3').textContent).toBe('');
    expect(screen.getByTestId('heatmap-cell-1-3').textContent).toBe('');
    expect(screen.getByTestId('heatmap-cell-4-0').textContent).toBe('');
  });

  test('highlights the max cell with data-max and correct value', () => {
    const { container } = renderExpanded();

    const maxCell = container.querySelector('[data-max="true"]');
    expect(maxCell).not.toBeNull();
    expect(maxCell).toHaveTextContent('30%');
    expect(maxCell).toHaveAttribute('data-testid', 'heatmap-cell-0-0');
  });

  test('only one max cell exists', () => {
    const { container } = renderExpanded();

    const maxCells = container.querySelectorAll('[data-max="true"]');
    expect(maxCells).toHaveLength(1);
  });

  test('renders team names on axes', () => {
    renderExpanded();

    expect(screen.getByText('South Africa →')).toBeInTheDocument();
    expect(screen.getByText('↑ Mexico ↓')).toBeInTheDocument();
  });

  test('legend shows correct max scoreline', () => {
    renderExpanded();

    const legend = screen.getByTestId('heatmap-legend');
    expect(legend).toHaveTextContent('0–0, 30%');
  });
});
