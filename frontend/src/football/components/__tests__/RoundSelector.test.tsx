import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import RoundSelector from '../RoundSelector';

const ROUNDS = ['Matchday 1', 'Matchday 2', 'Matchday 3', 'Quarter-finals', 'Final'];

describe('RoundSelector', () => {
  test('renders all round chips', () => {
    render(
      <RoundSelector rounds={ROUNDS} selected="Matchday 1" onChange={jest.fn()} />,
    );

    const chips = screen.getAllByTestId('round-chip');
    expect(chips).toHaveLength(5);
    expect(screen.getByText('Matchday 1')).toBeInTheDocument();
    expect(screen.getByText('Final')).toBeInTheDocument();
  });

  test('calls onChange when a chip is clicked', async () => {
    const onChange = jest.fn();
    render(
      <RoundSelector rounds={ROUNDS} selected="Matchday 1" onChange={onChange} />,
    );

    await userEvent.click(screen.getByText('Quarter-finals'));
    expect(onChange).toHaveBeenCalledWith('Quarter-finals');
  });

  test('renders with data-testid round-selector', () => {
    render(
      <RoundSelector rounds={ROUNDS} selected="Matchday 1" onChange={jest.fn()} />,
    );
    expect(screen.getByTestId('round-selector')).toBeInTheDocument();
  });
});
