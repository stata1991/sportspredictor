import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { HelmetProvider } from 'react-helmet-async';
import PrivacyPage from '../PrivacyPage';

const renderPrivacy = () =>
  render(
    <HelmetProvider>
      <MemoryRouter>
        <PrivacyPage />
      </MemoryRouter>
    </HelmetProvider>,
  );

test('renders privacy page heading', () => {
  renderPrivacy();
  expect(screen.getByText('Privacy Policy')).toBeInTheDocument();
});

test('sets correct page title', async () => {
  renderPrivacy();
  await waitFor(() => {
    expect(document.title).toContain('Privacy Policy | FantasyFuel');
  });
});
