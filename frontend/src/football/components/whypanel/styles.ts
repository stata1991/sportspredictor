/**
 * Shared styles and helpers for the why-panel sub-sections.
 */
import { colors } from '../../colors';

/** Roboto prose font — used by ContextSection and UpsetSection */
export const proseFontSx = {
  fontFamily: "'Roboto', sans-serif",
};

/** Uppercase section label style — used by NumbersSection, ContextSection, and UpsetSection */
export const sectionLabelSx = {
  color: colors.labelText,
  fontSize: '0.75rem',
  fontWeight: 600,
  letterSpacing: '0.08em',
  textTransform: 'uppercase' as const,
  mb: 1,
};

/** Map internal tool source names to user-facing labels */
const SOURCE_LABELS: Record<string, string> = {
  get_team_form: 'Recent form',
  get_head_to_head: 'Head-to-head',
  get_injuries: 'Injuries',
  get_market_consensus: 'Market odds',
  prediction_context: 'Model state',
};

export function formatSource(source: string): string {
  return SOURCE_LABELS[source] ?? source;
}
