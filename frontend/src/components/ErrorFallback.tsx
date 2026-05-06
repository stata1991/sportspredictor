import React from 'react';
import { Box, Typography, Button } from '@mui/material';

const ErrorFallback: React.FC = () => (
  <Box
    sx={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      minHeight: '60vh',
      textAlign: 'center',
      px: 2,
    }}
  >
    <Typography
      variant="h5"
      sx={{ color: '#ef5350', mb: 1, fontFamily: 'Orbitron, sans-serif' }}
    >
      Something went wrong
    </Typography>
    <Typography variant="body2" sx={{ color: '#b0bec5', mb: 3 }}>
      An unexpected error occurred. Please refresh the page.
    </Typography>
    <Button
      variant="contained"
      onClick={() => window.location.reload()}
    >
      Refresh
    </Button>
  </Box>
);

export default ErrorFallback;
