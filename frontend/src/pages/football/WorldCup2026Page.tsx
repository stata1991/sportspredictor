import React, { useState, useCallback } from 'react';
import { Box, Typography, Button, Card, Skeleton } from '@mui/material';
import { useNavigate } from 'react-router-dom';
import { useFixtures } from '../../football/hooks/useFixtures';
import FixtureList from '../../football/components/FixtureList';

/** Inner component that consumes the hook — remounts when `key` changes. */
const FixtureLoader: React.FC<{ onRetry: () => void }> = ({ onRetry }) => {
  const { fixtures, loading, error } = useFixtures();
  const navigate = useNavigate();

  const handleFixtureClick = useCallback(
    (fixtureId: number) => {
      navigate(`/football/match/${fixtureId}`);
    },
    [navigate],
  );

  // Loading state
  if (loading) {
    return (
      <Box data-testid="loading-state">
        {Array.from({ length: 5 }).map((_, i) => (
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

  // Error state
  if (error) {
    return (
      <Box
        data-testid="error-state"
        sx={{ textAlign: 'center', py: 6 }}
      >
        <Typography variant="h6" sx={{ color: '#ef5350', mb: 1 }}>
          Something went wrong
        </Typography>
        <Typography variant="body2" sx={{ color: '#b0bec5', mb: 3 }}>
          {error}
        </Typography>
        <Button variant="contained" onClick={onRetry}>
          Retry
        </Button>
      </Box>
    );
  }

  // Empty state
  if (!fixtures.length) {
    return (
      <Box
        data-testid="empty-state"
        sx={{ textAlign: 'center', py: 6 }}
      >
        <Typography variant="h6" sx={{ color: '#b0bec5' }}>
          Fixtures publish closer to kickoff. Check back soon.
        </Typography>
      </Box>
    );
  }

  // Success state
  return (
    <FixtureList fixtures={fixtures} onFixtureClick={handleFixtureClick} />
  );
};

const WorldCup2026Page: React.FC = () => {
  const [retryKey, setRetryKey] = useState(0);

  const handleRetry = useCallback(() => {
    setRetryKey((k) => k + 1);
  }, []);

  return (
    <Box sx={{ maxWidth: 700, mx: 'auto', px: { xs: 1, sm: 2 }, py: 3 }}>
      <Typography
        variant="h4"
        sx={{ textAlign: 'center', mb: 3 }}
      >
        FIFA World Cup 2026
      </Typography>
      <FixtureLoader key={retryKey} onRetry={handleRetry} />
    </Box>
  );
};

export default WorldCup2026Page;
