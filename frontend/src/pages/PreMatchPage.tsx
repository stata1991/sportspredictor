import React, { useEffect, useState } from 'react';
import { Box, Typography, Button, Divider, Paper } from '@mui/material';
import SportsCricketIcon from '@mui/icons-material/SportsCricket';
import FlashOnIcon from '@mui/icons-material/FlashOn';
import CalendarTodayIcon from '@mui/icons-material/CalendarToday';
import WbSunnyIcon from '@mui/icons-material/WbSunny';
import api from '../api';
import homeBg from '../non-home.png';

const SERIES_ID = 9237;

type PredictionType = 'winner' | 'score' | 'wickets' | 'powerplay';

type MatchListItem = {
  match_number: number;
  teams: string[];
  venue: string;
  start_time: string;
};

type PreMatchResponse = {
  batting_context?: string;
  match?: { team1: string; team2: string; venue: string; date: string };
  winner?: { probabilities: Record<string, number> };
  winner_reasoning?: string[];
  total_score?: { low: number; high: number };
  wickets?: { low: number; high: number };
  powerplay?: { low: number; high: number };
  message?: string;
  error?: string;
};

const PreMatchPage: React.FC = () => {
  const [result, setResult] = useState<PreMatchResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [date, setDate] = useState(new Date().toISOString().split('T')[0]);
  const [matchNumber, setMatchNumber] = useState(0);
  const [activeType, setActiveType] = useState<PredictionType>('winner');
  const [matches, setMatches] = useState<MatchListItem[]>([]);
  const [message, setMessage] = useState('');

  useEffect(() => {
    const fetchMatches = async () => {
      try {
        const res = await api.get('/matches', { params: { date } });
        const items = Array.isArray(res.data.matches) ? res.data.matches : [];
        setMatches(items);
        setMessage(items.length === 0 ? 'No matches found for this date.' : '');
        if (items.length > 0 && matchNumber >= items.length) {
          setMatchNumber(0);
        }
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        setMessage(msg);
        setMatches([]);
      }
    };

    fetchMatches();
  }, [date, matchNumber]);

  const handlePrediction = async (type: PredictionType) => {
    setLoading(true);
    setActiveType(type);
    setMessage('');
    try {
      const res = await api.get('/predict/pre-match', {
        params: { series_id: SERIES_ID, date, match_number: matchNumber },
      });
      const data: PreMatchResponse = res.data;
      if (data.error) {
        setMessage(data.error);
        setResult(null);
      } else {
        setResult(data);
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : String(err);
      setResult(null);
      setMessage(message);
    } finally {
      setLoading(false);
    }
  };

  const predictionButtons = [
    {
      label: 'Predict Winner',
      icon: <SportsCricketIcon />,
      action: () => handlePrediction('winner'),
    },
    {
      label: 'Powerplay',
      icon: <FlashOnIcon />,
      action: () => handlePrediction('powerplay'),
    },
    {
      label: 'Total Score',
      icon: <CalendarTodayIcon />,
      action: () => handlePrediction('score'),
    },
    {
      label: 'Wickets',
      icon: <WbSunnyIcon />,
      action: () => handlePrediction('wickets'),
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

      <Box sx={{ mt: 3, display: 'flex', flexDirection: 'column', gap: 2, alignItems: 'center' }}>
        <Box>
          <Typography variant="h6" sx={{ color: '#FFD700', mb: 1 }}>
            Select Date
          </Typography>
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            style={{
              padding: '8px 16px',
              borderRadius: '8px',
              fontSize: '1rem',
              fontFamily: 'Orbitron, sans-serif',
            }}
          />
        </Box>
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
          disabled={matches.length === 0}
        >
          {matches.length === 0 && <option value={0}>No matches</option>}
          {matches.map((match) => (
            <option key={match.match_number} value={match.match_number}>
              {match.teams.join(' vs ')}
            </option>
          ))}
        </select>
      </Box>

      <Box
        sx={{
          display: 'flex',
          flexWrap: 'wrap',
          justifyContent: 'center',
          gap: { xs: '1rem', sm: '2rem' },
          mt: 4,
        }}
      >
        {predictionButtons.map((btn) => (
          <Button
            key={btn.label}
            variant="contained"
            onClick={btn.action}
            disabled={loading}
            startIcon={btn.icon}
            sx={{
              background: 'linear-gradient(90deg, #FF6F61 0%, #FF3CAC 100%)',
              borderRadius: '30px',
              px: 4,
              py: 2,
              minWidth: { xs: '120px', sm: '150px' },
              fontSize: { xs: '0.8rem', sm: '1rem' },
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

      {result && !result.error && (
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
              px: { xs: 2, sm: 4 },
              py: { xs: 2, sm: 3 },
              maxWidth: { xs: '90%', sm: '700px' },
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
              🎯 Prediction Output - {activeType}
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
              {result.batting_context && activeType !== 'winner' && !result.message && (
                <Typography sx={{ color: '#94a3b8', fontSize: '0.85rem', mb: 1 }}>
                  {result.batting_context}
                </Typography>
              )}
              {result.message && (
                <Typography>{result.message}</Typography>
              )}
              {activeType === 'winner' && !result.message && (
                <>
                  {result.winner?.probabilities
                    ? Object.entries(result.winner.probabilities)
                        .sort((a, b) => b[1] - a[1])
                        .map(([team, p]) => `${team} ${Math.round(p * 100)}%`)
                        .join(' \u00B7 ')
                    : 'Winner prediction pending.'}
                  {result.winner_reasoning && result.winner_reasoning.length > 0 && (
                    <Box sx={{ mt: 1.5 }}>
                      <Typography sx={{ color: '#94a3b8', fontSize: '0.75rem', mb: 0.5 }}>
                        Based on:
                      </Typography>
                      {result.winner_reasoning.map((r, i) => (
                        <Typography key={i} sx={{ color: '#94a3b8', fontSize: '0.75rem', pl: 1 }}>
                          &bull; {r}
                        </Typography>
                      ))}
                    </Box>
                  )}
                </>
              )}
              {activeType === 'score' && (
                <>
                  {result.total_score
                    ? `Expected: ${result.total_score.low} – ${result.total_score.high} runs`
                    : 'Total score prediction pending.'}
                </>
              )}
              {activeType === 'wickets' && (
                <>
                  {result.wickets
                    ? `Expected: ${result.wickets.low} – ${result.wickets.high} wickets`
                    : 'Wickets prediction pending.'}
                </>
              )}
              {activeType === 'powerplay' && (
                <>
                  {result.powerplay
                    ? `Expected: ${result.powerplay.low} – ${result.powerplay.high} runs`
                    : 'Powerplay prediction pending.'}
                </>
              )}
            </Box>
          </Paper>
        </Box>
      )}

      {message && (
        <Typography sx={{ color: '#FFD700', mt: 3 }}>
          {message}
        </Typography>
      )}

      <Box
        sx={{
          position: 'fixed',
          bottom: 0,
          width: '100%',
          textAlign: 'center',
          p: { xs: 1, sm: 2 },
          backgroundColor: 'rgba(0,0,0,0.6)',
          zIndex: 10,
        }}
      >
        <Divider sx={{ borderColor: 'white', mb: 1 }} />
        <Typography variant="body2" color="white" fontFamily="Orbitron, sans-serif">
          ⚠️ FantasyFuel.ai is intended for entertainment and informational purposes only.
          Decisions should not be used for betting or gambling.
        </Typography>
      </Box>
    </Box>
  );
};

export default PreMatchPage;
