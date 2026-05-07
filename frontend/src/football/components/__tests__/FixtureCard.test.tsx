import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import FixtureCard from '../FixtureCard';
import { AFFixture } from '../../types/fixture';

const makeFixture = (overrides?: Partial<{
  id: number;
  date: string;
  statusShort: string;
  homeName: string;
  awayName: string;
  homeLogo: string | null;
  awayLogo: string | null;
  goalsHome: number | null;
  goalsAway: number | null;
}>): AFFixture => {
  const o = overrides || {};
  return {
    fixture: {
      id: o.id ?? 100,
      referee: null,
      timezone: 'UTC',
      date: o.date ?? '2026-06-11T18:00:00+00:00',
      timestamp: new Date(o.date ?? '2026-06-11T18:00:00+00:00').getTime() / 1000,
      venue: { id: 1, name: 'MetLife Stadium', city: 'East Rutherford' },
      status: { long: 'Not Started', short: o.statusShort ?? 'NS', elapsed: null, extra: null },
    },
    league: {
      id: 1,
      name: 'World Cup',
      country: null,
      logo: null,
      flag: null,
      season: 2026,
      round: 'Group A - 1',
    },
    teams: {
      home: { id: 1, name: o.homeName ?? 'USA', logo: o.homeLogo ?? null, winner: null },
      away: { id: 2, name: o.awayName ?? 'Brazil', logo: o.awayLogo ?? null, winner: null },
    },
    goals: { home: o.goalsHome ?? null, away: o.goalsAway ?? null },
    score: {
      halftime: { home: null, away: null },
      fulltime: { home: null, away: null },
      extratime: { home: null, away: null },
      penalty: { home: null, away: null },
    },
  };
};

describe('FixtureCard', () => {
  test('renders team names from props', () => {
    const fixture = makeFixture({ homeName: 'Germany', awayName: 'Japan' });
    render(<FixtureCard fixture={fixture} onClick={jest.fn()} />);
    expect(screen.getByText('Germany')).toBeInTheDocument();
    expect(screen.getByText('Japan')).toBeInTheDocument();
  });

  test('renders kickoff time', () => {
    // Use a fixed date and check that something time-like is rendered
    const fixture = makeFixture({ date: '2026-06-11T18:00:00+00:00' });
    render(<FixtureCard fixture={fixture} onClick={jest.fn()} />);
    // The exact format depends on the user's locale, but we can check for
    // common patterns — either "6:00 PM" (en-US) or "18:00" etc.
    const card = screen.getByTestId('fixture-card');
    // Just verify there's text content that includes digits and a colon (time)
    expect(card.textContent).toMatch(/\d{1,2}:\d{2}/);
  });

  test('calls onClick with fixture.id when clicked', async () => {
    const handleClick = jest.fn();
    const fixture = makeFixture({ id: 42 });
    render(<FixtureCard fixture={fixture} onClick={handleClick} />);

    // Click the CardActionArea button inside the card
    const button = screen.getByRole('button');
    await userEvent.click(button);
    expect(handleClick).toHaveBeenCalledWith(42);
  });

  test('renders without logo if logo is null (no broken image)', () => {
    const fixture = makeFixture({ homeLogo: null, awayLogo: null });
    render(<FixtureCard fixture={fixture} onClick={jest.fn()} />);
    // No <img> elements should be present
    const images = screen.queryAllByRole('img');
    expect(images).toHaveLength(0);
  });

  test('renders logos when provided', () => {
    const fixture = makeFixture({
      homeLogo: 'https://example.com/home.png',
      awayLogo: 'https://example.com/away.png',
    });
    render(<FixtureCard fixture={fixture} onClick={jest.fn()} />);
    const images = screen.getAllByRole('img');
    expect(images).toHaveLength(2);
    expect(images[0]).toHaveAttribute('src', 'https://example.com/home.png');
    expect(images[1]).toHaveAttribute('src', 'https://example.com/away.png');
  });

  test('renders prediction-badge-slot', () => {
    const fixture = makeFixture();
    render(<FixtureCard fixture={fixture} onClick={jest.fn()} />);
    expect(screen.getByTestId('prediction-badge-slot')).toBeInTheDocument();
  });

  test('renders status pill with correct label', () => {
    const fixture = makeFixture({ statusShort: 'FT' });
    render(<FixtureCard fixture={fixture} onClick={jest.fn()} />);
    expect(screen.getByTestId('status-pill')).toHaveTextContent('FT');
  });

  test('renders without badge by default', () => {
    const fixture = makeFixture();
    render(<FixtureCard fixture={fixture} onClick={jest.fn()} />);
    const slot = screen.getByTestId('prediction-badge-slot');
    expect(slot).toBeInTheDocument();
    expect(slot.textContent).toBe('');
  });

  test('renders badge content when prop passed', () => {
    const fixture = makeFixture();
    render(
      <FixtureCard
        fixture={fixture}
        onClick={jest.fn()}
        badge={<span data-testid="test-badge">Upset 54%</span>}
      />,
    );
    expect(screen.getByTestId('test-badge')).toBeInTheDocument();
    expect(screen.getByTestId('test-badge')).toHaveTextContent('Upset 54%');
    expect(screen.getByTestId('prediction-badge-slot')).toContainElement(
      screen.getByTestId('test-badge'),
    );
  });
});
