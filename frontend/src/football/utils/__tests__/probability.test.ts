import { formatPercent, topNScorelines, ScorelineEntry } from '../probability';

describe('formatPercent', () => {
  test('defaults to integer: 0.414 → "41%"', () => {
    expect(formatPercent(0.414)).toBe('41%');
  });

  test('formats 0 as "0%"', () => {
    expect(formatPercent(0)).toBe('0%');
  });

  test('formats 1 as "100%"', () => {
    expect(formatPercent(1)).toBe('100%');
  });

  test('digits=1 gives one decimal: 0.414 → "41.4%"', () => {
    expect(formatPercent(0.414, 1)).toBe('41.4%');
  });

  test('digits=2 gives two decimals: 0.33333 → "33.33%"', () => {
    expect(formatPercent(0.33333, 2)).toBe('33.33%');
  });

  test('rounds correctly: 0.005 → "1%" (integer), 0.005 with digits=1 → "0.5%"', () => {
    expect(formatPercent(0.005)).toBe('1%');
    expect(formatPercent(0.005, 1)).toBe('0.5%');
  });

  test('rounds 0.499 to "50%"', () => {
    expect(formatPercent(0.499)).toBe('50%');
  });
});

describe('topNScorelines', () => {
  // Minimal 3x3 matrix for focused testing
  const matrix = [
    [0.25, 0.12, 0.03],
    [0.20, 0.11, 0.02],
    [0.10, 0.05, 0.01],
  ];

  test('returns top 5 scorelines sorted by probability', () => {
    const result = topNScorelines(matrix);
    expect(result).toHaveLength(5);
    expect(result[0]).toEqual({ home: 0, away: 0, probability: 0.25 });
    expect(result[1]).toEqual({ home: 1, away: 0, probability: 0.20 });
    expect(result[2]).toEqual({ home: 0, away: 1, probability: 0.12 });
    expect(result[3]).toEqual({ home: 1, away: 1, probability: 0.11 });
    expect(result[4]).toEqual({ home: 2, away: 0, probability: 0.10 });
  });

  test('respects custom n', () => {
    const result = topNScorelines(matrix, 3);
    expect(result).toHaveLength(3);
  });

  test('returns all entries when n exceeds total cells', () => {
    const result = topNScorelines(matrix, 100);
    expect(result).toHaveLength(9); // 3x3 = 9 cells
  });

  test('handles empty matrix', () => {
    const result = topNScorelines([]);
    expect(result).toEqual([]);
  });

  test('works with 5x5 half-time matrix', () => {
    const htMatrix = [
      [0.55, 0.12, 0.01, 0.001, 0.0001],
      [0.21, 0.05, 0.005, 0.0004, 0.00002],
      [0.04, 0.009, 0.001, 0.00008, 0.000004],
      [0.005, 0.001, 0.0001, 0.00001, 0.000001],
      [0.0005, 0.0001, 0.00001, 0.000001, 0.0000001],
    ];
    const result = topNScorelines(htMatrix, 3);
    expect(result).toHaveLength(3);
    expect(result[0].home).toBe(0);
    expect(result[0].away).toBe(0);
    expect(result[1].home).toBe(1);
    expect(result[1].away).toBe(0);
    expect(result[2].home).toBe(0);
    expect(result[2].away).toBe(1);
  });

  test('maintains stable order for equal probabilities', () => {
    const tied = [
      [0.5, 0.5],
      [0.0, 0.0],
    ];
    const result = topNScorelines(tied, 2);
    expect(result).toHaveLength(2);
    // Both are 0.5 — stable sort keeps (0,0) before (0,1)
    expect(result[0].probability).toBe(0.5);
    expect(result[1].probability).toBe(0.5);
  });
});
