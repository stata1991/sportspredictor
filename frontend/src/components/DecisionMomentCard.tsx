import React from 'react';
import { Box, Typography } from '@mui/material';

type DecisionMoment = {
  moment_type: string;
  headline: string;
  detail: string;
  urgency: 'high' | 'medium' | 'low';
};

type Props = {
  moment: DecisionMoment;
};

const URGENCY_COLORS: Record<string, string> = {
  high: '#ef4444',
  medium: '#f59e0b',
  low: '#3b82f6',
};

const DecisionMomentCard: React.FC<Props> = ({ moment }) => {
  const color = URGENCY_COLORS[moment.urgency] || URGENCY_COLORS.low;

  return (
    <Box
      sx={{
        p: 1.5,
        borderRadius: 2,
        border: `2px solid ${color}`,
        backgroundColor: `${color}11`,
        mb: 1.5,
      }}
    >
      <Typography sx={{ fontWeight: 700, fontSize: 14, color }}>
        {moment.headline}
      </Typography>
      <Typography sx={{ fontSize: 12, color: '#94a3b8', mt: 0.25 }}>
        {moment.detail}
      </Typography>
    </Box>
  );
};

export default DecisionMomentCard;
