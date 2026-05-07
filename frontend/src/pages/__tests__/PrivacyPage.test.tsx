import React from 'react';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import PrivacyPage from '../PrivacyPage';

test('renders privacy page heading', () => {
  render(
    <MemoryRouter>
      <PrivacyPage />
    </MemoryRouter>,
  );
  expect(screen.getByText('Privacy Policy')).toBeInTheDocument();
});
