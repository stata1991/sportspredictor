import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { HelmetProvider } from 'react-helmet-async';
import AboutPage from '../AboutPage';

const renderAbout = () =>
  render(
    <HelmetProvider>
      <MemoryRouter>
        <AboutPage />
      </MemoryRouter>
    </HelmetProvider>,
  );

test('renders about page heading', () => {
  renderAbout();
  expect(screen.getByText('About')).toBeInTheDocument();
});

test('sets correct page title', async () => {
  renderAbout();
  await waitFor(() => {
    expect(document.title).toContain('About | FantasyFuel');
  });
});
