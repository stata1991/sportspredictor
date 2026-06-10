import { roundShortLabel, KNOCKOUT_ROUND_ORDER } from '../roundLabel';

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

describe('KNOCKOUT_ROUND_ORDER', () => {
  test('is the six knockout rounds in tournament order', () => {
    expect([...KNOCKOUT_ROUND_ORDER]).toEqual([
      'Round of 32',
      'Round of 16',
      'Quarter-finals',
      'Semi-finals',
      '3rd Place Final',
      'Final',
    ]);
  });

  test('every entry has a short label', () => {
    KNOCKOUT_ROUND_ORDER.forEach((r) => {
      expect(roundShortLabel(r)).not.toBeNull();
    });
  });
});
