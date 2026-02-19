import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Box, Typography, Button, Paper, Divider, CircularProgress, Tabs, Tab, Table, TableBody, TableCell, TableHead, TableRow } from '@mui/material';
import SportsCricketIcon from '@mui/icons-material/SportsCricket';
import FlashOnIcon from '@mui/icons-material/FlashOn';
import CalendarTodayIcon from '@mui/icons-material/CalendarToday';
import WbSunnyIcon from '@mui/icons-material/WbSunny';
import { useAuth } from '../context/AuthContext';
import api from '../api';
import ConfidenceBadge from '../components/ConfidenceBadge';
import DecisionMomentCard from '../components/DecisionMomentCard';
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
  batting_context?: string;
  data_quality?: string;
  fallback_level?: string;
  confidence?: number;
  uncertainty?: string;
  match?: { team1: string; team2: string; venue: string; date: string };
  winner?: { team?: string; probability?: number; probabilities?: Record<string, number> };
  total_score?: { low: number; mid: number; high: number };
  wickets?: { low: number; mid: number; high: number };
  powerplay?: { low: number; mid: number; high: number };
  features_used?: { confidence_components?: Record<string, number> };
  status?: string;
  actual_winner?: string | null;
  error?: string;
  message?: string;
};

type LiveResponse = {
  prediction_stage?: string;
  batting_context?: string;
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

const SERIES_ID = 11253;

const ACCURACY_KEY = 't20wc_prediction_accuracy';

type PredictionRecord = {
  date: string;
  match_label: string;
  predicted_winner: string;
  actual_winner: string | null;
  correct: boolean | null;
};

function loadAccuracyRecords(): PredictionRecord[] {
  try {
    const raw = localStorage.getItem(ACCURACY_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveAccuracyRecords(records: PredictionRecord[]): void {
  localStorage.setItem(ACCURACY_KEY, JSON.stringify(records));
}

const T20WorldCupPage: React.FC = () => {
  const { loading: authLoading } = useAuth();
  const [loading, setLoading] = useState(false);
  const [matchNumber, setMatchNumber] = useState(0);
  const [dateStr, setDateStr] = useState(new Date().toISOString().split('T')[0]);
  const [matches, setMatches] = useState<MatchListItem[]>([]);
  const [message, setMessage] = useState('');
  const [activeTab, setActiveTab] = useState<'prematch' | 'live'>('prematch');
  const [accuracyRecords, setAccuracyRecords] = useState<PredictionRecord[]>(loadAccuracyRecords);

  const [preMatchResult, setPreMatchResult] = useState<PreMatchResponse | null>(null);
  const [preMatchType, setPreMatchType] = useState<PredictionType>(null);

  const [liveResult, setLiveResult] = useState<LiveResponse | null>(null);
  const [liveType, setLiveType] = useState<PredictionType>(null);
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

  // Auto-refresh: poll every 30s while live tab is active and match is not completed
  const livePredictionStage = liveResult?.prediction_stage;
  useEffect(() => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    if (!livePredictionStage || livePredictionStage === 'completed' || activeTab !== 'live') return;

    pollRef.current = setInterval(async () => {
      try {
        const res = await api.get('/predict/live', {
          params: { series_id: SERIES_ID, date: dateStrRef.current, match_number: matchNumberRef.current },
        });
        const data: LiveResponse = res.data;
        if (!data.error) {
          setLiveResult(data);
          setLastUpdated(Date.now());
        }
      } catch { /* silent refresh failure */ }
    }, 30_000);

    return () => { if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; } };
  }, [livePredictionStage, activeTab]);

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

        // Resolve accuracy for completed matches regardless of prediction type
        if (data.match && data.prediction_stage === 'completed' && data.actual_winner) {
          const matchLabel = `${data.match.team1} vs ${data.match.team2}`;
          const records = loadAccuracyRecords();
          const idx = records.findIndex(r => r.date === dateStr && r.match_label === matchLabel);
          if (idx >= 0) {
            records[idx].actual_winner = data.actual_winner;
            records[idx].correct = records[idx].predicted_winner === data.actual_winner;
            saveAccuracyRecords(records);
            setAccuracyRecords([...records]);
          }
        }

        // Store new winner predictions for pre-match stages
        if (type === 'winner' && data.match && data.winner?.team && data.prediction_stage !== 'completed' && data.prediction_stage !== 'in_progress') {
          const matchLabel = `${data.match.team1} vs ${data.match.team2}`;
          const records = loadAccuracyRecords();
          const idx = records.findIndex(r => r.date === dateStr && r.match_label === matchLabel);
          if (idx >= 0) {
            records[idx].predicted_winner = data.winner.team;
          } else {
            records.push({
              date: dateStr,
              match_label: matchLabel,
              predicted_winner: data.winner.team,
              actual_winner: null,
              correct: null,
            });
          }
          saveAccuracyRecords(records);
          setAccuracyRecords([...records]);
        }
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
        setLastUpdated(Date.now());
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
                {preMatchResult.prediction_stage && STAGE_LABELS[preMatchResult.prediction_stage] && (
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                    <Typography sx={{ color: palette.accent, fontSize: 12, fontStyle: 'italic' }}>
                      {STAGE_LABELS[preMatchResult.prediction_stage]}
                    </Typography>
                    {preMatchResult.confidence != null && (
                      <ConfidenceBadge
                        confidence={preMatchResult.confidence}
                        components={preMatchResult.features_used?.confidence_components}
                      />
                    )}
                  </Box>
                )}
                {preMatchResult.batting_context && preMatchType !== 'winner' && !preMatchResult.message && (
                  <Typography sx={{ color: palette.muted, fontSize: 12, mt: 0.5 }}>
                    {preMatchResult.batting_context}
                  </Typography>
                )}
                <Box sx={{ color: palette.primary, fontSize: 14, mt: 1 }}>
                  {preMatchResult.message && (
                    <Typography>{preMatchResult.message}</Typography>
                  )}
                  {preMatchResult.prediction_stage === 'in_progress' && preMatchResult.match && (() => {
                    const matchLabel = `${preMatchResult.match.team1} vs ${preMatchResult.match.team2}`;
                    const existing = accuracyRecords.find(r => r.date === dateStr && r.match_label === matchLabel);
                    if (!existing) return null;
                    return (
                      <Typography sx={{ color: palette.muted, fontSize: 13, mt: 1 }}>
                        Your earlier pick: <strong style={{ color: palette.primary }}>{existing.predicted_winner}</strong>
                        {existing.actual_winner
                          ? ` — ${existing.correct ? 'Correct' : 'Wrong'} (${existing.actual_winner} won)`
                          : ' — result pending'}
                      </Typography>
                    );
                  })()}
                  {preMatchType === 'winner' && !preMatchResult.message && preMatchResult.winner?.probabilities && (() => {
                    const probs = preMatchResult.winner.probabilities;
                    const sorted = Object.entries(probs).sort((a, b) => b[1] - a[1]);
                    return (
                      <Typography sx={{ fontWeight: 700, fontSize: 18 }}>
                        {sorted.map(([team, p]) => `${team} ${Math.round(p * 100)}%`).join(' \u00B7 ')}
                      </Typography>
                    );
                  })()}
                  {preMatchType === 'score' && preMatchResult.total_score && (
                    <Typography>
                      Expected: {preMatchResult.total_score.low} – {preMatchResult.total_score.high} runs
                    </Typography>
                  )}
                  {preMatchType === 'wickets' && preMatchResult.wickets && (
                    <Typography>
                      Expected: {preMatchResult.wickets.low} – {preMatchResult.wickets.high} wickets
                    </Typography>
                  )}
                  {preMatchType === 'powerplay' && preMatchResult.powerplay && (
                    <Typography>
                      Expected: {preMatchResult.powerplay.low} – {preMatchResult.powerplay.high} runs
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
                {liveResult.prediction_stage && STAGE_LABELS[liveResult.prediction_stage] && (
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <Typography sx={{ color: palette.accent, fontSize: 12, fontStyle: 'italic' }}>
                      {STAGE_LABELS[liveResult.prediction_stage]}
                    </Typography>
                    {liveResult.confidence != null && (
                      <ConfidenceBadge
                        confidence={liveResult.confidence}
                        components={liveResult.features_used?.confidence_components}
                      />
                    )}
                  </Box>
                )}
                {liveResult.decision_moment && (
                  <DecisionMomentCard moment={liveResult.decision_moment} />
                )}
                {lastUpdated && (
                  <Typography sx={{ color: palette.muted, fontSize: 11, textAlign: 'right' }}>
                    Updated {secondsAgo}s ago
                  </Typography>
                )}

                {liveType === 'winner' && (
                  <Paper sx={{ p: 2, backgroundColor: '#0f172a', border: `1px solid ${palette.border}` }}>
                    <Typography sx={{ color: palette.muted, fontSize: 12 }}>Winner</Typography>
                    <Typography sx={{ fontWeight: 700, fontSize: 20 }}>
                      {liveResult.winner?.probabilities
                        ? Object.entries(liveResult.winner.probabilities)
                            .sort((a, b) => (b[1] ?? 0) - (a[1] ?? 0))
                            .map(([team, p]) => `${team} ${Math.round((p ?? 0) * 100)}%`)
                            .join(' \u00B7 ')
                        : 'Prediction pending'}
                    </Typography>
                  </Paper>
                )}

                {liveType === 'score' && (
                  <Paper sx={{ p: 2, backgroundColor: '#0f172a', border: `1px solid ${palette.border}` }}>
                    <Typography sx={{ color: palette.muted, fontSize: 12 }}>Total score</Typography>
                    {liveResult.batting_context && (
                      <Typography sx={{ color: palette.muted, fontSize: 11 }}>{liveResult.batting_context}</Typography>
                    )}
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
                    {liveResult.batting_context && (
                      <Typography sx={{ color: palette.muted, fontSize: 11 }}>{liveResult.batting_context}</Typography>
                    )}
                    <Typography sx={{ fontWeight: 700, fontSize: 20 }}>
                      {liveResult.wickets
                        ? `Expected: ${liveResult.wickets.low} – ${liveResult.wickets.high} wickets`
                        : 'Prediction pending'}
                    </Typography>
                  </Paper>
                )}

                {liveType === 'powerplay' && (
                  <Paper sx={{ p: 2, backgroundColor: '#0f172a', border: `1px solid ${palette.border}` }}>
                    <Typography sx={{ color: palette.muted, fontSize: 12 }}>Powerplay</Typography>
                    {liveResult.batting_context && (
                      <Typography sx={{ color: palette.muted, fontSize: 11 }}>{liveResult.batting_context}</Typography>
                    )}
                    <Typography sx={{ fontWeight: 700, fontSize: 20 }}>
                      {liveResult.powerplay
                        ? `Expected: ${liveResult.powerplay.low} – ${liveResult.powerplay.high} runs`
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

      {accuracyRecords.length > 0 && (() => {
        const completed = accuracyRecords.filter(r => r.actual_winner != null);
        const correct = completed.filter(r => r.correct).length;
        const pct = completed.length > 0 ? Math.round((correct / completed.length) * 100) : 0;
        return (
          <Paper
            elevation={0}
            sx={{
              width: '100%',
              maxWidth: 860,
              mt: 3,
              p: { xs: 2, sm: 3 },
              borderRadius: 3,
              backgroundColor: palette.card,
              border: `1px solid ${palette.border}`,
            }}
          >
            <Typography sx={{ fontWeight: 700, mb: 2 }}>Winner Prediction Accuracy</Typography>
            {completed.length > 0 ? (
              <>
                <Typography sx={{ color: palette.accent, fontSize: 14, mb: 2 }}>
                  {correct} of {completed.length} predictions correct ({pct}% accuracy)
                </Typography>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell sx={{ color: palette.muted, borderColor: palette.border, fontWeight: 600 }}>Date</TableCell>
                      <TableCell sx={{ color: palette.muted, borderColor: palette.border, fontWeight: 600 }}>Match</TableCell>
                      <TableCell sx={{ color: palette.muted, borderColor: palette.border, fontWeight: 600 }}>Predicted</TableCell>
                      <TableCell sx={{ color: palette.muted, borderColor: palette.border, fontWeight: 600 }}>Actual</TableCell>
                      <TableCell sx={{ color: palette.muted, borderColor: palette.border, fontWeight: 600 }}>Result</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {completed.map((r, i) => (
                      <TableRow key={i}>
                        <TableCell sx={{ color: palette.primary, borderColor: palette.border }}>
                          {new Date(r.date + 'T00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}
                        </TableCell>
                        <TableCell sx={{ color: palette.primary, borderColor: palette.border }}>{r.match_label}</TableCell>
                        <TableCell sx={{ color: palette.primary, borderColor: palette.border }}>{r.predicted_winner}</TableCell>
                        <TableCell sx={{ color: palette.primary, borderColor: palette.border }}>{r.actual_winner}</TableCell>
                        <TableCell sx={{ borderColor: palette.border, color: r.correct ? '#22c55e' : '#ef4444', fontWeight: 600 }}>
                          {r.correct ? 'Correct' : 'Wrong'}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </>
            ) : (
              <Typography sx={{ color: palette.muted, fontSize: 13 }}>
                Accuracy will appear as matches complete
              </Typography>
            )}
          </Paper>
        );
      })()}

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
