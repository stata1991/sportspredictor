import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import DateFilter from '../DateFilter';

const DATES = ['2026-06-11', '2026-06-12', '2026-06-13'];

describe('DateFilter', () => {
  test('renders All chip plus one chip per date', () => {
    render(
      <DateFilter dates={DATES} selected="all" onChange={jest.fn()} />,
    );

    const chips = screen.getAllByTestId('date-chip');
    // "All" + 3 dates = 4 chips
    expect(chips).toHaveLength(4);
    expect(screen.getByText('All')).toBeInTheDocument();
  });

  test('calls onChange with date key when clicked', async () => {
    const onChange = jest.fn();
    render(
      <DateFilter dates={DATES} selected="all" onChange={onChange} />,
    );

    // Click the second date chip (Jun 12)
    const chips = screen.getAllByTestId('date-chip');
    await userEvent.click(chips[2]); // index 0=All, 1=Jun 11, 2=Jun 12
    expect(onChange).toHaveBeenCalledWith('2026-06-12');
  });

  test('calls onChange with all when All chip clicked', async () => {
    const onChange = jest.fn();
    render(
      <DateFilter dates={DATES} selected="2026-06-11" onChange={onChange} />,
    );

    await userEvent.click(screen.getByText('All'));
    expect(onChange).toHaveBeenCalledWith('all');
  });

  test('renders with data-testid date-filter', () => {
    render(
      <DateFilter dates={DATES} selected="all" onChange={jest.fn()} />,
    );
    expect(screen.getByTestId('date-filter')).toBeInTheDocument();
  });
});
