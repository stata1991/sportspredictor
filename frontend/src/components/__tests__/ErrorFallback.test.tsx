import React from 'react';
import { render, screen } from '@testing-library/react';
import ErrorFallback from '../ErrorFallback';

test('renders error message and refresh button', () => {
  render(<ErrorFallback />);
  expect(screen.getByText('Something went wrong')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /refresh/i })).toBeInTheDocument();
});
