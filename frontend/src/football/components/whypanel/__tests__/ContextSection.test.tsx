import React from 'react';
import { render, screen } from '@testing-library/react';
import ContextSection from '../ContextSection';
import { Reasoning } from '../../../types/prediction';

const validReasoning: Reasoning = {
  paragraphs: [
    'Mexico enter this fixture as the clear favourite.',
    "Mexico's recent form underlines their status as favourites.",
    'The low_data confidence flag is the most important caveat here.',
  ],
  claims: [
    { text: 'Mexico have won 3 and drawn 2 of their last 5 matches', source: 'get_team_form' },
    { text: 'No previous meetings found', source: 'get_head_to_head' },
    { text: 'Mexico recent form is strong', source: 'get_team_form' }, // duplicate source
  ],
  upset_index: 0.45,
  upset_signals: [],
  upset_paths: [],
  validation_status: 'valid',
};

describe('ContextSection', () => {
  test('renders all 3 paragraphs as separate elements', () => {
    render(<ContextSection reasoning={validReasoning} />);

    expect(screen.getByTestId('paragraph-0')).toHaveTextContent(
      'Mexico enter this fixture as the clear favourite.',
    );
    expect(screen.getByTestId('paragraph-1')).toHaveTextContent(
      "Mexico's recent form underlines their status as favourites.",
    );
    expect(screen.getByTestId('paragraph-2')).toHaveTextContent(
      'The low_data confidence flag is the most important caveat here.',
    );
  });

  test('renders citation chips de-duped by source', () => {
    render(<ContextSection reasoning={validReasoning} />);

    const chipContainer = screen.getByTestId('citation-chips');
    // get_team_form appears twice in claims but should render once
    const chips = chipContainer.querySelectorAll('.MuiChip-root');
    expect(chips).toHaveLength(2); // get_team_form + get_head_to_head
  });

  test('chips show user-facing labels, not raw source strings', () => {
    render(<ContextSection reasoning={validReasoning} />);

    const chipContainer = screen.getByTestId('citation-chips');
    expect(chipContainer).toHaveTextContent('Recent form');
    expect(chipContainer).toHaveTextContent('Head-to-head');
    // Raw strings should not appear
    expect(chipContainer).not.toHaveTextContent('get_team_form');
    expect(chipContainer).not.toHaveTextContent('get_head_to_head');
  });

  test('does not render validation disclosure when status is valid', () => {
    render(<ContextSection reasoning={validReasoning} />);

    expect(screen.queryByTestId('validation-disclosure')).not.toBeInTheDocument();
  });

  test('renders validation disclosure when status is not valid', () => {
    const invalidReasoning: Reasoning = {
      ...validReasoning,
      validation_status: 'probability_leaked',
    };
    render(<ContextSection reasoning={invalidReasoning} />);

    const disclosure = screen.getByTestId('validation-disclosure');
    expect(disclosure).toHaveTextContent('Some claims could not be verified.');
  });

  test('renders WHY section label', () => {
    render(<ContextSection reasoning={validReasoning} />);

    expect(screen.getByText('Why')).toBeInTheDocument();
  });
});
