import React from 'react';
import { Box, Card, CircularProgress, Typography } from '@mui/material';
import { AFFixture } from '../types/fixture';
import { H2HSummary } from '../hooks/useHeadToHead';
import { flagClass } from '../utils/countryFlag';
import { colors } from '../colors';

function formatMatchDate(iso: string): string {
  const date = new Date(iso);
  return new Intl.DateTimeFormat(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  }).format(date);
}

/** Determine the winner label for a single H2H fixture. */
function winnerLabel(
  fx: AFFixture,
  homeTeamName: string,
  awayTeamName: string,
): string | null {
  if (fx.goals.home === null || fx.goals.away === null) return null;
  if (fx.goals.home > fx.goals.away) return fx.teams.home.name;
  if (fx.goals.away > fx.goals.home) return fx.teams.away.name;
  return 'Draw';
}

const TeamName: React.FC<{ name: string; bold?: boolean }> = ({ name, bold }) => {
  const flag = flagClass(name);
  return (
    <Box
      sx={{
        display: 'flex',
        alignItems: 'center',
        gap: 0.5,
        fontWeight: bold ? 700 : 400,
        color: bold ? colors.textPrimary : colors.textSecondary,
      }}
    >
      {flag && (
        <span className={flag} style={{ fontSize: '0.85rem', lineHeight: 1 }} />
      )}
      <span>{name}</span>
    </Box>
  );
};

interface HeadToHeadSectionProps {
  fixtures: AFFixture[];
  summary: H2HSummary | null;
  loading: boolean;
  error: string | null;
  homeTeam: string;
  awayTeam: string;
}

const HeadToHeadSection: React.FC<HeadToHeadSectionProps> = ({
  fixtures,
  summary,
  loading,
  error,
  homeTeam,
  awayTeam,
}) => {
  if (loading) {
    return (
      <Box data-testid="h2h-loading" sx={{ textAlign: 'center', py: 3 }}>
        <CircularProgress size={24} sx={{ color: colors.neutral }} />
      </Box>
    );
  }

  if (error) {
    return null; // Silently fail — H2H is supplementary, not critical.
  }

  return (
    <Box data-testid="h2h-section" sx={{ mt: 3 }}>
      <Typography
        variant="h6"
        sx={{ fontWeight: 700, mb: 1.5, color: colors.textPrimary }}
      >
        Head-to-Head
      </Typography>

      {fixtures.length === 0 ? (
        <Typography
          data-testid="h2h-empty"
          variant="body2"
          sx={{ color: colors.labelText, fontStyle: 'italic' }}
        >
          First meeting between these sides.
        </Typography>
      ) : (
        <>
          {/* Summary bar */}
          {summary && (
            <Box
              data-testid="h2h-summary"
              sx={{
                display: 'flex',
                justifyContent: 'center',
                gap: 3,
                mb: 2,
              }}
            >
              <Box sx={{ textAlign: 'center' }}>
                <Typography
                  variant="h6"
                  sx={{ fontWeight: 700, color: colors.homeAccent }}
                >
                  {summary.wins}
                </Typography>
                <Typography variant="caption" sx={{ color: colors.labelText }}>
                  {homeTeam} wins
                </Typography>
              </Box>
              <Box sx={{ textAlign: 'center' }}>
                <Typography
                  variant="h6"
                  sx={{ fontWeight: 700, color: colors.neutral }}
                >
                  {summary.draws}
                </Typography>
                <Typography variant="caption" sx={{ color: colors.labelText }}>
                  Draws
                </Typography>
              </Box>
              <Box sx={{ textAlign: 'center' }}>
                <Typography
                  variant="h6"
                  sx={{ fontWeight: 700, color: colors.awayAccent }}
                >
                  {summary.losses}
                </Typography>
                <Typography variant="caption" sx={{ color: colors.labelText }}>
                  {awayTeam} wins
                </Typography>
              </Box>
            </Box>
          )}

          {/* Individual fixtures */}
          {fixtures.map((fx) => {
            const winner = winnerLabel(fx, homeTeam, awayTeam);
            const isHomeWinner = winner === fx.teams.home.name;
            const isAwayWinner = winner === fx.teams.away.name;

            return (
              <Card
                key={fx.fixture.id}
                data-testid="h2h-fixture"
                sx={{
                  mb: 1,
                  px: 2,
                  py: 1,
                  backgroundColor: 'rgba(26, 26, 26, 0.9)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  flexWrap: 'wrap',
                  gap: 1,
                }}
              >
                <Box
                  sx={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 1,
                    flex: 1,
                    minWidth: 0,
                  }}
                >
                  <TeamName name={fx.teams.home.name} bold={isHomeWinner} />
                  <Typography
                    data-testid="h2h-score"
                    variant="body2"
                    sx={{
                      fontWeight: 700,
                      color: colors.textPrimary,
                      mx: 0.5,
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {fx.goals.home ?? '–'} – {fx.goals.away ?? '–'}
                  </Typography>
                  <TeamName name={fx.teams.away.name} bold={isAwayWinner} />
                </Box>
                <Typography
                  variant="caption"
                  sx={{ color: colors.labelText, whiteSpace: 'nowrap' }}
                >
                  {formatMatchDate(fx.fixture.date)}
                </Typography>
              </Card>
            );
          })}
        </>
      )}
    </Box>
  );
};

export default HeadToHeadSection;
