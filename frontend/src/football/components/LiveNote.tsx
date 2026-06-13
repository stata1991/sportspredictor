import React from 'react';
import { Box, Typography } from '@mui/material';
import { colors } from '../colors';
import { LiveNote as LiveNoteType } from '../types/statistics';

// The reactive "why" line on the live match detail. Display copy only —
// it narrates the moment it was handed; it never states a probability and
// never overrides the probability bar above it.

interface LiveNoteProps {
  note: LiveNoteType | null;
}

// What prompted the read, phrased so it reads as reactive, not stale.
const TRIGGER_PHRASE: Record<LiveNoteType['trigger'], string> = {
  goal: 'after the goal',
  red_card: 'after the red card',
  halftime: 'at the break',
  lean_cross: 'as the game shifts',
};

const accentFor = (side: LiveNoteType['leaning_side']): string => {
  if (side === 'home') return colors.homeAccent;
  if (side === 'away') return colors.awayAccent;
  return colors.labelText; // even → neutral, no green
};

const LiveNote: React.FC<LiveNoteProps> = ({ note }) => {
  if (!note || !note.text) return null;

  const phrase = TRIGGER_PHRASE[note.trigger] ?? 'live read';
  // "after the goal · 67'" — omit the minute at the break / when absent.
  const meta =
    note.trigger !== 'halftime' && typeof note.elapsed === 'number'
      ? `${phrase} · ${note.elapsed}'`
      : phrase;

  return (
    <Box
      data-testid="live-note"
      sx={{
        mb: 2,
        pl: 1.5,
        borderLeft: `3px solid ${accentFor(note.leaning_side)}`,
      }}
    >
      <Typography
        data-testid="live-note-text"
        sx={{
          color: colors.textSecondary,
          fontStyle: 'italic',
          fontSize: '0.9rem',
          lineHeight: 1.5,
        }}
      >
        {note.text}
      </Typography>
      <Typography
        data-testid="live-note-meta"
        variant="caption"
        sx={{
          color: colors.labelText,
          display: 'block',
          mt: 0.5,
          textTransform: 'lowercase',
          letterSpacing: '0.03em',
        }}
      >
        {meta}
      </Typography>
    </Box>
  );
};

export default LiveNote;
