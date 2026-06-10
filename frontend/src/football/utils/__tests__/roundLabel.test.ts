import { roundShortLabel } from '../roundLabel';

describe('roundShortLabel', () => {
  test.each([
    ['Round of 32', 'R32'],
    ['Round of 16', 'R16'],
    ['Quarter-finals', 'QF'],
    ['Semi-finals', 'SF'],
    ['3rd Place Final', '3rd'],
    ['Final', 'Final'],
    ['Group Stage - 1', 'MD1'],
    ['Group Stage - 2', 'MD2'],
    ['Group Stage - 3', 'MD3'],
  ])('maps %s → %s', (input, expected) => {
    expect(roundShortLabel(input)).toBe(expected);
  });

  test('unknown non-empty string falls back to the raw string', () => {
    expect(roundShortLabel('Preliminary Round')).toBe('Preliminary Round');
  });

  test('null → null (no badge)', () => {
    expect(roundShortLabel(null)).toBeNull();
  });

  test('undefined → null (no badge)', () => {
    expect(roundShortLabel(undefined)).toBeNull();
  });

  test('empty string → null (no badge)', () => {
    expect(roundShortLabel('')).toBeNull();
  });
});
