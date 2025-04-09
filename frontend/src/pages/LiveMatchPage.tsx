import React, { useState/*, useEffect*/ } from 'react';
import {
  Box,
  Typography,
  Button,
  Stack,
  Paper,
  Divider,
} from '@mui/material';
import LiveTvIcon from '@mui/icons-material/LiveTv';
import FlashOnIcon from '@mui/icons-material/FlashOn';
import ScoreboardIcon from '@mui/icons-material/Scoreboard';
import WbSunnyIcon from '@mui/icons-material/WbSunny';
// import { loadStripe } from '@stripe/stripe-js';
import { useAuth } from '../context/AuthContext';
import { useNavigate } from 'react-router-dom';
import homeBg from '../non-home.png';

// const stripePromise = loadStripe('pk_test_...'); // Replace with actual key

const LiveMatchPage: React.FC = () => {
  const { currentUser, loading: authLoading } = useAuth();
  // const [isSubscribed, setIsSubscribed] = useState(false);
  const [result, setResult] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(false);
  const navigate = useNavigate();
  const date = new Date().toISOString().split('T')[0];
  const [matchNumber, setMatchNumber] = useState(0);


  // useEffect(() => {
  //   if (!currentUser) return;
  //   const checkSubscription = async () => {
  //     try {
  //       const response = await fetch(`http://localhost:5000/check-subscription/${currentUser.uid}`);
  //       const data = await response.json();
  //       setIsSubscribed(data.isSubscribed);
  //     } catch (error) {
  //       console.error('Error checking subscription:', error);
  //       setIsSubscribed(false);
  //     }
  //   };
  //   checkSubscription();
  // }, [currentUser]);

  const handleLivePrediction = async (endpoint: string) => {
    setResult('🔄 Updating match context...');
    setLoading(true);
    try {
      await fetch(`http://127.0.0.1:8000/update-match-context?date=${date}&match_number=${matchNumber}`, { method: 'POST' });
      await fetch(`http://127.0.0.1:8000/live-match-state?date=${date}&match_number=${matchNumber}`);
      const predictionRes = await fetch(`http://127.0.0.1:8000${endpoint}?date=${date}&match_number=${matchNumber}`);
      const data = await predictionRes.json();
      setResult(JSON.stringify(data, null, 2));
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      setResult('❌ Error: ' + message);
    } finally {
      setLoading(false);
    }
  };

  // const handleSubscribe = async () => {
  //   if (!currentUser) return navigate('/auth');
  //   setLoading(true);
  //   try {
  //     const response = await fetch('http://localhost:5000/create-checkout-session', {
  //       method: 'POST',
  //       headers: { 'Content-Type': 'application/json' },
  //       body: JSON.stringify({ userId: currentUser.uid }),
  //     });
  //     const { url } = await response.json();
  //     window.location.href = url;
  //   } catch (error) {
  //     console.error('Checkout session error:', error);
  //     setLoading(false);
  //   }
  // };

  if (authLoading) {
    return <Typography color="white">Loading...</Typography>;
  }

  return (
    <Box
      sx={{
        backgroundImage: `url(${homeBg})`,
        backgroundSize: 'cover',
        backgroundPosition: 'center',
        minHeight: '100vh',
        color: 'white',
        fontFamily: 'Orbitron, sans-serif',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'flex-start',
        alignItems: 'center',
        textAlign: 'center',
        pt: 10,
        pb: 12,
        px: 2,
      }}
    >
      <Typography
        variant="h3"
        sx={{
          color: '#FFD700',
          fontWeight: 'bold',
          mb: 3,
        }}
      >
        Live Match Predictions
      </Typography>

      {currentUser ? (
        // isSubscribed ? (
          <>
          <Box sx={{ textAlign: 'center', mb: 3 }}>
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

            <Stack
              spacing={2}
              direction="row"
              sx={{ flexWrap: 'wrap', justifyContent: 'center', mb: 4 }}
            >
              <Button
                variant="contained"
                onClick={() => handleLivePrediction('/predict/winner-live')}
                startIcon={<LiveTvIcon />}
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
                LIVE WINNER
              </Button>
              <Button
                variant="contained"
                onClick={() => handleLivePrediction('/predict/powerplay-live')}
                startIcon={<FlashOnIcon />}
                sx={{ ...buttonStyle }}
              >
                LIVE POWERPLAY
              </Button>
              <Button
                variant="contained"
                onClick={() => handleLivePrediction('/predict/score-live')}
                startIcon={<ScoreboardIcon />}
                sx={{ ...buttonStyle }}
              >
                LIVE SCORE
              </Button>
              <Button
                variant="contained"
                onClick={() => handleLivePrediction('/predict/wickets-live')}
                startIcon={<WbSunnyIcon />}
                sx={{ ...buttonStyle }}
              >
                LIVE WICKETS
              </Button>
            </Stack>

            {loading && (
              <Typography align="center" sx={{ color: '#ffca28' }}>
                ⏳ Processing...
              </Typography>
            )}

            {result && (
              <Paper
                elevation={5}
                sx={{
                  mt: 4,
                  px: 4,
                  py: 3,
                  background: 'linear-gradient(145deg, #0f2027, #203a43, #2c5364)',
                  border: '2px solid #FFD700',
                  borderRadius: '20px',
                  boxShadow: '0 0 20px #FFD70088',
                  color: '#fff',
                  maxWidth: '85%',
                  overflowX: 'auto',
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
                    fontSize: '1.2rem',
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
                    fontSize: '0.95rem',
                    textAlign: 'left',
                    color: '#00E5FF',
                  }}
                >
                  {result}
                </Box>
              </Paper>
            )}
          </>
        // ) : (
        //   <Box textAlign="center" sx={{ mt: 4 }}>
        //     <Typography variant="h6" gutterBottom>
        //       Subscribe to Access Live Match Predictions
        //     </Typography>
        //     <Button
        //       variant="contained"
        //       onClick={handleSubscribe}
        //       disabled={loading}
        //       sx={{
        //         background: 'linear-gradient(90deg, #FF6F61 0%, #FF3CAC 100%)',
        //         borderRadius: '30px',
        //         px: 4,
        //         py: 2,
        //         fontSize: '1rem',
        //         fontWeight: 'bold',
        //         fontFamily: 'Orbitron, sans-serif',
        //         color: 'white',
        //         boxShadow: '0 0 15px rgba(255, 111, 97, 0.6)',
        //         '&:hover': {
        //           background: 'linear-gradient(90deg, #FF3CAC 0%, #FF6F61 100%)',
        //         },
        //       }}
        //     >
        //       {loading ? 'Processing...' : 'Subscribe Now ($4.99/month or ₹199)'}
        //     </Button>
        //   </Box>
        // )
      ) : (
        <Typography variant="h6" mt={6}>🔒 Please sign in to access live match predictions.</Typography>
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

const buttonStyle = {
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
};

export default LiveMatchPage;