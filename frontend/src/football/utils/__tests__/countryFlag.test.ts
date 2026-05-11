import { flagClass } from '../countryFlag';

describe('flagClass', () => {
  test('returns flag-icons class for known WC team', () => {
    expect(flagClass('France')).toBe('fi fi-fr');
  });

  test('handles England (GB subdivision)', () => {
    expect(flagClass('England')).toBe('fi fi-gb-eng');
  });

  test('handles Scotland (GB subdivision)', () => {
    expect(flagClass('Scotland')).toBe('fi fi-gb-sct');
  });

  test('handles accented names', () => {
    expect(flagClass('Curaçao')).toBe('fi fi-cw');
    expect(flagClass('Türkiye')).toBe('fi fi-tr');
  });

  test('handles multi-word country names', () => {
    expect(flagClass('South Korea')).toBe('fi fi-kr');
    expect(flagClass('Bosnia & Herzegovina')).toBe('fi fi-ba');
    expect(flagClass('Cape Verde Islands')).toBe('fi fi-cv');
    expect(flagClass('Congo DR')).toBe('fi fi-cd');
  });

  test('returns null for unknown country', () => {
    expect(flagClass('Atlantis')).toBeNull();
  });

  test('returns null for empty string', () => {
    expect(flagClass('')).toBeNull();
  });

  test('covers all 48 WC teams', () => {
    const teams = [
      'Algeria', 'Argentina', 'Australia', 'Austria', 'Belgium',
      'Bosnia & Herzegovina', 'Brazil', 'Canada', 'Cape Verde Islands',
      'Colombia', 'Congo DR', 'Croatia', 'Curaçao', 'Czech Republic',
      'Ecuador', 'Egypt', 'England', 'France', 'Germany', 'Ghana',
      'Haiti', 'Iran', 'Iraq', 'Ivory Coast', 'Japan', 'Jordan',
      'Mexico', 'Morocco', 'Netherlands', 'New Zealand', 'Norway',
      'Panama', 'Paraguay', 'Portugal', 'Qatar', 'Saudi Arabia',
      'Scotland', 'Senegal', 'South Africa', 'South Korea', 'Spain',
      'Sweden', 'Switzerland', 'Tunisia', 'Türkiye', 'USA', 'Uruguay',
      'Uzbekistan',
    ];

    for (const team of teams) {
      const result = flagClass(team);
      expect(result).not.toBeNull();
      expect(result).toMatch(/^fi fi-[a-z]{2}(-[a-z]+)?$/);
    }
  });
});
