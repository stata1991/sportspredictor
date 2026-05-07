import React, { useMemo } from 'react';
import { Box, Typography } from '@mui/material';
import { AFFixture } from '../types/fixture';
import FixtureCard from './FixtureCard';

interface FixtureListProps {
  fixtures: AFFixture[];
  onFixtureClick: (fixtureId: number) => void;
}

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
  // Parse as local date (noon to avoid any timezone edge cases in formatting)
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
  fixtures: AFFixture[];
}

const FixtureList: React.FC<FixtureListProps> = ({ fixtures, onFixtureClick }) => {
  const groups: DayGroup[] = useMemo(() => {
    if (!fixtures.length) return [];

    // Group by local date
    const map = new Map<string, AFFixture[]>();
    for (const f of fixtures) {
      const key = toLocalDateKey(f.fixture.date);
      const arr = map.get(key);
      if (arr) {
        arr.push(f);
      } else {
        map.set(key, [f]);
      }
    }

    // Sort groups chronologically by date key, then sort fixtures within each group
    return Array.from(map.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([dateKey, dayFixtures]) => ({
        dateKey,
        label: formatDayHeader(dateKey),
        fixtures: dayFixtures.sort(
          (a, b) => a.fixture.timestamp - b.fixture.timestamp,
        ),
      }));
  }, [fixtures]);

  if (!groups.length) return null;

  return (
    <Box>
      {groups.map((group) => (
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
              background: 'linear-gradient(180deg, rgba(13,13,13,0.95) 60%, rgba(13,13,13,0))',
              backdropFilter: 'blur(4px)',
            }}
          >
            {group.label}
          </Typography>
          {group.fixtures.map((f) => (
            <FixtureCard
              key={f.fixture.id}
              fixture={f}
              onClick={onFixtureClick}
            />
          ))}
        </Box>
      ))}
    </Box>
  );
};

export default FixtureList;
