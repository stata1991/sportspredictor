import React, { useState, useCallback, useMemo } from 'react';
import { Box, Typography, Card, Skeleton, Button, Chip } from '@mui/material';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import CancelIcon from '@mui/icons-material/Cancel';
import { useAccuracyMatches } from '../../football/hooks/useAccuracyMatches';
import { roundShortLabel } from '../../football/utils/roundLabel';
import { MatchReceipt } from '../../football/types/accuracy';
import { colors } from '../../football/colors';

// ── Hit / miss markers (orange check / pink cross — NO GREEN) ─────────

const HitMark: React.FC = () => (
  <CheckCircleIcon
    data-testid="hit-mark"
    aria-label="correct"
    sx={{ fontSize: '1rem', color: colors.homeAccent, verticalAlign: 'middle', ml: 0.5 }}
  />
);

const MissMark: React.FC = () => (
  <CancelIcon
    data-testid="miss-mark"
    aria-label="wrong"
    sx={{ fontSize: '1rem', color: colors.awayAccent, verticalAlign: 'middle', ml: 0.5 }}
  />
);

const goalsWord = (n: number) => `${n} goal${n === 1 ? '' : 's'}`;

// ── One match receipt card ────────────────────────────────────────────

const MatchCard: React.FC<{ m: MatchReceipt }> = ({ m }) => {
  const roundLabel = m.is_friendly ? null : roundShortLabel(m.round);

  return (
    <Card
      data-testid="match-receipt"
      sx={{
        mb: 1.5,
        p: { xs: 1.5, sm: 2 },
        background: 'linear-gradient(145deg, #1e1e1e, #2a2a2a)',
        border: '1px solid rgba(255,255,255,0.06)',
      }}
    >
      {/* Badge row */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5, minHeight: 22 }}>
        {m.is_friendly && (
          <Chip
            label="Warm-up"
            size="small"
            data-testid="warmup-chip"
            sx={{ height: 20, fontSize: '0.65rem', fontWeight: 700,
                  color: colors.darkText, backgroundColor: colors.labelText }}
          />
        )}
        {roundLabel && (
          <Chip
            label={roundLabel}
            size="small"
            data-testid="round-badge"
            sx={{ height: 20, fontSize: '0.65rem', fontWeight: 700, letterSpacing: '0.5px',
                  color: colors.darkText, backgroundColor: colors.labelText }}
          />
        )}
      </Box>

      {/* Teams + final score */}
      <Typography
        variant="subtitle1"
        sx={{ fontWeight: 700, color: colors.textPrimary, mb: 0.75 }}
      >
        {m.home_team} <Box component="span" sx={{ color: colors.labelText }}>{m.final_score}</Box> {m.away_team}
      </Typography>

      {/* Called line */}
      {m.winner_correct !== null && (
        <Typography
          variant="body2"
          data-testid="called-line"
          sx={{ color: colors.textSecondary, display: 'flex', alignItems: 'center' }}
        >
          Called: {m.winner_pick}
          {m.winner_correct ? <HitMark /> : <MissMark />}
          {!m.winner_correct && m.winner_actual && (
            <Box component="span" sx={{ color: colors.labelText, ml: 0.75 }}>
              ({m.winner_actual === 'Draw' ? 'drawn' : `${m.winner_actual} won`})
            </Box>
          )}
        </Typography>
      )}

      {/* Goals line */}
      {m.goals_correct !== null && (
        <Typography
          variant="body2"
          data-testid="goals-line"
          sx={{ color: colors.textSecondary, display: 'flex', alignItems: 'center' }}
        >
          Goals: {m.goals_pick}
          {m.goals_correct ? <HitMark /> : <MissMark />}
          <Box component="span" sx={{ color: colors.labelText, ml: 0.75 }}>
            ({goalsWord(m.goals_actual)})
          </Box>
        </Typography>
      )}
    </Card>
  );
};

// ── Content (remounts on retry) ───────────────────────────────────────

const TrackRecordContent: React.FC<{ onRetry: () => void }> = ({ onRetry }) => {
  const { matches, loading, error } = useAccuracyMatches();

  const headline = useMemo(() => {
    const winnerEval = matches.filter((m) => m.winner_correct !== null);
    const winnerHits = winnerEval.filter((m) => m.winner_correct === true).length;
    const goalsEval = matches.filter((m) => m.goals_correct !== null);
    const goalsHits = goalsEval.filter((m) => m.goals_correct === true).length;
    const pct = winnerEval.length
      ? Math.round((winnerHits / winnerEval.length) * 100)
      : 0;
    return { winnerHits, winnerTotal: winnerEval.length, pct, goalsHits, goalsTotal: goalsEval.length };
  }, [matches]);

  if (loading) {
    return (
      <Box data-testid="loading-state">
        {[0, 1, 2].map((i) => (
          <Card key={i} sx={{ mb: 1.5, p: 2 }}>
            <Skeleton variant="text" width="40%" />
            <Skeleton variant="text" width="60%" />
            <Skeleton variant="text" width="50%" />
          </Card>
        ))}
      </Box>
    );
  }

  if (error) {
    return (
      <Box data-testid="error-state" sx={{ textAlign: 'center', py: 6 }}>
        <Typography variant="h6" sx={{ color: '#ef5350', mb: 1 }}>
          Could not load the track record
        </Typography>
        <Typography variant="body2" sx={{ color: colors.labelText, mb: 3 }}>
          {error}
        </Typography>
        <Button variant="contained" onClick={onRetry}>
          Retry
        </Button>
      </Box>
    );
  }

  if (matches.length === 0) {
    return (
      <Box data-testid="empty-state" sx={{ textAlign: 'center', py: 6 }}>
        <Typography variant="h6" sx={{ color: colors.labelText, mb: 1 }}>
          No accuracy data yet
        </Typography>
        <Typography variant="body2" sx={{ color: colors.labelText }}>
          Track record will appear after completed matches are evaluated.
        </Typography>
      </Box>
    );
  }

  return (
    <Box data-testid="track-record-content">
      {/* Headline */}
      <Box data-testid="headline" sx={{ mb: 3 }}>
        <Typography
          variant="h5"
          sx={{ fontWeight: 800, color: colors.textPrimary }}
        >
          Winners called right: {headline.winnerHits} of {headline.winnerTotal}
          {headline.winnerTotal > 0 && ` (${headline.pct}%)`}
        </Typography>
        <Typography variant="body2" sx={{ color: colors.labelText, mt: 0.5 }}>
          Goals calls: {headline.goalsHits} of {headline.goalsTotal}
        </Typography>
      </Box>

      {/* Match list, newest first (payload order) */}
      {matches.map((m) => (
        <MatchCard key={m.fixture_id} m={m} />
      ))}
    </Box>
  );
};

const TrackRecordPage: React.FC = () => {
  const [retryKey, setRetryKey] = useState(0);
  const handleRetry = useCallback(() => setRetryKey((k) => k + 1), []);
  return <TrackRecordContent key={retryKey} onRetry={handleRetry} />;
};

export default TrackRecordPage;
