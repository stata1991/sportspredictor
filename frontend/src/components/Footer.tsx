import React from 'react';
import { Box, Typography } from '@mui/material';
import { Link } from 'react-router-dom';

const Footer: React.FC = () => (
  <Box
    component="footer"
    sx={{
      textAlign: 'center',
      py: 2,
      px: 2,
      mt: 4,
      borderTop: '1px solid rgba(255, 255, 255, 0.08)',
      backgroundColor: 'rgba(13, 13, 13, 0.6)',
    }}
  >
    <Box sx={{ display: 'flex', justifyContent: 'center', gap: 3, mb: 1 }}>
      <Typography
        component={Link}
        to="/privacy"
        sx={{
          color: '#b0bec5',
          fontSize: '0.75rem',
          textDecoration: 'none',
          '&:hover': { color: '#fff' },
        }}
      >
        Privacy
      </Typography>
      <Typography
        component={Link}
        to="/about"
        sx={{
          color: '#b0bec5',
          fontSize: '0.75rem',
          textDecoration: 'none',
          '&:hover': { color: '#fff' },
        }}
      >
        About
      </Typography>
    </Box>
    <Typography sx={{ color: '#78909c', fontSize: '0.7rem' }}>
      &copy; FantasyFuel.ai 2026
    </Typography>
  </Box>
);

export default Footer;
