import React, { useMemo, useState, useEffect } from 'react';
import { Box, Typography, Button, Card, Skeleton } from '@mui/material';
import { useOutletContext } from 'react-router-dom';
import FixtureList from '../../football/components/FixtureList';
import RoundSelector from '../../football/components/RoundSelector';
import DateFilter from '../../football/components/DateFilter';
import { WorldCupOutletContext } from '../../football/types/outletContext';
import { roundShortLabel } from '../../football/utils/roundLabel';
import {
  groupFixturesByRound,
  getRoundCategories,
  getDefaultRound,
  getDefaultDate,
  getUniqueDates,
  toLocalDateKey,
} from '../../football/utils/roundGrouping';

const SchedulePage: React.FC = () => {
  const { fixtures, loading, error, onRetry, onFixtureClick } =
    useOutletContext<WorldCupOutletContext>();

  const roundGroups = useMemo(() => groupFixturesByRound(fixtures), [fixtures]);
  const roundCategories = useMemo(
    () => getRoundCategories(fixtures),
    [fixtures],
  );

  const defaultRound = useMemo(
    () => getDefaultRound(roundGroups),
    [roundGroups],
  );

  const [selectedRound, setSelectedRound] = useState<string>('');
  const [selectedDate, setSelectedDate] = useState<string>('all');

  // Set default round when fixtures load
  useEffect(() => {
    if (defaultRound && !selectedRound) {
      setSelectedRound(defaultRound);
    }
  }, [defaultRound, selectedRound]);

  // Get fixtures for the selected round
  const roundFixtures = useMemo(() => {
    const group = roundGroups.find((g) => g.category === selectedRound);
    return group ? group.fixtures : [];
  }, [roundGroups, selectedRound]);

  // Get unique dates for the selected round
  const roundDates = useMemo(
    () => getUniqueDates(roundFixtures),
    [roundFixtures],
  );

  // Reset date filter and set default when round changes
  useEffect(() => {
    setSelectedDate(getDefaultDate(roundFixtures));
  }, [roundFixtures]);

  // Filter fixtures by selected date
  const filteredFixtures = useMemo(() => {
    if (selectedDate === 'all') return roundFixtures;
    return roundFixtures.filter(
      (f) => toLocalDateKey(f.fixture.date) === selectedDate,
    );
  }, [roundFixtures, selectedDate]);

  const handleRoundChange = (round: string) => {
    setSelectedRound(round);
  };

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

  return (
    <Box>
      <RoundSelector
        rounds={roundCategories}
        selected={selectedRound}
        onChange={handleRoundChange}
        renderLabel={(r) => roundShortLabel(r) ?? r}
      />
      <DateFilter
        dates={roundDates}
        selected={selectedDate}
        onChange={setSelectedDate}
      />
      {filteredFixtures.length > 0 ? (
        <FixtureList
          fixtures={filteredFixtures}
          onFixtureClick={onFixtureClick}
        />
      ) : (
        <Box data-testid="round-empty-state" sx={{ textAlign: 'center', py: 6 }}>
          <Typography variant="h6" sx={{ color: '#b0bec5' }}>
            No matches scheduled
            {selectedDate !== 'all' ? ` for this date` : ''}
            {selectedRound ? ` in ${roundShortLabel(selectedRound) ?? selectedRound}` : ''}.
          </Typography>
        </Box>
      )}
    </Box>
  );
};

export default SchedulePage;
