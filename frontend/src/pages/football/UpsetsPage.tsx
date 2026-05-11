import React, { useState, useCallback, useMemo } from 'react';
import { Helmet } from 'react-helmet-async';
import { Box, Typography, Button, Card, Skeleton } from '@mui/material';
import { useNavigate } from 'react-router-dom';
import { useUpsets } from '../../football/hooks/useUpsets';
import { UpsetListItem } from '../../football/types/upset';
import { AFFixture } from '../../football/types/fixture';
import FixtureCard from '../../football/components/FixtureCard';
import { formatPercent } from '../../football/utils/probability';
import { colors } from '../../football/colors';

// ── Helpers ──────────────────────────────────────────────────────────

/** Return YYYY-MM-DD in the user's local timezone. */
const toLocalDateKey = (isoDate: string): string => {
  const d = new Date(isoDate);
  const year = d.getFullYear();
  const month = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
};

/** Format a date key into a readable day header, e.g. "Thursday, June 11". */
const formatDayHeader = (dateKey: string): string => {
  const [y, m, d] = dateKey.split('-').map(Number);
  const date = new Date(y, m - 1, d, 12);
  return new Intl.DateTimeFormat(undefined, {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
  }).format(date);
};

interface DayGroup {
  dateKey: string;
  label: string;
  items: UpsetListItem[];
}

/** Group upsets by kickoff date, sort groups chronologically, items by upset_index DESC. */
function groupByDate(upsets: UpsetListItem[]): DayGroup[] {
  const map = new Map<string, UpsetListItem[]>();
  for (const u of upsets) {
    const key = toLocalDateKey(u.kickoff);
    const arr = map.get(key);
    if (arr) {
      arr.push(u);
    } else {
      map.set(key, [u]);
    }
  }

  return Array.from(map.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([dateKey, items]) => ({
      dateKey,
      label: formatDayHeader(dateKey),
      items: items.sort((a, b) => b.upset_index - a.upset_index),
    }));
}

/** Adapt UpsetListItem → AFFixture shape expected by FixtureCard. */
function upsetToFixtureShape(upset: UpsetListItem): AFFixture {
  return {
    fixture: {
      id: upset.fixture_id,
      referee: null,
      timezone: 'UTC',
      date: upset.kickoff,
      timestamp: new Date(upset.kickoff).getTime() / 1000,
      venue: { id: null, name: null, city: null },
      status: { long: upset.status, short: upset.status, elapsed: null, extra: null },
    },
    league: {
      id: 0,
      name: '',
      country: null,
      logo: null,
      flag: null,
      season: 2026,
      round: upset.round,
    },
    teams: {
      home: { id: 0, name: upset.home_team, logo: upset.home_logo, winner: null },
      away: { id: 0, name: upset.away_team, logo: upset.away_logo, winner: null },
    },
    goals: { home: null, away: null },
    score: {
      halftime: { home: null, away: null },
      fulltime: { home: null, away: null },
      extratime: { home: null, away: null },
      penalty: { home: null, away: null },
    },
  };
}

// ── Sub-components ───────────────────────────────────────────────────

const UpsetBadge: React.FC<{ value: number }> = ({ value }) => (
  <Box
    data-testid="upset-badge"
    sx={{
      display: 'inline-flex',
      alignItems: 'center',
      backgroundColor: 'rgba(236, 64, 122, 0.15)',
      border: '1px solid rgba(236, 64, 122, 0.4)',
      borderRadius: 1,
      color: colors.awayAccent,
      fontSize: '0.7rem',
      fontWeight: 700,
      px: 1,
      py: 0.5,
      mt: 1,
    }}
  >
    Upset risk: {formatPercent(value, 1)}
  </Box>
);

// ── State UIs ────────────────────────────────────────────────────────

const UpsetsLoadingState: React.FC = () => (
  <Box data-testid="loading-state">
    {Array.from({ length: 3 }).map((_, i) => (
      <Card key={i} sx={{ mb: 1.5, p: 2 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <Skeleton variant="text" width="30%" />
          <Skeleton variant="circular" width={28} height={28} />
          <Skeleton variant="text" width="10%" />
          <Skeleton variant="circular" width={28} height={28} />
          <Skeleton variant="text" width="30%" />
        </Box>
      </Card>
    ))}
  </Box>
);

const UpsetsErrorState: React.FC<{ error: string; onRetry: () => void }> = ({
  error,
  onRetry,
}) => (
  <Box data-testid="error-state" sx={{ textAlign: 'center', py: 6 }}>
    <Typography variant="h6" sx={{ color: '#ef5350', mb: 1 }}>
      Something went wrong
    </Typography>
    <Typography variant="body2" sx={{ color: colors.labelText, mb: 3 }}>
      {error}
    </Typography>
    <Button variant="contained" onClick={onRetry}>
      Retry
    </Button>
  </Box>
);

const UpsetsEmptyState: React.FC = () => (
  <Box data-testid="empty-state" sx={{ textAlign: 'center', py: 6 }}>
    <Typography variant="h6" sx={{ color: colors.labelText, mb: 1 }}>
      No upset alerts right now.
    </Typography>
    <Typography variant="body2" sx={{ color: colors.labelText }}>
      Check back closer to kickoff.
    </Typography>
  </Box>
);

// ── Inner loader (remounts on retry) ─────────────────────────────────

const UpsetLoader: React.FC<{ onRetry: () => void }> = ({ onRetry }) => {
  const { upsets, loading, error } = useUpsets(0.45);
  const navigate = useNavigate();

  const handleClick = useCallback(
    (fixtureId: number) => {
      navigate(`/football/match/${fixtureId}`);
    },
    [navigate],
  );

  const grouped = useMemo(() => groupByDate(upsets), [upsets]);

  if (loading) return <UpsetsLoadingState />;
  if (error) return <UpsetsErrorState error={error} onRetry={onRetry} />;
  if (upsets.length === 0) return <UpsetsEmptyState />;

  return (
    <Box>
      {grouped.map((group) => (
        <Box key={group.dateKey} sx={{ mb: 3 }}>
          <Typography
            variant="subtitle1"
            data-testid="day-header"
            sx={{
              position: 'sticky',
              top: 0,
              zIndex: 2,
              py: 1,
              px: 1,
              fontWeight: 700,
              fontSize: { xs: '0.85rem', sm: '0.95rem' },
              color: '#ffe082',
              letterSpacing: '0.5px',
              background:
                'linear-gradient(180deg, rgba(13,13,13,0.95) 60%, rgba(13,13,13,0))',
              backdropFilter: 'blur(4px)',
            }}
          >
            {group.label}
          </Typography>
          {group.items.map((upset) => (
            <FixtureCard
              key={upset.fixture_id}
              fixture={upsetToFixtureShape(upset)}
              badge={<UpsetBadge value={upset.upset_index} />}
              onClick={handleClick}
            />
          ))}
        </Box>
      ))}
    </Box>
  );
};

// ── Page shell ───────────────────────────────────────────────────────

const UpsetsPage: React.FC = () => {
  const [retryKey, setRetryKey] = useState(0);

  const handleRetry = useCallback(() => {
    setRetryKey((k) => k + 1);
  }, []);

  return (
    <>
    <Helmet>
      <title>Upset Watch — FIFA World Cup 2026 | FantasyFuel</title>
      <meta name="description" content="Fixtures most likely to produce upsets at the FIFA World Cup 2026, ranked by upset index." />
      <meta property="og:title" content="Upset Watch — FIFA World Cup 2026 | FantasyFuel" />
      <meta property="og:description" content="Fixtures most likely to produce upsets at the FIFA World Cup 2026, ranked by upset index." />
    </Helmet>
    <Box sx={{ maxWidth: 700, mx: 'auto', px: { xs: 1, sm: 2 }, py: 3 }}>
      <Typography variant="h4" sx={{ textAlign: 'center', mb: 3 }}>
        Upset Watch
      </Typography>
      <UpsetLoader key={retryKey} onRetry={handleRetry} />
    </Box>
    </>
  );
};

export default UpsetsPage;
