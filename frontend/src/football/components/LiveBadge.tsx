import React from 'react';
import { Box, Typography, keyframes } from '@mui/material';
import { isInPlay, isCompleted } from '../utils/fixtureStatus';

const pulse = keyframes`
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
`;

interface LiveBadgeProps {
  status: string;
  elapsedMinute?: number;
}

function getLabel(status: string, elapsed?: number): string | null {
  switch (status) {
    case '1H':
    case '2H':
    case 'ET':
      return elapsed != null ? `LIVE ${elapsed}'` : 'LIVE';
    case 'HT':
      return 'LIVE HT';
    case 'BT':
      return 'LIVE BT';
    case 'P':
      return 'LIVE PEN';
    case 'FT':
    case 'AET':
    case 'PEN':
      return 'FT';
    default:
      return null;
  }
}

const LiveBadge: React.FC<LiveBadgeProps> = ({ status, elapsedMinute }) => {
  const label = getLabel(status, elapsedMinute);
  if (label === null) return null;

  const live = isInPlay(status);
  const completed = isCompleted(status);
  const dotColor = live ? '#ec407a' : '#78909c';
  const textColor = live ? '#ec407a' : '#78909c';

  return (
    <Box
      data-testid="live-badge"
      sx={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 0.75,
      }}
    >
      {(live || completed) && (
        <Box
          data-testid="live-dot"
          sx={{
            width: 8,
            height: 8,
            borderRadius: '50%',
            backgroundColor: dotColor,
            ...(live && {
              animation: `${pulse} 1.5s ease-in-out infinite`,
            }),
          }}
        />
      )}
      <Typography
        variant="caption"
        aria-live="polite"
        data-testid="live-label"
        sx={{
          color: textColor,
          fontWeight: 700,
          fontSize: '0.75rem',
          letterSpacing: '0.05em',
        }}
      >
        {label}
      </Typography>
    </Box>
  );
};

export default LiveBadge;
