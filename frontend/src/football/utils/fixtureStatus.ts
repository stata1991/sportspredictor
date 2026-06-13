/**
 * Fixture status taxonomy.
 *
 * Maps API-Football `status.short` codes to semantic categories.
 * Single source of truth for the frontend — mirrors the backend's
 * detect_stage() logic without importing Python.
 */

// Mirrors the backend _LIVE_STATUSES. 'LIVE' is included for parity: football
// reports 1H/2H/etc, but API-Football emits 'LIVE' for some feeds, and the
// frontend/backend sets diverging is a latent version of the LIVETAB cold-start
// empty (a live fixture the frontend would classify as not-in-play).
export const IN_PLAY = new Set(['1H', 'HT', '2H', 'ET', 'BT', 'P', 'LIVE']);
export const COMPLETED = new Set(['FT', 'AET', 'PEN']);
export const PRE_MATCH = new Set(['NS', 'TBD']);
export const NOT_PREDICTABLE = new Set([
  'PST', 'CANC', 'ABD', 'AWD', 'WO', 'SUSP', 'INT',
]);

export const isInPlay = (s: string): boolean => IN_PLAY.has(s);
export const isCompleted = (s: string): boolean => COMPLETED.has(s);
export const isPreMatch = (s: string): boolean => PRE_MATCH.has(s);
export const isNotPredictable = (s: string): boolean => NOT_PREDICTABLE.has(s);
