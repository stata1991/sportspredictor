/**
 * Football feature design tokens.
 *
 * Single source of truth for hex colors used across the football UI.
 * RGBA variants stay inline at the callsite for now.
 */
export const colors = {
  homeAccent: '#ff6f00',
  awayAccent: '#ec407a',
  neutral: '#90a4ae',
  caution: '#ff9800',
  textPrimary: '#fff',
  textSecondary: '#e0e0e0',
  labelText: '#b0bec5',
  darkText: '#111',
} as const;
