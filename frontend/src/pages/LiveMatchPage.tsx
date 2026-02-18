import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Box, Typography, Button, Paper, Divider, CircularProgress } from '@mui/material';
import SportsCricketIcon from '@mui/icons-material/SportsCricket';
import FlashOnIcon from '@mui/icons-material/FlashOn';
import CalendarTodayIcon from '@mui/icons-material/CalendarToday';
import WbSunnyIcon from '@mui/icons-material/WbSunny';
import api from '../api';
import ConfidenceBadge from '../components/ConfidenceBadge';
import DecisionMomentCard from '../components/DecisionMomentCard';
import homeBg from '../non-home.png';

type MatchListItem = {
  match_number: number;
  teams: string[];
  venue: string;
  start_time: string;
};

type LiveResponse = {
  match?: { team1: string; team2: string; venue: string; date: string };
  winner?: { team?: string; probability?: number | null; probabilities?: Record<string, number> | null };
  live?: { batting_team?: string; runs?: number; wickets?: number; overs?: number; current_run_rate?: number };
  projected_total?: number | null;
  chase?: {
    will_reach?: boolean;
    finish_at?: string | null;
    short_by?: number | null;
    target?: number | null;
    required_run_rate?: number | null;
  } | null;
  wickets?: { low: number; high: number } | null;
  powerplay?: { low: number; high: number } | null;
  prediction_stage?: string;
  confidence?: number;
  features_used?: { confidence_components?: Record<string, number> };
  decision_moment?: { moment_type: string; headline: string; detail: string; urgency: 'high' | 'medium' | 'low' };
  error?: string;
  message?: string;
};

type PredictionType = 'winner' | 'score' | 'wickets' | 'powerplay' | null;

const STAGE_LABELS: Record<string, string> = {
  pre_toss: 'Pre-toss analysis — based on historical priors only',
  post_toss: 'Post-toss — toss result factored in',
  innings_break: 'Innings break — projecting chase outcome',
  live: 'Live — updating every 30s',
  completed: 'Match completed — final analysis',
  chase: 'Chase in progress — tracking target',
};

const SERIES_ID = 9237;

const LiveMatchPage: React.FC = () => {
  const [loading, setLoading] = useState(false);
  const [matchNumber, setMatchNumber] = useState(0);
  const [dateStr, setDateStr] = useState(new Date().toISOString().split('T')[0]);
  const [matches, setMatches] = useState<MatchListItem[]>([]);
  const [message, setMessage] = useState('');
  const [result, setResult] = useState<LiveResponse | null>(null);
  const [activeType, setActiveType] = useState<PredictionType>(null);
  const [lastUpdated, setLastUpdated] = useState<number | null>(null);
  const [secondsAgo, setSecondsAgo] = useState(0);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const dateStrRef = useRef(dateStr);
  dateStrRef.current = dateStr;
  const matchNumberRef = useRef(matchNumber);
  matchNumberRef.current = matchNumber;

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
        const res = await api.get('/matches', { params: { date: dateStr } });
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

  // Auto-refresh: poll every 30s while match is live
  const predictionStage = result?.prediction_stage;
  useEffect(() => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    if (!predictionStage || predictionStage === 'completed') return;

    pollRef.current = setInterval(async () => {
      try {
        const res = await api.get('/predict/live', {
          params: { series_id: SERIES_ID, date: dateStrRef.current, match_number: matchNumberRef.current },
        });
        const data: LiveResponse = res.data;
        if (!data.error) {
          setResult(data);
          setLastUpdated(Date.now());
        }
      } catch { /* silent refresh failure */ }
    }, 30_000);

    return () => { if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; } };
  }, [predictionStage]);

  // Stop polling on date/match change
  useEffect(() => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    setLastUpdated(null);
  }, [dateStr, matchNumber]);

  // Tick counter for "updated X seconds ago"
  useEffect(() => {
    if (!lastUpdated) { setSecondsAgo(0); return; }
    const id = setInterval(() => {
      setSecondsAgo(Math.floor((Date.now() - lastUpdated) / 1000));
    }, 1_000);
    return () => clearInterval(id);
  }, [lastUpdated]);

  const getPredictions = async (type: PredictionType) => {
    if (!type) return;
    setLoading(true);
    setActiveType(type);
    setMessage('');
    try {
      const res = await api.get('/predict/live', {
        params: { series_id: SERIES_ID, date: dateStr, match_number: matchNumber },
      });
      const data: LiveResponse = res.data;
      if (data.error) {
        setMessage(data.error);
        setResult(null);
      } else {
        setResult(data);
        setLastUpdated(Date.now());
        if (data.message) {
          setMessage(data.message);
        }
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setMessage(msg);
      setResult(null);
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
        Live Match Predictions
      </Typography>
      <Typography sx={{ color: palette.muted, mb: 4, textAlign: 'center' }}>
        Live IPL outputs for winner, total score, wickets, and powerplay.
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

        <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1.5, mt: 3 }}>
          {predictionButtons.map((btn) => (
            <Button
              key={btn.label}
              variant="outlined"
              onClick={() => getPredictions(btn.value)}
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

        {result && !result.error && (
          <Box sx={{ display: 'grid', gap: 2, mt: 3 }}>
            <Divider sx={{ borderColor: palette.border }} />
            {result.prediction_stage && STAGE_LABELS[result.prediction_stage] && (
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <Typography sx={{ color: palette.accent, fontSize: 12, fontStyle: 'italic' }}>
                  {STAGE_LABELS[result.prediction_stage]}
                </Typography>
                {result.confidence != null && (
                  <ConfidenceBadge
                    confidence={result.confidence}
                    components={result.features_used?.confidence_components}
                  />
                )}
              </Box>
            )}
            {result.decision_moment && (
              <DecisionMomentCard moment={result.decision_moment} />
            )}
            {lastUpdated && (
              <Typography sx={{ color: palette.muted, fontSize: 11, textAlign: 'right' }}>
                Updated {secondsAgo}s ago
              </Typography>
            )}

            {activeType === 'winner' && (
              <Paper sx={{ p: 2, backgroundColor: '#0f172a', border: `1px solid ${palette.border}` }}>
                <Typography sx={{ color: palette.muted, fontSize: 12 }}>Who will win</Typography>
                <Typography sx={{ fontWeight: 700, fontSize: 20 }}>
                  {result.winner?.team || 'Prediction pending'}
                </Typography>
                {result.winner?.probabilities && (
                  <Typography sx={{ color: palette.muted }}>
                    {Object.entries(result.winner.probabilities)
                      .map(([team, pct]) => `${team}: ${pct}`)
                      .join(' • ')}
                  </Typography>
                )}
              </Paper>
            )}

            {activeType === 'score' && (
              <Paper sx={{ p: 2, backgroundColor: '#0f172a', border: `1px solid ${palette.border}` }}>
                <Typography sx={{ color: palette.muted, fontSize: 12 }}>Total score</Typography>
                <Typography sx={{ fontWeight: 700, fontSize: 20 }}>
                  {result.projected_total !== null && result.projected_total !== undefined
                    ? result.projected_total
                    : 'Prediction pending'}
                </Typography>
                {result.chase && (
                  <Typography sx={{ color: palette.muted }}>
                    Target: {result.chase.target ?? 'n/a'} · Required RR: {result.chase.required_run_rate ?? 'n/a'}
                  </Typography>
                )}
                {result.chase && (
                  <Typography sx={{ color: palette.highlight, mt: 1 }}>
                    {result.chase.will_reach
                      ? `Likely to finish by ${result.chase.finish_at} overs`
                      : `Likely short by ${result.chase.short_by} runs`}
                  </Typography>
                )}
              </Paper>
            )}

            {activeType === 'wickets' && (
              <Paper sx={{ p: 2, backgroundColor: '#0f172a', border: `1px solid ${palette.border}` }}>
                <Typography sx={{ color: palette.muted, fontSize: 12 }}>Wickets</Typography>
                <Typography sx={{ fontWeight: 700, fontSize: 20 }}>
                  {result.wickets ? `${result.wickets.low}-${result.wickets.high}` : 'Prediction pending'}
                </Typography>
              </Paper>
            )}

            {activeType === 'powerplay' && (
              <Paper sx={{ p: 2, backgroundColor: '#0f172a', border: `1px solid ${palette.border}` }}>
                <Typography sx={{ color: palette.muted, fontSize: 12 }}>Powerplay score</Typography>
                <Typography sx={{ fontWeight: 700, fontSize: 20 }}>
                  {result.powerplay ? `${result.powerplay.low}-${result.powerplay.high}` : 'Prediction pending'}
                </Typography>
              </Paper>
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

export default LiveMatchPage;
