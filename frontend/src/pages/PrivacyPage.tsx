import React from 'react';
import { Box, Typography } from '@mui/material';

const PrivacyPage: React.FC = () => (
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
      Privacy Policy
    </Typography>

    <Box
      sx={{
        color: '#b0bec5',
        fontFamily: 'Orbitron, Roboto, sans-serif',
        fontSize: '0.9rem',
        lineHeight: 1.8,
        '& h6': { color: '#fff', mt: 3, mb: 1 },
      }}
    >
      <Typography variant="h6">Data Collection</Typography>
      <Typography variant="body2" sx={{ mb: 2 }}>
        FantasyFuel does not collect personal data server-side beyond standard
        HTTP request logs (IP address, user-agent, timestamps). These logs are
        retained for operational monitoring and deleted after 30 days.
      </Typography>

      <Typography variant="h6">Cookies</Typography>
      <Typography variant="body2" sx={{ mb: 2 }}>
        This site does not set cookies. If analytics or authentication features
        are enabled in the future, this section will be updated accordingly.
      </Typography>

      <Typography variant="h6">Third-Party Services</Typography>
      <Typography variant="body2" sx={{ mb: 2 }}>
        Prediction data is sourced from API-Football (api-sports.io). Agent
        reasoning is generated using Anthropic&apos;s Claude API. Error monitoring
        is provided by Sentry (sentry.io), which collects stack traces,
        browser user-agent strings, and error metadata for debugging purposes;
        no personally identifiable information (PII) is collected. These
        services process requests on our behalf and are subject to their own
        privacy policies.
      </Typography>

      <Typography variant="h6">Contact</Typography>
      <Typography variant="body2">
        For privacy-related questions, reach us at privacy@fantasyfuel.ai.
      </Typography>
    </Box>
  </Box>
);

export default PrivacyPage;
