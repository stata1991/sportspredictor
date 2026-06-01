import React, { useState, useCallback, useMemo } from 'react';
import { Helmet } from 'react-helmet-async';
import { Box, Typography, Tabs, Tab, keyframes } from '@mui/material';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useFixtures } from '../../football/hooks/useFixtures';
import { isInPlay } from '../../football/utils/fixtureStatus';
import { colors } from '../../football/colors';
import { WorldCupOutletContext } from '../../football/types/outletContext';

const pulse = keyframes`
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
`;

const TAB_PATHS = [
  '/football/world-cup-2026',
  '/football/world-cup-2026/live',
  '/football/world-cup-2026/track-record',
  '/football/world-cup-2026/standings',
] as const;

function pathToTabIndex(pathname: string): number {
  if (pathname.startsWith(TAB_PATHS[3])) return 3;
  if (pathname.startsWith(TAB_PATHS[2])) return 2;
  if (pathname.startsWith(TAB_PATHS[1])) return 1;
  return 0;
}

/** Inner component that consumes useFixtures — remounts when retryKey changes. */
const FixtureProvider: React.FC<{ onRetry: () => void }> = ({ onRetry }) => {
  const { fixtures, loading, error } = useFixtures();
  const navigate = useNavigate();
  const location = useLocation();

  const handleFixtureClick = useCallback(
    (fixtureId: number) => navigate(`/football/match/${fixtureId}`),
    [navigate],
  );

  const hasLive = useMemo(
    () => fixtures.some((f) => isInPlay(f.fixture.status.short)),
    [fixtures],
  );

  const tabIndex = pathToTabIndex(location.pathname);

  const handleTabChange = (_: React.SyntheticEvent, newValue: number) => {
    navigate(TAB_PATHS[newValue]);
  };

  const context: WorldCupOutletContext = {
    fixtures,
    loading,
    error,
    onRetry,
    onFixtureClick: handleFixtureClick,
  };

  return (
    <>
      <Tabs
        value={tabIndex}
        onChange={handleTabChange}
        variant="scrollable"
        scrollButtons={false}
        textColor="inherit"
        data-testid="wc-tabs"
        TabIndicatorProps={{ sx: { backgroundColor: colors.homeAccent, height: 3 } }}
        sx={{
          mb: 3,
          borderBottom: '1px solid rgba(255,255,255,0.08)',
          '& .MuiTab-root': {
            textTransform: 'none',
            color: colors.labelText,
            fontWeight: 500,
            '&:hover': {
              color: '#ff9800',
            },
            '&.Mui-selected': {
              color: colors.homeAccent,
              fontWeight: 700,
            },
          },
        }}
      >
        <Tab label="Schedule" data-testid="tab-schedule" />
        <Tab
          data-testid="tab-live"
          label={
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
              Live Match
              {hasLive && (
                <Box
                  data-testid="live-tab-dot"
                  sx={{
                    width: 8,
                    height: 8,
                    borderRadius: '50%',
                    backgroundColor: colors.awayAccent,
                    animation: `${pulse} 1.5s ease-in-out infinite`,
                  }}
                />
              )}
            </Box>
          }
        />
        <Tab label="Track Record" data-testid="tab-track-record" />
        <Tab label="Standings" data-testid="tab-standings" />
      </Tabs>

      <Outlet context={context} />
    </>
  );
};

function useRouteMeta(pathname: string) {
  if (pathname.startsWith(TAB_PATHS[3])) {
    return {
      title: 'Group Standings — FIFA World Cup 2026 | FantasyFuel',
      description: 'Live group standings for the FIFA World Cup 2026 — points, goal difference, and qualification status for all 12 groups.',
    };
  }
  if (pathname.startsWith(TAB_PATHS[2])) {
    return {
      title: 'Prediction Track Record — FIFA World Cup 2026 | FantasyFuel',
      description: 'Aggregate accuracy and hit rate of our FIFA World Cup 2026 match predictions.',
    };
  }
  if (pathname.startsWith(TAB_PATHS[1])) {
    return {
      title: 'Live Matches — FIFA World Cup 2026 | FantasyFuel',
      description: 'Live win probability updates for in-play FIFA World Cup 2026 matches, refreshed every 60 seconds.',
    };
  }
  return {
    title: 'FIFA World Cup 2026 Schedule | FantasyFuel',
    description: 'Full match schedule with pre-match win probabilities for the FIFA World Cup 2026, kicking off June 11.',
  };
}

const WorldCup2026Layout: React.FC = () => {
  const [retryKey, setRetryKey] = useState(0);
  const handleRetry = useCallback(() => setRetryKey((k) => k + 1), []);
  const location = useLocation();
  const { title, description } = useRouteMeta(location.pathname);

  return (
    <>
      <Helmet>
        <title>{title}</title>
        <meta name="description" content={description} />
        <meta property="og:title" content={title} />
        <meta property="og:description" content={description} />
      </Helmet>
      <Box sx={{ maxWidth: 700, mx: 'auto', px: { xs: 1, sm: 2 }, py: 3 }}>
        <Typography variant="h4" sx={{ textAlign: 'center', mb: 3 }}>
          FIFA World Cup 2026
        </Typography>
        <FixtureProvider key={retryKey} onRetry={handleRetry} />
      </Box>
    </>
  );
};

export default WorldCup2026Layout;
