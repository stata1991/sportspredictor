import React from 'react';
import { Box, Card, Typography } from '@mui/material';
import { StandingEntry } from '../types/standings';
import { flagClass } from '../utils/countryFlag';
import { colors } from '../colors';

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

const TeamCell: React.FC<{ entry: StandingEntry }> = ({ entry }) => {
  const flag = flagClass(entry.team.name);
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75 }}>
      {flag ? (
        <span className={flag} style={{ fontSize: '1rem', lineHeight: 1 }} />
      ) : entry.team.logo ? (
        <img src={entry.team.logo} alt="" style={{ width: 16, height: 16 }} />
      ) : null}
      <span>{entry.team.name}</span>
    </Box>
  );
};

interface ThirdPlaceRankingCardProps {
  entries: StandingEntry[];
}

const ThirdPlaceRankingCard: React.FC<ThirdPlaceRankingCardProps> = ({
  entries,
}) => (
  <Box data-testid="third-place-section" sx={{ mt: 4 }}>
    <Box sx={{ mb: 2, textAlign: 'center' }}>
      <Typography
        variant="h6"
        sx={{ fontWeight: 700, color: colors.textPrimary }}
      >
        Third-Placed Team Rankings
      </Typography>
      <Typography
        variant="body2"
        sx={{ color: colors.labelText, mt: 0.5 }}
      >
        Best 8 of 12 third-placed teams advance to the Round of 32
      </Typography>
    </Box>

    <Card
      data-testid="third-place-card"
      sx={{
        backgroundColor: 'rgba(26, 26, 26, 0.9)',
        borderTop: `2px dashed ${colors.neutral}`,
        borderLeft: 'none',
        overflow: 'clip',
      }}
    >
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
            {entries.map((entry) => (
              <tr key={entry.team.id}>
                <Box component="td" sx={{ ...tdSx, textAlign: 'left', pl: 2 }}>
                  {entry.rank}
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
  </Box>
);

export default ThirdPlaceRankingCard;
