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

  test('renderLabel transforms chip labels while keeping raw selection values', async () => {
    const onChange = jest.fn();
    render(
      <RoundSelector
        rounds={['Round of 16', 'Final']}
        selected="Round of 16"
        onChange={onChange}
        renderLabel={(r) => (r === 'Round of 16' ? 'R16' : r)}
      />,
    );
    // Label is transformed...
    expect(screen.getByText('R16')).toBeInTheDocument();
    expect(screen.queryByText('Round of 16')).not.toBeInTheDocument();
    // ...but onChange still emits the raw round value.
    await userEvent.click(screen.getByText('R16'));
    expect(onChange).toHaveBeenCalledWith('Round of 16');
  });
});
