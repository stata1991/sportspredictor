import React from 'react';
import {
  Box,
  Typography,
  Card,
  CardContent,
  Skeleton,
  Table,
  TableHead,
  TableRow,
  TableCell,
  TableBody,
} from '@mui/material';
import { useAccuracy } from '../../football/hooks/useAccuracy';
import { colors } from '../../football/colors';
import { AccuracyRollup } from '../../football/types/accuracy';

const WINDOW_LABELS: Record<string, string> = {
  all_time: 'All Time',
  last_7d: 'Last 7 Days',
};

const TYPE_LABELS: Record<string, string> = {
  winner: 'Winner',
  total_goals: 'Total Goals',
};

const formatPercent = (value: number | null): string =>
  value != null ? `${(value * 100).toFixed(0)}%` : '--';

const formatDecimal = (value: number | null): string =>
  value != null ? value.toFixed(3) : '--';

// ── KPI card ──────────────────────────────────────────────────────────

const KpiCard: React.FC<{
  label: string;
  value: string;
  subtitle: string;
}> = ({ label, value, subtitle }) => (
  <Card
    data-testid="kpi-card"
    sx={{
      flex: '1 1 180px',
      background: 'linear-gradient(145deg, #1e1e1e, #2a2a2a)',
      border: '1px solid rgba(255,255,255,0.06)',
    }}
  >
    <CardContent sx={{ textAlign: 'center' }}>
      <Typography
        variant="caption"
        sx={{ color: colors.labelText, fontWeight: 600 }}
      >
        {label}
      </Typography>
      <Typography
        variant="h4"
        data-testid="kpi-value"
        sx={{ color: colors.textPrimary, fontWeight: 800, my: 1 }}
      >
        {value}
      </Typography>
      <Typography variant="caption" sx={{ color: colors.labelText }}>
        {subtitle}
      </Typography>
    </CardContent>
  </Card>
);

// ── Table cell with consistent styling ────────────────────────────────

const borderStyle = 'rgba(255,255,255,0.08)';

const StyledCell: React.FC<{
  children: React.ReactNode;
  highlight?: boolean;
  header?: boolean;
}> = ({ children, highlight, header }) => (
  <TableCell
    sx={{
      color: highlight ? colors.homeAccent : header ? colors.labelText : colors.textPrimary,
      fontWeight: highlight || header ? 700 : 400,
      borderColor: borderStyle,
      ...(header && { fontSize: '0.75rem' }),
    }}
  >
    {children}
  </TableCell>
);

// ── Main component ────────────────────────────────────────────────────

const TrackRecordPage: React.FC = () => {
  const { rollups, loading, error } = useAccuracy();

  if (loading) {
    return (
      <Box data-testid="loading-state">
        <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap', mb: 3 }}>
          {[0, 1, 2].map((i) => (
            <Card key={i} sx={{ flex: '1 1 180px', p: 2 }}>
              <Skeleton variant="text" width="50%" />
              <Skeleton variant="text" width="60%" height={48} />
              <Skeleton variant="text" width="70%" />
            </Card>
          ))}
        </Box>
      </Box>
    );
  }

  if (error) {
    return (
      <Box data-testid="error-state" sx={{ textAlign: 'center', py: 6 }}>
        <Typography variant="h6" sx={{ color: '#ef5350', mb: 1 }}>
          Could not load accuracy data
        </Typography>
        <Typography variant="body2" sx={{ color: '#b0bec5', mb: 3 }}>
          {error}
        </Typography>
      </Box>
    );
  }

  if (rollups.length === 0) {
    return (
      <Box data-testid="empty-state" sx={{ textAlign: 'center', py: 6 }}>
        <Typography variant="h6" sx={{ color: colors.labelText, mb: 1 }}>
          No accuracy data yet
        </Typography>
        <Typography variant="body2" sx={{ color: colors.labelText }}>
          Track record will appear after completed matches are evaluated.
        </Typography>
      </Box>
    );
  }

  // KPI cards — sourced from all_time + winner rollup
  const headline: AccuracyRollup | undefined = rollups.find(
    (r) => r.window === 'all_time' && r.prediction_type === 'winner',
  );

  return (
    <Box data-testid="track-record-content">
      {headline && (
        <Box
          data-testid="kpi-section"
          sx={{ display: 'flex', gap: 2, flexWrap: 'wrap', mb: 4 }}
        >
          <KpiCard
            label="Top Pick Hit Rate"
            value={formatPercent(headline.top_pick_hit_rate)}
            subtitle="winners called right"
          />
          <KpiCard
            label="Total Predictions"
            value={String(headline.total_predictions)}
            subtitle="all-time"
          />
          <KpiCard
            label="Brier Score"
            value={formatDecimal(headline.brier_score)}
            subtitle="lower is better"
          />
        </Box>
      )}

      <Typography
        variant="subtitle1"
        sx={{ fontWeight: 700, mb: 1, color: colors.textPrimary }}
      >
        Breakdown
      </Typography>
      <Table size="small" data-testid="accuracy-table">
        <TableHead>
          <TableRow>
            <StyledCell header>Window</StyledCell>
            <StyledCell header>Type</StyledCell>
            <StyledCell header>Predictions</StyledCell>
            <StyledCell header>Hit Rate</StyledCell>
            <StyledCell header>Brier</StyledCell>
            <StyledCell header>Log Loss</StyledCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {rollups.map((r) => (
            <TableRow key={`${r.window}-${r.prediction_type}`}>
              <StyledCell>
                {WINDOW_LABELS[r.window] ?? r.window}
              </StyledCell>
              <StyledCell>
                {TYPE_LABELS[r.prediction_type] ?? r.prediction_type}
              </StyledCell>
              <StyledCell>{r.total_predictions}</StyledCell>
              <StyledCell highlight>
                {formatPercent(r.top_pick_hit_rate)}
              </StyledCell>
              <StyledCell>{formatDecimal(r.brier_score)}</StyledCell>
              <StyledCell>{formatDecimal(r.log_loss)}</StyledCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Box>
  );
};

export default TrackRecordPage;
