/**
 * Maps API-Football team names to ISO 3166-1 alpha-2 codes for flag-icons CSS.
 *
 * Covers all 48 FIFA World Cup 2026 participants.
 */
const COUNTRY_TO_ISO: Record<string, string> = {
  'Algeria': 'dz',
  'Argentina': 'ar',
  'Australia': 'au',
  'Austria': 'at',
  'Belgium': 'be',
  'Bosnia & Herzegovina': 'ba',
  'Brazil': 'br',
  'Canada': 'ca',
  'Cape Verde Islands': 'cv',
  'Colombia': 'co',
  'Congo DR': 'cd',
  'Croatia': 'hr',
  'Curaçao': 'cw',
  'Czech Republic': 'cz',
  'Ecuador': 'ec',
  'Egypt': 'eg',
  'England': 'gb-eng',
  'France': 'fr',
  'Germany': 'de',
  'Ghana': 'gh',
  'Haiti': 'ht',
  'Iran': 'ir',
  'Iraq': 'iq',
  'Ivory Coast': 'ci',
  'Japan': 'jp',
  'Jordan': 'jo',
  'Mexico': 'mx',
  'Morocco': 'ma',
  'Netherlands': 'nl',
  'New Zealand': 'nz',
  'Norway': 'no',
  'Panama': 'pa',
  'Paraguay': 'py',
  'Portugal': 'pt',
  'Qatar': 'qa',
  'Saudi Arabia': 'sa',
  'Scotland': 'gb-sct',
  'Senegal': 'sn',
  'South Africa': 'za',
  'South Korea': 'kr',
  'Spain': 'es',
  'Sweden': 'se',
  'Switzerland': 'ch',
  'Tunisia': 'tn',
  'Türkiye': 'tr',
  'USA': 'us',
  'Uruguay': 'uy',
  'Uzbekistan': 'uz',
};

/**
 * Returns the flag-icons CSS class for a given country name.
 *
 * Usage: `<span className={flagClass('France')} />`
 * Renders the French flag via flag-icons CSS.
 *
 * Returns `null` for unknown countries so the caller can fall back
 * to the API-Football logo URL.
 */
export function flagClass(countryName: string): string | null {
  const iso = COUNTRY_TO_ISO[countryName];
  return iso ? `fi fi-${iso}` : null;
}
