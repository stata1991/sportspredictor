import React, { useEffect } from 'react';
import { Box, Typography, Button } from '@mui/material';
import { useNavigate } from 'react-router-dom';

const NotFoundPage: React.FC = () => {
  const navigate = useNavigate();

  useEffect(() => {
    document.title = '404 — FantasyFuel';
  }, []);

  return (
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
        variant="h2"
        sx={{
          fontFamily: 'Orbitron, sans-serif',
          fontWeight: 700,
          color: '#ff6f00',
          mb: 2,
        }}
      >
        404
      </Typography>
      <Typography variant="h5" sx={{ color: '#fff', mb: 1, fontWeight: 600 }}>
        Page not found
      </Typography>
      <Typography
        variant="body1"
        sx={{ color: 'text.secondary', mb: 4, maxWidth: 400 }}
      >
        The page you&apos;re looking for doesn&apos;t exist or has been moved.
      </Typography>
      <Button variant="contained" onClick={() => navigate('/')}>
        Back to Home
      </Button>
    </Box>
  );
};

export default NotFoundPage;
