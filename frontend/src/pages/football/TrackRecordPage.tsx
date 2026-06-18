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

// How a knockout advancer went through, for the called line.
const advanceVerb = (decidedBy: MatchReceipt['decided_by']): string =>
  decidedBy === 'penalties'
    ? 'advanced on penalties'
    : decidedBy === 'extra_time'
    ? 'won in extra time'
    : 'won';

// Short tag appended to the score for a knockout decided past 90'.
const scoreTag = (decidedBy: MatchReceipt['decided_by']): string | null =>
  decidedBy === 'penalties' ? 'pens' : decidedBy === 'extra_time' ? 'ET' : null;

// The parenthetical on the called line.
// - Knockout (decided_by set): always show how the advancer went through —
//   never "drawn" (a knockout cannot draw).
// - Group stage: only on a miss — "X won" / "drawn".
const calledParenthetical = (m: MatchReceipt): string | null => {
  if (m.decided_by) {
    const verb = advanceVerb(m.decided_by);
    return m.winner_correct ? verb : `${m.winner_actual} ${verb}`;
  }
  if (!m.winner_correct && m.winner_actual) {
    return m.winner_actual === 'Draw' ? 'drawn' : `${m.winner_actual} won`;
  }
  return null;
};

// ── One match receipt card ────────────────────────────────────────────

const MatchCard: React.FC<{ m: MatchReceipt }> = ({ m }) => {
  const roundLabel = roundShortLabel(m.round);
  const tag = scoreTag(m.decided_by);
  const parenthetical = calledParenthetical(m);

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
      {/* Round badge (absent when round is unknown — graceful) */}
      {roundLabel && (
        <Box sx={{ mb: 0.5 }}>
          <Chip
            label={roundLabel}
            size="small"
            data-testid="round-badge"
            sx={{ height: 20, fontSize: '0.65rem', fontWeight: 700, letterSpacing: '0.5px',
                  color: colors.darkText, backgroundColor: colors.labelText }}
          />
        </Box>
      )}

      {/* Teams + final score (regulation; KO adds an ET/pens tag) */}
      <Typography
        variant="subtitle1"
        sx={{ fontWeight: 700, color: colors.textPrimary, mb: 0.75 }}
      >
        {m.home_team}{' '}
        <Box component="span" sx={{ color: colors.labelText }}>
          {m.final_score}
          {tag && (
            <Box component="span" data-testid="score-tag" sx={{ ml: 0.5 }}>
              · {tag}
            </Box>
          )}
        </Box>{' '}
        {m.away_team}
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
          {parenthetical && (
            <Box component="span" sx={{ color: colors.labelText, ml: 0.75 }}>
              ({parenthetical})
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

  // Public receipts are WC2026 only — pre-tournament warm-ups were internal
  // pipeline tests, never public calls. Filter BEFORE the list and the
  // headline so the number reflects exactly what's shown.
  const wcMatches = useMemo(
    () => matches.filter((m) => !m.is_friendly),
    [matches],
  );

  const headline = useMemo(() => {
    const winnerEval = wcMatches.filter((m) => m.winner_correct !== null);
    // Headline accuracy is DECISIVE matches only. A draw is structurally
    // unwinnable for the top pick — a draw is almost never any model's
    // single most-likely outcome — so lumping draws into the denominator
    // understates the real skill. Draws aren't hidden: they keep their own
    // honest line and still render in the list below.
    const decisive = winnerEval.filter((m) => m.winner_actual !== 'Draw');
    const decisiveHits = decisive.filter((m) => m.winner_correct === true).length;
    const drawnCount = winnerEval.length - decisive.length;
    const goalsEval = wcMatches.filter((m) => m.goals_correct !== null);
    const goalsHits = goalsEval.filter((m) => m.goals_correct === true).length;
    const pct = decisive.length
      ? Math.round((decisiveHits / decisive.length) * 100)
      : 0;
    return {
      decisiveHits,
      decisiveTotal: decisive.length,
      pct,
      drawnCount,
      goalsHits,
      goalsTotal: goalsEval.length,
    };
  }, [wcMatches]);

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

  if (wcMatches.length === 0) {
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
      {/* Headline — decisive accuracy leads; draws own their own line */}
      <Box data-testid="headline" sx={{ mb: 3 }}>
        <Typography
          variant="h5"
          sx={{ fontWeight: 800, color: colors.textPrimary }}
        >
          Winners called right: {headline.decisiveHits} of {headline.decisiveTotal}{' '}
          decisive {headline.decisiveTotal === 1 ? 'match' : 'matches'}
          {headline.decisiveTotal > 0 && ` (${headline.pct}%)`}
        </Typography>
        {headline.drawnCount > 0 && (
          <Typography
            data-testid="draw-line"
            variant="body2"
            sx={{ color: colors.labelText, mt: 0.5 }}
          >
            {headline.drawnCount}{' '}
            {headline.drawnCount === 1 ? 'match' : 'matches'} drawn — a draw is
            rarely the top call for any model.
          </Typography>
        )}
        <Typography variant="body2" sx={{ color: colors.labelText, mt: 0.5 }}>
          Goals calls: {headline.goalsHits} of {headline.goalsTotal}
        </Typography>
      </Box>

      {/* Match list, newest first (payload order) */}
      {wcMatches.map((m) => (
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
