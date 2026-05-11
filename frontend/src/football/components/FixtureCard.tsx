import React from 'react';
import { Card, CardActionArea, Box, Typography, Chip } from '@mui/material';
import { AFFixture } from '../types/fixture';
import { colors } from '../colors';
import { flagClass } from '../utils/countryFlag';

interface FixtureCardProps {
  fixture: AFFixture;
  onClick: (fixtureId: number) => void;
  badge?: React.ReactNode;
}

const STATUS_COLORS: Record<string, string> = {
  NS: '#90caf9',   // not started — blue
  '1H': '#66bb6a', // first half — green
  HT: '#ffa726',   // half time — orange
  '2H': '#66bb6a', // second half — green
  ET: '#ef5350',    // extra time — red
  PEN: '#ef5350',   // penalties — red
  FT: '#b0bec5',   // full time — grey
  AET: '#b0bec5',  // after extra time — grey
  PST: '#ffee58',  // postponed — yellow
  CANC: '#ef5350', // cancelled — red
};

const formatKickoff = (isoDate: string): string => {
  const date = new Date(isoDate);
  return new Intl.DateTimeFormat(undefined, {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  }).format(date);
};

const FixtureCard: React.FC<FixtureCardProps> = ({ fixture, onClick, badge }) => {
  const { teams, fixture: info } = fixture;
  const kickoff = formatKickoff(info.date);
  const statusShort = info.status.short;
  const statusColor = STATUS_COLORS[statusShort] || colors.labelText;

  return (
    <Card
      data-testid="fixture-card"
      sx={{
        mb: 1.5,
        background: 'linear-gradient(145deg, #1e1e1e, #2a2a2a)',
        border: '1px solid rgba(255,255,255,0.06)',
      }}
    >
      <CardActionArea
        onClick={() => onClick(info.id)}
        sx={{ p: { xs: 1.5, sm: 2 } }}
      >
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'nowrap',
            gap: 1,
          }}
        >
          {/* Home team */}
          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              gap: 1,
              flex: 1,
              minWidth: 0,
              justifyContent: 'flex-end',
            }}
          >
            <Typography
              variant="body1"
              sx={{
                fontWeight: 600,
                color: colors.textPrimary,
                textAlign: 'right',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
                fontSize: { xs: '0.85rem', sm: '1rem' },
              }}
            >
              {teams.home.name}
            </Typography>
            {(() => {
              const fc = flagClass(teams.home.name);
              if (fc) {
                return (
                  <Box
                    component="span"
                    className={fc}
                    role="img"
                    aria-label={`${teams.home.name} flag`}
                    data-testid="team-flag"
                    sx={{ fontSize: 22, flexShrink: 0, lineHeight: 1 }}
                  />
                );
              }
              return teams.home.logo ? (
                <Box
                  component="img"
                  src={teams.home.logo}
                  alt={`${teams.home.name} logo`}
                  sx={{ width: 28, height: 28, flexShrink: 0 }}
                />
              ) : null;
            })()}
          </Box>

          {/* Center: time / score / vs */}
          <Box
            sx={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              flexShrink: 0,
              mx: { xs: 0.5, sm: 1.5 },
              minWidth: 60,
            }}
          >
            {fixture.goals.home !== null && fixture.goals.away !== null ? (
              <Typography
                variant="body1"
                sx={{ fontWeight: 700, color: colors.textPrimary, fontSize: '1.1rem' }}
              >
                {fixture.goals.home} – {fixture.goals.away}
              </Typography>
            ) : (
              <Typography
                variant="body2"
                sx={{ color: colors.labelText, fontWeight: 500 }}
              >
                vs
              </Typography>
            )}
            <Typography
              variant="caption"
              sx={{ color: '#999', mt: 0.25, fontSize: '0.7rem' }}
            >
              {kickoff}
            </Typography>
            <Chip
              label={statusShort}
              size="small"
              data-testid="status-pill"
              sx={{
                mt: 0.5,
                height: 20,
                fontSize: '0.65rem',
                fontWeight: 700,
                color: colors.darkText,
                backgroundColor: statusColor,
              }}
            />
          </Box>

          {/* Away team */}
          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              gap: 1,
              flex: 1,
              minWidth: 0,
            }}
          >
            {(() => {
              const fc = flagClass(teams.away.name);
              if (fc) {
                return (
                  <Box
                    component="span"
                    className={fc}
                    role="img"
                    aria-label={`${teams.away.name} flag`}
                    data-testid="team-flag"
                    sx={{ fontSize: 22, flexShrink: 0, lineHeight: 1 }}
                  />
                );
              }
              return teams.away.logo ? (
                <Box
                  component="img"
                  src={teams.away.logo}
                  alt={`${teams.away.name} logo`}
                  sx={{ width: 28, height: 28, flexShrink: 0 }}
                />
              ) : null;
            })()}
            <Typography
              variant="body1"
              sx={{
                fontWeight: 600,
                color: colors.textPrimary,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
                fontSize: { xs: '0.85rem', sm: '1rem' },
              }}
            >
              {teams.away.name}
            </Typography>
          </Box>
        </Box>

        {/* Prediction badge slot */}
        <div data-testid="prediction-badge-slot">{badge}</div>
      </CardActionArea>
    </Card>
  );
};

export default FixtureCard;
