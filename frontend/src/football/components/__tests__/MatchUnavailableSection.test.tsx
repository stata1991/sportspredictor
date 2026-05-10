import React from 'react';
import { render, screen } from '@testing-library/react';
import MatchUnavailableSection from '../MatchUnavailableSection';

describe('MatchUnavailableSection', () => {
  test('renders with testid', () => {
    render(<MatchUnavailableSection />);
    expect(screen.getByTestId('match-unavailable')).toBeInTheDocument();
  });

  test('shows generic message when no status provided', () => {
    render(<MatchUnavailableSection />);
    expect(
      screen.getByText('This match cannot be predicted right now.'),
    ).toBeInTheDocument();
  });

  test.each([
    ['PST', 'postponed'],
    ['CANC', 'cancelled'],
    ['ABD', 'abandoned'],
    ['AWD', 'awarded'],
    ['WO', 'declared a walkover'],
    ['SUSP', 'suspended'],
    ['INT', 'interrupted'],
  ])('status=%s → shows "%s" verb', (status, verb) => {
    render(<MatchUnavailableSection status={status} />);
    expect(
      screen.getByText(`This match has been ${verb}.`),
    ).toBeInTheDocument();
  });

  test('shows generic message for unknown status code', () => {
    render(<MatchUnavailableSection status="XYZ" />);
    expect(
      screen.getByText('This match cannot be predicted right now.'),
    ).toBeInTheDocument();
  });

  test('always shows predictions-unavailable line', () => {
    render(<MatchUnavailableSection status="PST" />);
    expect(
      screen.getByText('Predictions are not available for this fixture.'),
    ).toBeInTheDocument();
  });
});
