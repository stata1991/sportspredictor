import React from 'react';
import { render } from '@testing-library/react';
import { HelmetProvider } from 'react-helmet-async';
import App from './App';

test('App renders without crashing', () => {
  render(
    <HelmetProvider>
      <App />
    </HelmetProvider>,
  );
});
