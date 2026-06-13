import React from 'react';
import { Box, Typography, Divider } from '@mui/material';
import { colors } from '../colors';
import {
  FixtureStatistics,
  TeamMatchStatistics,
} from '../types/statistics';

// Display-only live stats (STATS-A). No interpretation, no "who's better" —
// the numbers are shown; the reader draws the conclusion. The live
// probability bar above remains the only probabilistic statement.

interface LiveStatsPanelProps {
  stats: FixtureStatistics | null;
  homeTeam: string;
  awayTeam: string;
}

// Paired-number rows, in the order STATS-A specifies.
const NUMBER_ROWS: { key: keyof TeamMatchStatistics; label: string }[] = [
  { key: 'shots_total', label: 'Shots' },
  { key: 'shots_on_goal', label: 'Shots on goal' },
  { key: 'corners', label: 'Corners' },
  { key: 'yellow_cards', label: 'Yellow cards' },
  { key: 'red_cards', label: 'Red cards' },
  { key: 'goalkeeper_saves', label: 'Saves' },
  { key: 'fouls', label: 'Fouls' },
];

const numberSx = {
  fontWeight: 700,
  fontSize: '0.9rem',
  minWidth: '2.5ch',
} as const;

const PossessionBar: React.FC<{ home: number; away: number }> = ({
  home,
  away,
}) => (
  <Box data-testid="stat-row-possession" sx={{ mb: 1.5 }}>
    <Box
      sx={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'baseline',
        mb: 0.5,
      }}
    >
      <Typography
        data-testid="possession-home-pct"
        variant="caption"
        sx={{ color: colors.homeAccent, fontWeight: 700 }}
      >
        {home}%
      </Typography>
      <Typography
        variant="caption"
        sx={{ color: colors.labelText, letterSpacing: '0.04em' }}
      >
        Possession
      </Typography>
      <Typography
        data-testid="possession-away-pct"
        variant="caption"
        sx={{ color: colors.awayAccent, fontWeight: 700 }}
      >
        {away}%
      </Typography>
    </Box>
    <Box
      data-testid="possession-bar"
      sx={{
        display: 'flex',
        height: 8,
        borderRadius: 4,
        overflow: 'hidden',
        backgroundColor: 'rgba(255,255,255,0.08)',
      }}
    >
      <Box
        data-testid="possession-bar-home"
        sx={{
          flexGrow: Math.max(home, 0),
          minWidth: 0,
          backgroundColor: colors.homeAccent,
        }}
      />
      <Box
        data-testid="possession-bar-away"
        sx={{
          flexGrow: Math.max(away, 0),
          minWidth: 0,
          backgroundColor: colors.awayAccent,
        }}
      />
    </Box>
  </Box>
);

const StatRow: React.FC<{
  rowKey: string;
  label: string;
  home: number | null;
  away: number | null;
}> = ({ rowKey, label, home, away }) => (
  <Box
    data-testid={`stat-row-${rowKey}`}
    sx={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      py: 0.5,
    }}
  >
    <Typography
      sx={{ ...numberSx, color: colors.homeAccent, textAlign: 'left' }}
    >
      {home ?? '–'}
    </Typography>
    <Typography
      variant="caption"
      sx={{ color: colors.labelText, flexGrow: 1, textAlign: 'center' }}
    >
      {label}
    </Typography>
    <Typography
      sx={{ ...numberSx, color: colors.awayAccent, textAlign: 'right' }}
    >
      {away ?? '–'}
    </Typography>
  </Box>
);

const LiveStatsPanel: React.FC<LiveStatsPanelProps> = ({ stats }) => {
  // Possession needs both sides to render a meaningful split.
  const showPossession =
    stats != null &&
    stats.home.possession != null &&
    stats.away.possession != null;

  // A number row renders unless BOTH sides are null.
  const visibleRows = stats
    ? NUMBER_ROWS.filter(
        ({ key }) => stats.home[key] != null || stats.away[key] != null,
      )
    : [];

  const hasContent = showPossession || visibleRows.length > 0;

  if (!stats || !hasContent) {
    // Early minutes: stats not populated yet. Don't fake zeros.
    return (
      <Box data-testid="live-stats-panel" sx={{ mt: 1 }}>
        <Divider sx={{ borderColor: 'rgba(255,255,255,0.08)', mb: 1.5 }} />
        <Typography
          data-testid="live-stats-pending"
          variant="caption"
          sx={{ color: colors.labelText, display: 'block', textAlign: 'center' }}
        >
          Live stats coming in…
        </Typography>
      </Box>
    );
  }

  return (
    <Box data-testid="live-stats-panel" sx={{ mt: 1 }}>
      <Divider sx={{ borderColor: 'rgba(255,255,255,0.08)', mb: 1.5 }} />
      {showPossession && (
        <PossessionBar
          home={stats.home.possession as number}
          away={stats.away.possession as number}
        />
      )}
      {visibleRows.map(({ key, label }) => (
        <StatRow
          key={key}
          rowKey={key}
          label={label}
          home={stats.home[key]}
          away={stats.away[key]}
        />
      ))}
    </Box>
  );
};

export default LiveStatsPanel;
