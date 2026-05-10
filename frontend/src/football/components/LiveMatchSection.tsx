import React, { useState, useEffect, useRef } from 'react';
import {
  Box,
  Typography,
  Skeleton,
  LinearProgress,
  linearProgressClasses,
  Button,
} from '@mui/material';
import RefreshIcon from '@mui/icons-material/Refresh';
import { useLivePolling } from '../hooks/useLivePolling';
import { isInPlay } from '../utils/fixtureStatus';
import { colors } from '../colors';
import { formatPercent } from '../utils/probability';
import LiveBadge from './LiveBadge';

// ── Response type (mirrors backend predict_live return) ─────────────

export interface LiveWinner {
  elapsed: number;
  current_score: { home: number; away: number };
  p_home_win: number;
  p_draw: number;
  p_away_win: number;
  expected_total_goals: number;
}

export interface LiveResponse {
  fixture_id: number;
  home_team: string;
  away_team: string;
  status: string;
  stage: string;
  cached?: boolean;
  confidence?: string;
  predictions: {
    live_winner: LiveWinner;
  };
}

// ── Props ───────────────────────────────────────────────────────────

interface LiveMatchSectionProps {
  fixtureId: number;
  initialStatus: string;
  homeTeam: string;
  awayTeam: string;
}

// ── "Updated Xs ago" helper ─────────────────────────────────────────

function useElapsedSeconds(lastUpdated: Date | null): number {
  const [seconds, setSeconds] = useState(0);
  const lastUpdatedRef = useRef(lastUpdated);
  lastUpdatedRef.current = lastUpdated;

  useEffect(() => {
    if (!lastUpdated) {
      setSeconds(0);
      return;
    }
    setSeconds(Math.floor((Date.now() - lastUpdated.getTime()) / 1000));

    const id = setInterval(() => {
      if (lastUpdatedRef.current) {
        setSeconds(
          Math.floor((Date.now() - lastUpdatedRef.current.getTime()) / 1000),
        );
      }
    }, 5_000);

    return () => clearInterval(id);
  }, [lastUpdated]);

  return seconds;
}

// ── Probability bars (matches WinnerBars from NumbersSection) ───────

const ProbabilityBars: React.FC<{
  pHome: number;
  pDraw: number;
  pAway: number;
  homeTeam: string;
  awayTeam: string;
}> = ({ pHome, pDraw, pAway, homeTeam, awayTeam }) => {
  const bars = [
    { label: homeTeam, value: pHome, color: colors.homeAccent },
    { label: 'Draw', value: pDraw, color: colors.labelText },
    { label: awayTeam, value: pAway, color: colors.awayAccent },
  ];

  return (
    <Box data-testid="live-probability-bars" sx={{ mb: 2 }}>
      {bars.map((bar) => (
        <Box key={bar.label} sx={{ mb: 1 }}>
          <Box
            sx={{
              display: 'flex',
              justifyContent: 'space-between',
              mb: 0.25,
            }}
          >
            <Typography
              variant="caption"
              sx={{ color: colors.textPrimary, fontWeight: 600 }}
            >
              {bar.label}
            </Typography>
            <Typography
              variant="caption"
              sx={{ color: bar.color, fontWeight: 700 }}
            >
              {formatPercent(bar.value)}
            </Typography>
          </Box>
          <LinearProgress
            variant="determinate"
            value={bar.value * 100}
            sx={{
              height: 8,
              borderRadius: 4,
              backgroundColor: 'rgba(255,255,255,0.08)',
              [`& .${linearProgressClasses.bar}`]: {
                borderRadius: 4,
                backgroundColor: bar.color,
              },
            }}
          />
        </Box>
      ))}
    </Box>
  );
};

// ── Skeleton loading state ──────────────────────────────────────────

const LiveSkeleton: React.FC<{
  homeTeam: string;
  awayTeam: string;
  initialStatus: string;
}> = ({ homeTeam, awayTeam, initialStatus }) => (
  <Box data-testid="live-skeleton">
    <Box
      sx={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 2,
        mb: 2,
      }}
    >
      <Typography
        variant="h6"
        sx={{ color: colors.textPrimary, fontWeight: 700 }}
      >
        {homeTeam}
      </Typography>
      <Typography
        variant="h5"
        sx={{ color: colors.labelText, fontWeight: 700, mx: 1 }}
      >
        – — –
      </Typography>
      <Typography
        variant="h6"
        sx={{ color: colors.textPrimary, fontWeight: 700 }}
      >
        {awayTeam}
      </Typography>
      <LiveBadge status={initialStatus} />
    </Box>
    <Skeleton
      variant="rectangular"
      height={8}
      sx={{ borderRadius: 4, mb: 1, bgcolor: 'rgba(255,255,255,0.08)' }}
    />
    <Skeleton
      variant="rectangular"
      height={8}
      sx={{ borderRadius: 4, mb: 1, bgcolor: 'rgba(255,255,255,0.08)' }}
    />
    <Skeleton
      variant="rectangular"
      height={8}
      sx={{ borderRadius: 4, bgcolor: 'rgba(255,255,255,0.08)' }}
    />
  </Box>
);

// ── Main component ──────────────────────────────────────────────────

const LiveMatchSection: React.FC<LiveMatchSectionProps> = ({
  fixtureId,
  initialStatus,
  homeTeam,
  awayTeam,
}) => {
  // Track the latest known status for controlling polling.
  // Starts from initialStatus (from MatchPage's fixture fetch),
  // then updates when poll data arrives.
  const [currentStatus, setCurrentStatus] = useState(initialStatus);

  const { data, error, lastUpdated, refetch } =
    useLivePolling<LiveResponse>({
      url: `/api/football/predict/live/${fixtureId}`,
      intervalMs: 60_000,
      enabled: isInPlay(currentStatus),
      maxBackoffMs: 300_000,
    });

  // Sync status from poll data
  useEffect(() => {
    if (data?.status) {
      setCurrentStatus(data.status);
    }
  }, [data?.status]);

  const secondsAgo = useElapsedSeconds(lastUpdated);

  // First fetch hasn't resolved yet
  if (!data && !error) {
    return (
      <LiveSkeleton
        homeTeam={homeTeam}
        awayTeam={awayTeam}
        initialStatus={initialStatus}
      />
    );
  }

  // Error before any successful data
  if (!data && error) {
    return (
      <Box data-testid="live-error" sx={{ textAlign: 'center', py: 3 }}>
        <Typography
          variant="body2"
          sx={{ color: colors.labelText, mb: 1.5 }}
        >
          Could not load live predictions.
        </Typography>
        <Button
          size="small"
          variant="outlined"
          startIcon={<RefreshIcon />}
          onClick={() => refetch()}
          sx={{
            color: colors.textPrimary,
            borderColor: colors.labelText,
          }}
        >
          Retry
        </Button>
      </Box>
    );
  }

  // Have data — render live state
  const lw = data!.predictions.live_winner;

  return (
    <Box data-testid="live-match-section">
      {/* Score + badge row */}
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 2,
          mb: 2,
        }}
      >
        <Typography
          variant="h6"
          sx={{ color: colors.textPrimary, fontWeight: 700 }}
        >
          {data!.home_team}
        </Typography>
        <Typography
          variant="h4"
          data-testid="live-score"
          sx={{ color: colors.textPrimary, fontWeight: 800, mx: 1 }}
        >
          {lw.current_score.home} — {lw.current_score.away}
        </Typography>
        <Typography
          variant="h6"
          sx={{ color: colors.textPrimary, fontWeight: 700 }}
        >
          {data!.away_team}
        </Typography>
        <LiveBadge status={currentStatus} elapsedMinute={lw.elapsed} />
      </Box>

      {/* Probability bars */}
      <ProbabilityBars
        pHome={lw.p_home_win}
        pDraw={lw.p_draw}
        pAway={lw.p_away_win}
        homeTeam={data!.home_team}
        awayTeam={data!.away_team}
      />

      {/* Meta row */}
      <Box
        sx={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
        }}
      >
        <Typography variant="caption" sx={{ color: colors.labelText }}>
          Expected total goals: {lw.expected_total_goals.toFixed(1)}
        </Typography>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          {error && (
            <Typography
              variant="caption"
              data-testid="reconnecting"
              sx={{ color: colors.caution, fontWeight: 600 }}
            >
              Reconnecting…
            </Typography>
          )}
          {lastUpdated && (
            <Typography
              variant="caption"
              data-testid="updated-ago"
              sx={{ color: colors.labelText }}
            >
              Updated {secondsAgo}s ago
            </Typography>
          )}
        </Box>
      </Box>
    </Box>
  );
};

export default LiveMatchSection;
