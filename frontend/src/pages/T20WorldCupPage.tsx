import React, { useEffect, useMemo, useState } from 'react';
import { Box, Typography, Button, Paper, Divider, CircularProgress, Tabs, Tab } from '@mui/material';
import SportsCricketIcon from '@mui/icons-material/SportsCricket';
import FlashOnIcon from '@mui/icons-material/FlashOn';
import CalendarTodayIcon from '@mui/icons-material/CalendarToday';
import WbSunnyIcon from '@mui/icons-material/WbSunny';
import { useAuth } from '../context/AuthContext';
import api from '../api';
import homeBg from '../non-home.png';

type MatchListItem = {
  match_number: number;
  match_id?: number;
  teams: string[];
  venue: string;
  start_time: string;
};

type PreMatchResponse = {
  prediction_stage?: string;
  data_quality?: string;
  fallback_level?: string;
  confidence?: number;
  uncertainty?: string;
  match?: { team1: string; team2: string; venue: string; date: string };
  winner?: { team?: string; probability?: number; probabilities?: Record<string, number> };
  total_score?: { low: number; mid: number; high: number };
  wickets?: { low: number; mid: number; high: number };
  powerplay?: { low: number; mid: number; high: number };
  error?: string;
  message?: string;
};

type LiveResponse = {
  prediction_stage?: string;
  data_quality?: string;
  fallback_level?: string;
  confidence?: number;
  uncertainty?: string;
  match?: { team1: string; team2: string; venue: string; date: string };
  winner?: { team?: string; probability?: number; probabilities?: Record<string, number> | null };
  live?: { batting_team?: string; runs?: number; wickets?: number; overs?: number; current_run_rate?: number };
  projected_total?: number | null;
  total_score?: { low: number; mid: number; high: number };
  chase?: {
    will_reach?: boolean;
    finish_at?: string | null;
    short_by?: number | null;
    target?: number | null;
    required_run_rate?: number | null;
  } | null;
  wickets?: { low: number; mid: number; high: number } | null;
  powerplay?: { low: number; mid: number; high: number } | null;
  error?: string;
  message?: string;
};

type PredictionType = 'winner' | 'score' | 'wickets' | 'powerplay' | null;

const SERIES_ID = 11253;

const T20WorldCupPage: React.FC = () => {
  const { loading: authLoading } = useAuth();
  const [loading, setLoading] = useState(false);
  const [matchNumber, setMatchNumber] = useState(0);
  const [dateStr, setDateStr] = useState(new Date().toISOString().split('T')[0]);
  const [matches, setMatches] = useState<MatchListItem[]>([]);
  const [message, setMessage] = useState('');
  const [activeTab, setActiveTab] = useState<'prematch' | 'live'>('prematch');

  const [preMatchResult, setPreMatchResult] = useState<PreMatchResponse | null>(null);
  const [preMatchType, setPreMatchType] = useState<PredictionType>(null);

  const [liveResult, setLiveResult] = useState<LiveResponse | null>(null);
  const [liveType, setLiveType] = useState<PredictionType>(null);

  const palette = useMemo(
    () => ({
      bg: '#0d1117',
      card: '#111827',
      border: '#334155',
      primary: '#e2e8f0',
      muted: '#94a3b8',
      accent: '#22d3ee',
      highlight: '#f59e0b',
    }),
    []
  );

  useEffect(() => {
    const fetchMatches = async () => {
      try {
        const res = await api.get('/t20wc/matches', { params: { date: dateStr } });
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
  }, [dateStr, matchNumber]);

  const handlePreMatchPrediction = async (type: PredictionType) => {
    if (!type) return;
    setLoading(true);
    setPreMatchType(type);
    setMessage('');
    try {
      const res = await api.get('/predict/pre-match', {
        params: { series_id: SERIES_ID, date: dateStr, match_number: matchNumber },
      });
      const data: PreMatchResponse = res.data;
      if (data.error) {
        setMessage(data.error);
        setPreMatchResult(null);
      } else {
        setPreMatchResult(data);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setMessage(msg);
      setPreMatchResult(null);
    } finally {
      setLoading(false);
    }
  };

  const handleLivePrediction = async (type: PredictionType) => {
    if (!type) return;
    setLoading(true);
    setLiveType(type);
    setMessage('');
    try {
      const res = await api.get('/predict/live', {
        params: { series_id: SERIES_ID, date: dateStr, match_number: matchNumber },
      });
      const data: LiveResponse = res.data;
      if (data.error) {
        setMessage(data.error);
        setLiveResult(null);
      } else {
        setLiveResult(data);
        if (data.message) {
          setMessage(data.message);
        }
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setMessage(msg);
      setLiveResult(null);
    } finally {
      setLoading(false);
    }
  };

  const predictionButtons = [
    { label: 'Predict Winner', icon: <SportsCricketIcon />, value: 'winner' as PredictionType },
    { label: 'Total Score', icon: <CalendarTodayIcon />, value: 'score' as PredictionType },
    { label: 'Wickets', icon: <WbSunnyIcon />, value: 'wickets' as PredictionType },
    { label: 'Powerplay', icon: <FlashOnIcon />, value: 'powerplay' as PredictionType },
  ];

  if (authLoading) return <Typography color="white">Loading...</Typography>;

  return (
    <Box
      sx={{
        backgroundImage: `linear-gradient(rgba(13,17,23,0.92), rgba(13,17,23,0.92)), url(${homeBg})`,
        backgroundSize: 'cover',
        backgroundPosition: 'center',
        minHeight: '100vh',
        color: palette.primary,
        fontFamily: 'Orbitron, sans-serif',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        pt: 9,
        pb: 10,
        px: 2,
      }}
    >
      <Typography variant="h4" sx={{ fontWeight: 700, mb: 1, textAlign: 'center' }}>
        T20 World Cup Predictions
      </Typography>
      <Typography sx={{ color: palette.muted, mb: 4, textAlign: 'center' }}>
        Pick a date to load matches, then select pre-match or live predictions.
      </Typography>

      <Paper
        elevation={0}
        sx={{
          width: '100%',
          maxWidth: 860,
          p: { xs: 2, sm: 3 },
          borderRadius: 3,
          backgroundColor: palette.card,
          border: `1px solid ${palette.border}`,
        }}
      >
        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2, justifyContent: 'space-between', alignItems: 'center' }}>
          <Box>
            <Typography sx={{ color: palette.muted, mb: 0.5 }}>Date</Typography>
            <input
              type="date"
              value={dateStr}
              onChange={(e) => setDateStr(e.target.value)}
              style={{
                background: '#0f172a',
                color: '#e2e8f0',
                border: `1px solid ${palette.border}`,
                borderRadius: 8,
                padding: '8px 10px',
              }}
            />
          </Box>
          <Box>
            <Typography sx={{ color: palette.muted, mb: 0.5 }}>Match</Typography>
            <select
              value={matchNumber}
              onChange={(e) => setMatchNumber(Number(e.target.value))}
              style={{
                background: '#0f172a',
                color: '#e2e8f0',
                border: `1px solid ${palette.border}`,
                borderRadius: 8,
                padding: '8px 10px',
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
        </Box>

        <Tabs
          value={activeTab}
          onChange={(_, value) => setActiveTab(value)}
          textColor="inherit"
          indicatorColor="secondary"
          sx={{ mt: 3, borderBottom: `1px solid ${palette.border}` }}
        >
          <Tab label="Pre-match" value="prematch" sx={{ color: palette.primary }} />
          <Tab label="Live match" value="live" sx={{ color: palette.primary }} />
        </Tabs>

        {activeTab === 'prematch' && (
          <Box sx={{ mt: 2 }}>
            <Typography sx={{ color: palette.muted, fontSize: 12, mb: 1 }}>Pre-match predictions</Typography>
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1.5 }}>
              {predictionButtons.map((btn) => (
                <Button
                  key={btn.label}
                  variant="outlined"
                  onClick={() => handlePreMatchPrediction(btn.value)}
                  startIcon={btn.icon}
                  sx={{
                    borderColor: palette.border,
                    color: palette.primary,
                    textTransform: 'none',
                    fontWeight: 600,
                  }}
                >
                  {btn.label}
                </Button>
              ))}
            </Box>

            {loading && (
              <Box sx={{ mt: 2 }}>
                <CircularProgress size={18} sx={{ color: palette.primary }} />
              </Box>
            )}

            {preMatchResult && !preMatchResult.error && (
              <Paper sx={{ mt: 2, p: 2, backgroundColor: '#0f172a', border: `1px solid ${palette.border}` }}>
                <Typography sx={{ color: palette.muted, fontSize: 12 }}>
                  Pre-match output {preMatchType ? `- ${preMatchType}` : ''}
                </Typography>
                <Box sx={{ color: palette.primary, fontSize: 14, mt: 1 }}>
                  {preMatchResult.message && (
                    <Typography>{preMatchResult.message}</Typography>
                  )}
                  {preMatchType === 'winner' && !preMatchResult.message && (
                    <Typography>
                      Winner: {preMatchResult.winner?.team} ({preMatchResult.winner?.probability})
                    </Typography>
                  )}
                  {preMatchType === 'score' && preMatchResult.total_score && (
                    <Typography>
                      Total score range: {preMatchResult.total_score.low}-{preMatchResult.total_score.mid}-
                      {preMatchResult.total_score.high}
                    </Typography>
                  )}
                  {preMatchType === 'wickets' && preMatchResult.wickets && (
                    <Typography>
                      Wickets range: {preMatchResult.wickets.low}-{preMatchResult.wickets.mid}-{preMatchResult.wickets.high}
                    </Typography>
                  )}
                  {preMatchType === 'powerplay' && preMatchResult.powerplay && (
                    <Typography>
                      Powerplay range: {preMatchResult.powerplay.low}-{preMatchResult.powerplay.mid}-
                      {preMatchResult.powerplay.high}
                    </Typography>
                  )}
                </Box>
              </Paper>
            )}
          </Box>
        )}

        {activeTab === 'live' && (
          <Box sx={{ mt: 2 }}>
            <Typography sx={{ color: palette.muted, fontSize: 12, mb: 1 }}>Live predictions</Typography>
            <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1.5 }}>
              {predictionButtons.map((btn) => (
                <Button
                  key={btn.label}
                  variant="outlined"
                  onClick={() => handleLivePrediction(btn.value)}
                  startIcon={btn.icon}
                  sx={{
                    borderColor: palette.border,
                    color: palette.primary,
                    textTransform: 'none',
                    fontWeight: 600,
                  }}
                >
                  {btn.label}
                </Button>
              ))}
            </Box>

            {loading && (
              <Box sx={{ mt: 2 }}>
                <CircularProgress size={18} sx={{ color: palette.primary }} />
              </Box>
            )}

            {liveResult && !liveResult.error && (
              <Box sx={{ display: 'grid', gap: 2, mt: 2 }}>
                <Divider sx={{ borderColor: palette.border }} />

                {liveType === 'winner' && (
                  <Paper sx={{ p: 2, backgroundColor: '#0f172a', border: `1px solid ${palette.border}` }}>
                    <Typography sx={{ color: palette.muted, fontSize: 12 }}>Winner</Typography>
                    <Typography sx={{ fontWeight: 700, fontSize: 20 }}>
                      {liveResult.winner?.team || 'Prediction pending'}
                    </Typography>
                  </Paper>
                )}

                {liveType === 'score' && (
                  <Paper sx={{ p: 2, backgroundColor: '#0f172a', border: `1px solid ${palette.border}` }}>
                    <Typography sx={{ color: palette.muted, fontSize: 12 }}>Total score</Typography>
                    <Typography sx={{ fontWeight: 700, fontSize: 20 }}>
                      {liveResult.projected_total || 'Prediction pending'}
                    </Typography>
                    {liveResult.chase && (
                      <Box sx={{ mt: 1 }}>
                        <Typography sx={{ color: palette.muted, fontSize: 12 }}>Chase outcome</Typography>
                        {liveResult.chase.will_reach ? (
                          <Typography sx={{ color: palette.highlight }}>
                            Likely to reach target by {liveResult.chase.finish_at} overs
                          </Typography>
                        ) : (
                          <Typography sx={{ color: palette.highlight }}>
                            Likely short by {liveResult.chase.short_by} runs
                          </Typography>
                        )}
                      </Box>
                    )}
                  </Paper>
                )}

                {liveType === 'wickets' && (
                  <Paper sx={{ p: 2, backgroundColor: '#0f172a', border: `1px solid ${palette.border}` }}>
                    <Typography sx={{ color: palette.muted, fontSize: 12 }}>Wickets</Typography>
                    <Typography sx={{ fontWeight: 700, fontSize: 20 }}>
                      {liveResult.wickets
                        ? `${liveResult.wickets.low}-${liveResult.wickets.mid}-${liveResult.wickets.high}`
                        : 'Prediction pending'}
                    </Typography>
                  </Paper>
                )}

                {liveType === 'powerplay' && (
                  <Paper sx={{ p: 2, backgroundColor: '#0f172a', border: `1px solid ${palette.border}` }}>
                    <Typography sx={{ color: palette.muted, fontSize: 12 }}>Powerplay</Typography>
                    <Typography sx={{ fontWeight: 700, fontSize: 20 }}>
                      {liveResult.powerplay
                        ? `${liveResult.powerplay.low}-${liveResult.powerplay.mid}-${liveResult.powerplay.high}`
                        : 'Prediction pending'}
                    </Typography>
                  </Paper>
                )}
              </Box>
            )}
          </Box>
        )}

        {message && (
          <Typography sx={{ color: palette.muted, mt: 2 }}>
            {message}
          </Typography>
        )}
      </Paper>

      <Box
        sx={{
          position: 'fixed',
          bottom: 0,
          width: '100%',
          textAlign: 'center',
          p: { xs: 1, sm: 1.5 },
          backgroundColor: 'rgba(2,6,23,0.9)',
          borderTop: `1px solid ${palette.border}`,
        }}
      >
        <Typography variant="body2" color={palette.muted}>
          Entertainment only. Do not use for betting or gambling.
        </Typography>
      </Box>
    </Box>
  );
};

export default T20WorldCupPage;
