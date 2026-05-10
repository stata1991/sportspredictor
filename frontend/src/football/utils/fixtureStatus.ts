/**
 * Fixture status taxonomy.
 *
 * Maps API-Football `status.short` codes to semantic categories.
 * Single source of truth for the frontend — mirrors the backend's
 * detect_stage() logic without importing Python.
 */

export const IN_PLAY = new Set(['1H', 'HT', '2H', 'ET', 'BT', 'P']);
export const COMPLETED = new Set(['FT', 'AET', 'PEN']);
export const PRE_MATCH = new Set(['NS', 'TBD']);
export const NOT_PREDICTABLE = new Set([
  'PST', 'CANC', 'ABD', 'AWD', 'WO', 'SUSP', 'INT',
]);

export const isInPlay = (s: string): boolean => IN_PLAY.has(s);
export const isCompleted = (s: string): boolean => COMPLETED.has(s);
export const isPreMatch = (s: string): boolean => PRE_MATCH.has(s);
export const isNotPredictable = (s: string): boolean => NOT_PREDICTABLE.has(s);
