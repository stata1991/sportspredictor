import React, { useMemo, useState } from 'react';
import { Box, Typography, Button, Paper, Divider, ToggleButton, ToggleButtonGroup, CircularProgress } from '@mui/material';
import { useAuth } from '../context/AuthContext';
import homeBg from '../non-home.png';

type RiskMode = 'conservative' | 'balanced' | 'aggressive';

type WinnerLiveResponse = {
  current_score?: number;
  overs?: number;
  wickets?: number;
  win_probability?: Record<string, number>;
  message?: string;
  error?: string;
};

type LiveStateResponse = {
  batting_team?: string;
  runs?: number;
  wickets?: number;
  overs?: number;
};

type DecisionResponse = {
  recommendation: {
    direction: 'Hold' | 'Lean' | 'Strong' | 'Flip';
    action: string;
    moment: string;
  };
  micro_why: string;
  next_window_in: string;
  silent: boolean;
  silent_reason: string | null;
  internal_state: {
    direction_score: number;
  };
};

const LiveMatchPage: React.FC = () => {
  const { currentUser, loading: authLoading } = useAuth();
  const [loading, setLoading] = useState(false);
  const [riskMode, setRiskMode] = useState<RiskMode>('balanced');
  const [showWhy, setShowWhy] = useState(false);
  const [matchNumber, setMatchNumber] = useState(0);
  const [decision, setDecision] = useState<DecisionResponse | null>(null);
  const [message, setMessage] = useState('');

  const date = new Date().toISOString().split('T')[0];

  const palette = useMemo(
    () => ({
      bg: '#0d1117',
      card: '#111827',
      border: '#334155',
      primary: '#e2e8f0',
      muted: '#94a3b8',
      accent: '#22d3ee',
      hold: '#94a3b8',
      lean: '#38bdf8',
      strong: '#34d399',
      flip: '#f59e0b',
      silent: '#64748b',
    }),
    []
  );

  const directionColor = (d: string) => {
    if (d === 'Strong') return palette.strong;
    if (d === 'Lean') return palette.lean;
    if (d === 'Flip') return palette.flip;
    return palette.hold;
  };

  const getDecision = async () => {
    setLoading(true);
    setMessage('');
    try {
      const updateRes = await fetch(`http://127.0.0.1:8000/update-match-context?date=${date}&match_number=${matchNumber}`, {
        method: 'POST',
      });
      if (!updateRes.ok) throw new Error('Unable to update live match context');

      const liveRes = await fetch(`http://127.0.0.1:8000/live-match-state?date=${date}`);
      if (!liveRes.ok) throw new Error('Unable to fetch live state');
      const liveState: LiveStateResponse = await liveRes.json();

      const winnerRes = await fetch(`http://127.0.0.1:8000/predict/winner-live?date=${date}`);
      if (!winnerRes.ok) throw new Error('Unable to derive control edge');
      const winner: WinnerLiveResponse = await winnerRes.json();

      if (winner.message) {
        setMessage(winner.message);
        setDecision(null);
        return;
      }
      if (winner.error) {
        setMessage(winner.error);
        setDecision(null);
        return;
      }

      const battingTeam = liveState.batting_team || '';
      const winProb = winner.win_probability || {};
      const battingWin = battingTeam && winProb[battingTeam] !== undefined ? winProb[battingTeam] : 50;
      const winEdge = (battingWin - 50) / 50;

      const overs = typeof liveState.overs === 'number' ? liveState.overs : typeof winner.overs === 'number' ? winner.overs : 0;
      const runs = typeof liveState.runs === 'number' ? liveState.runs : typeof winner.current_score === 'number' ? winner.current_score : 0;
      const wickets =
        typeof liveState.wickets === 'number' ? liveState.wickets : typeof winner.wickets === 'number' ? winner.wickets : 0;
      const currentRunRate = overs > 0 ? runs / overs : 0;

      const assistRes = await fetch('http://127.0.0.1:8000/assist/decision', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          match_key: `${date}-${matchNumber}`,
          runs,
          wickets,
          overs,
          current_run_rate: currentRunRate,
          win_edge: winEdge,
          risk_mode: riskMode,
        }),
      });
      if (!assistRes.ok) throw new Error('Unable to fetch decision');
      const decisionData: DecisionResponse = await assistRes.json();
      setDecision(decisionData);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setMessage(msg);
      setDecision(null);
    } finally {
      setLoading(false);
    }
  };

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
        Live Decision Assistant
      </Typography>
      <Typography sx={{ color: palette.muted, mb: 4, textAlign: 'center' }}>
        One action per leverage moment. Silence when no edge.
      </Typography>

      {!currentUser ? (
        <Typography variant="h6">Please sign in to access live match decisions.</Typography>
      ) : (
        <Paper
          elevation={0}
          sx={{
            width: '100%',
            maxWidth: 760,
            p: { xs: 2, sm: 3 },
            borderRadius: 3,
            backgroundColor: palette.card,
            border: `1px solid ${palette.border}`,
          }}
        >
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2, justifyContent: 'space-between', alignItems: 'center' }}>
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
              >
                <option value={0}>Match 1</option>
                <option value={1}>Match 2</option>
              </select>
            </Box>

            <Box>
              <Typography sx={{ color: palette.muted, mb: 0.5 }}>Risk Mode</Typography>
              <ToggleButtonGroup
                value={riskMode}
                exclusive
                onChange={(_, v) => v && setRiskMode(v)}
                size="small"
                sx={{ background: '#0f172a', borderRadius: 2 }}
              >
                <ToggleButton value="conservative" sx={{ color: palette.primary }}>
                  Conservative
                </ToggleButton>
                <ToggleButton value="balanced" sx={{ color: palette.primary }}>
                  Balanced
                </ToggleButton>
                <ToggleButton value="aggressive" sx={{ color: palette.primary }}>
                  Aggressive
                </ToggleButton>
              </ToggleButtonGroup>
            </Box>
          </Box>

          <Button
            onClick={getDecision}
            disabled={loading}
            variant="contained"
            sx={{
              mt: 3,
              mb: 3,
              borderRadius: 8,
              px: 3,
              py: 1.2,
              backgroundColor: '#0ea5e9',
              fontWeight: 700,
              textTransform: 'none',
            }}
          >
            {loading ? <CircularProgress size={18} sx={{ color: '#fff' }} /> : 'Get Live Decision'}
          </Button>

          {message && (
            <Typography sx={{ color: palette.muted, mb: 2 }}>
              {message}
            </Typography>
          )}

          {decision && (
            <Box>
              <Divider sx={{ borderColor: palette.border, mb: 2 }} />
              <Typography sx={{ color: palette.muted, fontSize: 13 }}>Recommendation</Typography>
              <Typography
                variant="h3"
                sx={{
                  mt: 0.5,
                  fontWeight: 800,
                  color: decision.silent ? palette.silent : directionColor(decision.recommendation.direction),
                }}
              >
                {decision.silent ? 'Hold' : decision.recommendation.direction}
              </Typography>

              <Typography sx={{ mt: 1, color: palette.primary }}>
                {decision.silent ? 'No action. System is intentionally silent.' : decision.recommendation.action}
              </Typography>
              <Typography sx={{ mt: 0.5, color: palette.muted }}>
                Moment: {decision.recommendation.moment.replace(/_/g, ' ')}
              </Typography>
              <Typography sx={{ mt: 0.5, color: palette.accent }}>
                Next leverage window: {decision.next_window_in}
              </Typography>

              {decision.silent && decision.silent_reason && (
                <Typography sx={{ mt: 1, color: palette.muted }}>{decision.silent_reason}</Typography>
              )}

              <Button
                variant="text"
                onClick={() => setShowWhy((v) => !v)}
                sx={{ mt: 1, px: 0, textTransform: 'none', color: palette.primary }}
              >
                {showWhy ? 'Hide why' : 'Show why'}
              </Button>
              {showWhy && (
                <Typography sx={{ color: palette.muted }}>
                  {decision.micro_why}
                </Typography>
              )}
            </Box>
          )}
        </Paper>
      )}

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
