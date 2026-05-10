import React, { useMemo } from 'react';
import { Box, Typography, Card, Skeleton } from '@mui/material';
import { useOutletContext } from 'react-router-dom';
import FixtureCard from '../../football/components/FixtureCard';
import LiveBadge from '../../football/components/LiveBadge';
import { isInPlay } from '../../football/utils/fixtureStatus';
import { colors } from '../../football/colors';
import { WorldCupOutletContext } from '../../football/types/outletContext';

const LiveMatchPage: React.FC = () => {
  const { fixtures, loading, error, onFixtureClick } =
    useOutletContext<WorldCupOutletContext>();

  const liveFixtures = useMemo(
    () => fixtures.filter((f) => isInPlay(f.fixture.status.short)),
    [fixtures],
  );

  if (loading) {
    return (
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
  }

  if (error) {
    return (
      <Box data-testid="error-state" sx={{ textAlign: 'center', py: 6 }}>
        <Typography variant="h6" sx={{ color: '#ef5350', mb: 1 }}>
          Something went wrong
        </Typography>
        <Typography variant="body2" sx={{ color: '#b0bec5', mb: 3 }}>
          {error}
        </Typography>
      </Box>
    );
  }

  if (liveFixtures.length === 0) {
    return (
      <Box data-testid="live-empty-state" sx={{ textAlign: 'center', py: 6 }}>
        <Typography variant="h6" sx={{ color: colors.labelText, mb: 1 }}>
          No matches are live right now
        </Typography>
        <Typography variant="body2" sx={{ color: colors.labelText }}>
          Check back during match time for live updates and predictions.
        </Typography>
      </Box>
    );
  }

  return (
    <Box data-testid="live-match-list">
      <Typography
        variant="subtitle1"
        sx={{ fontWeight: 700, color: colors.awayAccent, mb: 2 }}
      >
        {liveFixtures.length}{' '}
        {liveFixtures.length === 1 ? 'match' : 'matches'} live
      </Typography>
      {liveFixtures.map((f) => (
        <FixtureCard
          key={f.fixture.id}
          fixture={f}
          onClick={onFixtureClick}
          badge={
            <LiveBadge
              status={f.fixture.status.short}
              elapsedMinute={f.fixture.status.elapsed ?? undefined}
            />
          }
        />
      ))}
    </Box>
  );
};

export default LiveMatchPage;
