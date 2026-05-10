import React from 'react';
import { render, screen } from '@testing-library/react';
import LiveBadge from '../LiveBadge';

describe('LiveBadge', () => {
  test.each([
    ['1H', 67, "LIVE 67'"],
    ['2H', 82, "LIVE 82'"],
    ['ET', 105, "LIVE 105'"],
    ['HT', undefined, 'LIVE HT'],
    ['BT', undefined, 'LIVE BT'],
    ['P', undefined, 'LIVE PEN'],
    ['FT', undefined, 'FT'],
    ['AET', undefined, 'FT'],
    ['PEN', undefined, 'FT'],
  ])(
    'status=%s elapsed=%s → label "%s"',
    (status, elapsed, expected) => {
      render(<LiveBadge status={status} elapsedMinute={elapsed} />);
      expect(screen.getByTestId('live-label')).toHaveTextContent(expected);
    },
  );

  test('returns null for NS', () => {
    const { container } = render(<LiveBadge status="NS" />);
    expect(container.firstChild).toBeNull();
  });

  test('returns null for unknown status', () => {
    const { container } = render(<LiveBadge status="XYZ" />);
    expect(container.firstChild).toBeNull();
  });

  test('has pulse animation for in-play statuses', () => {
    render(<LiveBadge status="1H" elapsedMinute={30} />);
    const dot = screen.getByTestId('live-dot');
    const style = window.getComputedStyle(dot);
    expect(style.animation).toBeTruthy();
  });

  test('no pulse animation for FT', () => {
    render(<LiveBadge status="FT" />);
    const dot = screen.getByTestId('live-dot');
    const style = window.getComputedStyle(dot);
    // FT has no animation keyframe applied
    expect(style.animation).toBeFalsy();
  });

  test('has aria-live="polite" for screen reader updates', () => {
    render(<LiveBadge status="2H" elapsedMinute={55} />);
    const label = screen.getByTestId('live-label');
    expect(label).toHaveAttribute('aria-live', 'polite');
  });

  test('renders elapsed minute without it for 1H when not provided', () => {
    render(<LiveBadge status="1H" />);
    expect(screen.getByTestId('live-label')).toHaveTextContent('LIVE');
  });
});
