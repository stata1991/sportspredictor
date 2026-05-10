import React from 'react';
import { Box, Typography, Button, Card, Skeleton } from '@mui/material';
import { useOutletContext } from 'react-router-dom';
import FixtureList from '../../football/components/FixtureList';
import { WorldCupOutletContext } from '../../football/types/outletContext';

const SchedulePage: React.FC = () => {
  const { fixtures, loading, error, onRetry, onFixtureClick } =
    useOutletContext<WorldCupOutletContext>();

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

  if (error) {
    return (
      <Box data-testid="error-state" sx={{ textAlign: 'center', py: 6 }}>
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

  if (!fixtures.length) {
    return (
      <Box data-testid="empty-state" sx={{ textAlign: 'center', py: 6 }}>
        <Typography variant="h6" sx={{ color: '#b0bec5' }}>
          Fixtures publish closer to kickoff. Check back soon.
        </Typography>
      </Box>
    );
  }

  return <FixtureList fixtures={fixtures} onFixtureClick={onFixtureClick} />;
};

export default SchedulePage;
