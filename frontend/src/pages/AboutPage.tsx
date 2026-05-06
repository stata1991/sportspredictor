import React from 'react';
import { Box, Typography } from '@mui/material';

const AboutPage: React.FC = () => (
  <Box sx={{ maxWidth: 700, mx: 'auto', px: { xs: 2, sm: 3 }, py: 4 }}>
    <Typography
      variant="h4"
      sx={{
        textAlign: 'center',
        mb: 3,
        fontWeight: 700,
        color: '#ffe082',
        fontFamily: 'Orbitron, sans-serif',
      }}
    >
      About
    </Typography>

    <Typography
      variant="body1"
      sx={{
        color: '#b0bec5',
        fontFamily: 'Orbitron, Roboto, sans-serif',
        fontSize: '0.9rem',
        lineHeight: 1.8,
      }}
    >
      FantasyFuel.ai generates match predictions for the FIFA World Cup 2026
      using a Dixon-Coles statistical model calibrated on historical
      international results, combined with an AI reasoning layer powered by
      Anthropic's Claude. The system produces win/draw/loss probabilities,
      scoreline distributions, upset risk indices, and natural-language analysis
      for every fixture. Built for the 48-team World Cup kicking off June 11,
      2026 across the United States, Canada, and Mexico.
    </Typography>

    <Typography
      variant="body2"
      sx={{
        color: '#78909c',
        mt: 3,
        fontFamily: 'Orbitron, Roboto, sans-serif',
        fontSize: '0.8rem',
      }}
    >
      Entertainment only. Do not use for betting or gambling.
    </Typography>
  </Box>
);

export default AboutPage;
