import React from 'react';
import { Box, Typography } from '@mui/material';
import { colors } from '../colors';

const STATUS_VERBS: Record<string, string> = {
  PST: 'postponed',
  CANC: 'cancelled',
  ABD: 'abandoned',
  AWD: 'awarded',
  WO: 'declared a walkover',
  SUSP: 'suspended',
  INT: 'interrupted',
};

interface MatchUnavailableSectionProps {
  status?: string;
}

const MatchUnavailableSection: React.FC<MatchUnavailableSectionProps> = ({
  status,
}) => {
  const verb = status ? STATUS_VERBS[status] : undefined;
  const message = verb
    ? `This match has been ${verb}.`
    : 'This match cannot be predicted right now.';

  return (
    <Box data-testid="match-unavailable" sx={{ textAlign: 'center', mt: 6 }}>
      <Typography
        variant="h5"
        sx={{ mb: 1, color: colors.textPrimary, fontWeight: 700 }}
      >
        Match Unavailable
      </Typography>
      <Typography variant="body2" sx={{ color: colors.labelText }}>
        {message}
      </Typography>
      <Typography variant="body2" sx={{ color: colors.labelText, mt: 1 }}>
        Predictions are not available for this fixture.
      </Typography>
    </Box>
  );
};

export default MatchUnavailableSection;
