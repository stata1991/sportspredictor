import React, { useCallback, useMemo, useState } from 'react';
import { Link as RouterLink } from 'react-router-dom';
import { Helmet } from 'react-helmet-async';
import {
  Box,
  Card,
  Grid,
  Skeleton,
  Typography,
  Button,
} from '@mui/material';
import CheckCircleIcon from '@mui/icons-material/CheckCircle';
import { useStandings } from '../../football/hooks/useStandings';
import { StandingEntry } from '../../football/types/standings';
import { flagClass } from '../../football/utils/countryFlag';
import { partitionStandings } from '../../football/utils/partitionStandings';
import { isGroupStageComplete } from '../../football/utils/groupStageComplete';
import ThirdPlaceRankingCard from '../../football/components/ThirdPlaceRankingCard';
import QualifiedMarker from '../../football/components/QualifiedMarker';
import { colors } from '../../football/colors';

const TeamCell: React.FC<{ entry: StandingEntry }> = ({ entry }) => {
  const flag = flagClass(entry.team.name);
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
      {flag ? (
        <span
          className={flag}
          style={{ fontSize: '1rem', lineHeight: 1 }}
        />
      ) : entry.team.logo ? (
        <img
          src={entry.team.logo}
          alt=""
          style={{ width: 16, height: 16 }}
        />
      ) : null}
      <span>{entry.team.name}</span>
    </Box>
  );
};

const thSx = {
  py: 0.5,
  px: { xs: 0.5, sm: 1 },
  fontWeight: 700,
  fontSize: '0.7rem',
  color: colors.labelText,
  textAlign: 'center' as const,
  whiteSpace: 'nowrap' as const,
};

const tdSx = {
  py: 0.5,
  px: { xs: 0.5, sm: 1 },
  fontSize: '0.8rem',
  color: colors.textSecondary,
  textAlign: 'center' as const,
  borderBottom: '1px solid rgba(255,255,255,0.04)',
};

const GroupCard: React.FC<{ group: StandingEntry[]; frozen?: boolean }> = ({
  group,
  frozen,
}) => {
  const groupName = group[0]?.group ?? 'Group';

  return (
    <Card
      data-testid="group-card"
      sx={{
        backgroundColor: 'rgba(26, 26, 26, 0.9)',
        borderLeft: `3px solid ${colors.homeAccent}`,
        overflow: 'clip',
      }}
    >
      <Box sx={{ px: 2, py: 1.5 }}>
        <Typography
          variant="subtitle1"
          sx={{ fontWeight: 700, color: colors.textPrimary }}
        >
          {groupName}
        </Typography>
      </Box>

      <Box sx={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr>
              <Box component="th" sx={{ ...thSx, textAlign: 'left', pl: 2 }}>#</Box>
              <Box component="th" sx={{ ...thSx, textAlign: 'left' }}>Team</Box>
              <Box component="th" sx={thSx}>P</Box>
              <Box component="th" sx={{ ...thSx, display: { xs: 'none', sm: 'table-cell' } }}>W</Box>
              <Box component="th" sx={{ ...thSx, display: { xs: 'none', sm: 'table-cell' } }}>D</Box>
              <Box component="th" sx={{ ...thSx, display: { xs: 'none', sm: 'table-cell' } }}>L</Box>
              <Box component="th" sx={{ ...thSx, display: { xs: 'none', md: 'table-cell' } }}>GF</Box>
              <Box component="th" sx={{ ...thSx, display: { xs: 'none', md: 'table-cell' } }}>GA</Box>
              <Box component="th" sx={thSx}>GD</Box>
              <Box component="th" sx={thSx}>Pts</Box>
            </tr>
          </thead>
          <tbody>
            {group.map((entry, idx) => (
              <tr key={entry.team.id}>
                <Box component="td" sx={{ ...tdSx, textAlign: 'left', pl: 2 }}>
                  {entry.rank}
                  {frozen && idx < 2 && <QualifiedMarker />}
                </Box>
                <Box component="td" sx={{ ...tdSx, textAlign: 'left' }}>
                  <TeamCell entry={entry} />
                </Box>
                <Box component="td" sx={tdSx}>{entry.all.played}</Box>
                <Box component="td" sx={{ ...tdSx, display: { xs: 'none', sm: 'table-cell' } }}>{entry.all.win}</Box>
                <Box component="td" sx={{ ...tdSx, display: { xs: 'none', sm: 'table-cell' } }}>{entry.all.draw}</Box>
                <Box component="td" sx={{ ...tdSx, display: { xs: 'none', sm: 'table-cell' } }}>{entry.all.lose}</Box>
                <Box component="td" sx={{ ...tdSx, display: { xs: 'none', md: 'table-cell' } }}>{entry.all.goals.for}</Box>
                <Box component="td" sx={{ ...tdSx, display: { xs: 'none', md: 'table-cell' } }}>{entry.all.goals.against}</Box>
                <Box component="td" sx={tdSx}>{entry.goalsDiff}</Box>
                <Box
                  component="td"
                  sx={{
                    ...tdSx,
                    fontWeight: 700,
                    color: colors.homeAccent,
                  }}
                >
                  {entry.points}
                </Box>
              </tr>
            ))}
          </tbody>
        </table>
      </Box>
    </Card>
  );
};

const LoadingSkeleton: React.FC = () => (
  <>
    <Grid container spacing={2}>
      {Array.from({ length: 6 }).map((_, i) => (
        <Grid key={i} size={{ xs: 12, sm: 6 }}>
          <Card sx={{ p: 2, backgroundColor: 'rgba(26, 26, 26, 0.9)' }}>
            <Skeleton variant="text" width="40%" sx={{ mb: 1 }} />
            {Array.from({ length: 4 }).map((_, j) => (
              <Skeleton key={j} variant="text" width="100%" />
            ))}
          </Card>
        </Grid>
      ))}
    </Grid>
    <Box data-testid="ranking-skeleton" sx={{ mt: 4 }}>
      <Skeleton variant="text" width="50%" sx={{ mx: 'auto', mb: 1 }} />
      <Card sx={{ p: 2, backgroundColor: 'rgba(26, 26, 26, 0.9)' }}>
        {Array.from({ length: 6 }).map((_, j) => (
          <Skeleton key={j} variant="text" width="100%" />
        ))}
      </Card>
    </Box>
  </>
);

const StandingsPage: React.FC = () => {
  const [retryKey, setRetryKey] = useState(0);
  const handleRetry = useCallback(() => setRetryKey((k) => k + 1), []);

  return (
    <>
      <Helmet>
        <title>Group Standings — FIFA World Cup 2026 | FantasyFuel</title>
        <meta
          name="description"
          content="Live group standings for the FIFA World Cup 2026 — points, goal difference, and qualification status for all 12 groups."
        />
      </Helmet>
      <Box sx={{ maxWidth: 960, mx: 'auto', px: { xs: 1, sm: 2 }, py: 3 }}>
        <Typography
          variant="h4"
          sx={{ textAlign: 'center', mb: 3 }}
        >
          FIFA World Cup 2026
        </Typography>
        <Typography
          variant="h6"
          sx={{ textAlign: 'center', mb: 3, color: colors.labelText }}
        >
          Group Standings
        </Typography>
        <StandingsContent key={retryKey} onRetry={handleRetry} />
      </Box>
    </>
  );
};

const StandingsContent: React.FC<{ onRetry: () => void }> = ({ onRetry }) => {
  const { groups, loading, error } = useStandings();

  const { realGroups, thirdPlaceRanking } = useMemo(
    () => partitionStandings(groups),
    [groups],
  );

  const frozen = useMemo(
    () => isGroupStageComplete(realGroups),
    [realGroups],
  );

  if (loading) {
    return (
      <Box data-testid="standings-loading">
        <LoadingSkeleton />
      </Box>
    );
  }

  if (error) {
    return (
      <Box data-testid="standings-error" sx={{ textAlign: 'center', py: 6 }}>
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

  if (!groups.length) {
    return (
      <Box data-testid="standings-empty" sx={{ textAlign: 'center', py: 6 }}>
        <Typography variant="h6" sx={{ color: colors.labelText }}>
          Standings will be available once the group stage begins.
        </Typography>
      </Box>
    );
  }

  return (
    <>
      {frozen && (
        <Box
          component={RouterLink}
          to="/football/world-cup-2026/knockouts"
          data-testid="group-stage-complete-banner"
          sx={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 1,
            mb: 3,
            px: 2,
            py: 1,
            borderRadius: 2,
            textDecoration: 'none',
            cursor: 'pointer',
            backgroundColor: 'rgba(255, 111, 0, 0.12)',
            border: `1px solid ${colors.homeAccent}`,
            '&:hover': { backgroundColor: 'rgba(255, 111, 0, 0.2)' },
          }}
        >
          <CheckCircleIcon sx={{ fontSize: '1rem', color: colors.homeAccent }} />
          <Typography
            variant="subtitle2"
            sx={{ fontWeight: 700, color: colors.textPrimary }}
          >
            Group Stage Complete — see the knockout bracket
          </Typography>
        </Box>
      )}
      <Grid container spacing={2} data-testid="standings-grid">
        {realGroups.map((group, i) => (
          <Grid key={group[0]?.group ?? i} size={{ xs: 12, sm: 6 }}>
            <GroupCard group={group} frozen={frozen} />
          </Grid>
        ))}
      </Grid>
      {thirdPlaceRanking && (
        <ThirdPlaceRankingCard entries={thirdPlaceRanking} frozen={frozen} />
      )}
    </>
  );
};

export default StandingsPage;
