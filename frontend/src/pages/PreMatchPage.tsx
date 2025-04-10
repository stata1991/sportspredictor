import React, { useState } from 'react';
import { Box, Typography, Button, Divider, Paper } from '@mui/material';
import SportsCricketIcon from '@mui/icons-material/SportsCricket';
import FlashOnIcon from '@mui/icons-material/FlashOn';
import CalendarTodayIcon from '@mui/icons-material/CalendarToday';
import WbSunnyIcon from '@mui/icons-material/WbSunny';
import homeBg from '../non-home.png';

const PreMatchPage: React.FC = () => {
  const [result, setResult] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);
  const date = new Date().toISOString().split('T')[0];
  const [matchNumber, setMatchNumber] = useState(0);


  const handlePrediction = async (endpoint: string) => {
    setLoading(true);
    setResult('🔄 Updating match context...');
    try {
      const updateRes = await fetch(`http://localhost:8000/update-match-context?date=${date}&match_number=${matchNumber}`, {
        method: 'POST',
      });
      if (!updateRes.ok) throw new Error(`Update context failed: ${updateRes.status}`);

      const response = await fetch(`http://localhost:8000${endpoint}?date=${date}&match_number=${matchNumber}`);
      if (!response.ok) throw new Error(`Prediction API failed: ${response.status}`);

      const data = await response.json();
      setResult(JSON.stringify(data, null, 2));
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      setResult('❌ Error: ' + message);
    } finally {
      setLoading(false);
    }
  };

  const predictionButtons = [
    {
      label: 'Predict Winner',
      icon: <SportsCricketIcon />,
      action: () => handlePrediction('/predict/winner'),
    },
    {
      label: 'Powerplay',
      icon: <FlashOnIcon />,
      action: () => handlePrediction('/predict/powerplay'),
    },
    {
      label: 'Total Score',
      icon: <CalendarTodayIcon />,
      action: () => handlePrediction('/predict/score'),
    },
    {
      label: 'Wickets',
      icon: <WbSunnyIcon />,
      action: () => handlePrediction('/predict/wickets'),
    },
  ];

  return (
    <Box
      sx={{
        backgroundImage: `url(${homeBg})`,
        backgroundSize: 'cover',
        backgroundPosition: 'center',
        backgroundRepeat: 'no-repeat',
        minHeight: '100vh',
        color: 'white',
        fontFamily: 'Orbitron, sans-serif',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        textAlign: 'center',
        paddingTop: '120px',
        paddingBottom: result ? '240px' : '160px',
        px: 2,
      }}
    >
     <Typography
  variant="h3"
  sx={{
    color: '#FFD700',
    fontWeight: 'bold',
    mb: 2,
    mt: 8,
    fontSize: { xs: '1.8rem', sm: '2.5rem', md: '3rem' },
    textAlign: 'center',
  }}
>
  Pre-Match Predictions
</Typography>
<Box sx={{ mt: 3 }}>
  <Typography variant="h6" sx={{ color: '#FFD700', mb: 1 }}>
    Select Match
  </Typography>
  <select
    value={matchNumber}
    onChange={(e) => setMatchNumber(Number(e.target.value))}
    style={{
      padding: '8px 16px',
      borderRadius: '8px',
      fontSize: '1rem',
      fontFamily: 'Orbitron, sans-serif',
    }}
  >
    <option value={0}>Match 1</option>
    <option value={1}>Match 2</option>
  </select>
</Box>


      <Box
        sx={{
          display: 'flex',
          flexWrap: 'wrap',
          justifyContent: 'center',
          gap: '2rem',
          mt: 4,
        }}
      >
        {predictionButtons.map((btn) => (
          <Button
            key={btn.label}
            variant="contained"
            onClick={btn.action}
            startIcon={btn.icon}
            sx={{
              background: 'linear-gradient(90deg, #FF6F61 0%, #FF3CAC 100%)',
              borderRadius: '30px',
              px: 4,
              py: 2,
              fontSize: '1rem',
              fontWeight: 'bold',
              fontFamily: 'Orbitron, sans-serif',
              color: 'white',
              boxShadow: '0 0 15px rgba(255, 111, 97, 0.6)',
              '&:hover': {
                background: 'linear-gradient(90deg, #FF3CAC 0%, #FF6F61 100%)',
              },
            }}
          >
            {btn.label.toUpperCase()}
          </Button>
        ))}
      </Box>

      {result && (
        <Box
          sx={{
            mt: 6,
            display: 'flex',
            justifyContent: 'center',
            width: '100%',
          }}
        >
          <Paper
            elevation={6}
            sx={{
              px: 4,
              py: 3,
              maxWidth: '700px',
              background: 'linear-gradient(145deg, #0f2027, #203a43, #2c5364)',
              border: '2px solid #FFD700',
              borderRadius: '20px',
              boxShadow: '0 0 20px #FFD70088',
              color: '#fff',
              fontFamily: 'Orbitron, monospace',
              '&:hover': {
                boxShadow: '0 0 30px #FF3CAC99',
                borderColor: '#FF3CAC',
              },
            }}
          >
            <Typography
              variant="h6"
              sx={{
                color: '#FFD700',
                fontWeight: 'bold',
                fontSize: '1.3rem',
                mb: 2,
                textAlign: 'center',
              }}
            >
              🎯 Prediction Result
            </Typography>
            <Box
              component="pre"
              sx={{
                whiteSpace: 'pre-wrap',
                fontSize: '1rem',
                textAlign: 'left',
                color: '#00E5FF',
              }}
            >
              {result}
            </Box>
          </Paper>
        </Box>
      )}

      {/* Disclaimer */}
      <Box
        sx={{
          position: 'fixed',
          bottom: 0,
          width: '100%',
          textAlign: 'center',
          p: 2,
          backgroundColor: 'rgba(0,0,0,0.6)',
          zIndex: 10,
        }}
      >
        <Divider sx={{ borderColor: 'white', mb: 1 }} />
        <Typography variant="body2" color="white" fontFamily="Orbitron, sans-serif">
          ⚠️ FantasyFuel.ai is intended for entertainment and informational purposes only.
          Predictions should not be used for betting or gambling.
        </Typography>
      </Box>
    </Box>
  );
};

export default PreMatchPage;
