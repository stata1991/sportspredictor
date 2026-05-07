import React from 'react';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import AboutPage from '../AboutPage';

test('renders about page heading', () => {
  render(
    <MemoryRouter>
      <AboutPage />
    </MemoryRouter>,
  );
  expect(screen.getByText('About')).toBeInTheDocument();
});
