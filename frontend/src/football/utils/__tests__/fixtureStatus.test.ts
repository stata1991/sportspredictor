import {
  isInPlay,
  isCompleted,
  isPreMatch,
  isNotPredictable,
} from '../fixtureStatus';

describe('fixtureStatus', () => {
  describe('isInPlay', () => {
    // 'LIVE' included for parity with backend _LIVE_STATUSES (LIVETAB-2).
    test.each(['1H', 'HT', '2H', 'ET', 'BT', 'P', 'LIVE'])(
      '%s → true',
      (s) => expect(isInPlay(s)).toBe(true),
    );

    test.each(['NS', 'FT', 'AET', 'PEN', 'PST', 'XYZ'])(
      '%s → false',
      (s) => expect(isInPlay(s)).toBe(false),
    );
  });

  describe('isCompleted', () => {
    test.each(['FT', 'AET', 'PEN'])(
      '%s → true',
      (s) => expect(isCompleted(s)).toBe(true),
    );

    test.each(['NS', '1H', 'HT', 'PST'])(
      '%s → false',
      (s) => expect(isCompleted(s)).toBe(false),
    );
  });

  describe('isPreMatch', () => {
    test.each(['NS', 'TBD'])(
      '%s → true',
      (s) => expect(isPreMatch(s)).toBe(true),
    );

    test.each(['1H', 'FT', 'PST'])(
      '%s → false',
      (s) => expect(isPreMatch(s)).toBe(false),
    );
  });

  describe('isNotPredictable', () => {
    test.each(['PST', 'CANC', 'ABD', 'AWD', 'WO', 'SUSP', 'INT'])(
      '%s → true',
      (s) => expect(isNotPredictable(s)).toBe(true),
    );

    test.each(['NS', '1H', 'FT'])(
      '%s → false',
      (s) => expect(isNotPredictable(s)).toBe(false),
    );
  });
});
