import React from 'react';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Footer from '../Footer';

test('renders footer with links and copyright', () => {
  render(
    <MemoryRouter>
      <Footer />
    </MemoryRouter>,
  );
  expect(screen.getByText('Privacy')).toBeInTheDocument();
  expect(screen.getByText('About')).toBeInTheDocument();
  expect(screen.getByText(/FantasyFuel.ai 2026/)).toBeInTheDocument();
});
