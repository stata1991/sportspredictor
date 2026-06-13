import React from 'react';
import { render, screen } from '@testing-library/react';
import LiveNote from '../LiveNote';
import { LiveNote as LiveNoteType } from '../../types/statistics';

const base: LiveNoteType = {
  text: 'Brazil are camped in their half and turning the screw.',
  trigger: 'goal',
  leaning_side: 'home',
  agrees_with_prediction: true,
  elapsed: 67,
};

describe('LiveNote', () => {
  test('renders the narration text and the trigger meta', () => {
    render(<LiveNote note={base} />);
    expect(screen.getByTestId('live-note-text')).toHaveTextContent(
      'turning the screw',
    );
    expect(screen.getByTestId('live-note-meta')).toHaveTextContent(
      "after the goal · 67'",
    );
  });

  test('halftime reads "at the break" without a minute', () => {
    render(<LiveNote note={{ ...base, trigger: 'halftime', elapsed: 45 }} />);
    expect(screen.getByTestId('live-note-meta')).toHaveTextContent('at the break');
    expect(screen.getByTestId('live-note-meta')).not.toHaveTextContent('·');
  });

  test('lean_cross reads "as the game shifts"', () => {
    render(<LiveNote note={{ ...base, trigger: 'lean_cross' }} />);
    expect(screen.getByTestId('live-note-meta')).toHaveTextContent(
      'as the game shifts',
    );
  });

  test('red_card reads "after the red card"', () => {
    render(<LiveNote note={{ ...base, trigger: 'red_card' }} />);
    expect(screen.getByTestId('live-note-meta')).toHaveTextContent(
      'after the red card',
    );
  });

  test('accent border uses the leaning side color (home/away), never green', () => {
    const { rerender, container } = render(<LiveNote note={base} />);
    expect(screen.getByTestId('live-note')).toHaveStyle(
      'border-left: 3px solid #ff6f00',
    );

    rerender(<LiveNote note={{ ...base, leaning_side: 'away' }} />);
    expect(screen.getByTestId('live-note')).toHaveStyle(
      'border-left: 3px solid #ec407a',
    );

    rerender(<LiveNote note={{ ...base, leaning_side: 'even' }} />);
    expect(screen.getByTestId('live-note')).toHaveStyle(
      'border-left: 3px solid #b0bec5',
    );

    expect(container.innerHTML.toLowerCase()).not.toMatch(
      /#4caf50|#00c853|#2e7d32|green/,
    );
  });

  test('renders nothing when note is null', () => {
    const { container } = render(<LiveNote note={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  test('renders nothing when text is empty', () => {
    const { container } = render(<LiveNote note={{ ...base, text: '' }} />);
    expect(container).toBeEmptyDOMElement();
  });
});
