import React, { useMemo, useState, useEffect } from 'react';
import { Box, Typography, Button, Card, Skeleton, Chip } from '@mui/material';
import { useOutletContext } from 'react-router-dom';
import RoundSelector from '../../football/components/RoundSelector';
import FixtureCard from '../../football/components/FixtureCard';
import { WorldCupOutletContext } from '../../football/types/outletContext';
import { KNOCKOUT_ROUND_ORDER, roundShortLabel } from '../../football/utils/roundLabel';
import {
  groupKnockoutFixturesByRound,
  defaultKnockoutRound,
} from '../../football/utils/knockoutView';
import { colors } from '../../football/colors';

const KnockoutsPage: React.FC = () => {
  const { fixtures, loading, error, onRetry, onFixtureClick } =
    useOutletContext<WorldCupOutletContext>();

  const byRound = useMemo(
    () => groupKnockoutFixturesByRound(fixtures),
    [fixtures],
  );
  const defaultRound = useMemo(() => defaultKnockoutRound(fixtures), [fixtures]);

  const [selectedRound, setSelectedRound] = useState<string>('');

  // Adopt the default round once, after fixtures load (mirrors SchedulePage).
  useEffect(() => {
    if (defaultRound && !selectedRound) setSelectedRound(defaultRound);
  }, [defaultRound, selectedRound]);

  const activeRound = selectedRound || defaultRound;
  const roundFixtures = byRound[activeRound] ?? [];

  if (loading) {
    return (
      <Box data-testid="knockouts-loading">
        {Array.from({ length: 4 }).map((_, i) => (
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
      <Box data-testid="knockouts-error" sx={{ textAlign: 'center', py: 6 }}>
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
  }

  return (
    <Box>
      {/* Round-tab strip is always shown — the page demonstrates its
          structure even before any knockout fixtures exist. */}
      <RoundSelector
        rounds={[...KNOCKOUT_ROUND_ORDER]}
        selected={activeRound}
        onChange={setSelectedRound}
        renderLabel={(r) => roundShortLabel(r) ?? r}
      />

      {roundFixtures.length > 0 ? (
        <Box data-testid="knockout-fixtures">
          {roundFixtures.map((f) => (
            <FixtureCard
              key={f.fixture.id}
              fixture={f}
              onClick={onFixtureClick}
              badge={
                <Box sx={{ display: 'flex', justifyContent: 'center', mt: 1 }}>
                  <Chip
                    label={roundShortLabel(f.league.round) ?? f.league.round}
                    size="small"
                    sx={{
                      height: 20,
                      fontSize: '0.65rem',
                      fontWeight: 700,
                      letterSpacing: '0.5px',
                      color: colors.darkText,
                      backgroundColor: colors.labelText,
                    }}
                  />
                </Box>
              }
            />
          ))}
        </Box>
      ) : (
        <Box
          data-testid="knockouts-placeholder"
          sx={{ textAlign: 'center', py: 6 }}
        >
          <Typography variant="h6" sx={{ color: colors.labelText }}>
            Bracket fills in once the groups sort themselves out.
          </Typography>
        </Box>
      )}
    </Box>
  );
};

export default KnockoutsPage;
